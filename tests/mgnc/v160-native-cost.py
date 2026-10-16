import subprocess,json,sys,time
from pathlib import Path
import argparse,shutil,hashlib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path);p.add_argument("--compiler",type=Path);p.add_argument("--fixtures",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
a=args.compiler;fixtures=args.fixtures;out=args.output;out.mkdir()
if a is None:
 assert args.seed,"--seed or an observed --compiler is required"
 project=out/"compiler";shutil.copytree(ROOT/"compiler/mgnc",project)
 shutil.copyfile(HERE/"harnesses/v160-native-driver.mgn",project/"src/Driver/driver.mgn")
 patches=json.loads((HERE/"v160-native-cost-patches.json").read_text())
 for change in patches:
  path=project/change["path"];text=path.read_text()
  assert text.count(change["match"])==change["count"],change["path"]
  path.write_text(text.replace(change["match"],change["replacement"]))
 inventory=[{"path":str(path.relative_to(project)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(project.rglob("*.mgn"))]
 (out/"observed-source.json").write_text(json.dumps(inventory,indent=2)+"\n")
 a=out/"a";built=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",a],capture_output=True,timeout=900)
 assert (built.returncode,built.stdout,built.stderr)==(0,b"",b""),(built.returncode,built.stdout,built.stderr)
a=a.resolve()
for c in json.loads((fixtures/"cases.json").read_text()):
 x=out/c["name"];r=subprocess.run([a,"build",fixtures/(c["name"]+".mgn"),"-o",x],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(c["name"],"build",r.returncode,r.stdout,r.stderr)
 report=out/(c["name"]+".json")
 r=subprocess.run([sys.executable,HERE/"v160-native-observe.py","--markers","--report",report,"--",x],capture_output=True,timeout=180)
 assert (r.returncode,r.stdout.hex(),r.stderr)==(0,c["stdout_hex"],b""),(c["name"],"run",r.returncode,r.stdout,r.stderr)
 data=json.loads(report.read_text());expected={str(i):c["expected_totals"].get(str(i),0) for i in range(1,14)}
 actual={str(i):data["totals"].get(str(i),0) for i in range(1,14)}
 assert actual==expected,(c["name"],actual,expected)
 print(c["name"],"PASS",actual,flush=True)
print("PUBLIC_COST_OK cells=78",flush=True)
