#!/usr/bin/env python3
"""Qualify additional bootstrap capabilities against an explicit compiler."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def program(body, prefix=''):
    return 'namespace App;\n' + prefix + '\nlet main:Function(List<String>):Int=function(args:List<String>):Int{\n' + body + '\n};\n'

CASES = {
    'filesystem-identities': (program(r'''
assert branch on createDirectory("observed"){Result<Unit,IoError>::Ok=>true,Result<Unit,IoError>::Err=>false};
assert branch on readDirectory("observed"){Result<List<DirectoryEntry>,IoError>::Ok(entries:List<DirectoryEntry>)=>entries->length()==0,Result<List<DirectoryEntry>,IoError>::Err=>false};
let observed:PathInfo=branch on inspectPath("observed"){Result<PathInfo,PathInfoError>::Ok(info:PathInfo)=>info,Result<PathInfo,PathInfoError>::Err=>panic{"inspect"}};
let retained:FileIdentity=observed->identity;
assert branch on inspectPath("observed"){Result<PathInfo,PathInfoError>::Ok(info:PathInfo)=>info->identity==retained,Result<PathInfo,PathInfoError>::Err=>false};
let join:Function(String,String):Result<String,IoError>=joinPath;
assert branch on join("observed","child"){Result<String,IoError>::Ok(path:String)=>path=="observed/child",Result<String,IoError>::Err=>false};
0
''', r'use Std\Io\{createDirectory,readDirectory,DirectoryEntry,inspectPath,PathInfo,PathInfoError,FileIdentity,joinPath,IoError};'), 0, b''),
    'numeric-binary': (program(r'''
assert Int<64,Unsigned>{18446744073709551615} / Int<64,Unsigned>{9223372036854775808} == Int<64,Unsigned>{1};
assert Int<1,Signed>{-1} % Int<1,Signed>{-1} == Int<1,Signed>{0};
assert Bits<64>{0}->not()==Bits<64>{18446744073709551615};
let expected:Bytes=bytesFromBits(List<Bits<8>>[Bits<8>{128},Bits<8>{0},Bits<8>{0},Bits<8>{0},Bits<8>{0},Bits<8>{0},Bits<8>{0},Bits<8>{0}]);
assert branch on Bits<64>{9223372036854775808}->toBytes(ByteOrder::BigEndian){Result<Bytes,BitWidthError>::Ok(value:Bytes)=>value==expected,Result<Bytes,BitWidthError>::Err=>false};
assert branch on expected->toBits<64>(ByteOrder::BigEndian){Result<Bits<64>,BinaryDecodeError>::Ok(value:Bits<64>)=>value==Bits<64>{9223372036854775808},Result<Bits<64>,BinaryDecodeError>::Err=>false};
0
''', r'''use Std\Numeric\{Bits,Signed,Unsigned};
use Std\Binary\{Bytes,bytesFromBits,ByteOrder,BitWidthError,BinaryDecodeError};'''), 0, b''),
    'normal-test-metadata': (program('assert initialized==1;\n0', '''var initialized:Int=0;
@test
let testBody:Function():Unit={initialized=initialized+1;function():Unit{panic{"test runner must not start"}}};'''), 0, b''),
    'return-five': (program('5'), 5, b''),
    'helper-assertion': (program('helper();\n0', 'let helper:Function():Unit=function():Unit{assert false;};'), 5, None),
    'assert-operand-panic': (program('assert panic{"operand"};'), 4, b'panic: operand\n'),
    'assert-noncompletion': (program('assert {return 7;};'), 7, b''),
    'assert-single-evaluation': (program('var count:Int=0;\nassert {count=count+1;true};\nassert count==1;\n0'), 0, b''),
}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    compiler=args.compiler.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for name,(source,status,diagnostic) in CASES.items():
        project=args.output/name
        (project/'src').mkdir(parents=True)
        manifest=project/'mognitio.toml'
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        path=project/'src/app.mgn'
        path.write_text(source)
        artifact=project/'program'
        row={'name':name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'observations':[]}
        for mode,command,expected in (
            ('run',[str(compiler),'run',str(manifest)],status),
            ('build',[str(compiler),'build',str(manifest),'-o',str(artifact)],0),
            ('native',[str(artifact)],status),
        ):
            run=subprocess.run(command,capture_output=True,timeout=120,cwd=project)
            passed=run.returncode==expected and run.stdout==b''
            if mode=='build':
                passed=passed and run.stderr==b'' and artifact.read_bytes().startswith(b'\x7fELF')
            elif diagnostic is None:
                passed=passed and b'assertion:' in run.stderr and b'src/app.mgn:2:' in run.stderr
            else:
                passed=passed and run.stderr==diagnostic
            row['observations'].append({'mode':mode,'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':passed})
            (args.output/'results.json').write_text(json.dumps(results+[row],indent=2)+'\n')
            assert passed,row
        assert row['observations'][0]['stderr_hex']==row['observations'][2]['stderr_hex'],row
        results.append(row)
        print(name+' PASS',flush=True)
    print('V170_SEED_PROBES_OK cases='+str(len(CASES))+' observations='+str(len(CASES)*3))

if __name__=='__main__':
    main()
