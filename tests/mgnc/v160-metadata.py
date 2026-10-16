#!/usr/bin/env python3
"""Check semantic facts required by whole-project lowering."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--seed", required=True, type=Path)
parser.add_argument("--interpret", action="store_true")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="mgnc-v160-metadata-") as temporary:
    work = Path(temporary)
    project = work / "compiler"
    shutil.copytree(ROOT / "compiler/mgnc", project)
    shutil.copyfile(ROOT / "tests/mgnc/harnesses/v160-metadata.mgn",
                    project / "src/mgnc.mgn")
    if args.interpret:
        command = [args.seed, "run", project / "mognitio.toml"]
    else:
        binary = work / "probe"
        built = subprocess.run([args.seed, "build", project / "mognitio.toml",
                                "-o", binary], capture_output=True, timeout=900)
        assert built.returncode == 0, built.stderr.decode()
        command = [binary]
    result = subprocess.run(command, capture_output=True, timeout=300)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stderr == b"", result.stderr
    assert result.stdout == b"V160_METADATA_OK literals=1 loops=1 patterns=1 nested=2\n"
    print(result.stdout.decode(), end="")
