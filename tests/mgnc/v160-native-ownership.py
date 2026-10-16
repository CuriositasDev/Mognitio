import ctypes,os,sys,signal,struct,json,re,subprocess,importlib.util
from pathlib import Path
module=Path(__file__).with_name("syscall-fault.py")
spec=importlib.util.spec_from_file_location("fault",module);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
parser=m.argparse.ArgumentParser();parser.add_argument("--mode",required=True);parser.add_argument("--secondary",default="");parser.add_argument("--reuse",action="store_true");parser.add_argument("--report",required=True);parser.add_argument("program");parser.add_argument("path");a=parser.parse_args()
pid=os.fork()
if pid==0:
 m.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(a.program,[a.program,a.path])
os.waitpid(pid,0);m.ptrace(0x4200,pid,0,ctypes.c_void_p(1))
mem=None;breakpoints={};entering=True;exec_seen=False;events=[];injected=False;secondary_done=False;pending=None;reused=None;maps_seen=0
def regs():
 r=m.Registers();m.ptrace(12,pid,0,ctypes.byref(r));return r
def setregs(r):m.ptrace(13,pid,0,ctypes.byref(r))
def read(address,n):
 if mem is None:return b""
 try:return os.pread(mem,n,address)
 except OSError:return b""
def word(address):
 b=read(address,8);return struct.unpack("<Q",b)[0] if len(b)==8 else 0
def write(address,value):assert os.pwrite(mem,struct.pack("<Q",value%(1<<64)),address)==8
def snapshot(r):
 ctx=r.r15
 if not ctx or not read(ctx,256):return None
 rec=word(ctx+168)
 if not rec:return None
 w=[word(rec+i*8) for i in range(24)]
 return {"record":rec,"fd":w[1] if w[1]<(1<<63) else -1,"maps":[w[i] for i in (2,4,6)],"sizes":[w[i] for i in (3,5,7)],"state":w[12],"site":w[14],"primary":word(ctx+176)}
def fds():
 result={}
 for entry in Path(f"/proc/{pid}/fd").iterdir():
  try:result[int(entry.name)]=os.readlink(entry)
  except FileNotFoundError:pass
 return result
def setup_breakpoints():
 site=int(a.mode[4:])
 data=Path(a.program).read_bytes();pattern=b"\x48\xb8"+struct.pack("<Q",site)+b"\x48\x89\x83\x70\0\0\0"
 offsets=[match.start() for match in re.finditer(re.escape(pattern),data)]
 assert offsets,(a.mode,"no materialization site")
 for off in offsets:
  address=0x400000+off;old=read(address,8);assert len(old)==8
  breakpoints[address]=old;os.pwrite(mem,b"\xcc"+old[1:],address)
try:
 while True:
  m.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):
   assert injected and (not a.secondary or secondary_done)
   assert os.WEXITSTATUS(status)==4,os.WEXITSTATUS(status)
   break
  assert not os.WIFSIGNALED(status),("signal",os.WTERMSIG(status))
  stop=os.WSTOPSIG(status);r=regs()
  if stop==signal.SIGTRAP:
   if not exec_seen:
    exec_seen=True;mem=os.open(f"/proc/{pid}/mem",os.O_RDWR)
    if a.mode.startswith("site"):setup_breakpoints()
    continue
   address=r.rip-1
   assert address in breakpoints,("unexpected trap",hex(address))
   for target,old in breakpoints.items():os.pwrite(mem,old,target)
   r.rip=address;setregs(r)
   owned=snapshot(r);assert owned is not None
   if a.reuse:
    assert owned["fd"]==-1 and owned["state"]==2
    path=word(owned["record"]+16);assert path
    saved=m.Registers.from_buffer_copy(r);old=read(address,8)
    os.pwrite(mem,b"\x0f\x05\xcc"+old[3:],address)
    r.rax=2;r.rdi=path;r.rsi=0;r.rdx=0;setregs(r)
    m.ptrace(7,pid,0,ctypes.c_void_p(0));_,inner=os.waitpid(pid,0)
    assert os.WIFSTOPPED(inner) and os.WSTOPSIG(inner)==signal.SIGTRAP
    got=regs();assert got.rax<(1<<63);reused=got.rax
    os.pwrite(mem,old,address);r=saved;setregs(r)
    events.append({"kind":"reuse","fd":reused})
   write(r.r15+160,word(r.r15+32)+1);injected=True
   events.append({"kind":"allocation-site","site":int(a.mode[4:]),"owned":owned})
   continue
  assert stop==(signal.SIGTRAP|0x80),stop
  if entering:
   pending=None;call=r.orig_rax;owned=snapshot(r)
   if call in (2,3,9,11,1,60):
    events.append({"kind":"enter","call":call,"fd":r.rdi if call in (1,2,3) else None,"address":r.rdi if call==11 else None,"size":r.rsi if call==11 else None,"owned":owned,"primary":word(r.r15+176) if r.r15 and read(r.r15,256) else 0,"fds":list(fds())})
   inject=False
   if call==9 and owned and owned["site"]==2 and not injected and not a.mode.startswith("site"):
    maps_seen+=1;inject=maps_seen==(1 if a.mode=="first-buffer" else 2)
    if inject:
     events.append({"kind":"allocation-site","site":2,"owned":owned});injected=True
   issecondary=injected and not secondary_done and ((a.secondary=="close" and call==3) or (a.secondary=="munmap" and call==11))
   if inject:
    pending=("allocation",12,False);r.orig_rax=(1<<64)-1;setregs(r)
   elif issecondary:
    # The OS release runs, but the reported result fails. Its real effect and
    # the source primary are both observable independently.
    pending=("secondary",5,True);secondary_done=True
   if call==60:
    current=fds()
    if reused is not None:assert reused in current,("reused fd was closed",events)
    else:assert not [fd for fd,target in current.items() if target==a.path],("owned fd leaked",events)
    diagnostics=[i for i,e in enumerate(events) if e["kind"]=="enter" and e["call"]==1 and e["fd"]==2]
    assert diagnostics
    first=diagnostics[0]
    assert not [e for e in events[first+1:] if e["kind"]=="enter" and e["call"] in (3,11)],"cleanup followed terminal reporting"
    close_events=[e for e in events if e["kind"]=="enter" and e["call"]==3]
    assert len(close_events)==1,("double or missing close",close_events)
    fault=next(i for i,e in enumerate(events) if e["kind"]=="allocation-site")
    terminal=[e for e in events[fault+1:] if e["kind"]=="enter" and e["call"] in (3,11)]
    assert all(e["primary"]==1 for e in terminal),("primary changed",terminal)
    owned=events[fault]["owned"]
    for address,size in zip(owned["maps"],owned["sizes"]):
     if address:
      matching=[e for e in terminal if e["call"]==11 and e["address"]==address and e["size"]==size]
      assert len(matching)==1,("missing or repeated scratch release",address,size,matching)

  elif pending:
   kind,error,after=pending
   if after:assert r.rax==0,("real cleanup failed",r.rax)
   r.rax=(-error)%(1<<64);setregs(r);events.append({"kind":kind+"-injected"})
  entering=not entering
 Path(a.report).write_text(json.dumps({"mode":a.mode,"secondary":a.secondary,"reuse":a.reuse,"events":events},indent=2)+"\n")
finally:
 if mem is not None:os.close(mem)
 try:os.kill(pid,signal.SIGKILL)
 except ProcessLookupError:pass
