#!/usr/bin/env python3
"""Inject raw creation replies without replacing typed runtime outcomes."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);observer=Path(__file__).with_name('publication-observe.py');rows=[]
names=['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other'];prefix=r'namespace App;use Std\Io\{createDirectory,IoError,IoOperation,IoErrorKind,IoErrorPhase};'
def fault(call,value,after=False,ordinal=1):return dict(call=call,ordinal=ordinal,**{'return':value},after=after)
with tempfile.TemporaryDirectory(prefix='mgn-create-fault-') as temporary:
 parent=Path(temporary);existing=parent/'existing';existing.mkdir();target=existing;source=options.output/'input.mgn';image=options.output/'program'
 def compile(phase='Target'):
  body='branch on createDirectory('+json.dumps(str(target))+'){Result<Unit,IoError>::Ok=>0,Result<Unit,IoError>::Err(error:IoError)=>{assert error->subject=='+json.dumps(str(target))+';assert branch on error->operation{'+','.join('IoOperation::'+name+'=>'+('true' if name=='CreateDirectory' else 'false') for name in ['ReadTextFile','WriteTextFile','ReadStdin','WriteStdout','WriteStderr','JoinPath','ReadDirectory','CreateDirectory'])+'};assert branch on error->phase{'+','.join('IoErrorPhase::'+name+'=>'+('true' if name==phase else 'false') for name in ['Input','Target','Body','Cleanup'])+'};20+(branch on error->kind{'+','.join('IoErrorKind::'+name+'=>'+str(index) for index,name in enumerate(names))+'})}}'
  source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};');image.unlink(missing_ok=True);result=subprocess.run([options.compiler,'build',source,'-o',image],capture_output=True,timeout=180);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(result.returncode,result.stderr)
 def run(name,rules,status=0,stderr=b'',cleanup=1,stats=None,mkdir=None):
  report=options.output/(name+'.json');result=subprocess.run([sys.executable,observer,'--report',report,'--rules',json.dumps(rules),image],capture_output=True,timeout=30);assert (result.returncode,result.stdout,result.stderr)==(status,b'',stderr),(name,status,result.returncode,result.stdout,result.stderr)
  events=json.loads(report.read_text())['events'];assert not [event for event in events if event['call'] in (0,2,3,257,263,316)],(name,'unexpected descriptor or rollback operation',events)
  assert len([event for event in events if event['call']==11])==cleanup,(name,'scratch release count',events)
  if stats is not None:assert len([event for event in events if event['call']==262])==stats,(name,'stat count',events)
  if mkdir is not None:assert len([event for event in events if event['call']==258])==mkdir,(name,'mkdir count',events)
  for event in [event for event in events if event['call'] in (262,258)]:assert event['arguments'][0]==(1<<64)-100 and event['owned']['record'] and event['owned']['fd']==-1,event
  for event in [event for event in events if event['call']==258]:assert event['arguments'][2]==0o777,event
  exit_event=events[-1];assert exit_event['call']==60 and exit_event['owned']['record']==0 and exit_event['owned']['primary']==(1 if status==4 else 2 if status==3 else 0),exit_event
  if stderr:
   diagnostic=next(index for index,event in enumerate(events) if event['call']==1 and event['arguments'][0]==2);assert not [event for event in events[diagnostic+1:] if event['call'] in (3,11)],(name,'cleanup after reporting')
  assert existing.is_dir();rows.append(dict(case=name,exit=status,syscalls=len(events),passed=True));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(name,'PASS',status,flush=True)
 internal=b'internal error: native runtime invariant\n';allocation=b'runtime error: allocation failure\n'
 compile();run('existing',[],stats=1,mkdir=0)
 errors=[(36,0),(2,2),(1,3),(13,3),(30,3),(20,4),(21,4),(12,6),(23,6),(24,6),(28,6),(122,6),(31,6),(5,7),(38,7),(40,7),(95,7),(32,7)]
 for error,kind in errors:
  if error!=2:run('stat-'+str(error),[fault(262,-error)],20+kind,stats=1,mkdir=0)
 run('stat-eintr',[fault(262,-4)],stats=2,mkdir=0)
 for value in (-9,-14,-22,-5000,1):run('stat-internal-'+str(value),[fault(262,value)],3,internal,stats=1,mkdir=0)
 # A real collision is rechecked, including a dangling link and trailing slash.
 run('mkdir-existing-race',[fault(262,-2)],stats=2,mkdir=1)
 for error,kind in errors:
  if error not in (2,):run('mkdir-'+str(error),[fault(262,-2),fault(258,-error)],20+kind,stats=1,mkdir=1)
 run('mkdir-eintr',[fault(262,-2),fault(258,-4)],stats=2,mkdir=2)
 for value in (-9,-14,-5000,1):run('mkdir-internal-'+str(value),[fault(262,-2),fault(258,value)],3,internal,stats=1,mkdir=1)
 run('primary-with-cleanup-secondary',[fault(262,-13),fault(11,-5,True)],23)
 for value in (-9,-14,-22,-5000,1):run('cleanup-internal-'+str(value),[fault(11,value,True)],3,internal)
 compile('Cleanup');run('cleanup-error',[fault(11,-5,True)],27)
 compile();run('result-allocation-after-release',[{'call':11,'allocation_failure':True}],4,allocation)
 for value in (0,1,4095,-4096,-(1<<63),-22):run('scratch-internal-'+str(value),[fault(9,value,ordinal=3)],3,internal,cleanup=0,stats=0,mkdir=0)
 for value in (-4,-5,-12):run('scratch-allocation-'+str(value),[fault(9,value,ordinal=3)],4,allocation,cleanup=0,stats=0,mkdir=0)
 target=parent/'new';compile();run('new-created',[],stats=1,mkdir=1);assert target.is_dir();target.rmdir()
 compile('Cleanup');run('created-before-cleanup-error',[fault(11,-5,True)],27,stats=1,mkdir=1);assert target.is_dir();target.rmdir()
 compile();run('created-before-result-allocation-failure',[{'call':11,'allocation_failure':True}],4,allocation,stats=1,mkdir=1);assert target.is_dir();target.rmdir()
 run('mkdir-notfound',[fault(258,-2)],22,stats=1,mkdir=1);assert not target.exists()
 run('mkdir-invalid',[fault(258,-22)],27,stats=1,mkdir=1);assert not target.exists()
 # Existing dangling links require the nofollow recheck; the link is preserved.
 target=parent/'dangling';target.symlink_to(parent/'missing');compile();run('dangling',[],24,stats=3,mkdir=1);assert target.is_symlink()
 run('nofollow-eintr',[fault(262,-4,ordinal=3)],24,stats=4,mkdir=1)
 for value in (-9,-14,-22,-5000,1):run('nofollow-internal-'+str(value),[fault(262,value,ordinal=3)],3,internal,stats=3,mkdir=1)
 target=str(target)+'/';compile();run('dangling-slash',[],22,stats=2,mkdir=1)
(options.output/'summary.json').write_text(json.dumps(dict(cases=len(rows),passed=True,compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest()),indent=2)+'\n');print('V170_PATH_RAW_FAULTS_OK',len(rows))
