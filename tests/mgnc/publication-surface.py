#!/usr/bin/env python3
"""Verify publication Function values, operand completion and retained roots."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument("--compiler",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
options=parser.parse_args();options.out.mkdir(parents=True,exist_ok=False);rows=[];fixtures=0
prefix=r'namespace App;use Std\Numeric\{Bits};use Std\Binary\{Bytes,bytesFromBits,bytesFromInts,ByteValueError,publishFile,BinaryFileMode,BinaryOutputError,BinaryOutputErrorKind};use Std\Io\{writeStdout};'
empty='bytesFromBits(List<Bits<8>>[])';signature='Function(String,Bytes,BinaryFileMode):Result<Unit,BinaryOutputError>'
def program(body,extra=''):return prefix+extra+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};'
with tempfile.TemporaryDirectory(prefix='mgn-pub-surface-') as temporary:
 work=Path(temporary);target=work/'target';source=options.out/'input.mgn';image=options.out/'program'
 def call(name,command,code=0,out=b'',err=b''):
  result=subprocess.run(list(map(str,command)),capture_output=True,timeout=180)
  rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=(result.returncode,result.stdout,result.stderr)==(code,out,err)))
  (options.out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert rows[-1]['passed'],rows[-1]
 def fixture(name,text,code=0,out=b'',err=b'',stress=True,payload=None):
  global fixtures
  fixtures+=1;source.write_text(text);(options.out/(name+'.mgn')).write_text(text);image.unlink(missing_ok=True)
  for verb in ('check','lower'):call(name+'-'+verb,[options.compiler,verb,source])
  call(name+'-build',[options.compiler,'build',source,'-o',image]);assert not target.exists()
  digest=hashlib.sha256(image.read_bytes()).hexdigest();(options.out/(name+'.sha256')).write_text(digest+'\n')
  for mode in ('native','stress') if stress else ('native',):
   command=[image] if mode=='native' else [sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',options.out/(name+'-stress.json'),'--',image]
   call(name+'-'+mode,command,code,out,err)
   if payload is not None:assert target.read_bytes()==payload;target.unlink()
   else:assert not target.exists()
  assert hashlib.sha256(image.read_bytes()).hexdigest()==digest
 fixture('evaluation-order',program('discard publishFile({discard writeStdout("p");""},{discard writeStdout("b");'+empty+'},{discard writeStdout("m");BinaryFileMode::Data});0'),out=b'pbm')
 fixture('panic-operand',program('discard publishFile({discard writeStdout("p");""},{discard writeStdout("b");stop()},{discard writeStdout("m");BinaryFileMode::Data});0','let stop:Function():Bytes=function():Bytes{panic{"stop"}};'),4,b'pb',b'panic: stop\n')
 for ordinal,arguments in enumerate([['{return 7;}',empty,'BinaryFileMode::Data'],['""','{return 7;}','BinaryFileMode::Data'],['""',empty,'{return 7;}']]):fixture('operand-return-'+str(ordinal),program('publishFile('+','.join(arguments)+')'),7)
 extra='let attempt:Function():Result<Unit,ByteValueError>=function():Result<Unit,ByteValueError>{discard publishFile({discard writeStdout("p");""},try bytesFromInts(List<Int>[-1]),{discard writeStdout("m");BinaryFileMode::Data});Result<Unit,ByteValueError>::Ok(unit)};'
 fixture('try-before-validation',program('branch on attempt(){Result<Unit,ByteValueError>::Ok=>1,Result<Unit,ByteValueError>::Err(e:ByteValueError)=>branch when{e->index==0&&e->value== -1=>0,else=>2}}',extra),out=b'p')
 extra='let attempt:Function():Result<Unit,BinaryOutputError>=function():Result<Unit,BinaryOutputError>{let save:'+signature+'=publishFile;try save("",'+empty+',BinaryFileMode::Data);Result<Unit,BinaryOutputError>::Ok(unit)};'
 fixture('first-class-try',program('branch on attempt(){Result<Unit,BinaryOutputError>::Ok=>1,Result<Unit,BinaryOutputError>::Err(e:BinaryOutputError)=>0}',extra))
 retain='let save:'+signature+'=publishFile;let captured:'+signature+'=function(path:String,data:Bytes,mode:BinaryFileMode):Result<Unit,BinaryOutputError>{save(path,data,mode)};let calls:List<'+signature+'>=List<'+signature+'>[captured,save];discard calls->append(captured);let bad:Result<Unit,BinaryOutputError>=captured("",'+empty+',BinaryFileMode::Data);let saved:Function():Result<Unit,BinaryOutputError>=function():Result<Unit,BinaryOutputError>{bad};var count:Int=0;loop while(count<32){discard publishFile("",'+empty+',BinaryFileMode::Data);count=count+1;};branch on saved(){Result<Unit,BinaryOutputError>::Ok=>1,Result<Unit,BinaryOutputError>::Err(e:BinaryOutputError)=>{assert e->subject=="";branch on e->kind{BinaryOutputErrorKind::InvalidPath=>0,BinaryOutputErrorKind::AlreadyExists=>1,BinaryOutputErrorKind::NotFound=>1,BinaryOutputErrorKind::PermissionDenied=>1,BinaryOutputErrorKind::UnsupportedTarget=>1,BinaryOutputErrorKind::ResourceExhausted=>1,BinaryOutputErrorKind::Other=>1}}}'
 fixture('retained-indirect-error',program(retain))
 write='let save:'+signature+'=publishFile;let data:Bytes=bytesFromBits(List<Bits<8>>[Bits<8>{0},Bits<8>{128},Bits<8>{255}]);let result:Result<Unit,BinaryOutputError>=save('+json.dumps(str(target))+',data,BinaryFileMode::Data);var count:Int=0;loop while(count<32){discard data->append(Bits<8>{1});count=count+1;};branch on result{Result<Unit,BinaryOutputError>::Ok=>0,Result<Unit,BinaryOutputError>::Err=>1}'
 fixture('retained-success',program(write),payload=bytes([0,128,255]))
 # Publication uses the same wrapper when a renamed import is re-exported.
 project=options.out/'project';(project/'src').mkdir(parents=True);manifest=project/'mognitio.toml';manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
 (project/'src/Bridge').mkdir()
 (project/'src/Bridge/value.mgn').write_text(r'namespace App\Bridge;use Std\Binary\{Bytes,BinaryFileMode,BinaryOutputError,publishFile as implementation};public let save:'+signature+'=implementation;')
 (project/'src/app.mgn').write_text(program('discard save("",'+empty+',BinaryFileMode::Data);0').replace('namespace App;','namespace App;use App\\Bridge\\{save};'))
 image.unlink();call('reexport-build',[options.compiler,'build',manifest,'-o',image]);call('reexport-native',[image]);call('reexport-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',options.out/'reexport-stress.json','--',image])
 # A fresh sandbox has no repository, compiler runtime, or inherited process state.
 image.unlink();source.write_text(program('discard publishFile("/tmp/output",'+empty+',BinaryFileMode::Data);0'));call('isolated-build',[options.compiler,'build',source,'-o',image])
 for proc in (True,False):
  command=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','1000','--gid','1000','--clearenv','--ro-bind',image,'/program','--dev','/dev','--tmpfs','/tmp','--chdir','/']
  if proc:command+=['--proc','/proc']
  call('isolation-'+str(proc),command+['--','/program'])
(options.out/'summary.json').write_text(json.dumps({'fixtures':fixtures+2,'observations':len(rows),'passed':True,'compiler_sha256':hashlib.sha256(options.compiler.read_bytes()).hexdigest()},indent=2)+'\n')
print('MGNC_PUBLICATION_SURFACE_OK',fixtures+2,len(rows))
