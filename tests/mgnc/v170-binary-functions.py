#!/usr/bin/env python3
"""Observe standard Bytes construction against independent byte/word vectors."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
IMPORTS=r'use Std\Numeric\{Bits,Unsigned,IntegerConversionError};use Std\Binary\{Bytes,ByteOrder,BitWidthError,BinaryDecodeError,ByteValueError,bytesFromInts,bytesFromBits};'
HELPERS='template unwrap<N:Int>=function(word:Bits<N>,order:ByteOrder):Bytes{branch on word->toBytes(order){Result<Bytes,BitWidthError>::Ok(value:Bytes)=>value,Result<Bytes,BitWidthError>::Err(error:BitWidthError)=>panic{"unexpected encoding error"}}};let empty:Function():Bytes=function():Bytes{branch on unwrap<8>(Bits<8>{0},ByteOrder::LittleEndian)->slice(0,0){Result<Bytes,SliceError>::Ok(value:Bytes)=>value,Result<Bytes,SliceError>::Err(error:SliceError)=>panic{"unexpected slice error"}}};'
def encoded(width,value,order):return f'unwrap<{width}>(Bits<{width}>{{{value}}},ByteOrder::{order})'
def vector(values):return 'empty()'+''.join('->append(Bits<8>{'+str(n)+'})' for n in values)
def matched(expression,t,error,yes,no):
    return 'branch on '+expression+'{Result<'+t+','+error+'>::Ok(value:'+t+')=>{'+yes+'},Result<'+t+','+error+'>::Err(error:'+error+')=>{'+no+'}};'
def program(checks,body='',prefix=''):
    functions=''.join('let check'+str(i)+':Function():Unit=function():Unit{'+''.join(checks[j:j+8])+'unit};' for i,j in enumerate(range(0,len(checks),8)))
    calls=''.join('check'+str(i)+'();' for i in range((len(checks)+7)//8))
    return 'namespace App;'+IMPORTS+prefix+HELPERS+functions+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+calls+body+'0};'
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


    for length in [0,1,2,8,31,32,33,255,256,1024]:
        values=[i%256 for i in range(length)];ints='List<Int>['+','.join(map(str,values))+']';bits='List<Bits<8>>['+','.join('Bits<8>{'+str(v)+'}' for v in values)+']'
        body='let values:List<Int>='+ints+';let words:List<Bits<8>>='+bits+';let a:Bytes=branch on bytesFromInts(values){Result<Bytes,ByteValueError>::Ok(value:Bytes)=>value,Result<Bytes,ByteValueError>::Err(error:ByteValueError)=>panic{"unexpected construction error"}};let b:Bytes=bytesFromBits(words);assert a==b;assert a->length()=='+str(length)+';var index:Int=0;loop over(values as expected:Int){branch on a->at(index){Result<Bits<8>,IndexError>::Ok(value:Bits<8>)=>{branch on value->asInteger<Unsigned>()->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(number:Int)=>{assert number==expected;},Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};},Result<Bits<8>,IndexError>::Err(error:IndexError)=>{assert false;}};index=index+1;};assert index=='+str(length)+';assert words->length()=='+str(length)+';'
        build('length-'+str(length),program([],body=body),stress=length in [0,8,256,1024],isolate=length in [0,256])
    failures=[[-1,256],[256,-1],[0,1,257,-1],[0,255,-(1<<63),256],[(1<<63)-1,-(1<<63)],[0,255,256,-1]]
    for ordinal,values in enumerate(failures):
        index=next(i for i,v in enumerate(values) if not 0<=v<=255);value=values[index];expression='bytesFromInts(List<Int>['+','.join(map(str,values))+'])';checks=[matched(expression,'Bytes','ByteValueError','assert false;',f'assert error->index=={index};assert error->value==({value});')]
        build('first-invalid-'+str(ordinal),program(checks),stress=True,isolate=ordinal==0)
    signature='Function(List<Int>):Result<Bytes,ByteValueError>'
    indirect='let nativeMake:'+signature+'=bytesFromInts;let apply:Function('+signature+',List<Int>):Result<Bytes,ByteValueError>=function(make:'+signature+',values:List<Int>):Result<Bytes,ByteValueError>{make(values)};let captured:'+signature+'=function(values:List<Int>):Result<Bytes,ByteValueError>{nativeMake(values)};let makers:List<'+signature+'>=List<'+signature+'>[captured,nativeMake];discard makers->append(captured);'
    indirect+=matched('apply(captured,List<Int>[0,255,128])','Bytes','ByteValueError','assert value=='+vector([0,255,128])+';','assert false;')
    indirect+=matched('captured(List<Int>[0,-1,256])','Bytes','ByteValueError','assert false;','assert error->index==1;assert error->value== -1;')
    indirect+='let nativeBits:Function(List<Bits<8>>):Bytes=bytesFromBits;let saved:Function():Bytes=function():Bytes{nativeBits(List<Bits<8>>[Bits<8>{0},Bits<8>{255},Bits<8>{128}])};assert saved()=='+vector([0,255,128])+';'
    build('indirect',program([],body=indirect),stress=True,isolate=True)
    retain='let original:List<Int>=List<Int>[0,-1,256];let bad:Result<Bytes,ByteValueError>=bytesFromInts(original);let kept:List<Result<Bytes,ByteValueError>>=List<Result<Bytes,ByteValueError>>[bad];let saved:Function():Result<Bytes,ByteValueError>=function():Result<Bytes,ByteValueError>{bad};discard kept->append(saved());'
    retain+=matched('saved()','Bytes','ByteValueError','assert false;','assert error->index==1;assert error->value== -1;')
    retain+='assert original->length()==3;branch on original->at(1){Result<Int,IndexError>::Ok(value:Int)=>{assert value== -1;},Result<Int,IndexError>::Err(error:IndexError)=>{assert false;}};var count:Int=0;discard bytesFromInts({count=count+1;List<Int>[1]});assert count==1;'
    build('retained-error',program([],body=retain),stress=True,isolate=True)

    build('operand-return',('namespace App;'+IMPORTS+HELPERS+'let main:Function(List<String>):Int=function(args:List<String>):Int{bytesFromInts({return 7;})};'),stress=True,isolate=True,status=7)
    def project_case(name,sources):
        folder=args.output/name;folder.mkdir();sources=dict(sources,**{'mognitio.toml':'[project]\nname="app"\nroot_namespace="App"\n'})
        for relative,text in sources.items():
            path=folder/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        inventory={relative:hashlib.sha256((folder/relative).read_bytes()).hexdigest() for relative in sources};fixtures[name]={'sources':inventory};artifact=folder/'program';manifest=folder/'mognitio.toml'
        for verb in ['check','lower']:call(name+'-'+verb,[compiler,verb,manifest])
        call(name+'-build',[compiler,'build',manifest,'-o',artifact]);fixtures[name]['artifact_sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest();save();call(name+'-native',[artifact]);call(name+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',folder/'stress.json','--',artifact]);call(name+'-isolated',['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','1000','--gid','1000','--clearenv','--ro-bind',artifact,'/program','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--chdir','/','--','/program']);assert all(hashlib.sha256((folder/relative).read_bytes()).hexdigest()==digest for relative,digest in inventory.items())
    bridge=r'namespace App\Bridge;use Std\Numeric\{Bits};use Std\Binary\{Bytes,ByteValueError,bytesFromInts as implementation,bytesFromBits};public let make:Function(List<Int>):Result<Bytes,ByteValueError>=implementation;public let makeBits:Function(List<Bits<8>>):Bytes=bytesFromBits;'
    body=matched('make(List<Int>[0,255,128])','Bytes','ByteValueError','assert value=='+vector([0,255,128])+';','assert false;')+'assert makeBits(List<Bits<8>>[Bits<8>{0},Bits<8>{255},Bits<8>{128}])=='+vector([0,255,128])+';'
    project_case('renamed-reexport',{'src/Bridge/value.mgn':bridge,'src/app.mgn':program([],body=body,prefix=r'use App\Bridge\{make,makeBits};')})
    fake=r'namespace App\Fake;use Std\Binary\{Bytes,ByteValueError};public let bytesFromInts:Function(List<Int>):Result<Bytes,ByteValueError>=function(values:List<Int>):Result<Bytes,ByteValueError>{Result<Bytes,ByteValueError>::Err(ByteValueError{index:77,value:99})};'
    body=matched('userMake(List<Int>[1])','Bytes','ByteValueError','assert false;','assert error->index==77;assert error->value==99;')+matched('bytesFromInts(List<Int>[1])','Bytes','ByteValueError','assert value=='+vector([1])+';','assert false;')
    project_case('user-same-name',{'src/Fake/value.mgn':fake,'src/app.mgn':program([],body=body,prefix=r'use App\Fake\{bytesFromInts as userMake};')})
    invalid=['bytesFromInts(List<Bits<8>>[])','bytesFromBits(List<Int>[])','bytesFromInts(1)','bytesFromBits(true)']
    for ordinal,expression in enumerate(invalid):
        folder=args.output/('invalid-'+str(ordinal));folder.mkdir();path=folder/'input.mgn';path.write_text(program([],body='discard '+expression+';'));artifact=folder/'program';artifact.write_bytes(b'preserved')
        for verb in ['check','lower','build']:
            run=subprocess.run(list(map(str,[compiler,verb,path]+(['-o',artifact] if verb=='build' else []))),capture_output=True,timeout=180)
            passed=run.returncode==1 and run.stdout==b'' and (b'type:' in run.stderr or b'semantic:' in run.stderr) and artifact.read_bytes()==b'preserved';rows.append({'case':'invalid-'+str(ordinal)+'-'+verb,'exit':run.returncode,'stderr_hex':run.stderr.hex(),'passed':passed});save();assert passed,rows[-1]
    print(f'V170_BINARY_FUNCTIONS_OK fixtures={len(fixtures)} observations={len(rows)}')
if __name__=='__main__':main()
