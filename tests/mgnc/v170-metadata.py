#!/usr/bin/env python3
"""Check declaration metadata without starting an implicit test runner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def program(prefix,body='0'):
    return 'namespace App;\n'+prefix+'\nlet main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};\n'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    compiler=args.compiler.resolve()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    positive={
        'body-not-run':({'src/app.mgn':program('@test let ignored:Function():Unit=function():Unit{assert false;};')},0,b'',b''),
        'initializer-once':({'src/app.mgn':program('var count:Int=0;@test let ignored:Function():Unit={count=count+1;function():Unit{panic{"not called"}}};','branch when{count==1=>0,else=>7}')},0,b'',b''),
        'indirect-initializer':({'src/app.mgn':program('let make:Function():Function():Unit=function():Function():Unit{function():Unit{panic{"not called"}}};@test let ignored:Function():Unit=make();')},0,b'',b''),
        'signature-alias':({'src/app.mgn':program('alias Check=Function():Unit;@test let ignored:Check=function():Unit{panic{"not called"}};')},0,b'',b''),
        'ordinary-call':({'src/app.mgn':program('@test let ordinary:Function():Unit=function():Unit{assert true;};','ordinary();0')},0,b'',b''),
        'public-import-alias':({'src/app.mgn':program(r'use App\Checks\{original as copied};','copied();0'),'src/Checks/test.mgn':r'namespace App\Checks;@test public let original:Function():Unit=function():Unit{assert true;};'},0,b'',b''),
        'unreachable-initializer':({'src/app.mgn':program(''),'src/Checks/test.mgn':r'namespace App\Checks;@test let ignored:Function():Unit=panic{"unreachable initializer"};'},0,b'',b''),
        'imported-initializer':({'src/app.mgn':program(r'use App\Checks\{original};'),'src/Checks/test.mgn':r'namespace App\Checks;use Std\Io\{writeStdout,IoError};@test public let original:Function():Unit={discard writeStdout("I");function():Unit{panic{"not called"}}};'},0,b'I',b''),
        'comment-string':({'src/app.mgn':program('// @test\nlet value:String="@test";')},0,b'',b''),
        'initializer-panic':({'src/app.mgn':program('')+'@test let ignored:Function():Unit=panic{"initializer"};\n'},4,b'',b'panic: initializer\n'),
    }
    negative={
        'unknown':(program('@unknown let bad:Function():Unit=function():Unit{unit};'),'semantic','unknown',False),
        'duplicate':(program('@test @test let bad:Function():Unit=function():Unit{unit};'),'semantic','@test',True),
        'module-var':(program('@test var bad:Function():Unit=function():Unit{unit};'),'semantic','@test',False),
        'local-let':(program('','@test let local:Function():Unit=function():Unit{unit};0'),'semantic','@test',False),
        'wrong-type':(program('@test let bad:Int=0;'),'type','Int',False),
        'wrong-parameters':(program('@test let bad:Function(Int):Unit=function(x:Int):Unit{unit};'),'type','Function',False),
        'wrong-result':(program('@test let bad:Function():Int=function():Int{0};'),'type','Function',False),
        'type-target':(program('@test type Bad=product{value:Int;};'),'semantic','@test',False),
        'template-target':(program('@test template bad<T>=function(value:T):T{value};'),'semantic','@test',False),
        'after-public':(program('public @test let bad:Function():Unit=function():Unit{unit};'),'parse','@',False),
        'unused-bad-body':(program('@test let bad:Function():Unit=function():Unit{assert 1;};'),'type','1',False),
    }
    observations=[]
    def call(name,command,status,stdout=b'',stderr=b'',phase=None,span=None):
        run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180,umask=0o022)
        passed=run.returncode==status and run.stdout==stdout
        passed=passed and (run.stderr==stderr if phase is None else ('mgnc: '+phase+':').encode() in run.stderr)
        if span is not None:passed=passed and ('['+str(span)+',').encode() in run.stderr
        row={'case':name,'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':bool(passed)}
        observations.append(row)
        (args.output/'results.json').write_text(json.dumps(observations,indent=2)+'\n')
        assert passed,row
    for name,(sources,status,stdout,stderr) in positive.items():
        project=args.output/name
        sources=dict(sources,**{'mognitio.toml':'[project]\nname="app"\nroot_namespace="App"\n'})
        for relative,text in sources.items():
            path=project/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text)
        inventory={relative:hashlib.sha256((project/relative).read_bytes()).hexdigest() for relative in sources}
        manifest=project/'mognitio.toml'
        for verb in ('check','lower'):call(name+'-'+verb,[compiler,verb,manifest],0)
        image=project/'program'
        call(name+'-build',[compiler,'build',manifest,'-o',image],0)
        call(name+'-native',[image],status,stdout,stderr)
        assert all(hashlib.sha256((project/relative).read_bytes()).hexdigest()==digest for relative,digest in inventory.items())
    for name,(source,phase,marker,last) in negative.items():
        path=args.output/(name+'.mgn')
        path.write_text(source)
        start=(source.rindex(marker) if last else source.index(marker))
        offset=len(source[:start].encode())
        output=args.output/(name+'.elf')
        output.write_bytes(b'preserved')
        for verb in ('check','lower','build'):
            command=[compiler,verb,path]+(['-o',output] if verb=='build' else [])
            call(name+'-'+verb,command,1,phase=phase,span=offset)
            assert output.read_bytes()==b'preserved'
    print('V170_METADATA_OK positive='+str(len(positive))+' negative='+str(len(negative))+' observations='+str(len(observations)))

if __name__=='__main__':main()
