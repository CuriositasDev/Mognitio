#!/usr/bin/env python3
"""Check complete scale fixtures and preserve every completed observation."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from v160_elf import elf
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path,required=True);p.add_argument("--fixtures",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--skip",action="append",default=[]);p.add_argument("--build-timeout",type=float,default=900);p.add_argument("--run-timeout",type=float,default=120);a=p.parse_args();a.output.mkdir()
manifest=a.fixtures/"manifest.json";cases=json.loads(manifest.read_text())
records=[{"name":c["name"],"status":"NotRun"} for c in cases]
report={"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),"build_guard_seconds":a.build_timeout,"run_guard_seconds":a.run_timeout,"records":records}
def save():(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
def inventory(case,folder):
 expected={item["path"] for item in case["inventory"]}
 actual={str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file()}
 assert actual==expected,(case["name"],"input membership",sorted(actual^expected))
 for item in case["inventory"]:
  data=(folder/item["path"]).read_bytes()
  assert len(data)==item["bytes"] and hashlib.sha256(data).hexdigest()==item["sha256"],(case["name"],"input inventory",item["path"])
save()
for c,row in zip(cases,records):
 name=c["name"];folder=a.fixtures/name
 if name in a.skip:continue
 x=a.output/name;start=time.monotonic();phase="inventory"
 try:
  assert hashlib.sha256(a.compiler.read_bytes()).hexdigest()==report["compiler_sha256"],"compiler changed"
  assert hashlib.sha256(manifest.read_bytes()).hexdigest()==report["manifest_sha256"],"manifest changed"
  inventory(c,folder);phase="build"
  r=subprocess.run([a.compiler,"build",folder/"mognitio.toml","-o",x],capture_output=True,timeout=a.build_timeout)
  (a.output/(name+".stdout")).write_bytes(r.stdout);(a.output/(name+".stderr")).write_bytes(r.stderr)
  row.update(exit=r.returncode,elapsed_seconds=time.monotonic()-start,stdout_sha256=hashlib.sha256(r.stdout).hexdigest(),stderr_sha256=hashlib.sha256(r.stderr).hexdigest())
  inventory(c,folder);row["input_unchanged"]=True
  assert r.returncode==c["build_status"] and not r.stdout,(name,r.returncode,r.stdout,r.stderr)
  if c["negative"]:
   assert not x.exists()
   expected=b"unsupported:" if c["axis"]=="closures" else b"type:"
   assert expected in r.stderr and b" [" in r.stderr,(name,r.stderr)
  else:
   assert not r.stderr
   data=x.read_bytes();elf(data);row["artifact_sha256"]=hashlib.sha256(data).hexdigest()
   if name.startswith("lifetime-"):
    args=["10000"]
   elif name=="io-resource":
    datafile=a.output/"text";datafile.write_bytes("四😀\0".encode());args=["100",str(datafile),"success"]
   else:args=[]
   phase="runtime"
   run=subprocess.run([x,*args],capture_output=True,timeout=a.run_timeout)
   row.update(runtime_exit=run.returncode,runtime_stdout_sha256=hashlib.sha256(run.stdout).hexdigest(),runtime_stderr_sha256=hashlib.sha256(run.stderr).hexdigest())
   assert (run.returncode,hashlib.sha256(run.stdout).hexdigest(),len(run.stdout),run.stderr.hex())==(c["run_status"],c["stdout_sha256"],c["stdout_bytes"],c["stderr_hex"]),(name,run.returncode,run.stdout,run.stderr,c)
  assert hashlib.sha256(a.compiler.read_bytes()).hexdigest()==report["compiler_sha256"],"compiler changed"
  assert hashlib.sha256(manifest.read_bytes()).hexdigest()==report["manifest_sha256"],"manifest changed"
  row["status"]="Passed";save();print(name,"PASS",flush=True)
 except BaseException as error:
  if isinstance(error,subprocess.TimeoutExpired):
   for stream,data in [("stdout",error.stdout),("stderr",error.stderr)]:
    (a.output/(name+"."+stream)).write_bytes(data or b"")
  row.update(status="Failed",phase=phase,reason=type(error).__name__,elapsed_seconds=time.monotonic()-start)
  save();raise
print("V160_SCALE_EXECUTION_OK passed="+str(sum(r["status"]=="Passed" for r in records))+" not_run="+str(sum(r["status"]=="NotRun" for r in records)),flush=True)
