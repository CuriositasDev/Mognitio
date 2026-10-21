#!/usr/bin/env python3
"""Count executed byte-copy/comparison instructions inside fixed stdout markers.

The target is unchanged. Ptrace single-steps only the marked region and counts
the actual RCX consumption of REP MOVSB / REPE CMPSB, including early mismatch.
This is a functional structural observation, never a wall-time measurement.
"""
from pathlib import Path
import argparse,ctypes,hashlib,importlib.util,json,os,signal,struct,time,platform
p=argparse.ArgumentParser();p.add_argument('--timeout',type=float,default=180);p.add_argument('--repository',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();command=a.command[1:] if a.command and a.command[0]=='--' else a.command;assert command and 0<a.timeout<=180
spec=importlib.util.spec_from_file_location('ptrace_abi',a.repository/'tests/mgnc/syscall-fault.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert platform.system()=='Linux' and platform.machine()=='x86_64'
image=Path(command[0]);digest=hashlib.sha256(image.read_bytes()).hexdigest();stdout=a.report.with_suffix('.stdout');stderr=a.report.with_suffix('.stderr');assert not a.report.exists() and not stdout.exists() and not stderr.exists();started=time.monotonic();pid=os.fork()
if pid==0:
 os.setsid()
 with stdout.open('wb') as out,stderr.open('wb') as err:os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
 m.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(command[0],command)
alive=True;mem=None;entering=True;pending=None;active=False;begun=False;ended=False;steps=0;copied=0;compared=0;rep_copies=0;rep_compares=0;result=None;target_signal=None;failure=None;samples={};mode=24
def registers():
 r=m.Registers();m.ptrace(12,pid,0,ctypes.byref(r));return r
def read(address,count):
 return os.pread(mem,count,address)
def heap(r):
 if not r.r15:return {}
 try:
  raw=read(r.r15,224)
  if len(raw)!=224:return {}
  values=struct.unpack('<28Q',raw)
  if values[27]<4096:return {}
  return dict(mapped=values[3],allocations=values[4],collections=values[5],live=values[6])
 except OSError:return {}
def initial_wait(expected):
 global alive,result,target_signal
 _,status=os.waitpid(pid,0)
 if os.WIFEXITED(status):alive=False;result=os.WEXITSTATUS(status);raise RuntimeError('target exited before trace entry')
 if os.WIFSIGNALED(status):alive=False;target_signal=os.WTERMSIG(status);raise RuntimeError('target signaled before trace entry')
 assert os.WIFSTOPPED(status) and os.WSTOPSIG(status)==expected
def alarm(signum,frame):raise TimeoutError("observer wall guard")
signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,a.timeout)
try:
 initial_wait(signal.SIGSTOP);m.ptrace(0x4200,pid,0,ctypes.c_void_p(1|0x100000));m.ptrace(7,pid,0,ctypes.c_void_p(0));initial_wait(signal.SIGTRAP);mem=os.open('/proc/'+str(pid)+'/mem',os.O_RDONLY)
 while True:
  assert time.monotonic()-started<a.timeout,'observer wall guard';assert steps<4000000,'observer instruction guard'
  before=registers() if mode==9 else None;opcode=read(before.rip,2) if before is not None else b'';end_after_step=False
  if before is not None and opcode==b'\x0f\x05' and before.rax==1 and before.rdi==1 and before.rdx<=64:
   marker=read(before.rsi,before.rdx)
   if marker==b'COST_END\n':assert active and begun and not ended;end_after_step=True
  m.ptrace(mode,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):alive=False;result=os.WEXITSTATUS(status);break
  if os.WIFSIGNALED(status):target_signal=os.WTERMSIG(status);alive=False;raise AssertionError(('target signal',target_signal))
  stop=os.WSTOPSIG(status)
  if mode==9:
   assert stop==signal.SIGTRAP,('single-step stop',stop);after=registers();steps+=1
   if opcode in [b'\xf3\xa4',b'\xf3\xa6']:
    assert before.rcx<=1048576 and after.rcx<=before.rcx and after.rip in [before.rip,before.rip+2],('unexpected REP transition',before.rip,after.rip,before.rcx,after.rcx)
    consumed=before.rcx-after.rcx
    if opcode==b'\xf3\xa4':copied+=consumed;rep_copies+=int(consumed>0)
    else:compared+=consumed;rep_compares+=int(consumed>0)
   if end_after_step:
    assert after.rax==len(b'COST_END\n');samples['end']=heap(after);active=False;ended=True;mode=24;entering=True
   continue
  assert stop==(signal.SIGTRAP|0x80),('syscall stop',stop);r=registers()
  if entering:
   pending=None
   if r.orig_rax==1 and r.rdi==1 and r.rdx<=64:
    marker=read(r.rsi,r.rdx)
    if marker==b'COST_BEGIN\n':assert not begun and not ended;pending='begin'
  elif pending=='begin':
   assert r.rax==len(b'COST_BEGIN\n');begun=True;active=True;samples['begin']=heap(r);mode=9
  entering=not entering
 assert result==0 and begun and ended and not active,('incomplete region',result,begun,ended)
 assert stdout.read_bytes()==b'COST_BEGIN\nCOST_END\n' and not stderr.read_bytes()
 assert hashlib.sha256(image.read_bytes()).hexdigest()==digest,'target bytes changed'
except BaseException as error:
 failure=type(error).__name__+': '+str(error)
finally:
 signal.setitimer(signal.ITIMER_REAL,0)
 if alive:
  try:os.killpg(pid,signal.SIGKILL)
  except ProcessLookupError:pass
  os.waitpid(pid,0);alive=False
 if mem is not None:os.close(mem)
 record=dict(child_pid=pid,target_reaped=not alive,kind='instruction-stepped-structural-cost-not-performance',target_sha256=digest,command=command,exit=result,signal=target_signal,environment=dict(kernel=platform.release(),machine=platform.machine(),uid=os.getuid()),harness_failure=failure,region_complete=begun and ended,instruction_steps=steps,copied_bytes=copied,compared_bytes=compared,rep_copy_steps=rep_copies,rep_compare_steps=rep_compares,heap_samples=samples,seconds=time.monotonic()-started)
 a.report.write_text(json.dumps(record,indent=2)+'\n')
assert failure is None,failure
print('BYTES_STEP_OBSERVED copied='+str(copied)+' compared='+str(compared)+' steps='+str(steps))
