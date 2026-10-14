#!/usr/bin/env python3
"""Run the adopted preliminary profile without adopting a formal budget."""
import argparse,hashlib,json,os,platform,statistics,time
from pathlib import Path
from v150_measurelib import observe
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--fixtures",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--only",action="append");a=p.parse_args()
compiler=a.compiler.resolve();fixtures=a.fixtures.resolve();a.output.mkdir(parents=True,exist_ok=False)
def sha(data):return hashlib.sha256(data).hexdigest()
manifest=json.loads((fixtures/"manifest.json").read_text())
cpu=Path("/proc/cpuinfo").read_text();release=Path("/etc/os-release").read_text()
assert "i9-10850K" in cpu and 'VERSION_ID="26.04"' in release and os.getuid()!=0 and platform.machine()=="x86_64"
environment={"cpu":next(line.split(":",1)[1].strip() for line in cpu.splitlines() if line.startswith("model name")),"meminfo":Path("/proc/meminfo").read_text(),"os_release":release,"kernel":platform.release(),"uid_nonroot":True,"python":platform.python_version(),"governors":{str(f.relative_to("/sys/devices/system/cpu")):f.read_text().strip() for f in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")},"cache":"Normal OS filesystem cache retained; fresh compiler process for every run.","initial_loadavg":Path("/proc/loadavg").read_text().strip()}
report={"schema":1,"stage":"preliminary-only","formal_budget_adopted":False,"compiler_sha256":sha(compiler.read_bytes()),"fixture_manifest_sha256":sha((fixtures/"manifest.json").read_bytes()),"environment":environment,"profile":{"warmups":1,"recorded_runs":3,"wall_cutoff_seconds":600,"observed_rss_cutoff_bytes":4096*1024**2,"sample_interval_seconds":.05,"peak_source":"wait4 ru_maxrss KiB * 1024","aggregation":"median wall and maximum RSS only when all runs are correct"},"selection":a.only,"cells":[]}
def save():(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
def verify(cell):
 root=fixtures/cell["name"]
 assert sha((root/"mognitio.toml").read_bytes())==cell["manifest_sha256"]
 expected={row["path"] for row in cell["inventory"]}
 assert {p.relative_to(root).as_posix() for p in (root/"src").rglob("*") if p.is_file()}==expected
 state={}
 for row in cell["inventory"]+[{"path":"mognitio.toml","sha256":cell["manifest_sha256"]}]:
  path=root/row["path"];data=path.read_bytes();assert sha(data)==row["sha256"]
  stat=path.stat();state[row["path"]]=(stat.st_mode,stat.st_mtime_ns,stat.st_size)
 return state
save()
for cell in manifest["cells"]:
 if a.only and cell["name"] not in a.only:continue
 assert sha(compiler.read_bytes())==report["compiler_sha256"]
 before=verify(cell);record={"name":cell["name"],"axis":cell["axis"],"size":cell["size"],"runs":[],"completed":False};report["cells"].append(record);save()
 for index in range(4):
  runname="warmup" if index==0 else f"run-{index}"
  load=Path("/proc/loadavg").read_text().strip()
  directory=a.output/cell["name"]/runname
  result=observe([compiler,"check",fixtures/cell["name"]/"mognitio.toml"],directory)
  stdout=(directory/"stdout").read_bytes();stderr=(directory/"stderr").read_bytes()
  correct=result["exit"]==cell["expected_exit"] and not stdout and (not stderr if cell["expected_exit"]==0 else ("mgnc: "+cell["phase"]+":").encode() in stderr)
  details=cell.get("detail") or {}
  if details.get("primary_start") is not None:
   correct=correct and f'[{details["primary_start"]},{details["primary_end"]})'.encode() in stderr
  try:
   unchanged=verify(cell)==before
   input_failure=None
  except (AssertionError,OSError) as error:
   unchanged=False
   input_failure=type(error).__name__+": "+str(error)
  correct=correct and unchanged and result["cutoff"] is None and result["harness_failure"] is None
  record["runs"].append({"kind":runname,"loadavg":load,"command":["A","check",cell["name"]+"/mognitio.toml"],"input_unchanged":unchanged,"input_failure":input_failure,"correct":correct,**result});save()
  print(cell["name"],runname,"correct="+str(correct),"seconds="+str(round(result["seconds"],3)),flush=True)
  if not correct:
   record["not_run"]=[{"kind":f"run-{j}","reason":"Earlier run failed; no replacement or success-only aggregation."} for j in range(max(1,index+1),4)]
   break
 if len(record["runs"])==4 and all(r["correct"] for r in record["runs"]):
  measured=record["runs"][1:];record.update(completed=True,wall_median_seconds=statistics.median(r["seconds"] for r in measured),rss_max_bytes=max(r["peak_rss_bytes"] for r in measured))
 save()
report["all_selected_completed"]=all(c["completed"] for c in report["cells"])
report["full_profile_selected"]=a.only is None and len(report["cells"])==len(manifest["cells"])
save()
print("V150_PRELIMINARY_RECORDED cells="+str(len(report["cells"]))+" completed="+str(sum(c["completed"] for c in report["cells"])),flush=True)
raise SystemExit(0 if report["all_selected_completed"] else 1)
