#!/usr/bin/env python3
"""Check pruning-map boundaries, persistence, fallback and generator provenance."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EXPECTED = b"V170_INT_MAP_OK boundaries=17 levels=12 updates=2048 dense_updates=1024 high_updates=64 snapshots=true\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=ROOT / "bin/mgn")
    args = parser.parse_args()
    subprocess.run(["python3", "-B", str(ROOT / "tests/mgnc/generate-prune-memo.py"), "--check"], check=True)
    with tempfile.TemporaryDirectory(prefix="prune-memo-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        for module in ("Data", "IntMap", "PruneMemo"):
            shutil.copytree(ROOT / "compiler/mgnc/src" / module, root / "src" / module)
        # Reuse the independent existing map oracle, including cross-boundary
        # writes and retained snapshots. Its historical stdout stays unchanged.
        source = (ROOT / "tests/mgnc/harnesses/v170-int-map.mgn").read_text()
        assert source.count("use Mgnc\\IntMap\\{") == 1
        source = source.replace("use Mgnc\\IntMap\\{", "use Mgnc\\PruneMemo\\{")
        (root / "src/mgnc.mgn").write_text(source)
        (root / "mognitio.toml").write_text('[project]\nname="mgnc"\nroot_namespace="Mgnc"\n')
        image = root / "probe"
        built = subprocess.run([str(args.compiler.resolve()), "build", str(root / "mognitio.toml"), "-o", str(image)], capture_output=True, timeout=600)
        assert (built.returncode, built.stdout, built.stderr) == (0, b"", b""), built
        ran = subprocess.run([str(image)], capture_output=True, timeout=180)
        assert (ran.returncode, ran.stdout, ran.stderr) == (0, EXPECTED, b""), ran
        print("PRUNE_MEMO_OK boundaries persistence fallback negative-keys")
if __name__ == "__main__":
    main()
