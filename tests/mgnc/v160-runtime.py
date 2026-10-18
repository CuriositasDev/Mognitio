#!/usr/bin/env python3
"""Execute generated runtime components and independently verify physical heaps."""
import json,struct,subprocess,sys,time
from pathlib import Path
import argparse,shutil
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument("--seed",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir()
project=out/"project";(project/"src").mkdir(parents=True)
(project/"mognitio.toml").write_text('[project]\nname = "runtimeprobe"\nroot_namespace = "Mgnc"\n')
modules=("Data","IntMap","Machine","Encode","Fields","WholeX64","WholeABI","WholeArena","WholeMark","WholeSweep","WholeCollect","WholeFrame","WholeFrameData")
for module in modules:shutil.copytree(ROOT/"compiler/mgnc/src"/module,project/"src"/module)
shutil.copyfile(ROOT/"tests/mgnc/harnesses/v160-runtime.mgn",project/"src/runtimeprobe.mgn")
A=out/"emitter"
built=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",A],capture_output=True,timeout=900)
assert (built.returncode,built.stdout,built.stderr)==(0,b"",b""),(built.returncode,built.stdout,built.stderr)
names=['graph', 'stress', 'fragment', 'static', 'variant', 'variant-scalar', 'buffer', 'empty', 'interior', 'unaligned', 'foreign', 'freed', 'old-start', 'bad-flags', 'bad-descriptor', 'bad-size', 'bad-tag', 'bad-count', 'root-cycle', 'free-cycle', 'ordinal', 'cap', 'overflow', 'abi', 'recursive', 'capture', 'partial', 'globals', 'full-live']
good={"graph":[50000,0],"stress":[200],"fragment":[1000,1000],"static":[0],"variant":[2],"variant-scalar":[1],"buffer":[2],"empty":[0],"abi":[1],"recursive":[1],"capture":[1],"partial":[3],"globals":[1],"full-live":[32768,32769]}
allocation={"ordinal","cap","overflow"}
def q(data,offset=0):return struct.unpack_from("<Q",data,offset)[0]
def verify(raw,counts,elf):
 pos=0;reports=[]
 for expected in counts:
  assert len(raw)-pos>=304,"short context"
  ctx=raw[pos:pos+256];roots=raw[pos+256:pos+288];global_values=raw[pos+288:pos+304];pos+=304
  blocks={};arenas=[];base=q(ctx,8);seen=set();total=0
  while base:
   assert base not in seen,"arena cycle"
   seen.add(base);assert len(raw)-pos>=64
   size=q(raw,pos+8);assert 4096<=size<=64*1024*1024
   area=raw[pos:pos+size];assert len(area)==size;pos+=size;total+=size
   begin=q(area,16)-base;end=q(area,24)-base;index=q(area,32)-base;indexlen=q(area,40)
   assert index==64 and begin==index+indexlen and begin<end<=size
   assert end-begin==q(area,48) and indexlen==(end-begin)//64
   bitmap=bytearray(indexlen);offset=begin;previous_free=False
   while offset<end:
    length,flags,descriptor=struct.unpack_from("<QQQ",area,offset)
    assert length>=32 and length%8==0 and offset+length<=end
    assert flags in (0,1),"stale mark or corrupt flags"
    assert not(previous_free and flags==0),"uncoalesced free neighbors"
    previous_free=flags==0
    if flags==0:assert descriptor==0
    else:assert descriptor<7
    bit=(offset-begin)//8;bitmap[bit//8]|=1<<(bit%8)
    blocks[base+offset]=(length,flags,descriptor,area[offset:offset+length])
    offset+=length
   assert offset==end and bitmap==area[index:index+indexlen],"block-start index mismatch"
   arenas.append((base,size));base=q(area)
  assert total==q(ctx,24),"mapped accounting"
  free=set();pointer=q(ctx,16)
  while pointer:
   assert pointer not in free,"free-list cycle"
   assert pointer in blocks and blocks[pointer][1]==0,"free membership"
   free.add(pointer);pointer=q(blocks[pointer][3],24)
  assert free=={a for a,b in blocks.items() if b[1]==0},"free-list completeness"
  reachable=set();queue=[q(roots,24)]
  static_seen=set()
  if q(ctx,136):queue.append(q(global_values))
  while queue:
   pointer=queue.pop()
   if not pointer or pointer in reachable or pointer in static_seen:continue
   if pointer not in blocks:
    # Encode's single load segment begins at virtual 0x400000.
    off=pointer-0x400000
    assert 0<=off<=len(elf)-40 and q(elf,off+8)==5 and q(elf,off+16)==4,"invalid object base"
    assert q(elf,off+24)==0 and q(elf,off+32)==0
    static_seen.add(pointer);continue
   length,flags,desc,data=blocks[pointer];assert flags==1,"root or edge points to free block"
   reachable.add(pointer)
   if desc in (0,5):queue.append(q(data,24))
   elif desc==6:queue.append(q(data,32))
   elif desc==2:
    tag=q(data,24);assert tag<2
    if tag==1:queue.append(q(data,32))
   elif desc==3:
    count=q(data,24);assert count<=(length-40)//8 and q(data,32)<=count
    queue.extend(q(data,40+i*8) for i in range(count))
   else:assert desc in (1,4)
  allocated={a for a,b in blocks.items() if b[1]}
  assert reachable==allocated,"unreachable object retained or live graph lost"
  assert len(reachable)==expected,(len(reachable),expected)
  live=sum(blocks[a][0] for a in reachable)
  assert live==q(ctx,48),"live byte accounting"
  assert q(ctx,80)==len(reachable) and q(ctx,88)==len(reachable),"mark worklist"
  capacity=q(ctx,72)
  assert capacity==0 or capacity>=4096 and capacity&(capacity-1)==0
  assert capacity>=len(reachable)*8
  assert capacity<=max(4096,2*50000*8),"worklist history growth"
  reports.append({"arenas":len(arenas),"mapped":total,"live":live,"objects":len(reachable),"free_blocks":len(free),"collections":q(ctx,40),"scratch":capacity})
 assert pos==len(raw),"trailing snapshot bytes"
 return reports
results=[]
for name in names:
 x=out/name
 build=subprocess.run([str(A),str(x),name],capture_output=True,timeout=60)
 assert build.returncode==0,(name,"emit",build.returncode,build.stderr)
 started=time.monotonic();run=subprocess.run([str(x)],capture_output=True,timeout=60)
 expected=0 if name in good else 71 if name in allocation else 72
 assert run.returncode==expected,(name,run.returncode,expected,len(run.stdout),run.stderr)
 assert not run.stderr
 reports=verify(run.stdout,good[name],x.read_bytes()) if name in good else []
 assert name in good or not run.stdout
 results.append({"case":name,"status":run.returncode,"snapshots":reports,"seconds":round(time.monotonic()-started,3)})
 print(json.dumps(results[-1]),flush=True)
(out/"results.json").write_text(json.dumps(results,indent=2)+"\n")

faults=[]
for syscall,ordinal in ((9,1),(9,2),(9,3),(25,1),(25,2)):
 result=subprocess.run(["python3",ROOT/"tests/mgnc/syscall-fault.py","--syscall",str(syscall),"--ordinal",str(ordinal),"--errno","12","--",out/"graph"],capture_output=True,timeout=60)
 assert (result.returncode,result.stdout,result.stderr)==(71,b"",b""),(syscall,ordinal,result.returncode,result.stdout,result.stderr)
 faults.append({"syscall":syscall,"ordinal":ordinal,"status":71})
(out/"faults.json").write_text(json.dumps(faults,indent=2)+"\n")
print("RUNTIME_COMPONENT_OK cases="+str(len(results))+" raw_faults="+str(len(faults)))
