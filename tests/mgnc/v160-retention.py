#!/usr/bin/env python3
"""Same-source normal execution and independent runtime retention witnesses."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser()
for name in ["seed","compiler","source","output"]:p.add_argument("--"+name,type=Path,required=True)
a=p.parse_args();a.output.mkdir();here=Path(__file__).resolve().parent;fixtures=here/"fixtures/v160-retention"
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
patchfile=here/"v160-retention-patches.json";patches=json.loads(patchfile.read_text());project=a.output/"compiler"
shutil.copytree(a.source,project)
before=[dict(path=str(p.relative_to(project)),sha256=sha(p)) for p in sorted(project.rglob("*.mgn"))]
for patch in patches:
 p=project/patch["path"];s=p.read_text();assert s.count(patch["match"])==patch["count"],patch["path"];p.write_text(s.replace(patch["match"],patch["replacement"]))
after=[dict(path=str(p.relative_to(project)),sha256=sha(p)) for p in sorted(project.rglob("*.mgn"))]
report=dict(compiler_sha256=sha(a.compiler),patch_manifest_sha256=sha(patchfile),normal_sources=before,observed_sources=after,records=[])
(a.output/"sources.json").write_text(json.dumps(report,indent=2)+"\n")
observed=a.output/"a";r=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",observed],capture_output=True,timeout=900)
(a.output/"build.stdout").write_bytes(r.stdout);(a.output/"build.stderr").write_bytes(r.stderr)
assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),r
report["observed_compiler_sha256"]=sha(observed)
for c in json.loads((fixtures/"manifest.json").read_text()):
 source=fixtures/(c["name"]+".mgn");assert sha(source)==c["source_sha256"]
 normal=a.output/(c["name"]+"-normal");marked=a.output/(c["name"]+"-observed")
 for compiler,image in [(a.compiler,normal),(observed,marked)]:
  r=subprocess.run([compiler,"build",source,"-o",image],capture_output=True,timeout=180);assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),r
 r=subprocess.run([normal],capture_output=True,timeout=180);assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),r
 output=a.output/(c["name"]+".json")
 r=subprocess.run([sys.executable,here/"v160-retention-observe.py","--report",output,"--text",c["text"],"--mode",c["mode"],marked],capture_output=True,timeout=180)
 (a.output/(c["name"]+".stdout")).write_bytes(r.stdout);(a.output/(c["name"]+".stderr")).write_bytes(r.stderr)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(c["name"],r)
 data=json.loads(output.read_text());assert data["passed"]
 report["records"].append(dict(name=c["name"],source_sha256=sha(source),normal_sha256=sha(normal),observed_sha256=sha(marked),witnesses=len(data["witnesses"]),report_sha256=sha(output),passed=True))
 (a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n");print(c["name"],"PASS",len(data["witnesses"]),flush=True)
report["controls"]=[]
for c in json.loads((fixtures/"controls.json").read_text()):
 source=fixtures/(c["name"]+".mgn");assert sha(source)==c["source_sha256"];image=a.output/c["name"]
 r=subprocess.run([observed,"build",source,"-o",image],capture_output=True,timeout=180);assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),r
 output=a.output/(c["name"]+".json")
 r=subprocess.run([sys.executable,here/"v160-retention-observe.py","--report",output,"--text",c["text"],"--mode",c["mode"],image],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(1,b"",b""),(c["name"],r)
 data=json.loads(output.read_text());assert data["exit"]==0 and data["stress"] and not data["passed"] and not data["witnesses"]
 report["controls"].append(dict(name=c["name"],source_sha256=sha(source),artifact_sha256=sha(image),report_sha256=sha(output),correctly_rejected=True))
 (a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n");print(c["name"],"REJECTED",flush=True)
assert sha(a.compiler)==report["compiler_sha256"]
print("V160_RETENTION_OK cases="+str(len(report["records"])))
