#!/usr/bin/env python3
"""Check native captured snapshots and compare resolved example tokens with a qualified reference."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.selfhost.analysis import analyze


def check(compiler, build, reference):
    def run(snap):
        with tempfile.TemporaryDirectory() as tmp:
            return analyze(compiler, build, 12, Path(tmp), snap)

    standalone = {"root": None, "sources": {"file:///single.mgn": "let x: String = true;\r\n"}}
    single = run(standalone)
    assert single["complete"] and not single["diagnostics"] and single["tokens"]["file:///single.mgn"], single
    source = "// 🐈\r\nlet invalid = ;"
    standalone["sources"]["file:///bad.mgn"] = source
    partial = run(standalone)
    assert len(partial["diagnostics"]) == 1 and partial["diagnostics"][0]["path"] == "file:///bad.mgn", partial
    assert partial["tokens"]["file:///single.mgn"] == single["tokens"]["file:///single.mgn"]

    broken = "let a:Int=; let b:Int=; let valid:Int=4;"
    recovered = run({"root": None, "sources": {"file:///multi.mgn": broken}})
    assert [d["start"] for d in recovered["diagnostics"]] == [broken.index(";"), broken.index(";", broken.index(";")+1)], recovered
    assert len(recovered["tokens"]["file:///multi.mgn"]) == 3, recovered

    count = 0
    for manifest in sorted((ROOT / "examples").glob("*/mognitio.toml")):
        sources = {path.relative_to(manifest.parent).as_posix(): path.read_bytes().decode()
                   for path in sorted((manifest.parent / "src").rglob("*.mgn"))}
        snapshot = {"root": "/snapshot", "manifest": manifest.read_text(), "sources": sources}
        actual = run(snapshot)
        assert actual["complete"] and not actual["diagnostics"], (manifest, actual["diagnostics"])
        if reference:
            reply = subprocess.run([str(reference / "runtime/sbcl"), "--core", str(reference / "runtime/mognitio.core"),
                                    "--noinform", "--no-sysinit", "--no-userinit", "--mognitio-worker"],
                                   input=json.dumps(snapshot).encode()+b"\n", capture_output=True, check=True, timeout=15)
            expected = json.loads(reply.stdout)
            assert expected["complete"] and expected["tokens"] == actual["tokens"], manifest
        count += 1
    print(f"Native standalone recovery and {count} captured example projects passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("build")
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    check(args.compiler.resolve(), args.build, args.reference)
