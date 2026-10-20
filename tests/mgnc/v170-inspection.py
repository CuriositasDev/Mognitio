#!/usr/bin/env python3
"""Observe path kinds, opaque identity and standalone inspection Function values."""
import argparse,hashlib,json,os,socket,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False)
prefix=r'namespace App;use Std\Io\{inspectPath,FileIdentity,PathInfo,PathInfoError,DirectoryEntryKind,IoErrorKind};'
kinds=['File','Directory','Symlink','Other'];errors=['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other'];rows=[];fixtures={}
def text(value):return json.dumps(str(value),ensure_ascii=False).replace(chr(92)+'u0000',chr(92)+'u{0}')
def branch(value,typ,names,expected):return 'branch on '+value+'{'+','.join(typ+'::'+name+'=>'+('true' if name==expected else 'false') for name in names)+'}'
def info(path):return 'branch on inspectPath('+text(path)+'){Result<PathInfo,PathInfoError>::Ok(value:PathInfo)=>value,Result<PathInfo,PathInfoError>::Err(error:PathInfoError)=>panic{error->subject}}'
def program(body,extra=''):return prefix+extra+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};'
def call(name,command,status=0,phase=None):
 result=subprocess.run(list(map(str,command)),capture_output=True,timeout=180)
 passed=result.returncode==status and result.stdout==b'' and (result.stderr==b'' if phase is None else phase.encode() in result.stderr)
 rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=passed));(options.output/'results.json').write_text(json.dumps(dict(fixtures=fixtures,observations=rows),indent=2)+'\n');assert passed,rows[-1]
with tempfile.TemporaryDirectory(prefix='mgn-inspection-') as temporary:
 work=Path(temporary);file=work/'file';file.write_bytes(b'same');other=work/'other';other.write_bytes(b'same');hard=work/'hard';os.link(file,hard);link=work/'link';link.symlink_to(work);dangling=work/'dangling';dangling.symlink_to(work/'missing');fifo=work/'pipe';os.mkfifo(fifo);sock=socket.socket(socket.AF_UNIX);sockpath=work/'socket';sock.bind(str(sockpath));unreadable=work/'unreadable';unreadable.write_bytes(b'private');unreadable.chmod(0)
 def fixture(name,body,extra='',stress=False,observe=False,status=0):
  folder=options.output/name;folder.mkdir();source=folder/'input.mgn';source.write_text(program(body,extra));image=folder/'program';fixtures[name]={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  for verb in ('check','lower'):call(name+'-'+verb,[options.compiler,verb,source])
  call(name+'-build',[options.compiler,'build',source,'-o',image]);fixtures[name]['artifact_sha256']=hashlib.sha256(image.read_bytes()).hexdigest();call(name+'-native',[image],status)
  if stress:call(name+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',folder/'stress.json','--',image],status)
  if observe:
   report=folder/'syscalls.json';call(name+'-observed',[sys.executable,Path(__file__).with_name('publication-observe.py'),'--report',report,image],status);events=json.loads(report.read_text())['events'];assert not [e for e in events if e['call'] in (0,2,3,257)],(name,'inspection acquired a file descriptor',events)
   for event in [e for e in events if e['call']==262]:assert event['arguments'][0]==(1<<64)-100 and event['arguments'][3]==256,event
  assert hashlib.sha256(image.read_bytes()).hexdigest()==fixtures[name]['artifact_sha256']
  return image
 try:
  for ordinal,(path,kind) in enumerate([(file,'File'),(work,'Directory'),(fifo,'Other'),(sockpath,'Other'),(link,'Symlink'),(str(link)+'///','Symlink'),(str(link)+'/.','Directory'),(dangling,'Symlink'),(str(dangling)+'/','Symlink'),('////','Directory'),(unreadable,'File')]):fixture('kind-'+str(ordinal),'let observed:PathInfo='+info(path)+';assert '+branch('observed->kind','DirectoryEntryKind',kinds,kind)+';0',stress=ordinal in (0,4,8),observe=True)
  for ordinal,(path,kind) in enumerate([('','InvalidPath'),(work/'missing','NotFound'),(file/'child','UnsupportedTarget'),(dangling/'child','NotFound'),(str(work)+'/'+'x'*256,'InvalidPath'),(str(work)+chr(0)+'child','InvalidPath')]):fixture('error-'+str(ordinal),'branch on inspectPath('+text(path)+'){Result<PathInfo,PathInfoError>::Ok=>1,Result<PathInfo,PathInfoError>::Err(error:PathInfoError)=>{assert error->subject=='+text(path)+';assert '+branch('error->kind','IoErrorKind',errors,kind)+';0}}',stress=True,observe=True)
  equal='let a:PathInfo='+info(file)+';let b:PathInfo='+info(hard)+';let c:PathInfo='+info(file)+';let d:PathInfo='+info(other)+';assert a->identity==a->identity;assert a->identity==b->identity;assert b->identity==a->identity;assert a->identity==c->identity;assert a->identity!=d->identity;assert !(a->identity!=b->identity);assert !(a->identity==d->identity);0'
  fixture('identity-equality',equal,stress=True,observe=True)
  equal='let link:PathInfo='+info(link)+';let slash:PathInfo='+info(str(link)+'///')+';let target:PathInfo='+info(work)+';assert link->identity==slash->identity;assert link->identity!=target->identity;0'
  fixture('link-identity',equal,stress=True,observe=True)
  retained='let api:Function(String):Result<PathInfo,PathInfoError>=inspectPath;let saved:Function(String):Result<PathInfo,PathInfoError>=function(path:String):Result<PathInfo,PathInfoError>{api(path)};let observed:PathInfo='+info(work)+';let identity:FileIdentity=observed->identity;let box:Box<FileIdentity>=Box<FileIdentity>{value:identity};let carried:Carry=Carry::Ready(identity);let kept:Result<Token,PathInfoError>=Result<Token,PathInfoError>::Ok(identity);let capture:Function():FileIdentity=function():FileIdentity{box->value};var count:Int=0;loop while(count<40){let values:List<FileIdentity>=List<FileIdentity>[capture(),identity];loop over(values as value:FileIdentity){assert value==identity;};assert branch on saved('+text(work)+'){Result<PathInfo,PathInfoError>::Ok(value:PathInfo)=>value->identity==identity,Result<PathInfo,PathInfoError>::Err=>false};let synthetic:PathInfo=PathInfo{kind:DirectoryEntryKind::Other,identity:capture()};assert synthetic->identity==identity;assert branch on carried{Carry::Ready(value:Token)=>value==identity};assert branch on kept{Result<Token,PathInfoError>::Ok(value:Token)=>value==identity,Result<Token,PathInfoError>::Err=>false};count=count+1;};0'
  fixture('retained-first-class',retained,'type Box<T>=product{value:T;};alias Token=FileIdentity;type Carry=sum{Ready(Token);};',stress=True)
  fixture('operand-return','inspectPath({return 7;})',stress=True,status=7)
  # Opaque construction and distinct error identities remain frontend errors.
  invalid=['discard FileIdentity{};0','let value:Result<PathInfo,IoError>=inspectPath(".");0','let attempt:Function():Result<PathInfo,IoError>=function():Result<PathInfo,IoError>{Result<PathInfo,IoError>::Ok(try inspectPath("."))};0']
  for ordinal,body in enumerate(invalid):
   folder=options.output/('invalid-'+str(ordinal));folder.mkdir();source=folder/'input.mgn';source.write_text(program(body).replace('namespace App;','namespace App;use Std\\Io\\{IoError};'));image=folder/'program';image.write_bytes(b'preserved')
   for verb in ('check','lower','build'):
    call('invalid-'+str(ordinal)+'-'+verb,[options.compiler,verb,source]+(['-o',image] if verb=='build' else []),1,':');assert image.read_bytes()==b'preserved'
 finally:sock.close();unreadable.chmod(0o600)
(options.output/'summary.json').write_text(json.dumps({'fixtures':len(fixtures),'observations':len(rows),'compiler_sha256':hashlib.sha256(options.compiler.read_bytes()).hexdigest(),'passed':True},indent=2)+'\n')
print('V170_INSPECTION_OK',len(fixtures),len(rows))
