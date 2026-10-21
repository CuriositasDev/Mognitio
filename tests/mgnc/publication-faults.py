#!/usr/bin/env python3
"""Check publication classification from raw syscall observations."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument("--compiler",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
options=parser.parse_args();options.out.mkdir(parents=True,exist_ok=False)
observer=Path(__file__).with_name("publication-observe.py")
kinds=["InvalidPath","AlreadyExists","NotFound","PermissionDenied","UnsupportedTarget","ResourceExhausted","Other"]
phases=["Input","Target","Body","Publish","Cleanup"];states=["NotPublished","Published","Unknown"]
def enum(field,typ,names):return "branch on e->"+field+"{"+",".join(f"{typ}::{name}=>{i}" for i,name in enumerate(names))+"}"
def status(kind,phase,state):return 20+kinds.index(kind)*15+phases.index(phase)*3+states.index(state)
def fault(call,ordinal,value,after=False):return {"call":call,"ordinal":ordinal,"return":value,"after":after}
rows=[]
with tempfile.TemporaryDirectory(prefix="mgn-publication-fault-") as temporary:
 work=Path(temporary);target=work/"target";source=options.out/"input.mgn";image=options.out/"program"
 imports="namespace App;use Std\\Numeric\\{Bits};use Std\\Binary\\{bytesFromBits,publishFile,BinaryFileMode,BinaryOutputError,BinaryOutputErrorKind,BinaryOutputPhase,BinaryPublicationState};"
 def compile_target(path):
  body="branch on publishFile("+json.dumps(str(path))+",bytesFromBits(List<Bits<8>>[Bits<8>{0},Bits<8>{128},Bits<8>{255}]),BinaryFileMode::Data){Result<Unit,BinaryOutputError>::Ok(x:Unit)=>0,Result<Unit,BinaryOutputError>::Err(e:BinaryOutputError)=>20+("+enum("kind","BinaryOutputErrorKind",kinds)+")*15+("+enum("phase","BinaryOutputPhase",phases)+")*3+("+enum("publication","BinaryPublicationState",states)+")}"
  source.write_text(imports+"let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};")
  image.unlink(missing_ok=True)
  result=subprocess.run([options.compiler,"build",source,"-o",image],capture_output=True,timeout=180)
  assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(result.returncode,result.stderr)
 def run(name,rules,expected,published=False,certified=None,stderr=b'',payload=bytes([0,128,255]),replaced=False,retained_temp=False):
  target.unlink(missing_ok=True);before={p.name for p in target.parent.iterdir()};report=options.out/(name+".json")
  result=subprocess.run([sys.executable,observer,"--report",report,"--rules",json.dumps(rules),image],capture_output=True,timeout=30)
  assert (result.returncode,result.stdout,result.stderr)==(expected,b"",stderr),(name,expected,result.returncode,result.stdout,result.stderr)
  data=json.loads(report.read_text());events=data["events"];commits=[e for e in events if e["call"]==316]
  assert len(commits)<=1,(name,"commit retried",commits)
  for commit in commits:
   assert commit["arguments"][0]==commit["arguments"][2] and commit["arguments"][4]==1,commit
   assert commit["owned"]["file"]==-1 and commit["owned"]["temp_owned"]==1,commit
   if certified is not None:assert commit["owned"]["certified"]==certified,(name,commit)
  if commits:
   after=events[events.index(commits[0])+1:]
   assert not [e for e in after if e["call"]==262 and e.get("path")==target.name],(name,"queried destination after commit")
  assert target.exists()==published,(name,target.exists(),published)
  if published:assert target.read_bytes()==payload;target.unlink()
  if replaced:
   event=next(e for e in events if "replaced_temp" in e);foreign=Path(event["replaced_temp"]["foreign"]);retained=Path(event["replaced_temp"]["retained"]);assert foreign.read_bytes()==b"foreign";assert retained.stat().st_ino!=foreign.stat().st_ino;foreign.unlink();retained.unlink()
  if retained_temp:
   retained=[p for p in target.parent.iterdir() if p.name not in before]
   assert len(retained)==1 and retained[0].name.startswith('.mgn-') and retained[0].is_file() and not retained[0].is_symlink(),(name,'unverified private leaf',retained)
   assert retained[0].read_bytes()==payload and not [e for e in events if e['call']==263],(name,'unsafe identity cleanup')
   data['retained_private_leaf']={'name':retained[0].name,'bytes_hex':retained[0].read_bytes().hex(),'reason':'identity verification failed; no unverified unlink'}
   report.write_text(json.dumps(data,indent=2)+'\n');retained[0].unlink()
  assert {p.name for p in target.parent.iterdir()}==before,(name,"temporary leak",list(target.parent.iterdir()))
  for close in [e for e in events if e["call"]==3]:
   assert close["arguments"][0] not in [close["owned"].get(key,-1) for key in ("parent","file","probe")],(name,"released descriptor remains owned",close)
  acquired={};closed=set()
  for event in events:
   if event["call"]==257 and event.get("kernel_return",-1)>=0 and not event.get("rules"):acquired[event["kernel_return"]]=acquired.get(event["kernel_return"],0)+1
   if event["call"]==3:
    token=(event["arguments"][0],acquired.get(event["arguments"][0],0));assert token not in closed,(name,"descriptor generation closed twice",token);closed.add(token)
  exit_event=events[-1];assert exit_event["call"]==60 and exit_event["owned"]["record"]==0,exit_event
  assert not [v for v in exit_event["fds"].values() if str(target.parent) in v],exit_event
  assert exit_event["owned"]["primary"]==(1 if expected==4 else 2 if expected==3 else 0),(name,exit_event)
  if stderr:
   diagnostic=next(i for i,e in enumerate(events) if e["call"]==1 and e["arguments"][0]==2)
   assert not [e for e in events[diagnostic+1:] if e["call"] in (3,11,263)],(name,"cleanup after reporting")
   for event in events:
    if "fail_allocation_ordinal" in event and event["owned"].get("path_map",0):
     owned=event["owned"];released=[e for e in events[events.index(event)+1:] if e["call"]==11 and e["arguments"][:2]==[owned["path_map"],owned["path_size"]]]
     assert len(released)==1,(name,"terminal mapping cleanup",released)
   if name.startswith("temp-stat-internal"):
    assert len([e for e in events if e["call"]==263])==1,(name,"terminal temporary cleanup")

  rows.append({"case":name,"expected":expected,"published":published,"syscalls":len(events),"passed":True})
  (options.out/"results.json").write_text(json.dumps(rows,indent=2)+"\n")
  print(name,"PASS",expected,flush=True);return data
 compile_target(target)
 baseline=run("success",[],0,True,1)
 opens=[e for e in baseline["events"] if e["call"]==257];closes=[e for e in baseline["events"] if e["call"]==3]
 assert len(opens)==3 and len(closes)==3,baseline
 run("parent-open",[fault(257,1,-2)],status("NotFound","Target","NotPublished"))
 run("target-query",[fault(262,1,-13)],status("PermissionDenied","Target","NotPublished"))
 run("profile-fstatfs",[fault(138,1,-5)],0,True,0)
 run("profile-statx",[fault(332,1,-5)],0,True,0)
 run("profile-uname",[fault(63,1,-5)],0,True,0)
 run("profile-proc-open",[fault(257,2,-13)],0,True,0)
 run("profile-proc-read",[fault(0,1,-5)],0,True,0)
 run("profile-probe-close",[fault(3,1,-5,True)],status("Other","Cleanup","NotPublished"))
 run("temp-open",[fault(257,3,-28)],status("ResourceExhausted","Target","NotPublished"))
 run("temp-stat",[fault(5,1,-5)],status("Other","Target","NotPublished"))
 run("write-error",[fault(1,1,-28)],status("ResourceExhausted","Body","NotPublished"))
 run("write-zero",[fault(1,1,0)],status("Other","Body","NotPublished"))
 run("write-interrupted",[fault(1,1,-4)],0,True,1)
 run("write-short",[{"call":1,"ordinal":1,"limit":1}],0,True,1)
 for error in (4,5,28):run("file-close-"+str(error),[fault(3,2,-error,True)],status("ResourceExhausted" if error==28 else "Other","Cleanup","NotPublished"))
 for error,kind in [(1,"PermissionDenied"),(2,"NotFound"),(4,"Other"),(11,"Other"),(12,"ResourceExhausted"),(13,"PermissionDenied"),(16,"Other"),(17,"AlreadyExists"),(18,"UnsupportedTarget"),(20,"UnsupportedTarget"),(22,"UnsupportedTarget"),(28,"ResourceExhausted"),(30,"PermissionDenied"),(36,"Other"),(39,"AlreadyExists"),(40,"Other"),(95,"UnsupportedTarget"),(116,"Other"),(122,"ResourceExhausted"),(38,"UnsupportedTarget")]:
  run("commit-"+str(error),[fault(316,1,-error)],status(kind,"Publish","NotPublished"),False,1)
 run("commit-unknown",[fault(316,1,-5)],status("Other","Publish","Unknown"),False,1)
 run("commit-success-reply-lost",[fault(316,1,-5,True)],status("Other","Publish","Unknown"),True,1)
 for error in (4,5):run("parent-close-"+str(error),[fault(3,3,-error,True)],status("Other","Cleanup","Published"),True,1)
 run("preserve-primary",[fault(1,1,-28),fault(3,2,-5,True),fault(3,3,-5,True)],status("ResourceExhausted","Body","NotPublished"))
 run("uncertified-exists",[fault(138,1,-5),fault(316,1,-17)],status("AlreadyExists","Publish","Unknown"),False,0)
 run("uncertified-enosys",[fault(138,1,-5),fault(316,1,-38)],status("UnsupportedTarget","Publish","NotPublished"),False,0)
 run("uncertified-publish",[fault(138,1,-5)],0,True,0)
 run("destination-appears-at-commit",[{"call":316,"action":"destination_file"}],status("AlreadyExists","Publish","NotPublished"),True,1,payload=b"winner")
 run("cleanup-refuses-foreign-identity",[fault(1,1,-28),{"call":262,"ordinal":2,"action":"replace_temp"}],status("ResourceExhausted","Body","NotPublished"),replaced=True)
 run("temporary-name-collision",[{"call":318,"action":"zero_random"},fault(257,3,-17)],0,True,1)

 run("private-allocation-terminal",[{"call":3,"ordinal":1,"allocation_failure":True}],4,stderr=b"runtime error: allocation failure\n")
 run("private-allocation-secondary-close",[{"call":3,"ordinal":1,"allocation_failure":True},fault(3,2,-5,True)],4,stderr=b"runtime error: allocation failure\n")
 run("published-result-allocation-terminal",[{"call":3,"ordinal":3,"allocation_failure":True}],4,True,1,stderr=b"runtime error: allocation failure\n")
 run("temp-stat-internal",[fault(5,1,-9)],3,stderr=b"internal error: native runtime invariant\n")
 run("temp-stat-internal-secondary-close",[fault(5,1,-9),fault(3,2,-5,True)],3,stderr=b"internal error: native runtime invariant\n")

 # Domain failures override ordinary API errors; an active runtime failure
 # remains primary. Execute releases before replacing their replies so the
 # observation does not pretend that a skipped release reached the kernel.
 internal=b"internal error: native runtime invariant\n"
 for reply in (1,-9,-14,-22,-4096,-5000):
  suffix=str(reply)
  run("cleanup-unlink-internal-"+suffix,[fault(1,1,-28),fault(263,1,reply,True)],3,stderr=internal)
  run("cleanup-file-internal-"+suffix,[fault(1,1,-28),fault(3,2,reply,True)],3,stderr=internal)
  run("cleanup-parent-internal-"+suffix,[fault(1,1,-28),fault(3,3,reply,True)],3,stderr=internal)
  run("cleanup-name-stat-internal-"+suffix,[fault(1,1,-28),fault(262,2,reply,True)],3,stderr=internal,payload=b'',retained_temp=True)
  run("cleanup-identity-stat-internal-"+suffix,[fault(5,1,-5),fault(5,2,reply,True)],3,stderr=internal,payload=b'',retained_temp=True)
  run("cleanup-map-runtime-primary-"+suffix,[{"call":3,"ordinal":1,"allocation_failure":True},fault(11,1,reply,True)],4,stderr=b"runtime error: allocation failure\n")
 run("cleanup-unlink-external-primary",[fault(1,1,-28),fault(263,1,-5,True)],status("ResourceExhausted","Body","NotPublished"))
 run("cleanup-file-external-primary",[fault(1,1,-28),fault(3,2,-5,True)],status("ResourceExhausted","Body","NotPublished"))
 run("cleanup-name-stat-external-primary",[fault(1,1,-28),fault(262,2,-5,True)],status("ResourceExhausted","Body","NotPublished"),payload=b'',retained_temp=True)
 run("cleanup-identity-stat-external-primary",[fault(5,1,-5),fault(5,2,-5,True)],status("Other","Target","NotPublished"),payload=b'',retained_temp=True)

 # Controlled entropy makes the first temporary candidate equal the requested name.
 target=work/(".mgn-"+"0"*40);compile_target(target)
 run("requested-name-is-not-staging",[{"call":318,"action":"zero_random"}],0,True,1)
(options.out/"summary.json").write_text(json.dumps({"cases":len(rows),"passed":True,"compiler_sha256":hashlib.sha256(options.compiler.read_bytes()).hexdigest()},indent=2)+"\n")
print("MGNC_PUBLICATION_RAW_FAULTS_OK",len(rows))
