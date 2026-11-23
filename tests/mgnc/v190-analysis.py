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

    manifest = '[project]\nname="app"\nroot_namespace="App"\n'
    path = "src/app.mgn"
    incomplete = run({"root": "/project", "manifest": '[project]\nname="app"\n',
                      "sources": {path: "namespace App; let bad:Int=;", "src/ok.mgn": "namespace App; let ok:Int=1;"}})
    assert not incomplete["complete"] and {d["path"] for d in incomplete["diagnostics"]} == {"mognitio.toml", path}, incomplete
    assert all(incomplete["tokens"].values()), incomplete

    for root in (None, "/project"):
        prefix = "namespace App; " if root else ""
        for count, complete in ((253, True), (254, False)):
            for expression in ("-" * count + "1", "(" * count + "1" + ")" * count, "1+" * count + "1"):
                result = run({"root": root, "manifest": manifest,
                              "sources": {path: prefix + "let value:Int=" + expression + ";"}})
                assert result["complete"] == complete, (root, count, result["diagnostics"])
                limited = [d for d in result["diagnostics"] if d["message"] == "Syntax nesting budget exceeded"]
                assert bool(limited) != complete and all(d["path"] == path for d in limited), limited
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "src").mkdir()
        (directory / "mognitio.toml").write_text(manifest)
        (directory / path).write_text("namespace App; let main:Function(List<String>):Int=function(args:List<String>):Int{"
                                      + "-" * 254 + "1};")
        command = [sys.executable, ROOT / "tests/mgnc/v190-normal-commands.py", "--child",
                   compiler, build, "run", directory / "mognitio.toml"]
        ordinary = subprocess.run(command, capture_output=True, timeout=30)
        assert ordinary.returncode == 1 and not ordinary.stderr, ordinary

    wide = run({"root": None, "sources": {path: "let xs:List<Int>=List<Int>[" + ",".join(["1"]*300) + "];"}})
    assert wide["complete"], wide["diagnostics"]

    duplicate = "namespace App; // 🐈\n@test @test let check:Function():Unit=function():Unit{assert true;};"
    path = "src/app.mgn"
    annotated = run({"root": "/project", "sources": {path: duplicate},
                     "manifest": '[project]\nname="app"\nroot_namespace="App"\n'})
    primary, = annotated["diagnostics"]
    note, = primary["related"]
    encoded = duplicate.encode()
    first, second = encoded.index(b"@test"), encoded.rindex(b"@test")
    assert (primary["message"], primary["start"], primary["end"]) == ("Duplicate attribute", second, second + 5)
    assert note == dict(path=path, message="First attribute", start=first, end=first+5)

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
