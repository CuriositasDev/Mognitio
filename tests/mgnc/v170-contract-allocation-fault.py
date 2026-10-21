#!/usr/bin/env python3
"""Fail one package constructor allocation while observing its live root record."""
import argparse,ctypes,importlib.util,json,os,re,signal,struct
from pathlib import Path
spec=importlib.util.spec_from_file_location('fault',Path(__file__).with_name('syscall-fault.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['box','package'],required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('program',type=Path);args=parser.parse_args();program=args.program.resolve();data=program.read_bytes();assert data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==62
size,descriptor_offset=(32,24) if args.stage=='box' else (48,32)
prefix=b'\x48\xbf'+struct.pack('<Q',size)+b'\x48\x8b\xb5'+struct.pack('<i',descriptor_offset)
suffix=(b'\x48\x8b\x95'+struct.pack('<i',56)+b'\x48\x89\x90'+struct.pack('<i',24)+b'\x48\x89\x85'+struct.pack('<i',-72)) if args.stage=='box' else (b'\x48\x8b\x95'+struct.pack('<i',-72)+b'\x48\x89\x90'+struct.pack('<i',24)+b'\x48\x8b\x95'+struct.pack('<i',40))
offsets=[match.start()+len(prefix) for match in re.finditer(re.escape(prefix)+b'\xe8.{4}'+re.escape(suffix),data,re.S)];assert offsets,('missing package allocation instruction',args.stage)
phoff=struct.unpack_from('<Q',data,32)[0];phsize,phcount=struct.unpack_from('<HH',data,54)
def address(offset):
    for index in range(phcount):
        kind,flags,file_offset,virtual,physical,file_size,memory_size,alignment=struct.unpack_from('<IIQQQQQQ',data,phoff+index*phsize)
        if kind==1 and flags&1 and file_offset<=offset<file_offset+file_size:return virtual+offset-file_offset
    raise AssertionError(('allocation outside executable load',offset))
pid=os.fork()
if pid==0:m.ptrace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execv(str(program),[str(program)])
os.waitpid(pid,0);m.ptrace(0x4200,pid,0,ctypes.c_void_p(1));mem=None;executed=False;injected=False;breakpoints={};snapshot=None
def read(pointer,count):return os.pread(mem,count,pointer)
def word(pointer):return struct.unpack('<Q',read(pointer,8))[0]
def write(pointer,value):assert os.pwrite(mem,struct.pack('<Q',value),pointer)==8
try:
    while True:
        m.ptrace(24,pid,0,ctypes.c_void_p(0));_,status=os.waitpid(pid,0)
        if os.WIFEXITED(status):
            result=os.WEXITSTATUS(status);assert injected and result==4,(injected,result);break
        assert not os.WIFSIGNALED(status),('signal',os.WTERMSIG(status));stop=os.WSTOPSIG(status);registers=m.Registers();m.ptrace(12,pid,0,ctypes.byref(registers))
        if stop==signal.SIGTRAP:
            if not executed:
                executed=True;mem=os.open(f'/proc/{pid}/mem',os.O_RDWR)
                for offset in offsets:
                    target=address(offset);old=read(target,8);assert len(old)==8 and old[0]==232;breakpoints[target]=old;assert os.pwrite(mem,b'\xcc'+old[1:],target)==8
                continue
            target=registers.rip-1;assert target in breakpoints and not injected,('unexpected breakpoint',target)
            for pointer,original in breakpoints.items():assert os.pwrite(mem,original,pointer)==len(original)
            registers.rip=target;m.ptrace(13,pid,0,ctypes.byref(registers));context=registers.r15;frame=registers.rbp;root=word(context);assert root==frame-64 and word(root+8)==frame
            bitmap=word(root+16);assert (word(bitmap),word(bitmap+8))==(1,1);box=word(frame-72);payload=word(frame+56);assert registers.rdi==size and word(context+168)==0 and word(context+176)==0
            snapshot=dict(root_frame=root,frame=frame,bitmap_count=1,bitmap_word=1,box=box,payload=payload,requested_bytes=size,allocation_before=word(context+32),primary_before=word(context+176),resources_before=word(context+168))
            if args.stage=='box':assert box==0
            else:
                assert box and box%8==0 and word(box)==32 and word(box+16)==word(frame+24) and word(box+24)==payload
                descriptor=word(word(context+96)+word(box+16)*8);assert word(descriptor)==0 and word(descriptor+8)==32;references=word(descriptor+16);assert references in (0,1)
                if references:assert word(descriptor+40)==24
                snapshot.update(box_descriptor=word(box+16),box_references=references,box_payload=word(box+24))
            write(context+152,1);write(context+160,snapshot['allocation_before']+1);injected=True;continue
        assert stop==(signal.SIGTRAP|0x80),stop
    args.report.write_text(json.dumps(dict(stage=args.stage,exit=result,injected=injected,snapshot=snapshot),indent=2)+'\n')
finally:
    if mem is not None:os.close(mem)
    try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
    except (ProcessLookupError,ChildProcessError):pass
