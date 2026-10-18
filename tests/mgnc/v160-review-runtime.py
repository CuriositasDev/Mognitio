#!/usr/bin/env python3
"""Runtime-owned module snapshots and nested specialization under forced GC."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
here=Path(__file__).resolve().parent;fixtures=here/"fixtures/v160-review-runtime"
manifest=fixtures/"manifest.json";rows=json.loads(manifest.read_text());digest=lambda b:hashlib.sha256(b).hexdigest()
report=dict(compiler_sha256=digest(a.compiler.read_bytes()),manifest_sha256=digest(manifest.read_bytes()),records=[])
for row in rows:
 source=fixtures/(row["name"]+".mgn");assert digest(source.read_bytes())==row["source_sha256"]
 image=a.output/row["name"];r=subprocess.run([a.compiler,"build",source,"-o",image],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(row["name"],r)
 for stress in (False,True):
  command=[image]
  observation=a.output/(row["name"]+"-stress.json")
  if stress:command=[sys.executable,here/"v160-native-observe.py","--stress","--report",observation,"--",image]
  r=subprocess.run(command,capture_output=True,timeout=180)
  passed=(r.returncode,r.stdout,r.stderr)==(row["expected_exit"],b"",b"")
  state=json.loads(observation.read_text()) if stress else None
  if stress:passed=passed and state["stress"] and state["heap"]["collections"]>0 and state["heap"]["primary"]==0
  report["records"].append(dict(name=row["name"],design_cells=row["design_cells"],stress=stress,exit=r.returncode,stdout_hex=r.stdout.hex(),stderr_hex=r.stderr.hex(),source_sha256=row["source_sha256"],artifact_sha256=digest(image.read_bytes()),observation=state,passed=passed))
  (a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
  assert passed,(row["name"],stress,r)
  print(row["name"],stress,"PASS",flush=True)
assert digest(a.compiler.read_bytes())==report["compiler_sha256"]
print("V160_REVIEW_RUNTIME_OK cases="+str(len(rows))+" observations="+str(len(report["records"])))
