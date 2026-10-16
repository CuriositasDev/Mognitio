#!/usr/bin/env python3
"""Materialize lower-command inputs and independent observations before lowering work."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

CASES = {
    "closures-and-control": r'''namespace App;
var number: Int = 1;
let saved: Function(): Int = function(): Int { number };
let update: Unit = { number = 2; unit };
template identity<T> = function(value: T): T { value };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    let select: Function(Int): Int = function(value: Int): Int {
        loop { branch when { value > 0 => { break value; }, else => { break 0; } }; }
    };
    var total: Int = 0;
    loop over (List<Int>[1, 2, 3] as item: Int) { total = total + item; };
    branch when { saved() == 1 && identity<Int>(total) == 6 => select(0), else => 9 }
};''',
    "values-and-methods": r'''namespace App;
type Pair = product { name: String; values: List<Int>; };
type Choice = sum { Empty; Present(Pair); };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    let value: Choice = Choice::Present(Pair { name: "a\0あ", values: List<Int>[3] });
    branch on value {
        Choice::Empty => 1,
        Choice::Present(pair: Pair) => {
            let pieces: List<String> = pair->name->scalars();
            let joined: String = pieces->join("-");
            branch on joined->slice(0, 1) {
                Result<String, SliceError>::Ok(text: String) => pair->values->length() - 1,
                Result<String, SliceError>::Err(error: SliceError) => 2,
            }
        },
    }
};''',
    "try-result-owner": r'''namespace App;
let convert: Function(Result<String, String>): Result<Int, String> =
function(input: Result<String, String>): Result<Int, String> {
    let value: String = try input;
    Result<Int, String>::Ok(value->length())
};
let main: Function(List<String>): Int = function(args: List<String>): Int {
    branch on convert(Result<String, String>::Err("kept")) {
        Result<Int, String>::Ok(value: Int) => value,
        Result<Int, String>::Err(error: String) => 0,
    }
};''',
    "binary-only-lowering": r'''namespace App;
use Std\Numeric\{Bits};
use Std\Binary\{Bytes,bytesFromBits};
template keep<N: Int> = function(value: Bits<N>): Bits<N> { value };
let main: Function(List<String>): Int = function(args: List<String>): Int {
    let bytes: Bytes = bytesFromBits(List<Bits<8>>[]);
    bytes->length()
};''',
    "path-only-lowering": r'''namespace App;
use Std\Io\{inspectPath,PathInfo,PathInfoError};
let main: Function(List<String>): Int = function(args: List<String>): Int {
    branch on inspectPath("not-evaluated") {
        Result<PathInfo, PathInfoError>::Ok(info: PathInfo) => 0,
        Result<PathInfo, PathInfoError>::Err(error: PathInfoError) => 1,
    }
};''',
    "never-execute": r'''namespace App;
use Std\Io\{writeTextFile,IoError};
let effect: Result<Unit, IoError> = writeTextFile("unexpected-side-effect", "bad");
let main: Function(List<String>): Int = function(args: List<String>): Int { panic { "not-run" } };
''',
    "unknown-completion": r'''namespace App;
let helper: Function(Bool): Int = function(flag: Bool): Int {
    branch when { flag => { return 1; }, else => { return 2; } }
};
let main: Function(List<String>): Int = function(args: List<String>): Int { helper(true) - 1 };
''',
    "unselected-non-normal": r'''namespace App;
let helper: Function(Bool): Int = function(flag: Bool): Int {
    branch when { flag => panic { "stop" }, else => 1 }
};
let main: Function(List<String>): Int = function(args: List<String>): Int { helper(false) - 1 };
''',
}
ENTRY = 'namespace App;\nlet main: Function(List<String>): Int = function(args: List<String>): Int { 0 };\n'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}

def materialize(root):
    root.mkdir(parents=True, exist_ok=False)
    programs = {name: {"app.mgn": source} for name, source in CASES.items()}
    programs["unreachable-helper"] = {"app.mgn": ENTRY, "unused.mgn":
        'namespace App;\ntemplate unused<T> = function(value: T): Function(): T { function(): T { value } };\n'}
    programs["unreachable-error"] = {"app.mgn": ENTRY, "zzz.mgn":
        'namespace App;\nlet wrong: Int = "type-error";\n'}
    programs["long-literal"] = {"app.mgn": 'namespace App;\nlet data: String = "' + 'a' * 131072 +
        '終";\nlet main: Function(List<String>): Int = function(args: List<String>): Int { data->length() % 256 };\n'}
    rows = []
    for name, sources in programs.items():
        project = root / name
        (project / 'src').mkdir(parents=True)
        (project / 'mognitio.toml').write_text('[project]\nname="app"\nroot_namespace="App"\n')
        for path, source in sources.items():
            (project / 'src' / path).write_text(source)
        rows.append({"name": name, "files": inventory(project),
                     "exit": 1 if name == 'unreachable-error' else 0,
                     "diagnostic": "type" if name == 'unreachable-error' else None})
    (root / 'manifest.json').write_text(json.dumps({"schema": 1, "cases": rows}, indent=2) + '\n')
    return rows

def run(compiler, root, rows, mode):
    results = []
    for row in rows:
        project = root / row['name']
        before = inventory(project)
        result = subprocess.run([str(compiler), mode, str(project / 'mognitio.toml')],
                                cwd=project, capture_output=True, timeout=900)
        valid = result.returncode == row['exit'] and result.stdout == b''
        valid = valid and (row['diagnostic'].encode() in result.stderr if row['diagnostic'] else result.stderr == b'')
        valid = valid and before == inventory(project) == row['files']
        results.append({"name": row['name'], "passed": valid, "exit": result.returncode,
                        "stdout_hex": result.stdout.hex(), "stderr_hex": result.stderr.hex()})
    (root / (mode + '-results.json')).write_text(json.dumps(results, indent=2) + '\n')
    assert all(x['passed'] for x in results), results
    print('V160_' + mode.upper() + '_CASES_OK cases=' + str(len(rows)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--mode', choices=['check', 'lower'], default='lower')
    args = parser.parse_args()
    root = args.output.resolve()
    rows = materialize(root)
    print('FIXTURES sha256=' + digest((root / 'manifest.json').read_bytes()), flush=True)
    if args.compiler:
        run(args.compiler.resolve(), root, rows, args.mode)

if __name__ == '__main__':
    main()
