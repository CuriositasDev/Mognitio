#!/usr/bin/env python3
"""Reject binary helper mutations independently of the lowering producer."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--seed',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
args.output=args.output.resolve()
args.output.mkdir(parents=True,exist_ok=False)
project=args.output/'compiler'
shutil.copytree(ROOT/'compiler/mgnc',project)
shutil.copy2(ROOT/'tests/mgnc/harnesses/v170-binary-functions.mgn',project/'src/mgnc.mgn')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inventory=[{'path':p.relative_to(project).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(project.rglob('*')) if p.is_file()]
(args.output/'inputs.json').write_text(json.dumps(inventory,indent=2)+'\n')
artifact=args.output/'probe'
build=subprocess.run([str(args.seed.resolve()),'build',str(project/'mognitio.toml'),'-o',str(artifact)],capture_output=True,timeout=900)
(args.output/'build.stdout').write_bytes(build.stdout)
(args.output/'build.stderr').write_bytes(build.stderr)
assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),(build.returncode,build.stderr)
run=subprocess.run([str(artifact)],capture_output=True,timeout=180)
(args.output/'run.stdout').write_bytes(run.stdout)
(args.output/'run.stderr').write_bytes(run.stderr)
expected=b'V170_BINARY_FUNCTION_IR_OK valid=1 rejected=20\n'
assert run.returncode==0 and run.stderr==b'' and run.stdout.endswith(expected) and run.stdout.count(b'V170_BINARY_FUNCTION_MUTANT ')==20,(run.returncode,run.stdout,run.stderr)
assert all(sha(project/row['path'])==row['sha256'] for row in inventory)
print(run.stdout.decode(),end='')
