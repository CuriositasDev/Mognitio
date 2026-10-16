#!/usr/bin/env python3
"""Observe generated instruction events and heap state without changing algorithms."""
import argparse,ctypes,importlib.util,json,os,signal,struct,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location("fault",Path(__file__).with_name("syscall-fault.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=argparse.ArgumentParser();p.add_argument("--report",type=Path,required=True);p.add_argument("--stress",action="store_true");p.add_argument("--markers",action="store_true");p.add_argument("command",nargs=argparse.REMAINDER);a=p.parse_args()
command=a.command[1:] if a.command[0]=="--" else a.command
pid=os.fork()
if pid==0:
 m.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(command[0],command)
os.waitpid(pid,0);m.ptrace(0x4200,pid,0,ctypes.c_void_p(1))
entering=True;executed=False;mem=None;events={};totals={};heap={};stress=False;context=None;high={"mapped":0,"live":0,"fds":0};start=time.monotonic()
def read(addr,n):
 try:return os.pread(mem,n,addr)
 except (OSError,TypeError):return b""
def word(addr):
 b=read(addr,8);return struct.unpack("<Q",b)[0] if len(b)==8 else None
def sample(ctx):
 global heap
 if not ctx:return
 data=read(ctx,224)
 if len(data)!=224:return
 values=struct.unpack("<28Q",data)
 if values[27]<4096:return
 heap={name:values[i] for name,i in {"mapped":3,"allocations":4,"collections":5,"live":6,"root":0,"resources":21,"primary":22}.items()}
 high["mapped"]=max(high["mapped"],heap["mapped"]);high["live"]=max(high["live"],heap["live"])
 high["fds"]=max(high["fds"],len(list(Path(f"/proc/{pid}/fd").iterdir())))
try:
 while True:
  m.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):
   result=os.WEXITSTATUS(status);break
  assert not os.WIFSIGNALED(status),("signal",os.WTERMSIG(status))
  stop=os.WSTOPSIG(status)
  r=m.Registers();m.ptrace(12,pid,0,ctypes.byref(r))
  if stop==signal.SIGTRAP:
   if not executed:executed=True;mem=os.open(f"/proc/{pid}/mem",os.O_RDWR);continue
   assert a.markers,("unexpected trap",r.rip)
   event=read(r.rip,1)[0];assert 1<=event<=13,event
   events[event]=events.get(event,0)+1
   amount=r.rcx if event in (8,13) else 1
   totals[event]=totals.get(event,0)+amount
   r.rip+=1;m.ptrace(13,pid,0,ctypes.byref(r));sample(r.r15)
   continue
  assert stop==(signal.SIGTRAP|0x80),stop
  if entering:
   sample(r.r15)
   if a.stress and not stress and heap:
    os.pwrite(mem,struct.pack("<Q",1),r.r15+152);stress=True
  entering=not entering
 if a.stress:assert stress,"stress context never reached"
 a.report.write_text(json.dumps({"exit":result,"events":events,"totals":totals,"heap":heap,"high":high,"stress":stress,"seconds":time.monotonic()-start},indent=2)+"\n")
 sys.exit(result)
finally:
 if mem is not None:os.close(mem)
 try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
 except (ProcessLookupError,ChildProcessError):pass
