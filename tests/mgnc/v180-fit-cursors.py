#!/usr/bin/env python3
"""Check emitted allocator bytes against independent ordered-block selection."""
import argparse,resource,ctypes,hashlib,json,mmap,os,random,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def records(text):
    groups={};current=None
    for line in text.splitlines():
        if line in ('ARENA','RESET'):current=[];groups[line]=current;continue
        values=list(map(int,line.split()));assert current is not None and len(values)>=3
        current.append(dict(kind=values[0],value=values[1],target=values[2],bytes=values[3:]))
    assert set(groups)=={'ARENA','RESET'}
    return groups
def assemble(rows,mutation=None,instrument=True,entry_label=0):
    rows=json.loads(json.dumps(rows));matched=0
    for row in rows:
        b=bytes(row['bytes'])
        if mutation=='disable-cache' and row['kind']==3 and row['value']==0 and b==bytes.fromhex('4d8bb2'):
            row.update(kind=4,value=0,bytes=list(bytes.fromhex('49be')));matched+=1
        elif mutation in ('first-owner','second-owner'):
            before=bytes.fromhex('4d39e30f84' if mutation=='first-owner' else '4c39e20f84')
            count=b.count(before)
            if count:row['bytes']=list(b.replace(before,bytes.fromhex('4d39e40f84')));matched+=count
        elif mutation=='half-promotion' and row['kind']==3 and row['value']==0 and b==bytes.fromhex('498982'):
            row['bytes']=list(bytes.fromhex('4d898a'));matched+=1
    if mutation=='disable-repair':
        indices=[i for i,row in enumerate(rows) if row['kind']==3 and row['value']==0 and bytes(row['bytes'])==bytes.fromhex('4d89b2')]
        assert len(indices)==2,('mutation membership repair',len(indices))
        rows[indices[-1]].update(kind=0,bytes=[144]*7);matched=1
    if mutation in ('disable-reset','disable-sweep-reset'):
        indices=[i for i,row in enumerate(rows) if row['kind']==3 and row['value']==0 and bytes(row['bytes'])==bytes.fromhex('488987')]
        assert len(indices)==1,('mutation membership reset',len(indices))
        rows[indices[0]].update(kind=0,bytes=[144]*7);matched=1
    if mutation:assert matched==1,('mutation membership',mutation,matched)
    # Count visits at the unique load of the next free block. This probe changes
    # no live value or flags consumed by the following allocator instructions.
    matches=0
    for row in rows:
        if row['kind']==3 and row['value']==0 and bytes(row['bytes'])==bytes.fromhex('498b86'):
            if instrument:row['bytes']=list(bytes.fromhex('49ff87f8000000'))+row['bytes']
            matches+=1
    if instrument:assert matches==1,('scan membership',matches)
    labels={};offset=0;sizes={0:0,1:0,2:4,3:4,4:8}
    for row in rows:
        assert row['kind'] in sizes
        if row['kind']==1:assert row['target'] not in labels;labels[row['target']]=offset
        offset+=len(row['bytes'])+sizes[row['kind']]
    code=bytearray()
    for row in rows:
        code.extend(row['bytes']);kind=row['kind']
        if kind==2:code.extend(struct.pack('<i',labels[row['target']]-len(code)-4))
        elif kind==3:code.extend(struct.pack('<i',row['value']))
        elif kind==4:code.extend(struct.pack('<q',row['value']))
    assert len(code)==offset
    return bytes(code),labels[entry_label]
class Image:
    def __init__(self,code,entry,argc):
        self.memory=mmap.mmap(-1,len(code),prot=mmap.PROT_READ|mmap.PROT_WRITE|mmap.PROT_EXEC)
        self.memory.write(code)
        self.address=ctypes.addressof(ctypes.c_char.from_buffer(self.memory))
        self.call=ctypes.CFUNCTYPE(ctypes.c_uint64,*([ctypes.c_uint64]*argc))(self.address+entry)
def load(address):return ctypes.c_uint64.from_address(address).value
def store(address,value):ctypes.c_uint64.from_address(address).value=value
def arena(sizes):
    span=sum(size+64 for size in sizes);bitmap=(span+63)//64
    start=(704+bitmap+4095)//4096*4096
    memory=ctypes.create_string_buffer(start+span+4096);base=ctypes.addressof(memory)
    for offset,value in [(0,0),(8,len(memory)),(16,base+start),(24,base+start+span),(32,base+704),(40,bitmap),(48,span)]:
        store(base+offset,value)
    rows=[];address=base+start
    for size in sizes:rows.append((address,size));address+=size+64
    rebuild(rows)
    return memory,rows
def rebuild(rows):
    for i,(address,size) in enumerate(rows):
        store(address,size);store(address+8,0);store(address+16,0);store(address+24,rows[i+1][0] if i+1<len(rows) else 0)
def sequence(image,reset,sizes,requests,reset_at=None,grow_at=None):
    memory,initial=arena(sizes);keep=[memory];base=ctypes.addressof(memory)
    context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context)
    for offset,value in [(8,base),(16,initial[0][0]),(24,len(memory)),(56,1<<60),(104,1)]:
        store(ctx+offset,value)
    oracle=list(initial);trace=[]
    for ordinal,requested in enumerate(requests):
        if ordinal==reset_at:
            reset.call(ctx);rebuild(initial);oracle=list(initial);store(ctx+16,oracle[0][0])
        if ordinal==grow_at:
            added,rows=arena([32,40]);keep.append(added);new=ctypes.addressof(added)
            store(new,load(ctx+8));store(rows[-1][0]+24,load(ctx+16))
            store(ctx+8,new);store(ctx+16,rows[0][0]);store(ctx+24,load(ctx+24)+len(added))
            oracle=rows+oracle
        selected=next(i for i,row in enumerate(oracle) if row[1]>=requested)
        expected,size=oracle[selected]
        actual=image.call(ctx,requested,0)
        assert actual==expected,('first-fit',ordinal,requested,actual-expected)
        remaining=size-requested
        assert load(actual)==(requested if remaining>=32 else size),('allocated size',ordinal)
        assert load(actual+8)==1 and load(actual+16)==0,('allocated header',ordinal)
        oracle[selected:selected+1]=[(actual+requested,remaining)] if remaining>=32 else []
        pointer=load(ctx+16)
        for address,free_size in oracle:
            assert pointer==address,('free-chain address',ordinal)
            assert load(pointer)==free_size and load(pointer+8)==0,('free-chain header',ordinal)
            pointer=load(pointer+24)
        assert pointer==0,('free-chain tail',ordinal)
        trace.append(selected)
    return load(ctx+248),trace
def sweep_cycles(image,sweeper,reserve):
    context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context)
    store(ctx+56,1<<60);store(ctx+104,1);reserve.call(ctx,32)
    base=load(ctx+8);size=load(base+8);free=[(load(base+16),load(base+48))]
    allocated={};requests=[1184,416,32,40,80,160,928,1184]*8
    try:
        for cycle in range(4):
            for requested in requests:
                index=next(i for i,row in enumerate(free) if row[1]>=requested)
                address,extent=free[index];actual=image.call(ctx,requested,0)
                assert actual==address,('first-fit after sweep',cycle,requested)
                remaining=extent-requested;physical=requested if remaining>=32 else extent
                allocated[address]=physical
                free[index:index+1]=[(address+requested,remaining)] if remaining>=32 else []
            survivors={address:extent for i,(address,extent) in enumerate(sorted(allocated.items())) if i%3==cycle%3}
            for address in survivors:store(address+8,3)
            blocks=sorted(free+[(address,extent) for address,extent in allocated.items() if address not in survivors])
            merged=[]
            for address,extent in blocks:
                if merged and merged[-1][0]+merged[-1][1]==address:
                    start,old=merged[-1];merged[-1]=(start,old+extent)
                else:merged.append((address,extent))
            sweeper.call(ctx);pointer=load(ctx+16)
            for address,extent in merged:
                assert pointer==address,('free-chain sweep address',cycle)
                assert load(pointer)==extent and load(pointer+8)==0,('free-chain sweep header',cycle)
                pointer=load(pointer+24)
            assert pointer==0 and load(ctx+48)==sum(survivors.values()),('free-chain sweep tail/live',cycle)
            assert all(load(address+8)==1 for address in survivors),('sweep survivor',cycle)
            free=merged;allocated=survivors
        return 4*len(requests)
    finally:
        libc=ctypes.CDLL(None);libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        assert libc.munmap(base,size)==0
def execute(path,mutation):
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    group=records(path.read_text());code,entry=assemble(group['ARENA'],None if mutation=='disable-reset' else mutation)
    image=Image(code,entry,3);rc,re=assemble(group['RESET'],'disable-reset' if mutation=='disable-reset' else None,instrument=False);reset=Image(rc,re,1)
    cases=0;requests_total=0
    patterns=[[40],[40,80,160],[416],[40,416,80],[40,1184,160],[1000,1000,40]]
    vectors=[[1184,416]*4,[416,1184]*4,[1184,40,416,80,1184,160,416,40],[696,440,184,696,440,184,160,40],[928,1184]*4,[1184,416,672,1184,416,672,160,40]]
    for count in [0,1,7,64,257,2048]:
        for pattern in patterns:
            sizes=[pattern[i%len(pattern)] for i in range(count)]+[1048576]
            for request in vectors:
                for at in [None,3]:
                    sequence(image,reset,sizes,request,reset_at=at);cases+=1;requests_total+=len(request)
    for count in [0,1,31,257]:
        sequence(image,reset,[40]*count+[1048576],[1184,416,1184,40,80,928,32,1184],grow_at=3);cases+=1;requests_total+=8
    for seed in range(16):
        rng=random.Random(seed)
        sizes=[32+8*rng.randrange(512) for _ in range(128)]+[4194304]
        request=[32+8*rng.randrange(1024) for _ in range(256)]
        sequence(image,reset,sizes,request,reset_at=117);cases+=1;requests_total+=len(request)
    counts,trace=sequence(image,reset,[40]*2048+[1048576],[1184,416]*32)
    assert counts<=2*2049+62,('work bound alternating',counts)
    sizes=[40]*2048+[16777216];request=list(range(168,4097,8))
    counts,trace=sequence(image,reset,sizes,request)
    assert counts<=16*2049+len(request),('work bound increasing',counts)
    # Probe removal must preserve every selection on a representative sequence.
    normal,entry=assemble(group['ARENA'],instrument=False);plain=Image(normal,entry,3)
    request=[1184,416,40,928,1184,40,80,32]*8
    a=sequence(image,reset,[40]*257+[1048576],request,reset_at=19)[1]
    b=sequence(plain,reset,[40]*257+[1048576],request,reset_at=19)[1]
    assert a==b
    reserve_code,reserve_entry=assemble(group['ARENA'],instrument=False,entry_label=3000)
    reserve=Image(reserve_code,reserve_entry,2)
    sweep_code,sweep_entry=assemble(group['ARENA'],mutation if mutation=='disable-sweep-reset' else None,instrument=False,entry_label=3001)
    sweeper=Image(sweep_code,sweep_entry,1)
    gc_requests=sweep_cycles(image,sweeper,reserve)
    context=ctypes.create_string_buffer(256);ctx=ctypes.addressof(context)
    store(ctx+56,1<<60);store(ctx+104,1)
    mappings=[]
    try:
        for requested in [32,2097152,32]:
            prior=load(ctx+8);reserve.call(ctx,requested);base=load(ctx+8)
            assert base and base!=prior and load(base)==prior,('arena head',requested)
            size=load(base+8);mappings.append((base,size))
            assert load(base+32)==base+704,('bitmap offset',requested)
            assert ctypes.string_at(base+64,640)==bytes(640),('cold cache',requested)
            assert load(base+16)==load(base+32)+load(base+40),('payload offset',requested)
            assert load(base+24)<=base+size,('arena bounds',requested)
            expected=load(base+16);actual=image.call(ctx,32,0)
            assert actual==expected,('first-fit new arena',requested)
    finally:
        libc=ctypes.CDLL(None);libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        for address,size in mappings:assert libc.munmap(address,size)==0
    print(json.dumps({'status':'Passed','cases':cases+11,'requests':requests_total+64+len(list(range(168,4097,8)))+131+gc_requests,'mutation':mutation}))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--execute',type=Path);parser.add_argument('--mutation');args=parser.parse_args()
    if args.execute:execute(args.execute,args.mutation);return
    assert args.compiler and args.output
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'source';(project/'src').mkdir(parents=True)
    shutil.copyfile(ROOT/'compiler/mgnc/mognitio.toml',project/'mognitio.toml')
    for module in ['Data','Machine','WholeX64','WholeABI','WholeFit','WholeArena','WholeSweep']:
        shutil.copytree(ROOT/'compiler/mgnc/src'/module,project/'src'/module)
    shutil.copyfile(ROOT/'tests/mgnc/harnesses/v180-fit-cursors.mgn',project/'src/mgnc.mgn')
    command=[str(args.compiler.resolve()),'build',str(project/'mognitio.toml'),'-o',str(out/'emitter')]
    built=subprocess.run(command,capture_output=True,timeout=600)
    (out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr)
    assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),('build',built.returncode,built.stderr)
    emitted=subprocess.run([str(out/'emitter')],capture_output=True,timeout=120)
    (out/'records.txt').write_bytes(emitted.stdout);(out/'emit.stderr').write_bytes(emitted.stderr)
    assert emitted.returncode==0 and not emitted.stderr
    rows=[]
    for mutation in [None,'disable-cache','first-owner','second-owner','half-promotion','disable-repair','disable-reset','disable-sweep-reset']:
        cmd=[sys.executable,str(Path(__file__).resolve()),'--execute',str(out/'records.txt')]
        if mutation:cmd+=['--mutation',mutation]
        result=subprocess.run(cmd,capture_output=True,timeout=180)
        name=mutation or 'normal';(out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        if mutation:
            assert result.returncode!=0 and b'mutation membership' not in result.stderr
            assert any(word in result.stderr for word in [b'first-fit',b'free-chain',b'work bound']) or (mutation in ('disable-repair','disable-reset','disable-sweep-reset') and result.returncode in (92,93) and not result.stderr),('unexpected mutant rejection',mutation,result.returncode,result.stderr)
        else:assert result.returncode==0,result.stderr
        rows.append({'mutation':mutation,'exit':result.returncode,'status':'Passed'})
    (out/'receipt.json').write_text(json.dumps({'status':'Passed','source':{str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(project.rglob('*')) if p.is_file()},'compiler_sha256':hashlib.sha256(args.compiler.read_bytes()).hexdigest(),'rows':rows},indent=2)+'\n')
    print('NATIVE_FIT_CURSORS_OK controls=8')
if __name__=='__main__':main()
