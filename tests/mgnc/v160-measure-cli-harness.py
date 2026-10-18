#!/usr/bin/env python3
"""Drive the measurement CLI with controlled results and a real frozen inventory."""
import argparse, contextlib, hashlib, io, json, os, runpy, struct, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import v160_measurelib
p=argparse.ArgumentParser()
for name in ["scale","c0","c1","manifest","seed-receipt"]:p.add_argument("--"+name,type=Path,required=True)
a=p.parse_args();here=Path(__file__).resolve().parent
manifest=json.loads(a.manifest.read_text())
scale={c["name"]:c for c in json.loads((a.scale/"manifest.json").read_text())}
image=bytearray(128);image[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
struct.pack_into("<HHIQQQIHHHHHH",image,16,2,62,1,0x400078,64,0,0,64,56,1,0,0,0)
struct.pack_into("<IIQQQQQQ",image,64,1,5,0,0x400000,0x400000,len(image),len(image),4096)
sha=lambda data:hashlib.sha256(data).hexdigest()
checks=0
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);compiler=root/"compiler";compiler.write_bytes(b"controlled observer input")
    for scenario in ["pass","formal","warmup-failure","invalid-elf","late-cutoff","partial"]:
        output=root/scenario;calls=[]
        def observe(command,directory,**options):
            directory=Path(directory);directory.mkdir(parents=True)
            cell=next(c for c in manifest["cells"] if c["name"]==directory.parent.name)
            status=cell["exit"];stdout=b"";stderr=b""
            if cell["operation"]=="run":
                c=scale[cell["input"]]
                if c["axis"] in ["text-bytes","combined"]:
                    size=c["size"] if c["axis"]=="text-bytes" else 16384
                    stdout=("x"*(size-10)+"日本😀").encode()
            elif status!=0:stderr=("mgnc: "+cell["phase"]+": controlled [0,1)\n").encode()
            elif cell["operation"]=="build":
                target=Path(command[-1]);target.write_bytes(image);target.chmod(0o755)
                if scenario=="invalid-elf" and cell["input"]=="modules-8":target.write_bytes(b"invalid")
            cutoff=None
            if scenario=="warmup-failure" and not calls:status=3
            if scenario=="late-cutoff" and not calls:cutoff="wall"
            calls.append((cell["name"],directory.name))
            (directory/"stdout").write_bytes(stdout);(directory/"stderr").write_bytes(stderr)
            return dict(exit=status,signal=None,seconds=.01,peak_rss_bytes=1024,cutoff=cutoff,
                        harness_failure=None,descendant_residue=0,unreaped_descendants=0)
        argv=[str(here/"v160-measure.py"),"--compiler",str(compiler),"--output",str(output)]
        for name in ["scale","c0","c1","manifest","seed-receipt"]:argv+=["--"+name,str(getattr(a,name.replace("-","_")))]
        if scenario=="partial":argv+=["--only","modules-8-build","--only","modules-8-run-0"]
        if scenario=="formal":
            identity=json.loads((root/"pass/results.json").read_text())["identity"]
            budget=dict(schema=1,status="accepted",accepted_at="2026-10-18",warmups=1,recorded_runs=3,
                        cells={c["name"]:dict(wall_median_seconds=.02,rss_max_bytes=1024,
                        wall_cutoff_seconds=1,observed_rss_cutoff_bytes=2048) for c in manifest["cells"]},**identity)
            policy=root/"synthetic-test-budget.json";policy.write_text(json.dumps(budget));argv+=["--formal-budget",str(policy)]
        with patch.object(sys,"argv",argv),patch.object(v160_measurelib,"observe",observe),contextlib.redirect_stdout(io.StringIO()):
            try:runpy.run_path(argv[0],run_name="__main__")
            except SystemExit as error:code=error.code
            else:raise AssertionError("missing CLI exit")
        report=json.loads((output/"results.json").read_text())
        if scenario in ["pass","formal"]:
            assert code==0 and report["complete"] and len(calls)==412
            assert all([r["kind"] for r in c["runs"]]==["warmup","run-1","run-2","run-3"] for c in report["cells"])
        elif scenario=="partial":
            assert code==0 and not report["complete"] and len(calls)==8
            assert sum(c["status"]=="NotRun" for c in report["cells"])==101
        else:
            assert code==1 and not report["complete"]
            failed=[c for c in report["cells"] if c["status"]=="Failed"];assert failed
            assert all(len(c["runs"])==1 for c in failed)
            if scenario=="invalid-elf":
                rejected=next(c for c in failed if c["name"]=="modules-8-build")
                assert rejected["runs"][0]["input_unchanged"] and rejected["runs"][0]["artifact_failure"]
                assert next(c for c in report["cells"] if c["name"]=="modules-8-run-0")["status"]=="NotRun"
        checks+=1
print("V160_MEASURE_CLI_HARNESS_OK scenarios="+str(checks))
