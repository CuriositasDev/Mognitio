#!/usr/bin/env python3
"""Observe real publication syscalls and replace selected raw kernel replies."""
import argparse,ctypes,importlib.util,json,os,signal,struct
from pathlib import Path
spec=importlib.util.spec_from_file_location("syscall_fault",Path(__file__).with_name("syscall-fault.py"))
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
parser=argparse.ArgumentParser();parser.add_argument("--report",type=Path,required=True);parser.add_argument("--rules",default="[]");parser.add_argument("program",type=Path)
options=parser.parse_args();rules=json.loads(options.rules);events=[];counts={};pending=[];mem=None;entering=True;started=False
pid=os.fork()
if pid==0:
 api.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(str(options.program),[str(options.program)])
os.waitpid(pid,0);api.ptrace(0x4200,pid,0,ctypes.c_void_p(1))
def read(address,count):
 try:return os.pread(mem,count,address) if mem is not None and address else b""
 except OSError:return b""
def word(address):
 data=read(address,8);return struct.unpack("<Q",data)[0] if len(data)==8 else 0
def text(address):return read(address,4096).split(b"\0",1)[0].decode(errors="backslashreplace")
def signed(value):return value-(1<<64) if value>=1<<63 else value
def ownership(registers):
 context=registers.r15
 if not read(context,256):return None
 record=word(context+168)
 if not record:return {"record":0,"primary":word(context+176)}
 if signed(word(record+8))!=-2:return {"record":record,"tag":signed(word(record+8))}
 return {"record":record,"tag":-2,"parent":signed(word(record+16)),"file":signed(word(record+24)),"path_map":word(record+32),"path_size":word(record+40),"temp_owned":word(record+48),"temp_name":text(word(record+56)),"probe":signed(word(record+80)),"identity_known":word(record+88),"certified":word(record+112),"primary":word(context+176)}
def fds():
 result={}
 for path in Path(f"/proc/{pid}/fd").iterdir():
  try:result[path.name]=os.readlink(path)
  except FileNotFoundError:pass
 return result
try:
 while True:
  api.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):
   code=os.WEXITSTATUS(status);break
  assert not os.WIFSIGNALED(status),("signal",os.WTERMSIG(status))
  stop=os.WSTOPSIG(status)
  if stop==signal.SIGTRAP:
   assert not started;started=True;mem=os.open(f"/proc/{pid}/mem",os.O_RDWR);continue
  assert stop==signal.SIGTRAP|0x80,stop
  registers=api.Registers();api.ptrace(12,pid,0,ctypes.byref(registers))
  if entering:
   call=registers.orig_rax;counts[call]=counts.get(call,0)+1;pending=[]
   event={"call":call,"ordinal":counts[call],"arguments":[registers.rdi,registers.rsi,registers.rdx,registers.r10,registers.r8,registers.r9],"owned":ownership(registers)}
   if call in (257,262,263,332):event["path"]=text(registers.rsi)
   if call==316:event.update(source=text(registers.rsi),destination=text(registers.r10))
   if call==60:event["fds"]=fds()
   events.append(event)
   for index,rule in enumerate(rules):
    if call==rule["call"] and counts[call]==rule.get("ordinal",1):
     pending.append((index,rule));event.setdefault("rules",[]).append(index)
     if rule.get("action")=="replace_temp":
      parent=Path(os.readlink(f"/proc/{pid}/fd/{registers.rdi}"));original=parent/event["path"];retained=parent/"retained-original";original.rename(retained);original.write_bytes(b"foreign");event["replaced_temp"]={"foreign":str(original),"retained":str(retained)}
     elif rule.get("action")=="destination_file":
      parent=Path(os.readlink(f"/proc/{pid}/fd/{registers.rdx}"));destination=parent/event["destination"];destination.write_bytes(b"winner");event["created_destination"]=str(destination)

     if "limit" in rule:registers.rdx=min(registers.rdx,rule["limit"])
     elif not rule.get("after",False) and not rule.get("allocation_failure",False) and not rule.get("action"):registers.orig_rax=(1<<64)-1
   if pending:api.ptrace(13,pid,0,ctypes.byref(registers))
  else:
   event["kernel_return"]=signed(registers.rax)
   for index,rule in pending:
    if "limit" in rule:continue
    if rule.get("action"):
     if rule["action"]=="zero_random":
      assert signed(registers.rax)==16;assert os.pwrite(mem,bytes(16),event["arguments"][0])==16;event["controlled_random_hex"]=bytes(16).hex()
     continue

    if rule.get("allocation_failure",False):
     ordinal=word(registers.r15+32)+1;assert os.pwrite(mem,struct.pack("<Q",ordinal),registers.r15+160)==8;event["fail_allocation_ordinal"]=ordinal;continue
    if rule.get("after",False):assert signed(registers.rax)>=0,(index,event)
    registers.rax=rule["return"]%(1<<64);api.ptrace(13,pid,0,ctypes.byref(registers));event["reported_return"]=rule["return"]
  entering=not entering
 reached={index for event in events for index in event.get("rules",[])}
 assert reached==set(range(len(rules))),("unreached fault",reached,rules)
 options.report.write_text(json.dumps({"exit":code,"events":events,"rules":rules},indent=2)+"\n")
 raise SystemExit(code)
finally:
 if mem is not None:os.close(mem)
 try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
 except (ProcessLookupError,ChildProcessError):pass
