#!/usr/bin/env python3
"""Observe actual roots, reachable managed blocks, descriptors, and resources."""
from pathlib import Path
import argparse,ctypes,importlib.util,json,os,signal,struct,sys
parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);parser.add_argument('--stress',action='store_true');parser.add_argument('command',nargs=argparse.REMAINDER);a=parser.parse_args();command=a.command[1:];spec=importlib.util.spec_from_file_location('fault',Path(__file__).with_name("syscall-fault.py"));api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
pid=os.fork()
if pid==0:api.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(command[0],command)
os.waitpid(pid,0);api.ptrace(0x4200,pid,0,ctypes.c_void_p(1));mem=None;entering=True;executed=False;armed=False;snapshots=[];failure=None;result=None
image=Path(command[0]).read_bytes();assert image[:4]==b'\x7fELF'
phoff=struct.unpack_from('<Q',image,32)[0];phsize,phcount=struct.unpack_from('<HH',image,54);readonly=[]
for ordinal in range(phcount):
 kind,flags,offset,address,physical,filesize,memsize,alignment=struct.unpack_from('<II6Q',image,phoff+ordinal*phsize)
 if kind==1 and flags&4 and not flags&2:readonly.append((address,address+memsize))
assert readonly

# Observe each requested allocation at an unchanged allocator instruction.
# The software breakpoint is restored for one original mov instruction, then
# reinstalled. No allocation, collection, or root algorithm is substituted.
pattern=bytes.fromhex('4989fc4989f54981fc00000000');matches=[]
for ordinal in range(phcount):
 kind,flags,offset,address,physical,filesize,memsize,alignment=struct.unpack_from('<II6Q',image,phoff+ordinal*phsize)
 if kind==1 and flags&1:
  region=image[offset:offset+filesize];cursor=0
  while True:
   position=region.find(pattern,cursor)
   if position<0:break
   matches.append(address+position);cursor=position+1
assert len(matches)==1,('allocator observation point',matches)
allocation_point=matches[0];original_byte=None;allocation_observations=0;maximum_requested_allocation=0
def static_address(value):return any(start<=value<end for start,end in readonly)

def read(address,count):return os.pread(mem,count,address)
def q(address):return struct.unpack('<Q',read(address,8))[0]
def ready(ctx):
 if mem is None:return False
 try:return ctx and q(ctx+216)>=4096
 except (OSError,struct.error):return False
def snapshot(ctx):
 descriptors={};table=q(ctx+96);count=q(ctx+104);assert count<10000
 static_table=q(ctx+112);static_count=q(ctx+120);assert static_count<1000000;static_objects={q(static_table+i*8) for i in range(static_count)};assert all(static_address(p) for p in static_objects)
 for i in range(count):
  d=q(table+i*8);mode,size,refs,variants,managed=struct.unpack('<5Q',read(d,40));assert mode in (0,1,2,3) and refs<10000 and variants<10000
  offsets=[q(d+40+j*8) for j in range(refs)] if mode==0 else [];cases=[]
  if mode==1:
   for j in range(variants):
    p=q(d+40+j*8);n=q(p);assert n<10000;cases.append([q(p+8+k*8) for k in range(n)])
  if mode==3:assert size==0 and refs==0 and variants==0 and not managed
  descriptors[i]=dict(mode=mode,size=size,offsets=offsets,cases=cases,managed=managed)
 blocks={};ranges=[];arena=q(ctx+8);seen=set();mapped=0
 while arena:
  assert arena not in seen;seen.add(arena);nxt,size,start,end=struct.unpack('<4Q',read(arena,32));assert 4096<=size<=2**32 and arena<=start<end<=arena+size;ranges.append((start,end));mapped+=size;cursor=start
  while cursor<end:
   length,flags,desc=struct.unpack('<3Q',read(cursor,24));assert length>=32 and length%8==0 and cursor+length<=end and flags in (0,1)
   if flags:
    assert desc in descriptors;d=descriptors[desc];offsets=d['offsets']
    if d['mode']==1:
     tag=q(cursor+24);assert tag<len(d['cases']);offsets=d['cases'][tag]
    if d['mode']==2:
     n,capacity=struct.unpack('<2Q',read(cursor+24,16));assert n<=capacity<=(length-40)//8;offsets=list(range(40,40+n*8,8)) if d['managed'] else []
    if d['mode']==3:assert q(cursor+24)<=length-32
    assert all(24<=p<=length-8 and p%8==0 for p in offsets);blocks[cursor]=dict(bytes=length,descriptor=desc,refs=[q(cursor+p) for p in offsets if q(cursor+p)])
   cursor+=length
  assert cursor==end;arena=nxt
 assert mapped==q(ctx+24)
 assert allocation_observations==q(ctx+32),(allocation_observations,q(ctx+32))
 roots=[];n=q(ctx+136);base=q(ctx+128);mask=q(ctx+144);assert n<10000
 for i in range(n):
  if q(mask+8+(i//64)*8)&(1<<(i%64)):
   value=q(base+i*8)
   if value:roots.append(value)
 frame=q(ctx);seen=set();slots=0
 while frame:
  assert frame not in seen;seen.add(frame);rbp=q(frame+8);mask=q(frame+16);n=q(mask);assert n<1000000;slots+=n
  for i in range(n):
   if q(mask+8+(i//64)*8)&(1<<(i%64)):
    value=q(rbp-72-i*8)
    if value:roots.append(value)
  frame=q(frame)
 reached={};pending=list(roots)
 while pending:
  p=pending.pop()
  if p in reached:continue
  if p not in blocks:
   assert p in static_objects and not any(start<=p<end for start,end in ranges),('invalid traced reference',p);continue
  reached[p]=blocks[p];pending.extend(blocks[p]['refs'])
 resource=q(ctx+168);resource_seen=set();scratch=0
 while resource:
  assert resource not in resource_seen;resource_seen.add(resource);assert q(resource+8)==2**64-1
  scratch+=sum(q(resource+offset+8) for offset in [16,32,48] if q(resource+offset));resource=q(resource)
 fds={}
 for p in Path('/proc/'+str(pid)+'/fd').iterdir():
  try:fds[p.name]=os.readlink(p)
  except FileNotFoundError:pass
 return dict(reachable_bytes=sum(b['bytes'] for b in reached.values()),reachable_objects=len(reached),nodes={str(k):v for k,v in reached.items()},roots=roots,mapped=mapped,last_collection_live=q(ctx+48),collections=q(ctx+40),allocations=q(ctx+32),descriptor_count=count,frame_depth=len(seen),frame_slots=slots,resource_depth=len(resource_seen),scratch_bytes=scratch,fd_count=len(fds))
try:
 while True:
  api.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):result=os.WEXITSTATUS(status);break
  assert not os.WIFSIGNALED(status),('child signal',os.WTERMSIG(status));r=api.Registers();api.ptrace(12,pid,0,ctypes.byref(r));stop=os.WSTOPSIG(status)
  if stop==signal.SIGTRAP:
   if not executed:
    executed=True;mem=os.open('/proc/'+str(pid)+'/mem',os.O_RDWR);original_byte=read(allocation_point,1);assert original_byte==pattern[:1];assert os.pwrite(mem,b'\xcc',allocation_point)==1;continue
   assert r.rip-1==allocation_point,('unexpected allocation trap',r.rip)
   assert 0<=r.rdi<2**63;allocation_observations+=1;maximum_requested_allocation=max(maximum_requested_allocation,r.rdi)
   assert os.pwrite(mem,original_byte,allocation_point)==1;r.rip=allocation_point;api.ptrace(13,pid,0,ctypes.byref(r));api.ptrace(9,pid,0,ctypes.c_void_p(0));_,stepped=os.waitpid(pid,0);assert os.WIFSTOPPED(stepped) and os.WSTOPSIG(stepped)==signal.SIGTRAP
   assert os.pwrite(mem,b'\xcc',allocation_point)==1;continue
  assert stop==signal.SIGTRAP|0x80
  if entering and ready(r.r15):
   if a.stress and not armed:os.pwrite(mem,struct.pack('<Q',1),r.r15+152);armed=True
   if r.orig_rax==1 and r.rdi==1 and read(r.rsi,r.rdx)==b'checkpoint\n':snapshots.append(snapshot(r.r15))
  entering=not entering
 assert result==0 and len(snapshots)==4 and (not a.stress or armed) and allocation_observations>0
except BaseException as error:failure=repr(error);raise
finally:
 a.report.write_text(json.dumps(dict(exit=result,stress=a.stress,armed=armed,snapshots=snapshots,allocation_observations=allocation_observations,maximum_requested_allocation=maximum_requested_allocation,error=failure),indent=2)+'\n')
 if mem is not None:os.close(mem)
 try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
 except (ProcessLookupError,ChildProcessError):pass
sys.exit(result)
