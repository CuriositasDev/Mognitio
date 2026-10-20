#!/usr/bin/env python3
"""Apply the immutable v1.5 semantic criteria to a new compiler and the old inputs."""
import argparse,hashlib,json,os,platform,statistics,sys,time
from pathlib import Path
p=argparse.ArgumentParser()
for name in ["repository","compiler","fixtures","output"]:p.add_argument("--"+name,type=Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.repository/"tests/mgnc"))
from v150_budget import load_budget,within_budget
from v160_measurelib import observe
def sha(data):return hashlib.sha256(data).hexdigest()
evidence=a.repository/"verification/v1.5.0-formal-performance"
raw=(evidence/"budget.json").read_bytes();assert sha(raw)=="49f2ce1d984122ec7aa81c66b234e3b6c62abcd68a2dbffe799666519b4e043f"
manifest_raw=(a.fixtures/"manifest.json").read_bytes();assert sha(manifest_raw)=="8e310e4d01a75deb988ce309ebef348bb693f1123c19f3c700d662c2fde4f9e8"
assert manifest_raw==(evidence/"semantic-fixtures.json").read_bytes()
manifest=json.loads(manifest_raw);identity=json.loads((evidence/"identity.json").read_text())
budget=load_budget(json.loads(raw),compiler_sha256=identity["compiler_sha256"],fixture_sha256=sha(manifest_raw),manifest=manifest,seed_sha256=identity["seed_receipt"]["sha256"])
digest=sha(a.compiler.read_bytes());a.output.mkdir()
cpu=Path("/proc/cpuinfo").read_text();release=Path("/etc/os-release").read_text()
assert "i9-10850K" in cpu and 'VERSION_ID="26.04"' in release and os.getuid()!=0 and platform.machine()=="x86_64"
report=dict(stage="inherited-v1.5-regression",compiler_sha256=digest,immutable_budget_sha256=sha(raw),fixture_manifest_sha256=sha(manifest_raw),original_budget_candidate_sha256=identity["compiler_sha256"],new_budget_adopted=False,warmups=1,recorded_runs=3,environment=dict(cpu=next(x for x in cpu.splitlines() if x.startswith("model name")),kernel=platform.release(),os_release=release,meminfo=Path("/proc/meminfo").read_text(),python=platform.python_version(),nonroot=True,governors={str(p):p.read_text().strip() for p in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")}),cells=[dict(name=c["name"],status="NotRun",runs=[]) for c in manifest["cells"]])
def save():(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
def inputs(cell):
 root=a.fixtures/cell["name"]
 assert sha((root/"mognitio.toml").read_bytes())==cell["manifest_sha256"]
 assert {str(p.relative_to(root)) for p in (root/"src").rglob("*") if p.is_file()}=={r["path"] for r in cell["inventory"]}
 result={}
 for row in cell["inventory"]+[dict(path="mognitio.toml",sha256=cell["manifest_sha256"])]:
  path=root/row["path"];assert sha(path.read_bytes())==row["sha256"]
  s=path.stat();result[row["path"]]=(s.st_mode,s.st_mtime_ns,s.st_size,s.st_ino,s.st_dev)
 return result
save()
for cell,row in zip(manifest["cells"],report["cells"]):
 before=inputs(cell);limits=budget["cells"][cell["name"]];row["limits"]=limits;row["status"]="Running";save()
 for i in range(4):
  kind="warmup" if i==0 else "run-"+str(i);directory=a.output/cell["name"]/kind
  assert sha(a.compiler.read_bytes())==digest
  load=Path("/proc/loadavg").read_text().strip()
  result=observe([a.compiler,"check",a.fixtures/cell["name"]/"mognitio.toml"],directory,timeout=limits["wall_cutoff_seconds"],rss_limit=limits["observed_rss_cutoff_bytes"])
  out=(directory/"stdout").read_bytes();err=(directory/"stderr").read_bytes()
  unchanged=inputs(cell)==before and sha(a.compiler.read_bytes())==digest
  correct=result["exit"]==cell["expected_exit"] and not out and (not err if cell["expected_exit"]==0 else ("mgnc: "+cell["phase"]+":").encode() in err)
  detail=cell.get("detail") or {}
  if detail.get("primary_start") is not None:correct=correct and ("[%s,%s)"%(detail["primary_start"],detail["primary_end"])).encode() in err
  correct=correct and unchanged and result["cutoff"] is None and result["harness_failure"] is None
  row["runs"].append(dict(kind=kind,loadavg=load,input_unchanged=unchanged,correct=correct,**result));save()
  print(cell["name"],kind,correct,round(result["seconds"],3),result["peak_rss_bytes"],flush=True)
  if not correct:break
 row["passed"]=within_budget(row["runs"],limits);row["status"]="Passed" if row["passed"] else "Failed"
 if len(row["runs"])==4 and all(x["correct"] for x in row["runs"]):
  row["wall_median_seconds"]=statistics.median(x["seconds"] for x in row["runs"][1:]);row["rss_max_bytes"]=max(x["peak_rss_bytes"] for x in row["runs"][1:])
 save()
report["passed"]=all(c["status"]=="Passed" for c in report["cells"]);save()
print("V160_INHERITED_PERFORMANCE",report["passed"],"cells",len(report["cells"]))
raise SystemExit(not report["passed"])
