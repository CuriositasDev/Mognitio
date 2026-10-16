#!/usr/bin/env python3
"""Validate generated native tables and machine invariants with negative controls."""
import argparse,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
project=a.output/"compiler";shutil.copytree(ROOT/"compiler/mgnc",project)
shutil.copyfile(HERE/"harnesses/v160-native-verifiers.mgn",project/"src/mgnc.mgn")
binary=a.output/"probe"
r=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(r.returncode,r.stdout,r.stderr)
r=subprocess.run([binary],capture_output=True,timeout=120)
assert r.returncode==0 and r.stderr==b"" and r.stdout.count(b"MUTANT ")==11 and b"V160_NATIVE_VERIFIERS_OK valid=2 rejected=11\n" in r.stdout,(r.returncode,r.stdout,r.stderr)
(a.output/"results.log").write_bytes(r.stdout);print(r.stdout.decode(),end="")
