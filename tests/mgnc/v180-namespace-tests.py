#!/usr/bin/env python3
"""Observe real namespace descendant memory and owned cutoff cleanup."""
import argparse
import json
import subprocess
from pathlib import Path
from v180_runner import namespace
from v180_observer import observe
from v180_evidence import canonical, file_record, require

p=argparse.ArgumentParser()
p.add_argument("--userland",type=Path,required=True)
p.add_argument("--output",type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
source=a.output/"source";source.mkdir()
# This independent observer control is not a compiler output or product backend.
assembly=a.output/"memory-control.s"
assembly.write_text('.global _start\n.text\n_start:\n mov $9,%rax\n xor %rdi,%rdi\n mov $100663296,%rsi\n mov $3,%rdx\n mov $34,%r10\n mov $-1,%r8\n xor %r9,%r9\n syscall\n mov %rax,%rdi\n mov $100663296,%rcx\n mov $1,%al\n rep stosb\n sub $16,%rsp\n movq $0,(%rsp)\n movq $500000000,8(%rsp)\n mov %rsp,%rdi\n xor %rsi,%rsi\n mov $35,%rax\n syscall\n mov $60,%rax\n xor %rdi,%rdi\n syscall\n')
control=a.output/"memory-control"
subprocess.run(["gcc","-nostdlib","-static","-o",str(control),str(assembly)],check=True)
rows=[]
for name,limit in [("normal",256*1024**2),("rss-kill",32*1024**2)]:
    output=a.output/(name+"-output");output.mkdir()
    command=namespace(a.userland,source,output,builder=control)+["/compiler"]
    result=observe(command,a.output/(name+"-raw"),timeout=5,rss_limit=limit)
    require(result["unreaped_descendants"]==0,"unreaped control process")
    if name=="normal":
        require(result["exit"]==0 and result["harness_failure"] is None
                and result["descendant_residue"]==0,"namespace normal lifecycle")
        require(result["sampled_peak_rss_bytes"]>96*1024**2,"descendant memory not observed")
    else:
        require(result["cutoff"]=="rss","namespace RSS guard missed target")
    rows.append(dict(name=name,command=command,result=result))
(a.output/"results.json").write_bytes(canonical(dict(status="Passed",control=file_record(control),rows=rows)))
print("NAMESPACE_MEMORY_CONTROLS_OK",len(rows))
