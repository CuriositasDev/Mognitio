#!/usr/bin/env python3
"""Exercise standard identities through constructors, aliases and re-exports."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--compiler", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
a.compiler = a.compiler.resolve()
a.output.mkdir()
records = []

def program(prefix, body="0"):
    return "namespace App;" + prefix + "let main:Function(List<String>):Int=function(args:List<String>):Int{" + body + "};\n"

cases = {}
def single(name, prefix, body="0", native=False):
    cases[name] = ({"src/app.mgn": program(prefix, body)}, native)

single("user-path-error-same-fields", r"use Std\Io\{IoErrorKind};type PathInfoError=product{kind:IoErrorKind;subject:String;};",
       'let value:PathInfoError=PathInfoError{kind:IoErrorKind::Other,subject:"kept"};branch when{value->subject=="kept"=>0,else=>1}', True)
single("user-directory-same-fields", "type DirectoryEntryKind=sum{File;Directory;Symlink;Other;};type DirectoryEntry=product{name:String;kind:DirectoryEntryKind;};",
       'let value:DirectoryEntry=DirectoryEntry{name:"kept",kind:DirectoryEntryKind::File};branch on value->kind{DirectoryEntryKind::File=>0,DirectoryEntryKind::Directory=>1,DirectoryEntryKind::Symlink=>2,DirectoryEntryKind::Other=>3}', True)
single("standard-directory-constructed", r"use Std\Io\{DirectoryEntry,DirectoryEntryKind};",
       'discard DirectoryEntry{name:"kept",kind:DirectoryEntryKind::File};0')
single("standard-kind-constructed", r"use Std\Io\{DirectoryEntryKind};", "discard DirectoryEntryKind::Other;0")
single("standard-path-error-constructed", r"use Std\Io\{PathInfoError,IoErrorKind};",
       'discard PathInfoError{kind:IoErrorKind::Other,subject:"kept"};0')
single("renamed-type", r"use Std\Io\{PathInfoError as Hidden};", "let values:List<Hidden>=List<Hidden>[];discard values;0")
single("type-alias", r"use Std\Io\{PathInfoError};alias Hidden=PathInfoError;", "let values:List<Hidden>=List<Hidden>[];discard values;0")
single("container-signature", r"use Std\Io\{PathInfoError};let keep:Function(List<PathInfoError>):List<PathInfoError>=function(values:List<PathInfoError>):List<PathInfoError>{values};")
single("generic-identity", r"use Std\Io\{PathInfoError};template keep<T>=function(value:T):T{value};",
       "discard keep<List<PathInfoError>>(List<PathInfoError>[]);0")
single("generic-alias", r"use Std\Io\{PathInfoError};alias Hidden<T>=Result<List<T>,String>;",
       "discard Hidden<PathInfoError>::Ok(List<PathInfoError>[]);0")
single("function-as-value", r"use Std\Io\{joinPath as hidden,IoError};let values:List<Function(String,String):Result<String,IoError>>=List<Function(String,String):Result<String,IoError>>[hidden];")
cases["type-reexport"] = ({
    "src/Bridge/value.mgn": r"namespace App\Bridge;use Std\Io\{PathInfoError};public alias Hidden=PathInfoError;",
    "src/app.mgn": program(r"use App\Bridge\{Hidden};", "let values:List<Hidden>=List<Hidden>[];discard values;0"),
}, False)
cases["function-reexport"] = ({
    "src/Bridge/value.mgn": r"namespace App\Bridge;use Std\Io\{joinPath,IoError};public let hidden:Function(String,String):Result<String,IoError>=joinPath;",
    "src/app.mgn": program(r"use App\Bridge\{hidden};"),
}, False)

for name, (sources, native) in cases.items():
    folder = a.output / name
    folder.mkdir()
    sources = dict(sources, **{"mognitio.toml": '[project]\nname="app"\nroot_namespace="App"\n'})
    for relative, text in sources.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    inventory = {relative: hashlib.sha256((folder / relative).read_bytes()).hexdigest() for relative in sources}
    for verb in ("check", "lower", "build"):
        output = folder / "program"
        command = [a.compiler, verb, folder / "mognitio.toml"]
        if verb == "build":
            command += ["-o", output]
        result = subprocess.run(command, capture_output=True, timeout=120)
        expected = 1 if verb == "build" and not native else 0
        valid = result.returncode == expected and result.stdout == b""
        valid = valid and (b"mgnc: unsupported:" in result.stderr and b" [" in result.stderr
                           if expected else result.stderr == b"")
        if expected:
            valid = valid and not output.exists()
        valid = valid and all(hashlib.sha256((folder / rel).read_bytes()).hexdigest() == digest
                              for rel, digest in inventory.items())
        row = dict(name=name, command=verb, expected=expected, exit=result.returncode,
                   stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex(), sources=inventory, passed=valid)
        if valid and verb == "build" and native:
            run = subprocess.run([output], capture_output=True, timeout=30)
            valid = (run.returncode, run.stdout, run.stderr) == (0, b"", b"")
            row.update(passed=valid, runtime_exit=run.returncode, runtime_stdout_hex=run.stdout.hex(),
                       runtime_stderr_hex=run.stderr.hex(), artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        records.append(row)
        (a.output / "results.json").write_text(json.dumps(dict(
            compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest(), records=records), indent=2) + "\n")
        assert valid, row
print("V160_PROFILE_BOUNDARIES_OK cases=" + str(len(cases)) + " observations=" + str(len(records)))
