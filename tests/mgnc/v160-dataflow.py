#!/usr/bin/env python3
"""Exercise assignment and current-subject variant facts, including loop meets."""
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
harness = ROOT / "tests/mgnc/harnesses/v160-dataflow.mgn"
print(json.dumps({"harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
                  "valid": [0, 7, 10], "rejected": [1, 2, 3, 4, 5, 6, 8, 9]}),
      flush=True)
with tempfile.TemporaryDirectory(prefix="mgnc-v160-dataflow-") as temporary:
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
    assert result.stdout == b"V160_DATAFLOW_OK valid=3 rejected=8\n"
    print(result.stdout.decode(), end="")
