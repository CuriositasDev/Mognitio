#!/usr/bin/env python3
"""Verify emitted mark membership, failure checks and bounded repeated searches."""
from pathlib import Path
import argparse,ctypes,hashlib,importlib.util,json,os,resource,shutil,signal,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fit',ROOT/'tests/mgnc/v180-fit-cursors.py');fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
load=fit.load;store=fit.store
def records(path):
 lines=path.read_text().splitlines();assert lines[0]=='MARK'
 return [dict(kind=v[0],value=v[1],target=v[2],bytes=v[3:]) for v in [list(map(int,x.split())) for x in lines[1:]]]
def image(path,mutation=None,instrument=True):
 rows=records(path);changed=0;before_static=True;before_loop=True
 for row in rows:
  raw=bytes(row['bytes'])
  if row['kind']==1 and row['target']==1003:before_static=False
  if row['kind']==1 and row['target']==1007:before_loop=False
  if mutation=='disable-cache' and row['kind']==3 and row['value']==56 and raw==bytes.fromhex('4d8b85'):
   row.update(kind=4,value=0,bytes=list(bytes.fromhex('49b8')));changed+=1
  if mutation=='disable-static-bounds' and before_static and row['kind']==2 and row['target']==1006 and raw[-2:] in [bytes.fromhex('0f82'),bytes.fromhex('0f87')]:
   row.update(kind=0,bytes=list(raw[:-2]+b'\x90'*6));changed+=1
  if mutation in ['skip-cache-upper','skip-cache-lower'] and before_loop and row['kind']==2 and row['target']==1007 and raw[-2:]==bytes.fromhex('0f83' if mutation=='skip-cache-upper' else '0f82'):
   row.update(kind=0,bytes=list(raw[:-2]+b'\x90'*6));changed+=1
  if mutation=='skip-cache-validation' and before_loop and row['kind']==2 and row['target']==1009:
   row['target']=1002;changed+=1
 if mutation:assert changed==(2 if mutation=='disable-static-bounds' else 1),('mutation membership',mutation,changed)
 counters=[0,0]
 if instrument:
  for row in rows:
   raw=bytes(row['bytes'])
   if row['kind']==3 and row['value']==0 and raw==bytes.fromhex('4d89c24d01ca49c1ea014c89d048c1e0034c01e8488b80'):
    row['bytes']=list(bytes.fromhex('49ff87f0000000'))+row['bytes'];counters[0]+=1
   if row['kind']==3 and row['value']==16 and raw in [bytes.fromhex('498b85'),bytes.fromhex('498b80')]:
    row['bytes']=list(bytes.fromhex('49ff87f8000000'))+row['bytes'];counters[1]+=1
  assert counters[0]==1 and counters[1] in [1,2],counters
 code,entry=fit.assemble(rows,instrument=False);return fit.Image(code,entry,3)
def setup(count=128,statics=1024):
 keep=[];arenas=[];objects=[]
 for i in range(count):
  buf=ctypes.create_string_buffer(8192);keep.append(buf);base=ctypes.addressof(buf);start=base+4096
  for offset,value in [(0,arenas[-1] if arenas else 0),(8,8192),(16,start),(24,start+4096),(32,base+704),(40,64),(48,4096)]:
   store(base+offset,value)
  # A 128-byte allocated object with independent block-start bit zero set.
  store(start,128);store(start+8,1);store(start+16,0);ctypes.c_ubyte.from_address(base+704).value=1
  arenas.append(base);objects.append(start)
 ctxbuf=ctypes.create_string_buffer(256);keep.append(ctxbuf);ctx=ctypes.addressof(ctxbuf)
 descriptor=ctypes.create_string_buffer(40);dt=(ctypes.c_uint64*1)(ctypes.addressof(descriptor));keep.extend([descriptor,dt])
 work=(ctypes.c_uint64*(count+10))();keep.append(work)
 staticbuf=ctypes.create_string_buffer(max(1,statics)*32);keep.append(staticbuf);sb=ctypes.addressof(staticbuf)
 staticobjects=[sb+i*32 for i in range(statics)]
 for ptr in staticobjects:store(ptr,32);store(ptr+8,5);store(ptr+16,0)
 st=(ctypes.c_uint64*max(1,statics))(*staticobjects);keep.append(st)
 for offset,value in [(8,arenas[-1] if arenas else 0),(64,ctypes.addressof(work)),(72,ctypes.sizeof(work)),(96,ctypes.addressof(dt)),(104,1),(112,ctypes.addressof(st)),(120,statics)]:
  store(ctx+offset,value)
 return dict(keep=keep,ctx=ctx,arenas=arenas,objects=objects,static=staticobjects,work=work)
def call(img,state,ptr,count=1):
 img.call(state['ctx'],ptr,count)
def rejected(img,state,ptr,edit=None):
 pid=os.fork()
 if pid==0:
  if edit:edit()
  call(img,state,ptr);os._exit(0)
 _,status=os.waitpid(pid,0);assert os.WIFEXITED(status) and os.WEXITSTATUS(status)==92,('invalid pointer admitted or wrong failure',status)
def run(path,mutation=None):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));img=image(path,mutation);s=setup();ctx=s['ctx'];order=[];cases=0
 for ptr in [0,*s['static'],s['static'][-1]]:
  call(img,s,ptr);assert load(ctx+80)==0;cases+=1
 # Alternate across disjoint ranges, then revisit already-marked objects.
 for index in [0,127,1,126,64,0,127,63,64]+list(range(128)):
  ptr=s['objects'][index];call(img,s,ptr)
  if ptr not in order:order.append(ptr)
  assert load(ptr+8)==3 and load(ctx+80)==len(order) and list(s['work'])[:len(order)]==order,('mark semantics',index)
  assert load(s['arenas'][-1]+56)==s['arenas'][index],('cache ownership',index)
  cases+=1
 # A newly prepended arena starts with an empty hint; old arenas stay valid.
 added=setup(1,0);base=added['arenas'][0];store(base,s['arenas'][-1]);store(ctx+8,base)
 ptr=s['objects'][5];call(img,s,ptr);assert list(s['work'])[:len(order)]==order;cases+=1
 assert load(base+56)==s['arenas'][5]
 # Cache hits must still validate allocation-start bitmap, extent, descriptor and flags.
 valid=s['objects'][5];call(img,s,valid)
 bad=valid+32
 for offset,value in [(0,32),(8,1),(16,0)]:store(bad+offset,value)
 for ptr in [1,s['static'][0]+8,s['static'][-1]+16,valid+1,bad,s['arenas'][5]+4095,s['arenas'][5]+8192]:
  rejected(img,s,ptr);cases+=1
 rejected(img,s,valid,lambda:setattr(ctypes.c_ubyte.from_address(s['arenas'][5]+704),'value',0));cases+=1
 for offset,value in [(0,24),(0,8192),(8,0),(8,5),(16,1)]:
  rejected(img,s,valid,lambda offset=offset,value=value:store(valid+offset,value));cases+=1
 for offset,value in [(8,4),(16,1)]:
  rejected(img,s,s['static'][0],lambda offset=offset,value=value:store(s['static'][0]+offset,value));cases+=1
 empty=setup(1,0);call(img,empty,empty['objects'][0]);assert load(empty['ctx']+80)==1;cases+=1
 static_only=setup(0,8);call(img,static_only,static_only['static'][0]);call(img,static_only,0);rejected(img,static_only,1);cases+=3
 # Repeated heap references have zero static-table probes and one cached arena
 # range probe after the initial full-chain search. Absolute bounds are structural.
 work=setup();call(img,work,work['objects'][0],4096)
 static_probes=load(work['ctx']+240);arena_probes=load(work['ctx']+248)
 assert static_probes==0,('static search work',static_probes)
 assert arena_probes<=128+4096,('arena search work',arena_probes)
 # Instrument removal must preserve values and the exact first-enqueue order.
 plain=image(path,mutation,instrument=False);normal=setup(8,16);expected=[]
 for ptr in [normal['static'][3],normal['objects'][0],normal['objects'][7],normal['objects'][0]]:
  call(plain,normal,ptr)
  if ptr in normal['objects'] and ptr not in expected:expected.append(ptr)
 assert list(normal['work'])[:len(expected)]==expected and load(normal['ctx']+80)==len(expected)
 return dict(status='Passed',cases=cases,static_probes=static_probes,arena_probes=arena_probes,mutation=mutation)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--execute',type=Path);parser.add_argument('--mutation');a=parser.parse_args()
 if a.execute:print(json.dumps(run(a.execute,a.mutation)));return
 assert a.compiler and a.output
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=out/'source';(source/'src').mkdir(parents=True)
 shutil.copy2(ROOT/'compiler/mgnc/mognitio.toml',source/'mognitio.toml')
 for module in ['Data','Machine','WholeX64','WholeABI','WholeMark']:
  shutil.copytree(ROOT/'compiler/mgnc/src'/module,source/'src'/module)
 shutil.copy2(ROOT/'tests/mgnc/harnesses/v180-mark-search.mgn',source/'src/mgnc.mgn')
 command=[str(a.compiler.resolve()),'build',str(source/'mognitio.toml'),'-o',str(out/'emitter')]
 built=subprocess.run(command,capture_output=True,timeout=600)
 (out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr)
 assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),('build failed',built.returncode,built.stderr)
 emitted=subprocess.run([str(out/'emitter')],capture_output=True,timeout=120)
 (out/'records.txt').write_bytes(emitted.stdout);(out/'emit.stderr').write_bytes(emitted.stderr)
 assert emitted.returncode==0 and not emitted.stderr
 rows=[]
 for mutation in [None,'disable-cache','disable-static-bounds','skip-cache-upper','skip-cache-lower','skip-cache-validation']:
  command=[sys.executable,str(Path(__file__).resolve()),'--execute',str(out/'records.txt')]
  if mutation:command+=['--mutation',mutation]
  result=subprocess.run(command,capture_output=True,timeout=120);name=mutation or 'normal'
  (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
  if mutation:
   assert result.returncode!=0 and b'mutation membership' not in result.stderr,('mutant survived or missing',mutation)
   assert any(x in result.stderr for x in [b'static search work',b'arena search work',b'invalid pointer admitted',b'mark semantics',b'cache ownership']) or (mutation in ['skip-cache-upper','skip-cache-lower'] and result.returncode in (92,-signal.SIGSEGV) and not result.stderr),('unclassified mutant failure',mutation,result.returncode,result.stderr)
  else:assert result.returncode==0,result.stderr
  rows.append(dict(mutation=mutation,exit=result.returncode,status='Passed'))
 receipt=dict(status='Passed',rows=rows,source={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*')) if p.is_file()},compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest())
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('NATIVE_MARK_SEARCH_OK controls=6')
if __name__=='__main__':main()
