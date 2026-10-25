#!/usr/bin/env python3
"""Check emitted reserve policy against unsigned arithmetic and actual mappings."""
import argparse,ctypes,hashlib,importlib.util,json,resource,subprocess,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("fit",Path(__file__).with_name("v180-fit-cursors.py"))
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
M=1024*1024
VALUES=[0,1,M-1,M,M+1,128*M-1,128*M,512*M-1,512*M,512*M+1,1024*M-1,1024*M,1024*M+1,2**31,2**32,2**63-1,2**63,2**64-1]
def expected(mapped,cap,request):
 preferred=min(mapped//8,128*M) if cap==0 and mapped>512*M else min(max(mapped//4,M),16*M)
 return max(request,preferred)
def prepared(path,mutation,policy):
 rows=fit.records(path.read_text())["ARENA"]
 begin=next(i for i,r in enumerate(rows) if r["kind"]==1 and r["target"]==14)
 end=next(i for i,r in enumerate(rows) if r["kind"]==1 and r["target"]==10)
 matches=0
 for i in range(begin,end):
  row=rows[i];b=bytes(row["bytes"])
  if mutation=="threshold" and row["kind"]==3 and row["value"]==512*M:
   branch=rows[i+1];assert branch["kind"]==2 and bytes(branch["bytes"])==bytes.fromhex("0f86"),"mutation membership threshold"
   branch["bytes"]=list(bytes.fromhex("0f82"));matches+=1
  elif mutation in ("large-cap","small-cap") and row["kind"]==4 and row["value"]==(128*M if mutation=="large-cap" else 16*M):
   row["value"]*=2;matches+=1
  elif mutation=="ignore-cap" and matches==0 and row["kind"]==3 and row["value"]==184 and b==bytes.fromhex("498b8f"):
   row.update(kind=4,value=0,bytes=list(bytes.fromhex("48b9")));matches+=1
  elif mutation=="large-rate" and bytes.fromhex("48c1e803") in b:
   matches+=b.count(bytes.fromhex("48c1e803"));row["bytes"]=list(b.replace(bytes.fromhex("48c1e803"),bytes.fromhex("48c1e802")))
 if mutation:assert matches==1,("mutation membership",mutation,matches)
 if policy:
  at=next(i for i in range(begin,end) if rows[i]["kind"]==3 and rows[i]["value"]==4095 and bytes(rows[i]["bytes"])==bytes.fromhex("4981c4"))
  # Return the selected R12 size before page rounding or mmap. The original
  # policy bytes and branches execute, including the explicit-cap exclusion.
  rows.insert(at,dict(kind=0,value=0,target=0,bytes=list(bytes.fromhex("4c89e04881c408000000415f415e415d415c5b5dc3"))))
 return rows
def execute(path,mutation):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 rows=prepared(path,mutation,True);code,entry=fit.assemble(rows,instrument=False,entry_label=3000);policy=fit.Image(code,entry,2)
 count=0
 for mapped in VALUES:
  for cap in [0,1]:
   for request in [32,2*M,256*M,2**63-8]:
    context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context);fit.store(ctx+24,mapped);fit.store(ctx+184,cap)
    actual=policy.call(ctx,request);wanted=expected(mapped,cap,request)
    assert actual==wanted,("reserve oracle",mapped,cap,request,actual,wanted);count+=1
 # Exercise real mmap, bitmap/payload geometry, accounting and cold metadata.
 rows=prepared(path,None,False);code,entry=fit.assemble(rows,instrument=False,entry_label=3000);reserve=fit.Image(code,entry,2)
 libc=ctypes.CDLL(None);libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
 for mapped,cap in [(512*M,0),(512*M+8,0),(2**31,0),(2**31,1<<60)]:
  context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context);fit.store(ctx+24,mapped);fit.store(ctx+184,cap)
  reserve.call(ctx,32);base=fit.load(ctx+8);assert base,"mmap"
  size=fit.load(base+8)
  try:
   payload=(expected(mapped,cap,32)+4095)//4096*4096
   assert fit.load(base+48)==payload and fit.load(base+40)==payload//64,"mapped policy"
   assert fit.load(base+32)==base+704 and fit.load(base+16)==base+704+payload//64,"bitmap geometry"
   assert fit.load(base+24)<=base+size and fit.load(ctx+24)==mapped+size,"mapping accounting"
   assert ctypes.string_at(base+64,640)==bytes(640),"cold metadata"
  finally:assert libc.munmap(base,size)==0
 print(json.dumps(dict(status="Passed",policy_cases=count,mapping_cases=4)))
def main():
 p=argparse.ArgumentParser();p.add_argument("--records",type=Path,required=True);p.add_argument("--output",type=Path);p.add_argument("--execute",action="store_true");p.add_argument("--mutation");a=p.parse_args()
 if a.execute:execute(a.records,a.mutation);return
 assert a.output;a.output.mkdir();rows=[]
 for mutation in [None,"threshold","large-cap","small-cap","ignore-cap","large-rate"]:
  cmd=[sys.executable,str(Path(__file__).resolve()),"--records",str(a.records.resolve()),"--execute"]
  if mutation:cmd+=["--mutation",mutation]
  r=subprocess.run(cmd,capture_output=True,timeout=30);name=mutation or "normal"
  (a.output/(name+".stdout")).write_bytes(r.stdout);(a.output/(name+".stderr")).write_bytes(r.stderr)
  if mutation:assert r.returncode!=0 and b"reserve oracle" in r.stderr and b"mutation membership" not in r.stderr,(mutation,r.returncode,r.stderr)
  else:assert r.returncode==0,r.stderr
  rows.append(dict(mutation=mutation,exit=r.returncode,status="Passed"))
 (a.output/"receipt.json").write_text(json.dumps(dict(status="Passed",records_sha256=hashlib.sha256(a.records.read_bytes()).hexdigest(),validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rows=rows),indent=2)+"\n")
 print("ARENA_CAPACITY_OK controls=6")
if __name__=="__main__":main()
