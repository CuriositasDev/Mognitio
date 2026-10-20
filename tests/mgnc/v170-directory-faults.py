#!/usr/bin/env python3
"""Replace raw directory records and kernel replies; observe owned cleanup."""
import argparse,hashlib,json,struct,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);observer=Path(__file__).with_name('publication-observe.py');rows=[];serial=0
prefix=r'namespace App;use Std\Io\{readDirectory,DirectoryEntry,DirectoryEntryKind,IoError,IoOperation,IoErrorKind,IoErrorPhase};';result_type='Result<List<DirectoryEntry>,IoError>';kinds=['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other']
def fault(call,value,after=False,ordinal=1):return dict(call=call,ordinal=ordinal,**{'return':value},after=after)
def record(name,dtype=0,inode=1,offset=0):
 length=(19+len(name)+1+7)//8*8;return struct.pack('<QqHB',inode,offset,length,dtype)+name+b'\0'+bytes(length-20-len(name))
def records(payload,count=None):return dict(call=217,action='directory_records',bytes_hex=payload.hex(),**({} if count is None else dict(reported_count=count)))
with tempfile.TemporaryDirectory(prefix='mgn-directory-fault-') as temporary:
 root=Path(temporary);file=root/'sample';file.write_bytes(b'unchanged');requested=str(root)+'//';image=options.output/'program'
 def compile(phase='Body',child=False,size=1,check_name=True):
  global serial
  serial+=1;source=options.output/('input-'+str(serial)+'.mgn');subject=requested+'sample' if child else requested
  body='branch on readDirectory('+json.dumps(requested)+'){'+result_type+'::Ok(entries:List<DirectoryEntry>)=>{assert entries->length()==1;var observed:Int= -1;loop over(entries as entry:DirectoryEntry){assert entry->name=="sample";observed=branch on entry->kind{DirectoryEntryKind::File=>0,DirectoryEntryKind::Directory=>1,DirectoryEntryKind::Symlink=>2,DirectoryEntryKind::Other=>3};};observed},'+result_type+'::Err(error:IoError)=>{assert error->subject=='+json.dumps(subject)+';assert branch on error->operation{'+','.join('IoOperation::'+name+'=>'+('true' if name=='ReadDirectory' else 'false') for name in ['ReadTextFile','WriteTextFile','ReadStdin','WriteStdout','WriteStderr','JoinPath','ReadDirectory','CreateDirectory'])+'};assert branch on error->phase{'+','.join('IoErrorPhase::'+name+'=>'+('true' if name==phase else 'false') for name in ['Input','Target','Body','Cleanup'])+'};20+(branch on error->kind{'+','.join('IoErrorKind::'+name+'=>'+str(index) for index,name in enumerate(kinds))+'})}}'
  body=body.replace('assert entries->length()==1;','assert entries->length()=='+str(size)+';').replace('assert entry->name=="sample";','assert entry->name=="sample";' if check_name else '')
  source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};');image.unlink(missing_ok=True);result=subprocess.run([options.compiler,'build',source,'-o',image],capture_output=True,timeout=180);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(result.returncode,result.stderr)
 def run(name,rules,status=0,stderr=b'',stats=None,removed=False):
  report=options.output/(name+'.json');result=subprocess.run([sys.executable,observer,'--report',report,'--rules',json.dumps(rules),image],capture_output=True,timeout=60);assert (result.returncode,result.stdout,result.stderr)==(status,b'',stderr),(name,status,result.returncode,result.stdout,result.stderr)
  events=json.loads(report.read_text())['events'];assert not [event for event in events if event['call'] in (0,2,258,263,316)],(name,events);opens=[event for event in events if event['call']==257 and event['kernel_return']>=0 and event.get('reported_return',event['kernel_return'])>=0];closes=[event for event in events if event['call']==3];assert len(closes)==len(opens),(name,'fd released other than once',events)
  if stats is not None:assert len([event for event in events if event['call']==262])==stats,(name,'child stat count',events)
  if closes:assert not [event for event in events[events.index(closes[-1])+1:] if event['call'] in (217,262)],(name,'filesystem observation after close')
  for event in [event for event in events if event['call']==11]:assert event['owned']['record']!=0 or stderr,(name,'scratch ownership lost before release')
  active={};boot=set()
  for event in events:
   if event['call']==9 and event['kernel_return']>0:
    address=event['kernel_return'];assert address not in active;active[address]=event['arguments'][1]
    if event['ordinal']<=2:boot.add(address)
   if event['call']==11 and event['kernel_return']==0:assert active.pop(event['arguments'][0])==event['arguments'][1],(name,'mapping generation or release size',event)
  assert set(active)==boot,(name,'scratch mapping retained',active,boot)
  exit_event=events[-1];assert exit_event['call']==60 and exit_event['owned']['record']==0 and exit_event['owned']['primary']==(1 if status==4 else 2 if status==3 else 0),exit_event
  assert not [value for value in exit_event['fds'].values() if str(root) in value],exit_event
  if stderr:
   diagnostic=next(index for index,event in enumerate(events) if event['call']==1 and event['arguments'][0]==2);assert not [event for event in events[diagnostic+1:] if event['call'] in (3,11)],(name,'cleanup after reporting')
  if removed:assert not file.exists();file.write_bytes(b'unchanged')
  else:assert file.read_bytes()==b'unchanged'
  rows.append(dict(case=name,exit=status,syscalls=len(events),source=serial,artifact_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),passed=True));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(name,'PASS',status,flush=True);return events
 internal=b'internal error: native runtime invariant\n';allocation=b'runtime error: allocation failure\n';compile('Target');run('success',[])
 errno_kinds=[(36,0),(2,2),(1,3),(13,3),(30,3),(20,4),(21,4),(12,6),(23,6),(24,6),(28,6),(122,6),(31,6),(5,7),(38,7),(40,7),(95,7),(32,7)]
 for error,kind in errno_kinds:run('open-'+str(error),[fault(257,-error)],20+kind,stats=0)
 run('open-eintr',[fault(257,-4)])
 for value in (-9,-14,-5000):run('open-internal-'+str(value),[fault(257,value)],3,internal,stats=0)
 compile('Body')
 for error,kind in errno_kinds:
  if error!=20:run('scan-'+str(error),[fault(217,-error)],20+kind,stats=0)
 run('scan-eintr',[fault(217,-4)])
 for value in (-9,-14,-20,-22,-5000):run('scan-internal-'+str(value),[fault(217,value)],3,internal,stats=0)
 valid=record(b'sample');malformed=[('count-over',valid,65537),('short-header',valid,19),('zero-reclen',valid[:16]+bytes(2)+valid[18:],None),('short-reclen',valid[:16]+struct.pack('<H',16)+valid[18:],None),('unaligned-reclen',valid[:16]+struct.pack('<H',25)+valid[18:],None),('past-end',valid[:16]+struct.pack('<H',65528)+valid[18:],None),('missing-nul',valid[:19]+b'x'*(len(valid)-19),None),('empty',record(b''),None),('slash',record(b'a/b'),None)]
 for name,payload,count in malformed:run('record-'+name,[records(payload,count)],3,internal,stats=0)
 for index,raw in enumerate([b'bad-\xff',b'bad-\xc0\x80',b'bad-\xed\xa0\x80',b'bad-\xf4\x90\x80\x80',b'bad-\xe2\x82',b'bad-\x80']):run('invalid-utf8-'+str(index),[records(record(raw))],21,stats=0)
 run('dtype-inode-offset-ignored',[records(record(b'sample',255,0,-1))])
 run('duplicates-first-file',[records(valid+valid),dict(call=262,ordinal=2,action='stat_mode',mode=0o40755)])
 run('duplicates-first-directory',[records(valid+valid),dict(call=262,ordinal=1,action='stat_mode',mode=0o40755)],1)
 # Even a duplicate is decoded and classified before deduplication.
 run('duplicate-invalid-encoding',[records(valid+record(b'bad-\xff'))],21,stats=1)
 compile('Body',True)
 for error,kind in errno_kinds:
  if error!=20:run('child-'+str(error),[fault(262,-error)],20+kind,stats=1)
 run('child-eintr',[fault(262,-4)])
 for value in (-9,-14,-20,-22,-5000,1):run('child-internal-'+str(value),[fault(262,value)],3,internal,stats=1)
 run('duplicate-later-failure',[records(valid+valid),fault(262,-2,ordinal=2)],22,stats=2)
 run('removed-after-enumeration',[dict(call=217,action='unlink_after_scan',name='sample')],22,stats=1,removed=True)
 run('child-primary-cleanup-secondary',[fault(262,-13),fault(11,-5,True)],23)
 run('child-primary-internal-secondary',[fault(262,-13),fault(11,-14,True)],3,internal)
 compile('Cleanup')
 for error,kind in [(5,7),(4,7),(13,3),(12,6)]:run('close-'+str(error),[fault(3,-error,True)],20+kind)
 for value in (-9,-5000,1):run('close-internal-'+str(value),[fault(3,value,True)],3,internal)
 run('unmap-external',[fault(11,-5,True)],27)
 for value in (-14,-22,-5000,1):run('unmap-internal-'+str(value),[fault(11,value,True)],3,internal)
 run('external-then-internal-unmap',[fault(11,-5,True),fault(11,-14,True,ordinal=2)],3,internal)
 compile()
 run('values-survive-entry-removal-at-close',[dict(call=3,action='unlink_after_close',name='sample')],removed=True)
 run('materialization-allocation-failure',[dict(call=3,allocation_failure=True)],4,allocation)
 run('allocation-primary-internal-cleanup-secondary',[dict(call=3,allocation_failure=True),fault(11,-14,True)],4,allocation)
 for ordinal in (3,4,5,6):run('map-allocation-'+str(ordinal),[fault(9,-12,ordinal=ordinal)],4,allocation)
 for value in (0,1,4095,-4096,-22):run('map-internal-'+str(value),[fault(9,value,ordinal=4)],3,internal)
 # Fail both staging growth regions while their old mappings remain owned.
 for index in range(40):(root/('long-name-'+str(index).zfill(3)+'-'+'x'*80)).write_bytes(b'kept')
 compile(size=41,check_name=False);baseline=run('growth-baseline',[]);close=next(index for index,event in enumerate(baseline) if event['call']==3);growing=[event for event in baseline[:close] if event['call']==9 and event['arguments'][1] in (2048,1280)];assert len(growing)==2,growing
 for event in growing:run('growth-map-failure-'+str(event['arguments'][1]),[fault(9,-12,ordinal=event['ordinal'])],4,allocation)
 run('growth-release-external',[fault(11,-5,True)],27)
 run('growth-release-internal',[fault(11,-14,True)],3,internal)
(options.output/'summary.json').write_text(json.dumps(dict(cases=len(rows),passed=True,compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest()),indent=2)+'\n');print('V170_DIRECTORY_RAW_FAULTS_OK',len(rows))
