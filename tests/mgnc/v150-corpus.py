#!/usr/bin/env python3
"""Freeze a complete source inventory and observe one bounded project check."""
import argparse,hashlib,json,subprocess,tempfile,time,resource
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C0="4908a1a91be61d64695b9e048b833637aee0aefc"
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--corpus",choices=["C0","C1"],required=True);p.add_argument("--evidence",required=True,type=Path);args=p.parse_args()
def sha(data):return hashlib.sha256(data).hexdigest()
if args.corpus=="C0":
 paths=subprocess.check_output(["git","ls-tree","-r","--name-only",C0,"compiler/mgnc/src"],cwd=ROOT,text=True).splitlines()
 files={path:subprocess.check_output(["git","show",C0+":"+path],cwd=ROOT) for path in paths if path.endswith(".mgn")}
 manifest=subprocess.check_output(["git","show",C0+":compiler/mgnc/mognitio.toml"],cwd=ROOT)
 revision=C0
else:
 files={path.relative_to(ROOT).as_posix():path.read_bytes() for path in (ROOT/"compiler/mgnc/src").rglob("*.mgn")}
 manifest=(ROOT/"compiler/mgnc/mognitio.toml").read_bytes()
 revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
inventory=[{"path":path,"bytes":len(files[path]),"sha256":sha(files[path])} for path in sorted(files)]
inventory_hash=sha("".join(row["sha256"]+"  "+row["path"]+"\n" for row in inventory).encode())
if args.corpus=="C0":
 assert len(inventory)==57 and sum(r["bytes"] for r in inventory)==823559
 assert inventory_hash=="9f0a7f789d99d91da9257f7a7d816d437961eadf540c3f78c1c0adfa5460e177"
 assert sha(manifest)=="aa004c27dd46461893d674154416d45aabbb4c73502b4b91d1a12fa46e303ba2"
with tempfile.TemporaryDirectory(prefix="v150-corpus-") as temp:
 root=Path(temp);project=root/"compiler/mgnc";project.mkdir(parents=True)
 for path,data in files.items():
  target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 (project/"mognitio.toml").write_bytes(manifest)
 metrics=root/"metrics";command=[str(args.compiler.resolve()),"check",str(project/"mognitio.toml")]
 started=time.monotonic()
 try:
  result=subprocess.run(["/usr/bin/time","-f","%e %M","-o",str(metrics),"timeout","600",*command],capture_output=True,timeout=605)
  timedout=result.returncode==124
 except subprocess.TimeoutExpired as error:
  result=subprocess.CompletedProcess(command,124,error.stdout or b"",error.stderr or b"");timedout=True
 elapsed=time.monotonic()-started
 measured=metrics.read_text().splitlines()[-1].split() if metrics.exists() and metrics.stat().st_size else []
 rss=int(measured[1])*1024 if len(measured)==2 else None
 record={"corpus":args.corpus,"revision":revision,"compiler_sha256":sha(args.compiler.read_bytes()),"inventory":inventory,"inventory_sha256":inventory_hash,"manifest_sha256":sha(manifest),"command":["A","check","CORPUS/compiler/mgnc/mognitio.toml"],"seconds":elapsed,"peak_rss_bytes":rss,"timeout":timedout,"exit":result.returncode,"stdout_hex":result.stdout.hex(),"stderr":result.stderr.decode(errors="replace")}
 record["passed"]=result.returncode==0 and result.stdout==result.stderr==b"" and not timedout and rss is not None and rss<=4096*2**20
 args.evidence.write_text(json.dumps(record,indent=2)+"\n")
 assert record["passed"],{k:v for k,v in record.items() if k!="inventory"}
 print(json.dumps({k:v for k,v in record.items() if k not in ("inventory","stderr")},sort_keys=True))
