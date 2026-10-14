#!/usr/bin/env python3
"""Check generated fixture expectations once; this is not a measurement run."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--fixtures",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
manifest=json.loads((a.fixtures/"manifest.json").read_text())
report={"stage":"fixture-functional-preflight","compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":[]}
for cell in manifest["cells"]:
 if cell["axis"]=="corpus":continue
 for file in cell["inventory"]:assert hashlib.sha256((a.fixtures/cell["name"]/file["path"]).read_bytes()).hexdigest()==file["sha256"]
 try:
  r=subprocess.run([a.compiler,"check",a.fixtures/cell["name"]/"mognitio.toml"],capture_output=True,timeout=600)
  valid=r.returncode==cell["expected_exit"] and not r.stdout and (not r.stderr if cell["expected_exit"]==0 else ("mgnc: "+cell["phase"]+":").encode() in r.stderr)
  row={"name":cell["name"],"exit":r.returncode,"stderr":r.stderr.decode(),"passed":valid}
 except subprocess.TimeoutExpired as error:row={"name":cell["name"],"timeout":True,"passed":False}
 report["records"].append(row);a.evidence.write_text(json.dumps(report,indent=2)+"\n");print(cell["name"],row["passed"],flush=True)
report["passed"]=all(row["passed"] for row in report["records"]);a.evidence.write_text(json.dumps(report,indent=2)+"\n")
assert report["passed"],[row for row in report["records"] if not row["passed"]]
print("V150_SCALE_PREFLIGHT_OK",len(report["records"]),flush=True)
