#!/usr/bin/env python3
"""Observe lexical joins, one-level creation, permissions and protected entries."""
import argparse,hashlib,json,os,socket,stat,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);rows=[];fixtures={}
prefix=r'namespace App;use Std\Io\{joinPath,createDirectory,IoError,IoOperation,IoErrorKind,IoErrorPhase};'
operations=['ReadTextFile','WriteTextFile','ReadStdin','WriteStdout','WriteStderr','JoinPath','ReadDirectory','CreateDirectory'];kinds=['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other'];phases=['Input','Target','Body','Cleanup']
def quoted(value):return json.dumps(str(value),ensure_ascii=False).replace(chr(92)+'u0000',chr(92)+'u{0}')
def enum(value,typ,names,wanted):return 'branch on '+value+'{'+','.join(typ+'::'+name+'=>'+('true' if name==wanted else 'false') for name in names)+'}'
def checked_error(expression,ok,operation,kind,subject,phase):return 'branch on '+expression+'{Result<'+ok+',IoError>::Ok=>{assert false;},Result<'+ok+',IoError>::Err(error:IoError)=>{assert '+enum('error->operation','IoOperation',operations,operation)+';assert '+enum('error->kind','IoErrorKind',kinds,kind)+';assert '+enum('error->phase','IoErrorPhase',phases,phase)+';assert error->subject=='+quoted(subject)+';}};0'
def call(name,command,status=0,mask=0o022,diagnostic=False):
 result=subprocess.run(list(map(str,command)),capture_output=True,timeout=180,umask=mask);rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=result.returncode==status and result.stdout==b'' and (result.stderr!=b'' if diagnostic else result.stderr==b'')));(options.output/'results.json').write_text(json.dumps(dict(fixtures=fixtures,observations=rows),indent=2)+'\n');assert rows[-1]['passed'],rows[-1]
with tempfile.TemporaryDirectory(prefix='mgn-path-operations-') as temporary:
 work=Path(temporary)
 def fixture(name,body,stress=False,observe=None,mask=0o022,after=None,status=0):
  folder=options.output/name;folder.mkdir();source=folder/'input.mgn';source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};');image=folder/'program';fixtures[name]=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
  for verb in ('check','lower'):call(name+'-'+verb,[options.compiler,verb,source])
  call(name+'-build',[options.compiler,'build',source,'-o',image]);fixtures[name]['artifact_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
  for mode in ('native','stress') if stress else ('native',):
   command=[image] if mode=='native' else [sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',folder/'stress.json','--',image];call(name+'-'+mode,command,status,mask)
   if after:after()
  if observe:
   report=folder/'syscalls.json';call(name+'-observed',[sys.executable,Path(__file__).with_name('publication-observe.py'),'--report',report,image],status,mask);events=json.loads(report.read_text())['events'];observe(events)
   if after:after()
  assert hashlib.sha256(image.read_bytes()).hexdigest()==fixtures[name]['artifact_sha256'];return image
 def pure(events):assert not [event for event in events if event['call'] in (0,2,3,5,63,138,217,257,258,262,263,316,332)],events
 joins=[('content','page.txt'),('/','page.txt'),('content/','nested/a.txt'),('content//','./a.txt'),('content','../other'),('content','nested/'),('.','.././x//'),('missing','child'),('/does-not-exist','child'),('a\\b','c\\d'),('~','$HOME'),('-','*'),('//','a/b'),('日本語','é/é'),('x'*5000,'y'*5000)]
 for index,(base,relative) in enumerate(joins):
  wanted=base+('' if base.endswith('/') else '/')+relative;body='branch on joinPath('+quoted(base)+','+quoted(relative)+'){Result<String,IoError>::Ok(value:String)=>{assert value=='+quoted(wanted)+';assert value->length()=='+str(len(wanted))+';0},Result<String,IoError>::Err=>1}'
  fixture('join-'+str(index),body,stress=index in (0,12,13,14),observe=pure)
 for index,(base,relative,subject) in enumerate([('','x',''),('x','',''),('x','/absolute','/absolute'),('x','//','//'),('a'+chr(0),'b','a'+chr(0)),('a','b'+chr(0),'b'+chr(0)),('','/absolute','')]):fixture('join-invalid-'+str(index),checked_error('joinPath('+quoted(base)+','+quoted(relative)+')','String','JoinPath','InvalidPath',subject,'Input'),stress=True,observe=pure)
 fixture('join-return','joinPath({return 7;},"never")',stress=True,status=7)
 def creation(path,kind=None,phase='Target'):
  expression='createDirectory('+quoted(path)+')'
  return checked_error(expression,'Unit','CreateDirectory',kind,path,phase) if kind else 'branch on '+expression+'{Result<Unit,IoError>::Ok=>0,Result<Unit,IoError>::Err=>1}'
 def no_fd(events):assert not [event for event in events if event['call'] in (0,2,3,257)],events
 for mask in (0o022,0o077,0o111):
  target=work/('new-'+str(mask))
  def created(path=target,mode=0o777&~mask):assert path.is_dir() and stat.S_IMODE(path.stat().st_mode)==mode;(path).rmdir()
  fixture('create-mask-'+str(mask),creation(target),stress=True,observe=no_fd,mask=mask,after=created)
 existing=work/'existing';existing.mkdir();(existing/'kept').write_bytes(b'kept');existing.chmod(0o500);link=work/'link';link.symlink_to(existing)
 def unchanged(events):
  no_fd(events);assert not [event for event in events if event['call']==258],events
 for index,path in enumerate((existing,link,str(link)+'///',work,str(work)+'/./',str(work)+'/../'+work.name)):
  fixture('create-existing-'+str(index),creation(path),stress=True,observe=unchanged)
  assert existing.stat().st_mode&0o777==0o500 and (existing/'kept').read_bytes()==b'kept' and link.is_symlink()
 existing.chmod(0o700)
 file=work/'file';file.write_bytes(b'original');file.chmod(0o640);hard=work/'hard';os.link(file,hard);filelink=work/'file-link';filelink.symlink_to(file);dangling=work/'dangling';dangling.symlink_to(work/'absent');fifo=work/'fifo';os.mkfifo(fifo);sock=socket.socket(socket.AF_UNIX);sockpath=work/'socket';sock.bind(str(sockpath))
 try:
  failures=[(file,'UnsupportedTarget'),(hard,'UnsupportedTarget'),(filelink,'UnsupportedTarget'),(dangling,'UnsupportedTarget'),(fifo,'UnsupportedTarget'),(sockpath,'UnsupportedTarget'),(str(file)+'/','UnsupportedTarget'),(str(filelink)+'/','UnsupportedTarget'),(str(dangling)+'/','NotFound'),(work/'missing/child','NotFound'),(file/'child','UnsupportedTarget'),(dangling/'child','NotFound'),(work/('n'*256),'InvalidPath')]
  for index,(path,kind) in enumerate(failures):fixture('create-error-'+str(index),creation(path,kind),stress=True,observe=no_fd);assert file.read_bytes()==b'original' and stat.S_IMODE(file.stat().st_mode)==0o640 and dangling.is_symlink()
 finally:sock.close()
 for index,path in enumerate(('',str(work)+chr(0)+'bad')):fixture('create-invalid-'+str(index),creation(path,'InvalidPath','Input'),stress=True,observe=pure)
 acl=work/'acl';acl.mkdir();subprocess.run(['setfacl','-m','d:u::rwx,d:g::r-x,d:o::---',acl],check=True);target=acl/'created'
 def acl_created():assert stat.S_IMODE(target.stat().st_mode)==0o750;target.rmdir()
 fixture('create-default-acl',creation(target),stress=True,observe=no_fd,mask=0o077,after=acl_created)
 group=work/'setgid';group.mkdir();group.chmod(0o2770);group_target=group/'created'
 def group_created():assert group_target.stat().st_gid==group.stat().st_gid and stat.S_IMODE(group_target.stat().st_mode)==0o2755;group_target.rmdir()
 fixture('create-setgid',creation(group_target),stress=True,observe=no_fd,after=group_created)
 # Both source typing and invalid-source output preservation remain independent of native support.
 invalid=['joinPath(true,"x")','joinPath("x",List<String>[])','createDirectory(1)','createDirectory(List<String>[])']
 for index,expression in enumerate(invalid):
  folder=options.output/('invalid-'+str(index));folder.mkdir();source=folder/'input.mgn';source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{discard '+expression+';0};');image=folder/'program';image.write_bytes(b'preserved')
  for verb in ('check','lower','build'):call('invalid-'+str(index)+'-'+verb,[options.compiler,verb,source]+(['-o',image] if verb=='build' else []),1,diagnostic=True);assert image.read_bytes()==b'preserved'
(options.output/'summary.json').write_text(json.dumps(dict(fixtures=len(fixtures),observations=len(rows),compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest(),passed=True),indent=2)+'\n');print('V170_PATH_OPERATIONS_OK',len(fixtures),len(rows))
