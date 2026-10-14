#!/usr/bin/env python3
"""Inject acquisition/enumeration/read/cleanup failures at the compiler project entry."""
import argparse,hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix="v150-project-faults-") as temp:
 root=Path(temp);project=root/"input";(project/"src/Unused").mkdir(parents=True)
 manifest=project/"mognitio.toml";manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
 (project/"src/app.mgn").write_text("namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{0};")
 (project/"src/Unused/unused.mgn").write_text("namespace App\\Unused;let value:Int=1;")
 def inventory():return {p.relative_to(project).as_posix():(p.stat().st_mode,hashlib.sha256(p.read_bytes()).hexdigest()) for p in project.rglob("*") if p.is_file()}
 before=inventory();trace=root/"trace"
 baseline=subprocess.run(["strace","-qq","-o",trace,a.compiler,"check",manifest],capture_output=True,timeout=120)
 assert (baseline.returncode,baseline.stdout,baseline.stderr)==(0,b"",b""),baseline
 calls={}
 for line in trace.read_text().splitlines():
  match=re.match(r"([a-z0-9_]+)\(",line)
  if match:calls.setdefault(match[1],[]).append(line)
 numbers={"newfstatat":262,"statx":332,"openat":257,"read":0,"getdents64":217,"close":3}
 assert len(calls.get("getdents64",[]))>=4,calls.keys()
 records=[]
 for name,number in numbers.items():
  count=len(calls.get(name,[]))
  if not count:continue
  for ordinal in sorted({1,min(2,count),count}):
   command=[sys.executable,Path(__file__).with_name("syscall-fault.py"),"--syscall",str(number),"--ordinal",str(ordinal),"--errno","5"]
   if name=="close":command+=["--after"]
   result=subprocess.run(command+["--",a.compiler,"check",manifest],capture_output=True,timeout=120)
   good=result.returncode==2 and not result.stdout and (b"mgnc: io:" in result.stderr or b"mgnc: manifest:" in result.stderr) and inventory()==before
   records.append({"syscall":name,"ordinal":ordinal,"after":name=="close","exit":result.returncode,"stderr":result.stderr.decode(),"input_unchanged":inventory()==before,"passed":good})
   a.evidence.write_text(json.dumps({"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":records},indent=2)+"\n")
   print(name,ordinal,good,flush=True)
 assert all(r["passed"] for r in records),[r for r in records if not r["passed"]]
 print("V150_PROJECT_FAULTS_OK checks="+str(len(records)))
