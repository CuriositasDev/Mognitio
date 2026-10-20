#!/usr/bin/env python3
"""Observe nonrecursive directory values, order, kinds and failure subjects."""
import argparse,hashlib,json,os,re,socket,stat,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);rows=[];fixtures={}
prefix=r'namespace App;use Std\Io\{readDirectory,DirectoryEntry,DirectoryEntryKind,IoError,IoErrorKind,IoOperation,IoErrorPhase};';result_type='Result<List<DirectoryEntry>,IoError>'
def quoted(value):return re.sub(r'\\u([0-9a-fA-F]{4})',lambda match:chr(92)+'u{'+match[1]+'}',json.dumps(str(value),ensure_ascii=False))
def enum(value,typ,names,wanted):return 'branch on '+value+'{'+','.join(typ+'::'+name+'=>'+('true' if name==wanted else 'false') for name in names)+'}'
def checked_error(path,kind,phase='Target',subject=None):return 'branch on readDirectory('+quoted(path)+'){'+result_type+'::Ok=>{assert false;},'+result_type+'::Err(error:IoError)=>{assert error->subject=='+quoted(path if subject is None else subject)+';assert '+enum('error->kind','IoErrorKind',['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other'],kind)+';assert '+enum('error->operation','IoOperation',['ReadTextFile','WriteTextFile','ReadStdin','WriteStdout','WriteStderr','JoinPath','ReadDirectory','CreateDirectory'],'ReadDirectory')+';assert '+enum('error->phase','IoErrorPhase',['Input','Target','Body','Cleanup'],phase)+';}};0'
def list_body(path,expected):
 pairs=sorted(expected);names='List<String>['+','.join(quoted(name) for name,kind in pairs)+']';kinds='List<Int>['+','.join(str(kind) for name,kind in pairs)+']'
 def at(value):return 'branch on '+value+'->at(index){Result<'+('String' if value=='names' else 'Int')+',IndexError>::Ok(found:'+('String' if value=='names' else 'Int')+')=>found,Result<'+('String' if value=='names' else 'Int')+',IndexError>::Err=>panic{"missing expected entry"}}'
 return 'let entries:List<DirectoryEntry>=branch on readDirectory('+quoted(path)+'){'+result_type+'::Ok(value:List<DirectoryEntry>)=>value,'+result_type+'::Err=>panic{"unexpected directory error"}};let names:List<String>='+names+';let kinds:List<Int>='+kinds+';assert entries->length()==names->length();var index:Int=0;loop over(entries as entry:DirectoryEntry){let wanted:String='+at('names')+';assert entry->name==wanted;let kind:Int='+at('kinds')+';assert (branch on entry->kind{DirectoryEntryKind::File=>0,DirectoryEntryKind::Directory=>1,DirectoryEntryKind::Symlink=>2,DirectoryEntryKind::Other=>3})==kind;index=index+1;};assert index==names->length();0'
def call(name,command,status=0,diagnostic=False,out=b''):
 result=subprocess.run(list(map(str,command)),capture_output=True,timeout=300);rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=result.returncode==status and result.stdout==out and (bool(result.stderr) if diagnostic else result.stderr==b'')));(options.output/'results.json').write_text(json.dumps(dict(fixtures=fixtures,observations=rows),indent=2)+'\n');assert rows[-1]['passed'],rows[-1]
def snapshot(root):return sorted((os.fsencode(path.relative_to(root)),stat.S_IFMT(path.lstat().st_mode),stat.S_IMODE(path.lstat().st_mode),path.read_bytes() if path.is_file() and not path.is_symlink() else os.readlink(path) if path.is_symlink() else None) for path in root.rglob('*'))
with tempfile.TemporaryDirectory(prefix='mgn-directory-') as temporary:
 work=Path(temporary)
 def fixture(name,body,stress=True,observe=True,extra='',status=0,out=b''):
  folder=options.output/name;folder.mkdir();source=folder/'input.mgn';source.write_text(prefix+extra+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};');image=folder/'program';fixtures[name]=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
  for verb in ('check','lower'):call(name+'-'+verb,[options.compiler,verb,source])
  call(name+'-build',[options.compiler,'build',source,'-o',image]);fixtures[name]['artifact_sha256']=hashlib.sha256(image.read_bytes()).hexdigest();call(name+'-native',[image],status,out=out)
  if stress:call(name+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',folder/'stress.json','--',image],status,out=out)
  if observe:
   report=folder/'syscalls.json';call(name+'-observed',[sys.executable,Path(__file__).with_name('publication-observe.py'),'--report',report,image],status,out=out);events=json.loads(report.read_text())['events'];assert not [event for event in events if event['call'] in (0,2,258,263,316)],events
   opens=[event for event in events if event['call']==257];closes=[event for event in events if event['call']==3];assert len(opens)<=1 and len(closes)==sum(event['kernel_return']>=0 for event in opens),events
   for event in opens:assert event['arguments'][0]==(1<<64)-100 and event['arguments'][2]==589824 and event['arguments'][3]==0,event
   for event in [event for event in events if event['call']==217]:assert event['arguments'][2]==65536,event
   for event in [event for event in events if event['call']==262]:assert event['arguments'][0]<(1<<63) and event['arguments'][3]==256 and event['path'] not in ('.','..') and '/' not in event['path'],event
   assert events[-1]['owned']['record']==0
  assert hashlib.sha256(image.read_bytes()).hexdigest()==fixtures[name]['artifact_sha256']
 empty=work/'empty';empty.mkdir();fixture('empty',list_body(empty,[]))
 mixed=work/'mixed';mixed.mkdir();expected=[]
 names=['a','a.txt','aA','aé','b','.hidden','日本語','é','é','😀',chr(1),'line\nfeed','carriage\rreturn','tab\tname','-leading','a\\b']
 for name in names:(mixed/name).write_bytes(b'unchanged');expected.append((name,0))
 (mixed/'unreadable').write_bytes(b'unreadable');(mixed/'unreadable').chmod(0);expected.append(('unreadable',0));(mixed/'directory').mkdir();(mixed/'directory'/'grandchild').write_bytes(b'kept');expected.append(('directory',1));(mixed/'directory-link').symlink_to(mixed/'directory');expected.append(('directory-link',2));(mixed/'dangling').symlink_to(mixed/'absent');expected.append(('dangling',2));os.link(mixed/'a',mixed/'hardlink');expected.append(('hardlink',0));os.mkfifo(mixed/'fifo');expected.append(('fifo',3));sock=socket.socket(socket.AF_UNIX);sock.bind(str(mixed/'socket'));expected.append(('socket',3));root_link=work/'root-link';root_link.symlink_to(mixed)
 try:
  for index,path in enumerate((mixed,str(mixed)+'///',root_link,str(root_link)+'//',str(mixed)+'/./')):fixture('mixed-'+str(index),list_body(path,expected))
  # User-created values retain ordinary aggregate rules without API-name checks.
  fixture('constructed-value','let entry:DirectoryEntry=DirectoryEntry{name:"../synthetic",kind:DirectoryEntryKind::Other};assert entry->name=="../synthetic";0')
 finally:sock.close();(mixed/'unreadable').chmod(0o600)
 file=work/'file';file.write_bytes(b'kept');filelink=work/'file-link';filelink.symlink_to(file);dangling=work/'dangling';dangling.symlink_to(work/'absent')
 for index,(path,kind) in enumerate([(work/'absent','NotFound'),(file,'UnsupportedTarget'),(filelink,'UnsupportedTarget'),(dangling,'NotFound'),(file/'child','UnsupportedTarget'),(work/('n'*256),'InvalidPath')]):fixture('target-error-'+str(index),checked_error(path,kind))
 for index,path in enumerate(('',str(work)+chr(0)+'bad')):fixture('invalid-input-'+str(index),checked_error(path,'InvalidPath','Input'))
 restricted=work/'restricted';restricted.mkdir();restricted.chmod(0)
 try:fixture('root-permission',checked_error(restricted,'PermissionDenied'))
 finally:restricted.chmod(0o700)
 child_root=work/'children';child_root.mkdir();(child_root/'secret').write_bytes(b'kept');child_root.chmod(0o444)
 try:fixture('child-permission',checked_error(str(child_root)+'//','PermissionDenied','Body',str(child_root)+'//secret'))
 finally:child_root.chmod(0o700)
 bad=work/'invalid-name';bad.mkdir();raw=os.fsencode(bad)+b'/bad-\xff';fd=os.open(raw,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd);fixture('invalid-utf8-name',checked_error(bad,'InvalidEncoding','Body'));os.unlink(raw)
 fixture('argument-return','readDirectory({return 7;})',status=7)
 large=work/'large';large.mkdir();large_names=[('entry-'+str(index).zfill(5)+'-'+'x'*48,0) for index in range(2200)]
 for name,kind in reversed(large_names):(large/name).touch()
 # The host independently compares the full vector without a large source literal.
 body='let entries:List<DirectoryEntry>=branch on readDirectory('+quoted(large)+'){'+result_type+'::Ok(value:List<DirectoryEntry>)=>value,'+result_type+'::Err=>panic{"unexpected directory error"}};assert entries->length()==2200;loop over(entries as entry:DirectoryEntry){assert branch on entry->kind{DirectoryEntryKind::File=>true,DirectoryEntryKind::Directory=>false,DirectoryEntryKind::Symlink=>false,DirectoryEntryKind::Other=>false};discard writeStdout(entry->name);discard writeStdout('+quoted(chr(0))+');};0'
 expected_output=b''.join(name.encode()+bytes(1) for name,kind in sorted(large_names));fixture('multiple-chunks-growth-sort',body,stress=False,extra=r'use Std\Io\{writeStdout};',out=expected_output)
 for index,expression in enumerate(('readDirectory(1)','readDirectory(List<String>[])')):
  folder=options.output/('invalid-'+str(index));folder.mkdir();source=folder/'input.mgn';source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{discard '+expression+';0};');image=folder/'program';image.write_bytes(b'preserved')
  for verb in ('check','lower','build'):call('invalid-'+str(index)+'-'+verb,[options.compiler,verb,source]+(['-o',image] if verb=='build' else []),1,True);assert image.read_bytes()==b'preserved'
(options.output/'summary.json').write_text(json.dumps(dict(fixtures=len(fixtures),observations=len(rows),compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest(),passed=True),indent=2)+'\n');print('V170_DIRECTORY_OK',len(fixtures),len(rows))
