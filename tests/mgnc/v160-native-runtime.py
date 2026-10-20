#!/usr/bin/env python3
"""Exercise generated native values and I/O through the isolated full backend."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path);p.add_argument("--seed",type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
compiler=a.compiler
if compiler is None:
 assert a.seed,"--compiler or --seed is required"
 project=a.output/"compiler";shutil.copytree(ROOT/"compiler/mgnc",project)
 compiler=a.output/"a"
 r=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",compiler],capture_output=True,timeout=900)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(r.returncode,r.stdout,r.stderr)
compiler=compiler.resolve()
cases=json.loads((HERE/"v160-native-values.json").read_text());values=a.output/"values";values.mkdir()
for name,c in cases.items():
 source=values/(name+".mgn");source.write_text(c["source"]);x=values/name
 r=subprocess.run([compiler,"build",source,"-o",x],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(name,"build",r.returncode,r.stdout,r.stderr)
 r=subprocess.run([x,*c["args"]],capture_output=True,timeout=120)
 assert (r.returncode,r.stdout,r.stderr)==(c["status"],c["stdout"].encode(),c["stderr"].encode()),(name,"run",r.returncode,r.stdout,r.stderr)
 print(name,"PASS",flush=True)
subprocess.run([sys.executable,HERE/"v160-native-io.py",compiler,a.output/"io"],check=True,timeout=300)
expected={"diamond":(11,b""),"nested-snapshot":(0,b""),"snapshot":(0,b""),"type-import":(4,b"panic: type dependency\n"),"unused":(0,b""),"unused-import":(4,b"panic: unused dependency\n")}
for name,(status,stderr) in expected.items():
 target=a.output/("module-"+name)
 r=subprocess.run([compiler,"build",HERE/"fixtures/v160-module"/name/"mognitio.toml","-o",target],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(name,r.returncode,r.stdout,r.stderr)
 r=subprocess.run([target],capture_output=True,timeout=120)
 assert (r.returncode,r.stdout,r.stderr)==(status,b"",stderr),(name,r.returncode,r.stdout,r.stderr)
 print("module",name,"PASS",flush=True)
for name in ("closure","list","unicode","args","result","at-int","at-error","slice","slice-error","join","scalars","empty-text","loop-capture","callee-arguments","partial-product","partial-list","argument-lifetime"):
 c=cases[name];report=a.output/("stress-"+name+".json")
 r=subprocess.run([sys.executable,HERE/"v160-native-observe.py","--stress","--report",report,"--",values/name,*c["args"]],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(c["status"],c["stdout"].encode(),c["stderr"].encode()),(name,"stress",r.returncode,r.stdout,r.stderr)
 data=json.loads(report.read_text());assert data["heap"]["collections"]>0 and data["heap"]["primary"]==0
 print("stress",name,"PASS",flush=True)
print("V160_NATIVE_RUNTIME_OK values=41 io=26 modules=6 stress=17",flush=True)
