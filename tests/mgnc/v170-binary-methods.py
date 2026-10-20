#!/usr/bin/env python3
"""Observe Bytes methods and encoding against independent byte/word vectors."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
IMPORTS=r'use Std\Numeric\{Bits};use Std\Binary\{Bytes,ByteOrder,BitWidthError,BinaryDecodeError};'
HELPERS='template unwrap<N:Int>=function(word:Bits<N>,order:ByteOrder):Bytes{branch on word->toBytes(order){Result<Bytes,BitWidthError>::Ok(value:Bytes)=>value,Result<Bytes,BitWidthError>::Err(error:BitWidthError)=>panic{"unexpected encoding error"}}};let empty:Function():Bytes=function():Bytes{branch on unwrap<8>(Bits<8>{0},ByteOrder::LittleEndian)->slice(0,0){Result<Bytes,SliceError>::Ok(value:Bytes)=>value,Result<Bytes,SliceError>::Err(error:SliceError)=>panic{"unexpected slice error"}}};'
def encoded(width,value,order):return f'unwrap<{width}>(Bits<{width}>{{{value}}},ByteOrder::{order})'
def vector(values):return 'empty()'+''.join('->append(Bits<8>{'+str(n)+'})' for n in values)
def matched(expression,t,error,yes,no):
    return 'branch on '+expression+'{Result<'+t+','+error+'>::Ok(value:'+t+')=>{'+yes+'},Result<'+t+','+error+'>::Err(error:'+error+')=>{'+no+'}};'
def program(checks,body='',prefix=''):
    functions=''.join('let check'+str(i)+':Function():Unit=function():Unit{'+''.join(checks[j:j+8])+'unit};' for i,j in enumerate(range(0,len(checks),8)))
    calls=''.join('check'+str(i)+'();' for i in range((len(checks)+7)//8))
    return 'namespace App;'+IMPORTS+HELPERS+prefix+functions+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+calls+body+'0};'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    compiler=args.compiler.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False);rows=[];fixtures={}
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

    vectors=0
    for width in range(1,65):
        checks=[]
        if width%8:
            for order in ['LittleEndian','BigEndian']:
                checks.append(matched(f'Bits<{width}>{{0}}->toBytes(ByteOrder::{order})','Bytes','BitWidthError','assert false;',f'assert error->width=={width};'))
                checks.append(matched(vector([255])+f'->toBits<{width}>(ByteOrder::{order})',f'Bits<{width}>','BinaryDecodeError','assert false;',f'assert error->width=={width};assert error->length==1;'))
        else:
            mask=(1<<width)-1
            for word in sorted(set([0,1,mask,1<<(width-1),0x0123456789abcdef&mask])):
                for order in ['LittleEndian','BigEndian']:
                    data=list(word.to_bytes(width//8,'little' if order=='LittleEndian' else 'big'));text='let bytes:Bytes='+encoded(width,word,order)+';assert bytes->length()=='+str(len(data))+';'
                    for index,value in enumerate(data):text+=matched(f'bytes->at({index})','Bits<8>','IndexError',f'assert value==Bits<8>{{{value}}};','assert false;')
                    for decode_order in ['LittleEndian','BigEndian']:
                        expected=int.from_bytes(bytes(data),'little' if decode_order=='LittleEndian' else 'big');text+=matched(f'bytes->toBits<{width}>(ByteOrder::{decode_order})',f'Bits<{width}>','BinaryDecodeError',f'assert value==Bits<{width}>{{{expected}}};','assert false;')
                    checks.append('{'+text+'};');vectors+=1
            for size in sorted(set([0,width//8-1,width//8+1,9])):
                checks.append(matched(vector([128]*size)+f'->toBits<{width}>(ByteOrder::LittleEndian)',f'Bits<{width}>','BinaryDecodeError','assert false;',f'assert error->width=={width};assert error->length=={size};'))
        build('width-'+str(width),program(checks),stress=width%8==0,isolate=width in [1,8,63,64])
    data=[0,255,128,65];checks=[]
    for index in [-(1<<63),-1,0,1,3,4,5,(1<<63)-1]:
        good=0<=index<len(data);checks.append(matched(vector(data)+f'->at({index})','Bits<8>','IndexError',f'assert value==Bits<8>{{{data[index]}}};' if good else 'assert false;','assert false;' if good else f'assert error->index==({index});assert error->length==4;'))
    for start in [-1,0,1,4,5]:
        for end in [-1,0,1,4,5]:
            good=0<=start<=end<=4;checks.append(matched(vector(data)+f'->slice({start},{end})','Bytes','SliceError','assert value=='+vector(data[start:end])+';' if good else 'assert false;','assert false;' if good else f'assert error->start==({start});assert error->end==({end});assert error->length==4;'))
    build('bounds',program(checks),stress=True,isolate=True)
    retained='''
let bytes:Bytes='''+vector(data)+''';let emptyBytes:Bytes=empty();
assert bytes->length()==4;assert emptyBytes->length()==0;
assert bytes=='''+vector(data)+''';assert bytes!='''+vector(list(reversed(data)))+''';
assert emptyBytes==empty();assert bytes!=emptyBytes;
assert bytes->concat(emptyBytes)==bytes;assert emptyBytes->concat(bytes)==bytes;
let changed:Bytes=bytes->append(Bits<8>{0});assert changed==bytes->concat('''+vector([0])+''');
assert bytes->length()==4;assert changed->length()==5;
let saved:Function():Bytes=function():Bytes{bytes};let list:List<Bytes>=List<Bytes>[saved(),changed];
discard list->append(empty());assert saved()==bytes;
branch on list->at(1){Result<Bytes,IndexError>::Ok(value:Bytes)=>{assert value==changed;},Result<Bytes,IndexError>::Err(error:IndexError)=>{assert false;}};
var count:Int=0;discard ({count=count+1;bytes})->slice({count=count+1;0},{count=count+1;4});assert count==3;
'''
    build('snapshots',program([],body=retained),stress=True,isolate=True)
    invalid=['empty()->append(1)','empty()->toBits<0>(ByteOrder::LittleEndian)','empty()->toBits<65>(ByteOrder::LittleEndian)','empty()->toBits<Int>(ByteOrder::LittleEndian)','empty()->toBits<8>(1)','Bits<8>{1}->toBytes(0)']
    for ordinal,expression in enumerate(invalid):
        folder=args.output/('invalid-'+str(ordinal));folder.mkdir();path=folder/'input.mgn';path.write_text(program([],body='discard '+expression+';'));artifact=folder/'program';artifact.write_bytes(b'preserved')
        for verb in ['check','lower','build']:
            run=subprocess.run(list(map(str,[compiler,verb,path]+(['-o',artifact] if verb=='build' else []))),capture_output=True,timeout=180)
            passed=run.returncode==1 and run.stdout==b'' and (b'type:' in run.stderr or b'semantic:' in run.stderr) and artifact.read_bytes()==b'preserved';rows.append({'case':'invalid-'+str(ordinal)+'-'+verb,'exit':run.returncode,'stderr_hex':run.stderr.hex(),'passed':passed});save();assert passed,rows[-1]
    print(f'V170_BINARY_METHODS_OK widths=64 vectors={vectors} fixtures={len(fixtures)} observations={len(rows)}')
if __name__=='__main__':main()
