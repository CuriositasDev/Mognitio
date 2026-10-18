#!/usr/bin/env python3
"""Observe fixed-program lifetime and resource loops across increasing counts."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
for name in ["compiler","fixtures","output"]:p.add_argument("--"+name,type=Path,required=True)
a=p.parse_args();a.compiler=a.compiler.resolve();a.output.mkdir()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
manifest=a.fixtures/"manifest.json";cases={c["name"]:c for c in json.loads(manifest.read_text())}
names=["lifetime-bounded","lifetime-retained","io-resource"]
records=[dict(program=name,arguments=args,status="NotRun") for name in names for args in cases[name]["arguments"]]
assert len(records)==15
report=dict(schema=1,stage="functional-lifetime-observation",compiler_sha256=sha(a.compiler),
            fixture_manifest_sha256=sha(manifest),builds=[],records=records,complete=False)
def save():(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
def inventory(name):
    folder=a.fixtures/name;expected={r["path"] for r in cases[name]["inventory"]}
    assert {str(x.relative_to(folder)) for x in folder.rglob("*") if x.is_file()}==expected
    for row in cases[name]["inventory"]:
        path=folder/row["path"];assert path.stat().st_size==row["bytes"] and sha(path)==row["sha256"]
def identity():
    assert sha(a.compiler)==report["compiler_sha256"] and sha(manifest)==report["fixture_manifest_sha256"]
save();valid=a.output/"valid";valid.write_bytes("四😀\0".encode());invalid=a.output/"invalid";invalid.write_bytes(b"\xff")
for name in names:
    identity();inventory(name);image=a.output/name
    build=dict(program=name,status="Running");report["builds"].append(build);save()
    try:
        result=subprocess.run([a.compiler,"build",a.fixtures/name/"mognitio.toml","-o",image],capture_output=True,timeout=900)
        build.update(exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex())
        assert (result.returncode,result.stdout,result.stderr)==(0,b"",b"")
        identity();inventory(name);build.update(status="Passed",artifact_sha256=sha(image));save()
    except BaseException as error:
        if isinstance(error,subprocess.TimeoutExpired):build.update(stdout_hex=(error.stdout or b"").hex(),stderr_hex=(error.stderr or b"").hex())
        build.update(status="Failed",reason=type(error).__name__+": "+str(error));save();raise
    for row in (r for r in records if r["program"]==name):
        arguments=list(row["arguments"]);tag="-".join(arguments)
        if name=="io-resource":
            count,mode=arguments;arguments=[count,str({"success":valid,"decode":invalid,"read":Path("/proc/self/mem")}[mode]),mode]
        observed=a.output/(name+"-"+tag+".json");row["status"]="Running";save()
        try:
            result=subprocess.run([sys.executable,HERE/"v160-native-observe.py","--report",observed,"--",image,*arguments],capture_output=True,timeout=900)
            row.update(exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex())
            assert (result.returncode,result.stdout,result.stderr)==(0,b"",b"")
            data=json.loads(observed.read_text())
            assert data["heap"]["resources"]==0 and data["high"]["fds"]<=(4 if name=="io-resource" else 3)
            identity();inventory(name);assert sha(image)==build["artifact_sha256"]
            row.update(status="Passed",observation=observed.name,observation_sha256=sha(observed),
                       heap=data["heap"],high=data["high"])
            save();print(name,tag,"PASS",flush=True)
        except BaseException as error:
            if isinstance(error,subprocess.TimeoutExpired):row.update(stdout_hex=(error.stdout or b"").hex(),stderr_hex=(error.stderr or b"").hex())
            row.update(status="Failed",reason=type(error).__name__+": "+str(error));save();raise
report["complete"]=all(r["status"]=="Passed" for r in records);save()
print("V160_NATIVE_LIFETIME_OK observations=15")
