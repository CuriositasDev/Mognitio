#!/usr/bin/env python3
"""Exercise actual emitted collector code against independently constructed ABI data.

The sweep entry is a no-op so tests can inspect mark states directly. This tests
precise scan decisions; the public alpha runner separately covers heap lifetime.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = r'''namespace Mgnc;
use Mgnc\Data\{empty,number};use Mgnc\Machine\{Code,Record,flush};use Mgnc\WholeCollect\{emit as collect};use Mgnc\WholeMark\{emit as mark};use Std\Io\{writeStdout};
let scalar:Function(Int):String=function(value:Int):String{branch when{value<0=>"-"+number(-value),else=>number(value)}};
let main:Function(List<String>):Int=function(args:List<String>):Int{let code:Code=flush(collect(mark(Code{records:empty<Record>(),nextLabel:256,pending:List<Int>[]})));loop over(code->records->pages->append(code->records->tail) as page:List<Record>){loop over(page as record:Record){var line:String=number(record->kind)+" "+scalar(record->value)+" "+number(record->target);loop over(record->bytes as byte:Int){line=line+" "+number(byte);};discard writeStdout(line+"\n");};};0};
'''
C_TEST = r'''#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
extern void gc_test(uint64_t*);
static uint64_t* add(uint64_t*heap,size_t *cursor,uint64_t*bitmap,size_t size,size_t descriptor){
 uint64_t*p=(uint64_t*)((uint8_t*)heap+*cursor);bitmap[*cursor/8/64]|=1ULL<<(*cursor/8%64);*cursor+=size;p[0]=size;p[1]=1;p[2]=descriptor;return p;
}
static void leaf(uint64_t*p){p[3]=1;p[4]=3;((uint32_t*)(p+5))[0]=7;((uint32_t*)(p+5))[1]=0;((uint32_t*)(p+5))[2]=17;}
int main(void){
 uint64_t context[32]={0},arena[8]={0},bitmap[16]={0};uint64_t*heap=aligned_alloc(16,4096);memset(heap,0,4096);size_t cursor=0;
 uint64_t *big=add(heap,&cursor,bitmap,56,0),*globalbig=add(heap,&cursor,bitmap,56,0),*rawonly=add(heap,&cursor,bitmap,56,0),*bufferbig=add(heap,&cursor,bitmap,56,0);
 leaf(big);leaf(globalbig);leaf(rawonly);leaf(bufferbig);
 uint64_t*productbig=add(heap,&cursor,bitmap,56,0),*variantbig=add(heap,&cursor,bitmap,56,0),*boxbig=add(heap,&cursor,bitmap,56,0),*closurebig=add(heap,&cursor,bitmap,56,0);leaf(productbig);leaf(variantbig);leaf(boxbig);leaf(closurebig);
 uint64_t *product=add(heap,&cursor,bitmap,56,1);product[3]=(uintptr_t)productbig;product[4]=0;product[5]=(uintptr_t)rawonly;product[6]=19;
 uint64_t *buffer=add(heap,&cursor,bitmap,64,2);buffer[3]=3;buffer[4]=0;buffer[5]=15;buffer[6]=(uintptr_t)bufferbig;buffer[7]=1;
 uint64_t*sum=add(heap,&cursor,bitmap,40,3),*box=add(heap,&cursor,bitmap,32,4),*closure=add(heap,&cursor,bitmap,40,5),*env=add(heap,&cursor,bitmap,32,6);sum[3]=0;sum[4]=(uintptr_t)variantbig;box[3]=(uintptr_t)boxbig;closure[3]=0xfeedface;closure[4]=(uintptr_t)env;env[3]=(uintptr_t)closurebig;
 uint64_t row0[]={1,33},row1[]={0};uint64_t d0[]={4,40,0,0,0},d1[]={0,56,3,0,0,25,32,49},d2[]={2,0,0,0,2};uint64_t d3[]={1,40,0,2,0,(uintptr_t)row0,(uintptr_t)row1},d4[]={0,32,1,0,0,25},d5[]={0,40,1,0,0,32},d6[]={0,32,1,0,0,25};uint64_t*descriptors[]={d0,d1,d2,d3,d4,d5,d6};
 arena[2]=(uintptr_t)heap;arena[3]=(uintptr_t)((uint8_t*)heap+cursor);arena[4]=(uintptr_t)bitmap;
 context[1]=(uintptr_t)arena;context[12]=(uintptr_t)descriptors;context[13]=7;
 uint64_t slots[]={ (uintptr_t)rawonly,(uintptr_t)closure,(uintptr_t)box,(uintptr_t)sum,(uintptr_t)buffer,(uintptr_t)product,(uintptr_t)big,1};
 uint64_t map[]={4294967296ULL+8,127,3};uint64_t frame[]={0,(uintptr_t)&slots[7]+72,(uintptr_t)map};context[0]=(uintptr_t)frame;
 uint64_t globals[]={ (uintptr_t)globalbig,13,(uintptr_t)rawonly};uint64_t globalmap[]={4294967296ULL+3,3,3};context[16]=(uintptr_t)globals;context[17]=3;context[18]=(uintptr_t)globalmap;
 gc_test(context);
 assert(big[1]==3&&globalbig[1]==3&&product[1]==3&&buffer[1]==3&&bufferbig[1]==3);assert(rawonly[1]==1);assert(productbig[1]==3&&variantbig[1]==3&&boxbig[1]==3&&closurebig[1]==3&&env[1]==3&&closure[1]==3&&box[1]==3&&sum[1]==3);assert(context[10]==13);
 for(size_t at=0;at<cursor;){uint64_t*o=(uint64_t*)((uint8_t*)heap+at);o[1]=1;at+=o[0];}
 uint64_t wideSlots[66];for(int i=0;i<66;i++)wideSlots[i]=(uintptr_t)rawonly;wideSlots[1]=129;wideSlots[0]=(uintptr_t)globalbig;
 uint64_t wideMap[]={4294967296ULL+66,0,3,0,3};frame[1]=(uintptr_t)&wideSlots[65]+72;frame[2]=(uintptr_t)wideMap;context[17]=0;gc_test(context);assert(globalbig[1]==3&&rawonly[1]==1&&context[10]==1);
 for(size_t at=0;at<cursor;){uint64_t*o=(uint64_t*)((uint8_t*)heap+at);o[1]=1;at+=o[0];}
 uint64_t legacySlot=(uintptr_t)product,legacyMap[]={1,1};frame[1]=(uintptr_t)&legacySlot+72;frame[2]=(uintptr_t)legacyMap;gc_test(context);assert(product[1]==3&&productbig[1]==3&&rawonly[1]==1&&context[10]==2);
 puts("GC_NATIVE_TAGGED_OK immediate/global/frame/product/variant/box/closure/buffer/raw/multiword/legacy");free(heap);return 0;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='v200-tagged-gc-') as temporary:
        work = Path(temporary)
        src = work / 'src'
        src.mkdir()
        (work / 'mognitio.toml').write_text('[project]\nname = "gcprobe"\nroot_namespace = "Mgnc"\n')
        (src / 'gcprobe.mgn').write_text(GENERATOR)
        pending, seen = ['WholeCollect', 'WholeMark'], set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            for original in (ROOT / 'compiler/mgnc/src' / name).glob('*.mgn'):
                text = original.read_text()
                target = src / name / original.name
                target.parent.mkdir(exist_ok=True)
                target.write_text(text)
                pending.extend(re.findall(r'use Mgnc\\(\w+)\\', text))
        probe = work / 'probe'
        subprocess.run([str(args.seed.resolve()), 'build', str(work / 'mognitio.toml'), '-o', str(probe)], check=True)
        result = subprocess.run([str(probe)], check=True, capture_output=True)
        assembly = ['.intel_syntax noprefix', '.text', '.global gc_test', 'gc_test:', 'push r15', 'mov r15,rdi', 'call mgn_11', 'pop r15', 'ret']
        for row in result.stdout.decode().splitlines():
            kind, value, target, *octets = map(int, row.split())
            if octets:
                assembly.append('.byte ' + ','.join(map(str, octets)))
            if kind == 1:
                assembly.append('mgn_' + str(target) + ':')
            elif kind == 2:
                assembly.append('.long mgn_' + str(target) + ' - . - 4')
            elif kind == 3:
                assembly.append('.long ' + str(value))
            elif kind == 4:
                assembly.append('.quad ' + str(value))
            elif kind == 5:
                assembly.append('.quad mgn_' + str(target))
        assembly.extend(['mgn_15:', 'ret', 'mgn_1:', 'mgn_2:', 'ud2', '.section .note.GNU-stack,"",@progbits'])
        (work / 'runtime.S').write_text('\n'.join(assembly) + '\n')
        (work / 'test.c').write_text(C_TEST)
        binary = work / 'collector'
        subprocess.run(['gcc', '-no-pie', '-O0', str(work / 'test.c'), str(work / 'runtime.S'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
