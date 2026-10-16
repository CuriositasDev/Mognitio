#!/usr/bin/env python3
"""Audit an explicit seed before using it for the next compiler stage."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "module-snapshots": (12, r'''
namespace App;
var count: Int = 1;
let before: Function(): Int = function(): Int { count };
let update: Unit = { count = 2; unit };
let after: Function(): Int = function(): Int { count };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    before() * 10 + after()
};
'''),
    "nested-module-snapshot": (1, r'''
namespace App;
var count: Int = 1;
var maker: Function(): Function(): Int = function(): Function(): Int {
    function(): Int { count }
};
let update: Unit = { count = 2; unit };
let reader: Function(): Int = maker();
let replace: Unit = { maker = function(): Function(): Int {
    function(): Int { 9 }
}; unit };
let main: Function(List<String>): Int = function(args: List<String>): Int { reader() };
'''),
    "generic-capture": (0, r'''
namespace App;
template make<T> = function(value: T): Function(): T { function(): T { value } };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    let first: Function(): Int = make<Int>(7);
    let second: Function(): String = make<String>("old" + " value");
    let third: Function(): Int = make<Int>(9);
    assert first() == 7 && second() == "old value" && third() == 9;
    0
};
'''),
    "result-reconstruction": (0, r'''
namespace App;
type Failure = product { text: String; values: List<String>; };
let fail: Function(): Result<String, Failure> = function(): Result<String, Failure> {
    Result<String, Failure>::Err(Failure { text: "old" + " payload", values: List<String>["kept"] })
};
let propagate: Function(): Result<Int, Failure> = function(): Result<Int, Failure> {
    let value: String = try fail();
    Result<Int, Failure>::Ok(value->length())
};
let main: Function(List<String>): Int = function(args: List<String>): Int {
    branch on propagate() {
        Result<Int, Failure>::Ok(value: Int) => 9,
        Result<Int, Failure>::Err(error: Failure) => {
            assert error->text == "old payload" && error->values->length() == 1;
            0
        },
    }
};
'''),
    "arena-and-bytes": (0, r'''
namespace App;
use Std\Binary\{Bytes};
type Operation = product { opcode: Int; inputs: List<Int>; text: String; };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    var pages: List<List<Operation>> = List<List<Operation>>[];
    var index: Int = 0;
    loop while (index < 128) {
        var page: List<Operation> = List<Operation>[];
        var offset: Int = 0;
        loop while (offset < 64) {
            page = page->append(Operation { opcode: index + offset,
                inputs: List<Int>[index, offset], text: "operation" });
            offset = offset + 1;
        };
        pages = pages->append(page);
        index = index + 1;
    };
    let snapshot: List<List<Operation>> = pages;
    pages = pages->append(List<Operation>[]);
    assert snapshot->length() == 128 && pages->length() == 129;
    var total: Int = 0;
    loop over (snapshot as page: List<Operation>) {
        loop over (page as op: Operation) { total = total + op->opcode; };
    };
    assert total == 778240;
    0
};
'''),
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--corpus", type=Path, default=ROOT / "compiler/mgnc")
    args = parser.parse_args()
    seed = args.seed.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((seed / "manifest.json").read_text())
    subprocess.run(["python3", str(ROOT / "scripts/freeze-seed.py"), "--verify", str(seed)], check=True)
    fixtures = []
    for name, (expected, source) in CASES.items():
        project = output / name
        (project / "src").mkdir(parents=True)
        (project / "mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="App"\n')
        (project / "src/app.mgn").write_text(source)
        fixtures.append({"name": name, "exit": expected, "source_sha256": sha(project / "src/app.mgn")})
    # Freeze the inputs and independent expected outcomes before running the seed.
    (output / "fixtures.json").write_text(json.dumps(fixtures, indent=2) + "\n")
    results = []
    def execute(name, command, expected):
        started = time.monotonic()
        run = subprocess.run(command, capture_output=True, timeout=900)
        row = {"name": name, "exit": run.returncode, "seconds": time.monotonic() - started,
               "stdout_hex": run.stdout.hex(), "stderr_hex": run.stderr.hex(),
               "passed": (run.returncode, run.stdout, run.stderr) == (expected, b"", b"")}
        results.append(row)
        (output / "results.json").write_text(json.dumps({"seed_manifest_sha256": sha(seed / "manifest.json"),
            "seed_source": manifest["sourceCommit"], "fixture_manifest_sha256": sha(output / "fixtures.json"),
            "results": results}, indent=2) + "\n")
        if not row["passed"]:
            raise AssertionError((name, run.returncode, run.stdout, run.stderr))
        print(name + " PASS", flush=True)
    for fixture in fixtures:
        project = output / fixture["name"]
        for mode in ("run", "build"):
            command = [str(seed / "bin/mgn"), mode, str(project / "mognitio.toml")]
            if mode == "build":
                command += ["-o", str(project / "program")]
            execute(fixture["name"] + "-" + mode, command, 0 if mode == "build" else fixture["exit"])
        execute(fixture["name"] + "-native", [str(project / "program")], fixture["exit"])
    corpus = args.corpus.resolve()
    inventory = [{"path": p.relative_to(corpus).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
                 for p in sorted(corpus.rglob("*.mgn"))]
    (output / "corpus.json").write_text(json.dumps(inventory, indent=2) + "\n")
    execute("compiler-scale-build", [str(seed / "bin/mgn"), "build", str(corpus / "mognitio.toml"),
                                    "-o", str(output / "compiler")], 0)
    execute("compiler-scale-check", [str(output / "compiler"), "check", str(corpus / "mognitio.toml")], 0)
    print("V160_SEED_CAPABILITY_OK cells=17 corpus_files=" + str(len(inventory)), flush=True)

if __name__ == "__main__":
    main()
