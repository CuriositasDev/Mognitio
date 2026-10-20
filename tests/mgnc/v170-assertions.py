#!/usr/bin/env python3
"""Observe assertions through semantic checks, lowering and standalone ELF."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def program(body,prefix=''):
    return 'namespace App;\n'+prefix+'\nlet main:Function(List<String>):Int=function(args:List<String>):Int{\n'+body+'\n};\n'

def assertion(source,needle=b'assert false;',path='src/app.mgn'):
    data=source.encode()
    start=data.rindex(needle)
    prefix=data[:start].decode().replace('\r\n','\n').replace('\r','\n')
    line=prefix.count('\n')+1
    column=len(prefix.rsplit('\n',1)[-1])+1
    return (f'{path}:{line}:{column}: assertion: assertion failed (outside test) '
            f'[bytes {start},{start+len(needle)})\n').encode()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    compiler=args.compiler.resolve()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    cases={
        'true':(program('assert true;\n0'),0,b''),
        'ordinary-return-five':(program('5'),5,b''),
        'false':(program('assert false;\n0'),5,None),
        'same-line':(program('assert true; assert false;\n0'),5,None),
        'helper-location':(program('helper();\n0','let helper:Function():Unit=function():Unit{assert false;};'),5,None),
        'unicode-crlf-tab':(program('discard "😀é";\tassert true; assert false;\n0').replace('\n','\r\n'),5,None),
        'operand-panic':(program('assert panic{"operand"};'),4,b'panic: operand\n'),
        'panic-payload-kind':(program('assert panic{"assertion: fake"};'),4,b'panic: assertion: fake\n'),
        'operand-return':(program('assert {return 7;};'),7,b''),
        'single-evaluation':(program('var count:Int=0;assert {count=count+1;true};assert count==1;count'),1,b''),
        'operand-break':(program('let result:Int=loop{assert {break 7;};};result'),7,b''),
        'operand-continue':(program('var count:Int=0;loop while(count<3){assert {count=count+1;continue;};};count'),3,b''),
        'unselected-false':(program('branch when{false=>{assert false;0},else=>0}'),0,b''),
        'try-operand':(program('branch on probe(){Result<Unit,String>::Ok=>9,Result<Unit,String>::Err(text:String)=>branch when{text=="kept"=>0,else=>8}}',
            'let probe:Function():Result<Unit,String>=function():Result<Unit,String>{assert try Result<Bool,String>::Err("kept");Result<Unit,String>::Ok(unit)};'),0,b''),
        'managed-operand':(program('var values:List<String>=List<String>[];var index:Int=0;loop while(index<256){values=values->append("kept"+" value");assert values->length()==index+1;index=index+1;};0'),0,b''),
    }
    results=[]
    def observe(name,command,status,stderr=b'',closed=False):
        run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180,umask=0o022,preexec_fn=(lambda:os.close(2)) if closed else None)
        row={'case':name,'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),
             'passed':(run.returncode,run.stdout,run.stderr)==(status,b'',stderr)}
        results.append(row)
        (args.output/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'observations':results},indent=2)+'\n')
        assert row['passed'],row
        return run
    for name,(source,status,stderr) in cases.items():
        project=args.output/name
        (project/'src').mkdir(parents=True)
        manifest=project/'mognitio.toml'
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        path=project/'src/app.mgn'
        path.write_bytes(source.encode())
        inputs={p.relative_to(project).as_posix():p.read_bytes() for p in (path,manifest)}
        for verb in ('check','lower'):
            observe(name+'-'+verb,[compiler,verb,manifest],0)
        artifact=project/'program'
        observe(name+'-build',[compiler,'build',manifest,'-o',artifact],0)
        assert artifact.read_bytes().startswith(b'\x7fELF') and artifact.stat().st_mode&0o777==0o755
        expected=assertion(source) if stderr is None else stderr
        observe(name+'-native',[artifact],status,expected)
        if name in ('managed-operand','helper-location','operand-return','try-operand'):
            observer=Path(__file__).resolve().parent/'v160-native-observe.py'
            observe(name+'-stress',[sys.executable,observer,'--stress','--report',project/'stress.json','--',artifact],status,expected)
        if stderr is None:
            observe(name+'-closed-stderr',[artifact],status,b'',closed=True)
            detached=args.output/(name+'-detached')
            shutil.copy2(artifact,detached)
            path.unlink()
            manifest.unlink()
            observe(name+'-detached',[detached],status,expected)
            observe(name+'-isolated',['bwrap','--unshare-all','--die-with-parent','--new-session',
                '--uid','1000','--gid','1000','--clearenv','--ro-bind',detached,'/program',
                '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--chdir','/','--','/program'],status,expected)
            path.write_bytes(inputs['src/app.mgn'])
            manifest.write_bytes(inputs['mognitio.toml'])
        assert all((project/relative).read_bytes()==data for relative,data in inputs.items())
    negatives={
        'non-bool':program('assert 1;0'),
        'unit':program('assert unit;0'),
        'unused-body':program('0','let unused:Function():Unit=function():Unit{assert 1;};'),
        'unreachable-after-panic':program('assert panic{"stop"};assert true;'),
    }
    for name,source in negatives.items():
        path=args.output/(name+'.mgn')
        path.write_text(source)
        output=args.output/(name+'.elf')
        output.write_bytes(b'preserved')
        for verb in ('check','lower','build'):
            cmd=[str(compiler),verb,str(path)]
            if verb=='build':cmd+=['-o',str(output)]
            run=subprocess.run(cmd,capture_output=True,timeout=180)
            assert run.returncode==1 and run.stdout==b'' and (b'type:' in run.stderr or b'semantic:' in run.stderr),(name,verb,run.returncode,run.stderr)
            assert output.read_bytes()==b'preserved'
            results.append({'case':name+'-'+verb,'exit':run.returncode,'passed':True})
    (args.output/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'observations':results},indent=2)+'\n')
    print('V170_ASSERTIONS_OK positive='+str(len(cases))+' negative='+str(len(negatives))+' observations='+str(len(results)))

if __name__=='__main__':
    main()
