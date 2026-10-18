#!/usr/bin/env python3
"""Read concrete managed heaps at observation-only GC/constructor trap points."""
import argparse,ctypes,importlib.util,json,os,signal,struct,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--report",type=Path,required=True);p.add_argument("--text",required=True);p.add_argument("--mode",choices=["result","direct","nested"],required=True);p.add_argument("image",type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location("fault",Path(__file__).with_name("syscall-fault.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
pid=os.fork()
if pid==0:
 m.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(str(a.image),[str(a.image)])
os.waitpid(pid,0);m.ptrace(0x4200,pid,0,ctypes.c_void_p(1))
mem=None;entering=True;executed=False;stress=False;events=[];parents=[];closures=[];witnesses=[];snapshots=[]
def read(addr,n):return os.pread(mem,n,addr)
def q(addr):return struct.unpack("<Q",read(addr,8))[0]
def heap(ctx):
 blocks={};descriptors={};arena=q(ctx+8);seen=set();total=0;table=q(ctx+96);count=q(ctx+104)
 assert count<10000
 for i in range(count):
  d=q(table+i*8);mode,size,refs,variants,managed=struct.unpack("<5Q",read(d,40))
  assert mode in (0,1,2) and refs<10000 and variants<10000
  offsets=[q(d+40+j*8) for j in range(refs)] if mode==0 else []
  cases=[]
  if mode==1:
   for j in range(variants):
    v=q(d+40+j*8);n=q(v);assert n<10000;cases.append([q(v+8+k*8) for k in range(n)])
  descriptors[i]=dict(mode=mode,size=size,offsets=offsets,cases=cases,managed=managed)
 while arena:
  assert arena not in seen;seen.add(arena)
  nxt,size,start,end=struct.unpack("<4Q",read(arena,32));assert 4096<=size<=2**32 and arena<=start<end<=arena+size
  total+=size;cursor=start
  while cursor<end:
   length,flags,desc=struct.unpack("<3Q",read(cursor,24));assert length>=32 and length%8==0 and cursor+length<=end and flags in (0,1)
   if flags==1:
    assert desc in descriptors;d=descriptors[desc];offsets=d["offsets"]
    if d["mode"]==1:
     tag=q(cursor+24);assert tag<len(d["cases"]);offsets=d["cases"][tag]
    if d["mode"]==2:
     n,capacity=struct.unpack("<2Q",read(cursor+24,16));assert n<=capacity<=(length-40)//8;offsets=list(range(40,40+n*8,8)) if d["managed"] else []
    assert all(24<=x<=length-8 and x%8==0 for x in offsets)
    refs=[q(cursor+x) for x in offsets if q(cursor+x)!=0]
    text=None
    if d["mode"]==0 and d["size"]==0 and length>=40:
     n=q(cursor+24);assert n<=length-40
     if read(cursor+40,n)==a.text.encode():text=a.text
    blocks[cursor]=dict(size=length,descriptor=desc,refs=refs,text=text)
   cursor+=length
  assert cursor==end;arena=nxt
 assert total==q(ctx+24)
 roots=[];n=q(ctx+136);base=q(ctx+128);mask=q(ctx+144)
 assert n<10000
 for i in range(n):
  if q(mask+8+(i//64)*8)&(1<<(i%64)):
   value=q(base+i*8)
   if value:roots.append(value)
 frame=q(ctx);seen=set()
 while frame:
  assert frame not in seen;seen.add(frame);rbp=q(frame+8);mask=q(frame+16);n=q(mask);assert n<1000000
  for i in range(n):
   if q(mask+8+(i//64)*8)&(1<<(i%64)):
    value=q(rbp-72-i*8)
    if value:roots.append(value)
  frame=q(frame)
 return blocks,descriptors,roots
def reaches(blocks,starts,targets,excluded=None):
 queue=list(starts);seen=set()
 while queue:
  node=queue.pop()
  if node==excluded or node in seen:continue
  seen.add(node)
  if node in targets:return True
  if node in blocks:queue.extend(blocks[node]["refs"])
 return False
try:
 while True:
  m.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
  if os.WIFEXITED(status):result=os.WEXITSTATUS(status);break
  assert not os.WIFSIGNALED(status),("child signal",os.WTERMSIG(status))
  r=m.Registers();m.ptrace(12,pid,0,ctypes.byref(r));stop=os.WSTOPSIG(status)
  if stop==signal.SIGTRAP:
   if not executed:executed=True;mem=os.open(f"/proc/{pid}/mem",os.O_RDWR);continue
   event=read(r.rip,1)[0];assert event in (14,15,16),event
   if not stress:os.pwrite(mem,struct.pack("<Q",1),r.r15+152);stress=True
   r.rip+=1;m.ptrace(13,pid,0,ctypes.byref(r))
   blocks,descriptors,roots=heap(r.r15);targets={k for k,v in blocks.items() if v["text"]==a.text}
   row=dict(event=event,collection=q(r.r15+40),targets=sorted(targets),roots=roots)
   if event==15:
    node=r.rax
    if node in blocks and q(node+24)==1 and reaches(blocks,[q(node+32)],targets):
     parent=dict(address=node,payload=q(node+32),descriptor=blocks[node]["descriptor"])
     parents.append(parent);row["result"]=parent
   if event==16:
    node=r.rax
    if node in blocks and reaches(blocks,[q(node+32)],targets):
     closure=dict(address=node,environment=q(node+32),descriptor=blocks[node]["descriptor"])
     closures.append(closure);row["closure"]=closure
   if event==14 and targets:
    if a.mode=="result" and len(parents)==1:
     parent=parents[0]
     if parent["address"] not in blocks and parent["payload"] in blocks and reaches(blocks,[parent["payload"]],targets):
      witnesses.append(dict(kind="parent-reclaimed-payload-live",event=len(events),parent=parent))
    if a.mode in ("direct","nested") and closures:
     reader=closures[0] if a.mode=="direct" else closures[1] if len(closures)>1 else None
     if reader and reader["address"] in blocks and reaches(blocks,roots,targets) and not reaches(blocks,roots,targets,reader["address"]):
      parent_gone=a.mode=="direct" or (closures[0]["address"] not in blocks and closures[0]["environment"] not in blocks)
      if parent_gone:witnesses.append(dict(kind="reader-dominates-retention",event=len(events),reader=reader,parent_reclaimed=parent_gone))
    # Store the independent heap graph supporting every collection observation.
    snapshots.append(dict(event=len(events),blocks={str(k):v for k,v in blocks.items()},roots=roots))
   events.append(row);continue
  assert stop==signal.SIGTRAP|0x80,stop
  if entering and not stress and mem is not None:
   try:ready=r.r15!=0 and q(r.r15+216)>=4096
   except (OSError,struct.error):ready=False
   if ready:os.pwrite(mem,struct.pack("<Q",1),r.r15+152);stress=True
  entering=not entering
 same_payload=a.mode!="result" or (len(parents)>=2 and parents[0]["payload"]==parents[1]["payload"] and parents[0]["descriptor"]!=parents[1]["descriptor"])
 passed=result==0 and stress and bool(witnesses) and same_payload
 a.report.write_text(json.dumps(dict(exit=result,stress=stress,mode=a.mode,events=events,snapshots=snapshots,witnesses=witnesses,parents=parents,closures=closures,same_payload_new_descriptor=same_payload,passed=passed),indent=2)+"\n")
 sys.exit(0 if passed else 1)
finally:
 if mem is not None:os.close(mem)
 try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
 except (ProcessLookupError,ChildProcessError):pass
