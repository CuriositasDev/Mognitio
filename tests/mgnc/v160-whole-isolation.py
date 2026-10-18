#!/usr/bin/env python3
"""Check and lower complete fixed corpora without the compiler toolchain."""
import argparse,hashlib,json,os,stat,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser()
for key in ["repository","compiler","userland","c0","c1","output"]:p.add_argument("--"+key,type=Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.repository/"tests/mgnc"))
from isolated import prefix
def sha(b):return hashlib.sha256(b).hexdigest()
def inventory(root):
 rows=[]
 for p in sorted(root.rglob("*")):
  if p.is_symlink():rows.append([str(p.relative_to(root)),"link",os.readlink(p)])
  elif p.is_file():rows.append([str(p.relative_to(root)),stat.S_IMODE(p.stat().st_mode),sha(p.read_bytes())])
 return rows
a.output.mkdir();work=a.output/"empty";work.mkdir()
userland=inventory(a.userland);compiler=sha(a.compiler.read_bytes())
report=dict(compiler_sha256=compiler,userland_inventory_sha256=sha(json.dumps(userland,sort_keys=True).encode()),userland_files=len(userland),userland_release=(a.userland/"etc/os-release").read_text(),nonroot=os.getuid()!=0,records=[])
for name,corpus in [("C0",a.c0),("C1",a.c1)]:
 before=inventory(corpus)
 for verb in ["check","lower"]:
  command=prefix(a.userland,a.compiler,work)+["--ro-bind",str(corpus),"/corpus","/emitter",verb,"/corpus/mognitio.toml"]
  start=time.monotonic()
  try:r=subprocess.run(command,capture_output=True,timeout=900);status=r.returncode;out=r.stdout;err=r.stderr;timeout=False
  except subprocess.TimeoutExpired as e:status=None;out=e.stdout or b"";err=e.stderr or b"";timeout=True
  stem=name+"-"+verb;(a.output/(stem+".stdout")).write_bytes(out);(a.output/(stem+".stderr")).write_bytes(err)
  correct=(status,out,err)==(0,b"",b"") and not timeout and inventory(corpus)==before and not list(work.iterdir())
  report["records"].append(dict(name=stem,command=command,input_inventory=before,exit=status,timeout=timeout,elapsed_seconds=time.monotonic()-start,stdout_sha256=sha(out),stderr_sha256=sha(err),passed=correct))
  (a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
  print(stem,correct,flush=True)
  assert correct,stem
assert inventory(a.userland)==userland and sha(a.compiler.read_bytes())==compiler
report["passed"]=True;(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
