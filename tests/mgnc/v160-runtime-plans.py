#!/usr/bin/env python3
"""Check root/layout plans and their independent negative controls."""
import argparse,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args();args.output.mkdir()
project=args.output/"project";shutil.copytree(ROOT/"compiler/mgnc",project)
shutil.copyfile(ROOT/"tests/mgnc/harnesses/v160-runtime-plans.mgn",project/"src/mgnc.mgn")
binary=args.output/"probe"
result=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(result.returncode,result.stdout,result.stderr)
result=subprocess.run([binary],capture_output=True,timeout=120)
assert result.returncode==0 and not result.stderr,(result.returncode,result.stdout,result.stderr)
assert result.stdout.count(b"V160_ROOT_MUTANT ")==9 and result.stdout.count(b"V160_LAYOUT_MUTANT ")==8
assert b"V160_RUNTIME_PLAN_OK instances=52 descriptors=76 rejected=17\n" in result.stdout
(args.output/"results.log").write_bytes(result.stdout);print(result.stdout.decode(),end="")
