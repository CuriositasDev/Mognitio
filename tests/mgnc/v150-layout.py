#!/usr/bin/env python3
import argparse,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);args=p.parse_args()
with tempfile.TemporaryDirectory(prefix="v150-layout-") as temp:
 work=Path(temp);shutil.copytree(ROOT/"compiler/mgnc",work/"compiler")
 (work/"compiler/src/mgnc.mgn").write_text((ROOT/"tests/mgnc/harnesses/v150-layout.mgn").read_text())
 binary=work/"probe"
 result=subprocess.run([str(args.seed),"build",str(work/"compiler/mognitio.toml"),"-o",str(binary)],capture_output=True)
 assert result.returncode==0,result.stderr.decode()
 result=subprocess.run([binary],capture_output=True,timeout=120)
 assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
 assert result.stdout==b"V150_LAYOUT_OK valid=2 mutations=13\n",result.stdout
 print(result.stdout.decode(),end="")
