#!/usr/bin/env python3
"""Exercise post-collection reserve in actual allocator bytes with a reclaim stub."""
import argparse,ctypes,hashlib,importlib.util,json,resource,subprocess,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('fit',Path(__file__).with_name('v180-fit-cursors.py'))
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
M=1024*1024
def prepared(path,mutation=None,fail=False):
 rows=fit.records(path.read_text())['ARENA']
 collect=next(i for i,r in enumerate(rows) if r['kind']==1 and r['target']==11)
 assert rows[collect+1]['kind']==0
 # Collector boundary: count collections, expose a separately prepared reclaimed
 # chain at the chosen collection count, and leave all callee-save registers intact.
 stub='49ff8728000000498b8728000000493b87d8000000720e498b87d000000049898710000000c3'
 rows[collect+1]['bytes']=list(bytes.fromhex(stub))
 if fail:
  count=0
  for row in rows[:next(i for i,r in enumerate(rows) if r['kind']==1 and r['target']==10)]:
   b=bytes(row['bytes'])
   if bytes.fromhex('0f05') in b:
    count+=b.count(bytes.fromhex('0f05'));row['bytes']=list(b.replace(bytes.fromhex('0f05'),bytes.fromhex('48c7c0f4ffffff')))
  assert count==1,'mmap mutation membership'
 start=next(i for i,r in enumerate(rows) if r['kind']==1 and r['target']==10)
 matches=0
 for i in range(start,next(j for j,r in enumerate(rows) if r['kind']==1 and r['target']==15)):
  row=rows[i];b=bytes(row['bytes'])
  if mutation=='threshold' and row['kind']==3 and row['value']==512*M:
   assert rows[i+1]['kind']==2 and bytes(rows[i+1]['bytes'])==bytes.fromhex('0f86')
   rows[i+1]['bytes']=list(bytes.fromhex('0f82'));matches+=1
  elif mutation in ['ignore-cap','ignore-stress'] and row['kind']==3 and row['value']==(184 if mutation=='ignore-cap' else 152) and b==bytes.fromhex('498b87'):
   # Only the post-collection exclusion, not the earlier stress scheduling.
   if mutation=='ignore-stress' and i<next(j for j in range(start,len(rows)) if rows[j]['kind']==3 and rows[j]['value']==184):continue
   row.update(kind=4,value=0,bytes=list(bytes.fromhex('48b8')));matches+=1
  elif mutation=='count-small' and row['kind']==2 and b.endswith(bytes.fromhex('4c39e20f82')):
   row.update(kind=0,bytes=list(b[:-2])+[144]*6);matches+=1
  elif mutation=='large-rate' and i>next(j for j in range(start,len(rows)) if rows[j]['kind']==3 and rows[j]['value']==184) and bytes.fromhex('49c1e803') in b:
   matches+=b.count(bytes.fromhex('49c1e803'));row['bytes']=list(b.replace(bytes.fromhex('49c1e803'),bytes.fromhex('49c1e802')))
 if mutation=='fatal-optional-map':
  for i,row in enumerate(rows[:start]):
   if row['kind']==3 and row['value']==-4095:
    assert rows[i+1]['kind']==2 and bytes(rows[i+1]['bytes'])==bytes.fromhex('0f83')
    rows[i+1]['target']=1;matches+=1
 if mutation:assert matches==1,('mutation membership',mutation,matches)
 return rows
def one(path,mutation,mapped,sizes,request,grow,cap=0,stress=0,fail=False):
 rows=prepared(path,mutation,fail);code,entry=fit.assemble(rows,instrument=False);image=fit.Image(code,entry,3)
 memory,blocks=fit.arena(sizes);base=ctypes.addressof(memory)
 context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context)
 for offset,value in [(8,base),(16,0),(24,mapped),(56,1<<60),(104,1),(152,stress),(184,cap),(208,blocks[0][0]),(216,2 if stress else 1)]:
  fit.store(ctx+offset,value)
 wanted=next((a for a,n in blocks if n>=request),None)
 actual=image.call(ctx,request,0);head=fit.load(ctx+8)
 try:
  assert (head!=base)==grow,('reserve oracle growth',mapped,cap,stress,fail,sizes,head!=base,grow)
  assert fit.load(ctx+40)==(2 if stress else 1),'reserve oracle collection count'
  assert fit.load(ctx+32)==1 and fit.load(actual+8)==1 and fit.load(actual+16)==0,'reserve oracle allocation header'
  if grow:
   assert actual==fit.load(head+16),'reserve oracle first fit in new head'
   assert fit.load(head)==base and fit.load(ctx+24)==mapped+fit.load(head+8),'reserve oracle accounting'
  else:assert actual==wanted and fit.load(ctx+24)==mapped,'reserve oracle reclaimed first fit'
 finally:
  if head!=base:
   libc=ctypes.CDLL(None);libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t];assert libc.munmap(head,fit.load(head+8))==0
def execute(path,mutation):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 cases=[
  (512*M,[64],48,False,0,0,False),
  (512*M+8,[64],48,True,0,0,False),
  (513*M,[64],48,False,1<<60,0,False),
  (513*M,[64],48,False,0,1,False),
  (513*M,[100*M],48,False,0,0,False),
  (513*M,[15*M]*5+[16*M],16*M,True,0,0,False),
  (513*M,[64],48,False,0,0,True)]
 for case in cases:one(path,mutation,*case)
 print(json.dumps(dict(status='Passed',cases=len(cases))))
def main():
 p=argparse.ArgumentParser();p.add_argument('--records',required=True,type=Path);p.add_argument('--output',type=Path);p.add_argument('--execute',action='store_true');p.add_argument('--mutation');p.add_argument('--mandatory-failure',action='store_true');a=p.parse_args()
 if a.mandatory_failure:one(a.records,None,513*M,[40],48,False,fail=True);raise AssertionError('mandatory mapping failure returned')
 if a.execute:execute(a.records,a.mutation);return
 a.output.mkdir();rows=[]
 for mutation in [None,'threshold','ignore-cap','ignore-stress','count-small','large-rate','fatal-optional-map']:
  cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--records',str(a.records),'--execute']
  if mutation:cmd+=['--mutation',mutation]
  r=subprocess.run(cmd,capture_output=True,timeout=90);name=mutation or 'normal'
  (a.output/(name+'.stdout')).write_bytes(r.stdout);(a.output/(name+'.stderr')).write_bytes(r.stderr)
  if mutation=='fatal-optional-map':assert r.returncode==91 and not r.stderr,(mutation,r.returncode,r.stderr)
  elif mutation:assert r.returncode!=0 and b'reserve oracle' in r.stderr and b'mutation membership' not in r.stderr,(mutation,r.returncode,r.stderr)
  else:assert r.returncode==0,(r.returncode,r.stderr)
  rows.append(dict(mutation=mutation,exit=r.returncode,status='Passed'))
 cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--records',str(a.records),'--mandatory-failure']
 r=subprocess.run(cmd,capture_output=True,timeout=5)
 (a.output/'mandatory-failure.stdout').write_bytes(r.stdout);(a.output/'mandatory-failure.stderr').write_bytes(r.stderr)
 assert r.returncode==91 and not r.stderr,('mandatory failure',r.returncode,r.stderr)
 rows.append(dict(mutation='mandatory-mmap-failure',exit=r.returncode,status='Passed'))
 (a.output/'receipt.json').write_text(json.dumps(dict(status='Passed',rows=rows,records_sha256=hashlib.sha256(a.records.read_bytes()).hexdigest(),validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
 print('POST_COLLECTION_RESERVE_OK controls=8')
if __name__=='__main__':main()
