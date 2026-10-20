#!/usr/bin/env python3
"""Lower-command CLI, encoding, exact locations and read-only boundaries."""
import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--compiler", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
a.compiler = a.compiler.resolve()
a.output.mkdir()
root = a.output / "inputs"
root.mkdir()
entry = "namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{0};"
source = root / "valid.mgn"
source.write_text(entry)
existing = root / "existing"
existing.write_bytes(b"keep")
project = root / "project"
(project / "src").mkdir(parents=True)
manifest = project / "mognitio.toml"
manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
(project / "src/app.mgn").write_text(entry)
records = []


def snapshot():
    return {str(p.relative_to(root)): [stat.S_IMODE(p.stat().st_mode),
            p.stat().st_mtime_ns, p.stat().st_ino,
            hashlib.sha256(p.read_bytes()).hexdigest()]
            for p in root.rglob("*") if p.is_file()}


def invoke(name, args, expected, phase="", span=None, unknown_position=False):
    before = snapshot()
    result = subprocess.run([a.compiler, *map(str, args)], cwd=root,
                            capture_output=True, timeout=120)
    valid = result.returncode == expected and result.stdout == b"" and snapshot() == before
    valid = valid and (("mgnc: " + phase + ":").encode() in result.stderr
                       if phase else result.stderr == b"")
    if span:
        valid = valid and f"[{span[0]},{span[1]})".encode() in result.stderr
        valid = valid and f":{span[2]}:{span[3]} [".encode() in result.stderr
    if unknown_position:
        valid = valid and b"position unknown" in result.stderr and b" [" not in result.stderr
    records.append(dict(name=name, exit=result.returncode, stdout_hex=result.stdout.hex(),
                        stderr_hex=result.stderr.hex(), input_inventory=before, passed=valid))
    (a.output / "results.json").write_text(json.dumps(dict(
        compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest(),
        records=records), indent=2) + "\n")
    assert valid, (name, result.returncode, result.stderr)


for index, args in enumerate([
    ["lower"], ["lower", source, "extra"], ["lower", source, "-o", existing],
    ["lower", manifest, "-o", root / "absent"], ["lower", ""],
    ["Lower", source], ["lower", "source.txt"],
]):
    invoke("cli-" + str(index), args, 2, "cli")
invoke("single", ["lower", source], 0)
invoke("manifest", ["lower", manifest], 0)
invoke("missing", ["lower", root / "missing.mgn"], 2, "io")
source.write_bytes(b"\xff")
invoke("source-encoding", ["lower", source], 1, "source", unknown_position=True)
source.write_text(entry)
manifest.write_bytes(b"\xff")
invoke("manifest-encoding", ["lower", manifest], 2, "manifest", unknown_position=True)
raw = "//日本語😀\r\n\t" + entry.replace("{0};", "{missing};")
source.write_text(raw)
offset = len(raw[:raw.index("missing")].encode())
line = raw[:raw.index("missing")].count("\n") + 1
column = len(raw[:raw.index("missing")].rsplit("\n", 1)[-1]) + 1
invoke("utf8-span", ["lower", source], 1, "semantic", (offset, offset + 7, line, column))
# A last, unreachable source still receives full static checking before all three operations.
manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
unused = project / "src/zzz.mgn"
unused_source = "namespace App;\nlet wrong:Int=true;\n"
unused.write_text(unused_source)
offset = unused_source.index("true")
for command in ("check", "lower", "build"):
    args = [command, manifest] + (["-o", root / "absent"] if command == "build" else [])
    invoke("unreachable-type-" + command, args, 1, "type",
           (offset, offset + 4, 2, len("let wrong:Int=") + 1))
    assert b"src/zzz.mgn" in bytes.fromhex(records[-1]["stderr_hex"])
assert not (root / "absent").exists() and existing.read_bytes() == b"keep"
print("V160_LOWER_DRIVER_OK checks=" + str(len(records)))
