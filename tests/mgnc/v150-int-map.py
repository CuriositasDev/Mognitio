#!/usr/bin/env python3
import argparse,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);args=p.parse_args()
with tempfile.TemporaryDirectory(prefix="v150-int-map-") as temp:
 work=Path(temp);(work/"src").mkdir()
 for module in ["Data","Tables","IntMap"]:shutil.copytree(ROOT/"compiler/mgnc/src"/module,work/"src"/module)
 (work/"src/app.mgn").write_text((ROOT/"tests/mgnc/harnesses/v150-int-map.mgn").read_text())
 (work/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="Mgnc"\n')
 result=subprocess.run([str(args.seed),"build",str(work/"mognitio.toml"),"-o",str(work/"probe")],capture_output=True)
 assert result.returncode==0,result.stderr.decode()
 result=subprocess.run([work/"probe"],capture_output=True,timeout=60)
 assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
 print(result.stdout.decode(),end="")
