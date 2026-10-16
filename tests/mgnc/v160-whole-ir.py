#!/usr/bin/env python3
"""Check whole-source correspondence and independent semantic/IR ID permutations."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=Path, required=True)
args = parser.parse_args()
harness = ROOT / "tests/mgnc/harnesses/v160-whole-ir.mgn"
print(json.dumps({"harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
                  "valid": 3, "mutations": 13}),
      flush=True)
with tempfile.TemporaryDirectory(prefix="mgnc-v160-whole-ir-") as temporary:
    work = Path(temporary)
    project = work / "compiler"
    shutil.copytree(ROOT / "compiler/mgnc", project)
    shutil.copyfile(harness, project / "src/mgnc.mgn")
    binary = work / "probe"
    built = subprocess.run([args.seed, "build", project / "mognitio.toml",
                            "-o", binary], capture_output=True, timeout=900)
    assert built.returncode == 0, built.stderr.decode()
    result = subprocess.run([binary], capture_output=True, timeout=120)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stderr == b"", result.stderr
    assert result.stdout.endswith(b"V160_WHOLE_IR_OK valid=3 rejected=13\n")
    assert result.stdout.count(b"V160_MUTANT ") == 13
    print(result.stdout.decode(), end="")
