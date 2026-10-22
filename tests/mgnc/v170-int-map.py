#!/usr/bin/env python3
"""Compile radix boundary and persistent-snapshot cases with a selected compiler."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = b"V170_INT_MAP_OK boundaries=17 levels=12 updates=2048 dense_updates=1024 high_updates=64 snapshots=true\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    with tempfile.TemporaryDirectory(prefix="v170-int-map-") as temporary:
        project = Path(temporary)
        (project / "src").mkdir()
        for module in ("Data", "IntMap"):
            shutil.copytree(ROOT / "compiler/mgnc/src" / module, project / "src" / module)
        shutil.copyfile(ROOT / "tests/mgnc/harnesses/v170-int-map.mgn", project / "src/app.mgn")
        (project / "mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="Mgnc"\n')
        image = project / "probe"
        result = subprocess.run([compiler, "build", project / "mognitio.toml", "-o", image],
                                capture_output=True, timeout=300)
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), result
        result = subprocess.run([image], capture_output=True, timeout=180)
        assert (result.returncode, result.stdout, result.stderr) == (0, EXPECTED, b""), result
        print(result.stdout.decode(), end="")


if __name__ == "__main__":
    main()
