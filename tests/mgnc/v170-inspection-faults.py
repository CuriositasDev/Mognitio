#!/usr/bin/env python3
"""Check raw inspection/cleanup failures and all bits of opaque identity."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);observer=Path(__file__).with_name('publication-observe.py');rows=[]
names=['InvalidPath','InvalidEncoding','NotFound','PermissionDenied','UnsupportedTarget','BrokenPipe','ResourceExhausted','Other'];prefix=r'namespace App;use Std\Io\{inspectPath,PathInfo,PathInfoError,IoErrorKind};'
def fault(call,value,after=False,ordinal=1):return dict(call=call,ordinal=ordinal,**{'return':value},after=after)
with tempfile.TemporaryDirectory(prefix='mgn-inspection-fault-') as temporary:
 target=Path(temporary)/'file';target.write_bytes(b'unchanged');source=options.output/'input.mgn';image=options.output/'program'
 def compile(body):
  source.write_text(prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};');image.unlink(missing_ok=True);result=subprocess.run([options.compiler,'build',source,'-o',image],capture_output=True,timeout=180);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(result.returncode,result.stderr)
 def run(name,rules,status=0,stderr=b''):
  report=options.output/(name+'.json');result=subprocess.run([sys.executable,observer,'--report',report,'--rules',json.dumps(rules),image],capture_output=True,timeout=30);assert (result.returncode,result.stdout,result.stderr)==(status,b'',stderr),(name,status,result.returncode,result.stdout,result.stderr)
  events=json.loads(report.read_text())['events'];assert not [event for event in events if event['call'] in (0,2,3,257)],(name,'inspection acquired or closed a file descriptor',events)
  for event in [event for event in events if event['call']==262]:assert event['arguments'][0]==(1<<64)-100 and event['arguments'][3]==256,event
  assert len([event for event in events if event['call']==11])==1,(name,'scratch released other than once',events)
  for event in [event for event in events if event['call']==11]:
   assert event['owned']['record']!=0 or stderr,(name,'lost scratch ownership before cleanup')
  exit_event=events[-1];assert exit_event['call']==60 and exit_event['owned']['record']==0 and exit_event['owned']['primary']==(1 if status==4 else 2 if status==3 else 0),exit_event
  assert not [value for value in exit_event['fds'].values() if str(target.parent) in value],exit_event
  if stderr:
   diagnostic=next(index for index,event in enumerate(events) if event['call']==1 and event['arguments'][0]==2);assert not [event for event in events[diagnostic+1:] if event['call'] in (3,11)],(name,'cleanup after reporting')
  assert target.read_bytes()==b'unchanged';rows.append(dict(case=name,exit=status,syscalls=len(events),passed=True));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(name,'PASS',status,flush=True)
 body='branch on inspectPath('+json.dumps(str(target))+'){Result<PathInfo,PathInfoError>::Ok=>0,Result<PathInfo,PathInfoError>::Err(error:PathInfoError)=>{assert error->subject=='+json.dumps(str(target))+';20+(branch on error->kind{'+','.join('IoErrorKind::'+name+'=>'+str(index) for index,name in enumerate(names))+'})}}'
 compile(body);run('success',[])
 for error,kind in [(36,0),(2,2),(1,3),(13,3),(20,4),(95,4),(12,6),(23,6),(24,6),(28,6),(122,6),(5,7),(38,7),(40,7),(30,7),(32,7)]:run('stat-'+str(error),[fault(262,-error)],20+kind)
 run('stat-eintr',[fault(262,-4)])
 for error in (9,14,22,5000):run('stat-internal-'+str(error),[fault(262,-error)],3,b'internal error: native runtime invariant\n')
 run('stat-unexpected-positive',[fault(262,1)],3,b'internal error: native runtime invariant\n')
 run('cleanup-error',[fault(11,-5,True)],27)
 run('stat-primary-cleanup-secondary',[fault(262,-13),fault(11,-5,True)],23)
 for value in (-14,-22,-5000,1):run('cleanup-internal-'+str(value),[fault(11,value,True)],3,b'internal error: native runtime invariant\n')
 for name,rules in [('success-result-allocation',[{'call':11,'allocation_failure':True}]),('error-result-allocation',[fault(262,-13),{'call':11,'allocation_failure':True}])]:run(name,rules,4,b'runtime error: allocation failure\n')
 # Change only the raw successful stat buffer, never a preclassified language value.
 def observed():return 'branch on inspectPath('+json.dumps(str(target))+'){Result<PathInfo,PathInfoError>::Ok(value:PathInfo)=>value,Result<PathInfo,PathInfoError>::Err(error:PathInfoError)=>panic{"unexpected inspection error"}}'
 compile('let a:PathInfo='+observed()+';let b:PathInfo='+observed()+';assert (a->identity==b->identity)== !(a->identity!=b->identity);branch when{a->identity==b->identity=>0,else=>1}')
 for name,left,right,expected in [('all-word-bits',((1<<64)-1,1<<63),((1<<64)-1,1<<63),0),('device-low-bit',((1<<64)-1,1<<63),((1<<64)-2,1<<63),1),('inode-high-bit',((1<<64)-1,1<<63),((1<<64)-1,0),1)]:
  rules=[dict(call=262,ordinal=index+1,action='stat_words',dev=words[0],inode=words[1],stress=True) for index,words in enumerate((left,right))]
  # Two independent inspections each own and release one scratch mapping.
  report=options.output/(name+'.json');result=subprocess.run([sys.executable,observer,'--report',report,'--rules',json.dumps(rules),image],capture_output=True,timeout=30);assert (result.returncode,result.stdout,result.stderr)==(expected,b'',b''),(name,result.returncode,result.stderr)
  events=json.loads(report.read_text())['events'];assert len([event for event in events if event['call']==262])==2 and len([event for event in events if event['call']==11])==2;assert not [event for event in events if event['call'] in (0,2,3,257)];rows.append(dict(case=name,exit=expected,passed=True));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 # A retained observation remains usable after the last directory entry is removed.
 report=options.output/'retained-after-removal.json';rules=[dict(call=262,ordinal=2,action='unlink_after_stat')];result=subprocess.run([sys.executable,observer,'--report',report,'--rules',json.dumps(rules),image],capture_output=True,timeout=30);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(result.returncode,result.stderr);assert not target.exists();events=json.loads(report.read_text())['events'];assert len([event for event in events if event['call']==262])==2 and not [event for event in events if event['call'] in (0,2,3,257)];rows.append(dict(case='retained-after-removal',exit=0,passed=True));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
(options.output/'summary.json').write_text(json.dumps(dict(cases=len(rows),passed=True,compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest()),indent=2)+'\n');print('V170_INSPECTION_RAW_FAULTS_OK',len(rows))
