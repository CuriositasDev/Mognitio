#!/usr/bin/env python3
"""Check a permuted DAG once and reject the prior numeric scheduling policy."""
import argparse, re, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
sources={}
for path in (ROOT/"compiler/mgnc/src").rglob("*.mgn"):
    text=path.read_text();match=re.search(r"namespace ([A-Za-z0-9_\\]+);",text)
    if match:sources[match.group(1)]=(path,text)
harness=(ROOT/"tests/mgnc/harnesses/v160-root-order.mgn").read_text()
pending=re.findall(r"use (Mgnc\\[A-Za-z0-9_\\]+)\\\{",harness);selected={}
while pending:
    name=pending.pop()
    if name in selected:continue
    path,text=sources[name];selected[name]=(path,text)
    pending+=re.findall(r"use (Mgnc\\[A-Za-z0-9_\\]+)\\\{",text)
for variant in ["ordered","numeric-order-mutant"]:
    project=a.output/variant;project.mkdir();(project/"src").mkdir()
    shutil.copyfile(ROOT/"compiler/mgnc/mognitio.toml",project/"mognitio.toml")
    (project/"src/mgnc.mgn").write_text(harness)
    for path,text in selected.values():
        target=project/"src"/path.relative_to(ROOT/"compiler/mgnc/src");target.parent.mkdir(parents=True,exist_ok=True)
        if variant=="numeric-order-mutant" and "namespace Mgnc\\WholeRootFlow;" in text:
            old=" var queue:Paged<Int>=try postorder(body);var pending:Map=create();"
            new=" var queue:Paged<Int>=empty<Int>();var pending:Map=create();id=body->blocks->count;loop while(id>0){id=id-1;queue=push<Int>(queue,id);};"
            assert old in text;text=text.replace(old,new)
        target.write_text(text)
    binary=project/"probe"
    result=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
    assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(variant,result.returncode,result.stdout,result.stderr)
    result=subprocess.run([binary],capture_output=True,timeout=120)
    expected=(0,b"V160_ROOT_ORDER_OK blocks=64 updates=64\n",b"") if variant=="ordered" else (1,b"whole IR: root order repeated DAG updates\n",b"")
    assert (result.returncode,result.stdout,result.stderr)==expected,(variant,result.returncode,result.stdout,result.stderr)
    (project/"results.log").write_bytes(result.stdout)
    print(variant,"PASS",flush=True)
print("V160_ROOT_ORDER_CHECK_OK positive=1 rejected=1")
