#!/usr/bin/env python3
"""Observe checked numeric Results against a test-only mathematical oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

IMPORTS=r'use Std\Numeric\{Bits,Signed,Unsigned,IntegerConversionError,BitShiftError};'
def integer(width,signed):return f'Int<{width},{"Signed" if signed else "Unsigned"}>'
def bounds(width,signed):return (-(1<<(width-1)),(1<<(width-1))-1) if signed else (0,(1<<width)-1)
def literal(t,value):return str(value) if t=='Int' else t+'{'+str(value)+'}'
def matched(expression,t,error,success,expected=None,fields=''):
    yes='assert converted=='+literal(t,expected)+';' if success else 'assert false;'
    no='assert false;' if success else fields
    return 'branch on '+expression+'{Result<'+t+','+error+'>::Ok(converted:'+t+')=>{'+yes+'},Result<'+t+','+error+'>::Err(failure:'+error+')=>{'+no+'}};'
def program(checks,prefix='',body=''):
    chunks=[checks[i:i+16] for i in range(0,len(checks),16)]
    functions=''.join('let check'+str(i)+':Function():Unit=function():Unit{'+''.join(chunk)+'unit};' for i,chunk in enumerate(chunks))
    return 'namespace App;'+IMPORTS+prefix+functions+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+''.join('check'+str(i)+'();' for i in range(len(chunks)))+body+'0};'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    compiler=args.compiler.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False);rows=[];fixtures={};conversion_count=0;bit_count=0
    def save():
        (args.output/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'fixtures':fixtures,'observations':rows},indent=2)+'\n')
    def call(name,command,status=0,phase=None):
        run=subprocess.run(list(map(str,command)),capture_output=True,timeout=240,umask=0o022)
        passed=run.returncode==status and run.stdout==b'' and (run.stderr==b'' if phase is None else ('mgnc: '+phase+':').encode() in run.stderr)
        rows.append({'case':name,'command':list(map(str,command)),'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':passed});save();assert passed,rows[-1]
    def build(name,text,stress=False,isolate=False,status=0):
        folder=args.output/name;folder.mkdir();path=folder/'input.mgn';path.write_text(text);digest=hashlib.sha256(path.read_bytes()).hexdigest();artifact=folder/'program'
        fixtures[name]={'source_sha256':digest}
        for verb in ['check','lower']:call(name+'-'+verb,[compiler,verb,path])
        call(name+'-build',[compiler,'build',path,'-o',artifact]);fixtures[name]['artifact_sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest();save()
        call(name+'-native',[artifact],status)
        if stress:call(name+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',folder/'stress.json','--',artifact],status)
        if isolate:call(name+'-isolated',['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','1000','--gid','1000','--clearenv','--ro-bind',artifact,'/program','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--chdir','/','--','/program'],status)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        assert hashlib.sha256(artifact.read_bytes()).hexdigest()==fixtures[name]['artifact_sha256']
        return artifact
    # Every source width/sign and ordinary Int, with all destination widths
    # represented by the diagonal plus independent ordinary-Int boundary cells.
    sources=[(n,s,integer(n,s)) for n in range(1,65) for s in [False,True]]+[(64,True,'Int')]
    for width,signed,t in sources:
        lo,hi=bounds(width,signed);values=sorted(set([lo,hi,0]+([1] if hi>=1 else [])+([-1] if lo<0 else [])));checks=[]
        targets=[(n,s,integer(n,s)) for n in sorted(set([1,8,32,63,64,width])) for s in [False,True]]+[(64,True,'Int')]
        for target_width,target_sign,destination in targets:
            minimum,maximum=bounds(target_width,target_sign)
            for value in values:
                success=minimum<=value<=maximum;checks.append(matched('('+literal(t,value)+')->convertTo<'+destination+'>()',destination,'IntegerConversionError',success,value if success else None));conversion_count+=1
        build('convert-'+str(width)+'-'+('int' if t=='Int' else 'signed' if signed else 'unsigned'),program(checks))
    for width in range(1,65):
        checks=[]
        for signed in [False,True]:
            destination=integer(width,signed);minimum,maximum=bounds(width,signed)
            for value in sorted(set([-(1<<63),-1,0,1,(1<<63)-1,minimum,maximum,min(maximum+1,(1<<63)-1),max(minimum-1,-(1<<63))])):
                if not -(1<<63)<=value<=(1<<63)-1:continue
                success=minimum<=value<=maximum;checks.append(matched('('+str(value)+')->convertTo<'+destination+'>()',destination,'IntegerConversionError',success,value if success else None));conversion_count+=1
        build('destination-'+str(width),program(checks))
    for width in range(1,65):
        bits=f'Bits<{width}>';mask=(1<<width)-1;checks=[]
        for pattern in sorted(set([0,1,mask,1<<(width-1)])):
            for count in sorted(set([-(1<<63),-1,0,1,width-1,width,width+1,(1<<63)-1])):
                success=0<=count<width
                for method in ['shiftLeft','shiftRight','at']:
                    result='Bool' if method=='at' else bits;error='IndexError' if method=='at' else 'BitShiftError'
                    if success:expected=bool((pattern>>count)&1) if method=='at' else ((pattern<<count)&mask) if method=='shiftLeft' else pattern>>count
                    else:expected=None
                    fields='assert failure->'+('index' if method=='at' else 'count')+'=='+str(count)+';assert failure->'+('length' if method=='at' else 'width')+'=='+str(width)+';'
                    text=matched(literal(bits,pattern)+'->'+method+'('+str(count)+')',result,error,success,expected,fields)
                    if method=='at' and success:text=text.replace('Bool{True}','true').replace('Bool{False}','false')
                    checks.append(text);bit_count+=1
        build('bits-'+str(width),program(checks))
    generic=program([
        matched('cast<8>(127)','Int<8,Signed>','IntegerConversionError',True,127),
        matched('cast<8>(128)','Int<8,Signed>','IntegerConversionError',False),
        matched('shifter<64>(Bits<64>{1},63)','Bits<64>','BitShiftError',True,9223372036854775808),
        matched('shifter<64>(Bits<64>{1},64)','Bits<64>','BitShiftError',False,fields='assert failure->count==64;assert failure->width==64;'),
    ],prefix='template cast<N:Int>=function(value:Int):Result<Int<N,Signed>,IntegerConversionError>{value->convertTo<Int<N,Signed>>()};template shifter<N:Int>=function(value:Bits<N>,count:Int):Result<Bits<N>,BitShiftError>{value->shiftLeft(count)};')
    build('generic-results',generic,stress=True)
    transfers='namespace App;'+IMPORTS+'let receiver:Function(Int):Bits<64>=function(value:Int):Bits<64>{Bits<64>{1}};let main:Function(List<String>):Int=function(args:List<String>):Int{receiver({return 7;})->shiftLeft(64)};'
    build('operand-return',transfers,stress=True,status=7)
    # Real stress collections cross both error allocations and retain returned
    # errors/Results in closures and containers after helper-frame removal.
    retain=program([],body="""
var count:Int=0;
let result:Result<Bits<64>,BitShiftError>=({count=count+1;Bits<64>{9223372036854775808}})->shiftLeft(64);
assert count==1;
let kept:List<Result<Bits<64>,BitShiftError>>=List<Result<Bits<64>,BitShiftError>>[result];
let saved:Function():Result<Bits<64>,BitShiftError>=function():Result<Bits<64>,BitShiftError>{result};
discard kept->append(saved());
branch on saved(){Result<Bits<64>,BitShiftError>::Ok(value:Bits<64>)=>{assert false;},Result<Bits<64>,BitShiftError>::Err(error:BitShiftError)=>{assert error->count==64;assert error->width==64;}};
""")
    build('retained-error',retain,stress=True,isolate=True)
    for name,checks in [
        ('conversion-error',[matched('Int<64,Unsigned>{18446744073709551615}->convertTo<Int>()','Int','IntegerConversionError',False)]),
        ('shift-error',[matched('Bits<64>{1}->shiftRight(-1)','Bits<64>','BitShiftError',False,fields='assert failure->count== -1;assert failure->width==64;')]),
        ('at-error',[matched('Bits<1>{1}->at(1)','Bool','IndexError',False,fields='assert failure->index==1;assert failure->length==1;')]),
        ('conversion-success',[matched('Int<64,Unsigned>{9223372036854775807}->convertTo<Int>()','Int','IntegerConversionError',True,9223372036854775807)]),
    ]:build(name,program(checks),stress=True,isolate=True)
    invalid=['Bits<8>{1}->shiftLeft(Int<8,Signed>{1})','Bits<8>{1}->at(true)','Int<8,Signed>{1}->convertTo<Bits<8>>()','Bits<8>{1}->convertTo<Int>()']
    for ordinal,expression in enumerate(invalid):
        folder=args.output/('invalid-'+str(ordinal));folder.mkdir();path=folder/'input.mgn';path.write_text(program([],body='discard '+expression+';'));artifact=folder/'program';artifact.write_bytes(b'preserved')
        for verb in ['check','lower','build']:
            command=[compiler,verb,path]+(['-o',artifact] if verb=='build' else []);run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180)
            passed=run.returncode==1 and run.stdout==b'' and (b'type:' in run.stderr or b'semantic:' in run.stderr) and artifact.read_bytes()==b'preserved';rows.append({'case':'invalid-'+str(ordinal)+'-'+verb,'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':passed});save();assert passed,rows[-1]
    print(f'V170_NUMERIC_RESULTS_OK conversions={conversion_count} bit_operations={bit_count} fixtures={len(fixtures)} observations={len(rows)}')
if __name__=='__main__':main()
