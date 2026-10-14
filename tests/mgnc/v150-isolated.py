#!/usr/bin/env python3
"""Whole-corpus check and A -> P -> X in a toolchain-free Ubuntu userland."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess,tempfile,time
from pathlib import Path
from isolated import prefix
from native import elf
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--fixtures",required=True,type=Path);p.add_argument("--userland",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
def sha(data):return hashlib.sha256(data).hexdigest()
def inventory(root):
 records=[]
 for path in sorted(root.rglob("*")):
  relative=path.relative_to(root).as_posix()
  if path.is_symlink():records.append([relative,"link",os.readlink(path)])
  elif path.is_file():records.append([relative,stat.S_IMODE(path.stat().st_mode),sha(path.read_bytes())])
 return records
userland=a.userland.resolve();release=(userland/"etc/os-release").read_text()
assert 'VERSION_ID="24.04"' in release or 'VERSION_ID="26.04"' in release
environment=inventory(userland)
assert not any(Path(row[0]).name in {"sbcl","mgn","mgnc","gcc","clang","as","ld","python3"} or row[0].endswith(".mgn") for row in environment)
record={"compiler_sha256":sha(a.compiler.read_bytes()),"environment":{"name":userland.name,"os_release":release,"inventory_sha256":sha(json.dumps(environment,sort_keys=True).encode()),"files":len(environment),"kernel":os.uname().release},"functional_only":True,"records":[]}
def save():a.evidence.write_text(json.dumps(record,indent=2)+"\n")
manifest=json.loads((a.fixtures/"manifest.json").read_text())
with tempfile.TemporaryDirectory(prefix="v150-isolation-") as temp:
 root=Path(temp);inputs=root/"input";inputs.mkdir();output=root/"output";output.mkdir();(output/"input").mkdir()
 for corpus in ["C0","C1"]:
  cell=next(c for c in manifest["cells"] if c["name"]==corpus)
  assert sha((a.fixtures/corpus/"mognitio.toml").read_bytes())==cell["manifest_sha256"]
  for item in cell["inventory"]:assert sha((a.fixtures/corpus/item["path"]).read_bytes())==item["sha256"]
  shutil.copytree(a.fixtures/corpus,inputs/corpus)
 baseline=inventory(inputs)
 for corpus in ["C0","C1"]:
  trace=a.evidence.with_suffix("."+corpus+".trace");command=prefix(userland,a.compiler.resolve(),output)+["--ro-bind",inputs,"/output/input","/emitter","check","/output/input/"+corpus+"/mognitio.toml"]
  started=time.monotonic()
  try:result=subprocess.run(["strace","-f","-qq","-e","trace=%file,execve,execveat","-o",trace,*map(str,command)],capture_output=True,timeout=1800)
  except subprocess.TimeoutExpired as error:
   record["records"].append({"corpus":corpus,"timeout":True,"passed":False});save();raise
  trace_text=trace.read_text();executions=[line for line in trace_text.splitlines() if "execve(" in line or "execveat(" in line]
  passed=(result.returncode,result.stdout,result.stderr)==(0,b"",b"") and inventory(inputs)==baseline and {p.name for p in output.iterdir()}=={"input"} and len(executions)==2 and '"/emitter"' in executions[-1]
  row={"corpus":corpus,"seconds":time.monotonic()-started,"exit":result.returncode,"stdout_hex":result.stdout.hex(),"stderr":result.stderr.decode(),"exec_count_including_sandbox":len(executions),"input_unchanged":inventory(inputs)==baseline,"output_directory_unchanged":{p.name for p in output.iterdir()}=={"input"},"trace_sha256":sha(trace.read_bytes()),"passed":passed}
  record["records"].append(row);save();assert passed,row
  print("V150_ISOLATED_CORPUS",userland.name,corpus,flush=True)
 source=output/"input.mgn";source.write_text("namespace App;let helper:Function(Int):Int=function(value:Int):Int{value+3};let main:Function(List<String>):Int=function(args:List<String>):Int{helper(args->length())};")
 result=subprocess.run(prefix(userland,a.compiler.resolve(),output)+["/emitter","build","input.mgn","-o","program"],capture_output=True,timeout=120)
 assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),result
 artifact=output/"program";elf(artifact.read_bytes());empty=root/"empty";empty.mkdir()
 runtime=[]
 for count in [0,3]:
  result=subprocess.run(prefix(userland,artifact,empty)+["/emitter"]+["x"]*count,capture_output=True,timeout=10)
  assert (result.returncode,result.stdout,result.stderr)==(count+3,b"",b""),result
  runtime.append({"arguments":count,"exit":result.returncode})
 record["generation"]={"source_sha256":sha(source.read_bytes()),"artifact_sha256":sha(artifact.read_bytes()),"runtime":runtime,"passed":True}
 record["passed"]=all(row["passed"] for row in record["records"]);save()
 print("V150_ISOLATED_OK",userland.name,flush=True)
