#!/usr/bin/env python3
"""Check widths 1..64 against mathematical integers and fixed machine vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

IMPORTS=r'use Std\Numeric\{Bits,Signed,Unsigned};'
def literal(t,n):return t+'{'+str(n)+'}'
def source(body,prefix=''):
    return 'namespace App;'+IMPORTS+prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};'
def trunc(a,b):return (abs(a)//abs(b))*(-1 if (a<0)!=(b<0) else 1)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    compiler=args.compiler.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False);rows=[];assertions=0
    def call(name,command,status=0,stderr=b'',phase=None):
        run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180,umask=0o022)
        passed=run.returncode==status and run.stdout==b'' and (run.stderr==stderr if phase is None else ('mgnc: '+phase+':').encode() in run.stderr)
        rows.append({'case':name,'command':list(map(str,command)),'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':passed})
        (args.output/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'observations':rows},indent=2)+'\n');assert passed,rows[-1]
        return run
    def build(name,text):
        folder=args.output/name;folder.mkdir();path=folder/'input.mgn';path.write_text(text);sha=hashlib.sha256(path.read_bytes()).hexdigest();artifact=folder/'program'
        for verb in ['check','lower']:call(name+'-'+verb,[compiler,verb,path])
        call(name+'-build',[compiler,'build',path,'-o',artifact]);assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
        return artifact
    for width in range(1,65):
        for signed in [False,True]:
            t=f'Int<{width},{"Signed" if signed else "Unsigned"}>';bits=f'Bits<{width}>';u=f'Int<{width},Unsigned>'
            lo=-(1<<(width-1)) if signed else 0;hi=(1<<(width-1))-1 if signed else (1<<width)-1;mask=(1<<width)-1
            body='let high:'+t+'='+literal(t,hi)+';let low:'+t+'='+literal(t,lo)+';'
            body+='let selected:'+t+'=branch when{args->length()==0=>high,else=>low};assert (selected>low)==(args->length()==0);'
            checks=[]
            for a,b in [(lo,hi),(hi,lo),(hi,hi),(lo,lo),(0,0)]:
                for op,value in [('+',a+b),('-',a-b),('*',a*b)]:
                    if lo<=value<=hi:checks.append(literal(t,a)+op+literal(t,b)+'=='+literal(t,value))
                if b:
                    q=trunc(a,b);r=a-q*b
                    if lo<=q<=hi:checks.append(literal(t,a)+'/'+literal(t,b)+'=='+literal(t,q))
                    checks.append(literal(t,a)+'%'+literal(t,b)+'=='+literal(t,r))
                for op,value in [('<',a<b),('<=',a<=b),('>',a>b),('>=',a>=b),('==',a==b),('!=',a!=b)]:checks.append('('+literal(t,a)+op+literal(t,b)+')=='+str(value).lower())
            for value in [lo,hi,0]:
                pattern=value&mask
                checks.extend([literal(t,value)+'->toBits()=='+literal(bits,pattern),literal(bits,pattern)+'->asInteger<Unsigned>()=='+literal(u,pattern),literal(bits,pattern)+'->not()=='+literal(bits,pattern^mask),literal(bits,pattern)+'->length()=='+str(width)])
                if signed:checks.append(literal(bits,pattern)+'->asInteger<Signed>()=='+literal(t,value))
                if lo<=-value<=hi:checks.append('(-'+literal(t,value)+')=='+literal(t,-value))
                for method,answer in [('and',pattern&mask),('or',pattern|mask),('xor',pattern^mask)]:checks.append(literal(bits,pattern)+'->'+method+'('+literal(bits,mask)+')=='+literal(bits,answer))
            body+=''.join('assert '+condition+';' for condition in checks)+'0';assertions+=len(checks)+1
            artifact=build(f'width-{width}-'+('signed' if signed else 'unsigned'),source(body))
            call(artifact.parent.name+'-native',[artifact]);call(artifact.parent.name+'-dynamic',[artifact,'dynamic'])
    generic=[
        source('assert one<1>()==Bits<1>{1};assert one<8>()==Bits<8>{1};assert one<64>()==Bits<64>{1};0','template one<N:Int>=function():Bits<N>{Bits<N>{1}};'),
        source('assert keep<Int<64,Unsigned>>(Int<64,Unsigned>{18446744073709551615})==Int<64,Unsigned>{18446744073709551615};0','template keep<T>=function(value:T):T{value};'),
        source('assert maximum<64>()==Int<64,Unsigned>{18446744073709551615};0','template maximum<N:Int>=function():Int<N,Unsigned>{Int<N,Unsigned>{18446744073709551615}};'),
    ]
    for ordinal,text in enumerate(generic):
        artifact=build('generic-'+str(ordinal),text);call('generic-'+str(ordinal)+'-native',[artifact])
    capture=source('let saved:Function():Int<64,Unsigned>=make(Int<64,Unsigned>{18446744073709551615});assert saved()==Int<64,Unsigned>{18446744073709551615};0','let make:Function(Int<64,Unsigned>):Function():Int<64,Unsigned>=function(value:Int<64,Unsigned>):Function():Int<64,Unsigned>{function():Int<64,Unsigned>{value}};')
    artifact=build('scalar-capture',capture);call('scalar-capture-native',[artifact]);call('scalar-capture-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',artifact.parent/'stress.json','--',artifact])
    # These instruction words are independent fixed vectors, including both
    # halves of the unsigned range and signed narrow-word canonicalization.
    vectors=[('Int<64,Unsigned>',18446744073709551615,b'\xff'*8),('Int<64,Unsigned>',9223372036854775808,b'\x00'*7+b'\x80'),('Int<8,Signed>',-128,b'\x80'+b'\xff'*7),('Bits<8>',255,b'\xff'+b'\x00'*7),('Bits<1>',1,b'\x01'+b'\x00'*7)]
    for ordinal,(t,value,word) in enumerate(vectors):
        artifact=build('vector-'+str(ordinal),source('discard '+literal(t,value)+';0'))
        assert b'\x48\xb8'+word in artifact.read_bytes(),(t,value)
        call('vector-'+str(ordinal)+'-native',[artifact])
    # Independent failures cover machine-width carry/high product and narrow
    # overflow, hardware-trap avoidance, zero division and unsigned negation.
    failures=[]
    for width in [1,8,31,32,63,64]:
        for signed in [False,True]:
            t=f'Int<{width},{"Signed" if signed else "Unsigned"}>';lo=-(1<<(width-1)) if signed else 0;hi=(1<<(width-1))-1 if signed else (1<<width)-1
            overflow=[literal(t,hi)+'+'+literal(t,1)] if hi>=1 else [literal(t,lo)+'+'+literal(t,lo)]
            if signed:overflow += ['-'+literal(t,lo),literal(t,lo)+'/'+literal(t,-1),literal(t,lo)+'-'+literal(t,1 if hi>=1 else lo)] if hi>=1 else ['-'+literal(t,lo),literal(t,lo)+'/'+literal(t,-1)]
            else:overflow+=['-'+literal(t,hi),literal(t,0)+'-'+literal(t,hi)]
            if hi>=2:overflow.append(literal(t,hi)+'*'+literal(t,2))
            for expression in overflow:failures.append((t,expression,b'runtime error: integer overflow\n'))
            for op in ['/','%']:failures.append((t,literal(t,hi)+op+literal(t,0),b'runtime error: division by zero\n'))
    for ordinal,(t,expression,message) in enumerate(failures):
        artifact=build('failure-'+str(ordinal),source('discard '+expression+';0'));call('failure-'+str(ordinal)+'-native',[artifact],4,message)
    for width in [1,8,64]:
        t=f'Int<{width},Unsigned>';hi=(1<<width)-1
        prefix='type Box=product{value:'+t+';bits:Bits<'+str(width)+'>;mark:Signed;};let global:'+t+'='+literal(t,hi)+';'
        body='let saved:Box=Box{value:global,bits:global->toBits(),mark:Signed{}};let values:List<'+t+'>=List<'+t+'>[saved->value];let keep:Function():'+t+'=function():'+t+'{saved->value};'
        body+='let observed:'+t+'=branch on values->at(0){Result<'+t+',IndexError>::Ok(value:'+t+')=>value,Result<'+t+',IndexError>::Err(error:IndexError)=>panic{"at"}};assert keep()==observed;assert observed=='+literal(t,hi)+';0'
        artifact=build('container-'+str(width),source(body,prefix));call('container-'+str(width)+'-native',[artifact]);call('container-'+str(width)+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',artifact.parent/'stress.json','--',artifact])
    invalid=[('Int<8,Signed>{128}','type'),('Int<8,Signed>{-129}','type'),('Int<64,Unsigned>{18446744073709551616}','type'),('Bits<8>{256}','type'),('Int<8,Signed>{1}+Int<8,Unsigned>{1}','type'),('Bits<8>{1}<Bits<8>{2}','type')]
    for ordinal,(expression,phase) in enumerate(invalid):
        folder=args.output/('invalid-'+str(ordinal));folder.mkdir();path=folder/'input.mgn';path.write_text(source('discard '+expression+';0'));artifact=folder/'program';artifact.write_bytes(b'preserved')
        for verb in ['check','lower','build']:
            command=[compiler,verb,path]+(['-o',artifact] if verb=='build' else []);call('invalid-'+str(ordinal)+'-'+verb,command,1,phase=phase)
            assert artifact.read_bytes()==b'preserved'
    unsupported=['Int<8,Signed>{1}->convertTo<Int>()','Bits<8>{1}->shiftLeft(0)','Bits<8>{1}->shiftRight(1)','Bits<8>{1}->at(0)']
    for ordinal,expression in enumerate(unsupported):
        folder=args.output/('unsupported-'+str(ordinal));folder.mkdir();path=folder/'input.mgn';path.write_text(source('discard '+expression+';0'));artifact=folder/'program';artifact.write_bytes(b'preserved')
        for verb in ['check','lower']:call('unsupported-'+str(ordinal)+'-'+verb,[compiler,verb,path])
        call('unsupported-'+str(ordinal)+'-build',[compiler,'build',path,'-o',artifact],1,phase='unsupported');assert artifact.read_bytes()==b'preserved'
    print(f'V170_NUMERIC_SCALARS_OK widths=128 oracle_assertions={assertions} fixed_vectors={len(vectors)} runtime_failures={len(failures)} containers=4 generic=3 checked_result_gates=4 negative={len(invalid)} observations={len(rows)}')
if __name__=='__main__':main()
