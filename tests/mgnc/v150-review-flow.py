#!/usr/bin/env python3
"""Regression probes for Unknown operator selection and module initializer flow."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--compiler", required=True, type=Path)
parser.add_argument("--evidence", required=True, type=Path)
parser.add_argument("--command", choices=("check", "lower"), default="check")
args = parser.parse_args()
compiler = args.compiler.resolve()
records = []


def main(body="0"):
    return "let main:Function(List<String>):Int=function(args:List<String>):Int{" + body + "};"


cases = []


def add(name, source, phase=None, native=False, exit_code=7, token=None, other=None):
    cases.append((name, source, phase, native, exit_code, token, other))


def expression(name, body, phase=None, native=True, prefix=""):
    add(name, "namespace App;" + prefix + main(body), phase, native)


expression("unknown-neg", "-{return 7;}")
for operator, name in [("-", "sub"), ("*", "mul"), ("/", "div"), ("%", "rem"),
                       ("<", "lt"), ("<=", "le"), (">", "gt"), (">=", "ge")]:
    expression("unknown-" + name, "{return 7;}" + operator + "{return 9;}")
for operator, name in [("+", "add"), ("==", "eq"), ("!=", "ne")]:
    expression("ambiguous-" + name, "{return 7;}" + operator + "{return 9;}", "type")
expression("unknown-not", "!{return 7;}")
expression("unknown-and", "{return 7;}&&{return 9;}")
expression("unknown-or", "{return 7;}||{return 9;}")
expression("known-int-left", "1+{return 7;}")
expression("known-int-right", "{return 7;}+1")
expression("known-string", '"x"+{return 7;}', native=False)
expression("known-bool-eq", "true=={return 7;}")
expression("known-unit-eq", "unit=={return 7;}")
expression("known-mismatch", "1+true", "type")
expression("known-invalid", "List<Int>[]-{return 7;}", "type")
expression("known-fixed", "Int<8,Signed>{1}+{return 7;}", native=False,
           prefix="use Std\\Numeric\\{Signed};")
expression("fixed-does-not-mix", "Int<8,Signed>{1}+1", "type",
           prefix="use Std\\Numeric\\{Signed};")
expression("known-bits-eq", "Bits<8>{1}=={return 7;}", native=False,
           prefix="use Std\\Numeric\\{Bits};")
expression("bits-no-sub", "Bits<8>{1}-{return 7;}", "type",
           prefix="use Std\\Numeric\\{Bits};")
stopped = 'let stopped:Int=panic{"stop"};'
compile_time = "type Box=product{};alias Alias=Box;template identity<T>=function(x:T):T{x};"
add("unreachable-main", "namespace App;" + stopped + main(), "semantic", token="main")
add("unreachable-var", "namespace App;" + main() + stopped + "var later:Int=0;", "semantic", token="later")
add("compile-time-does-not-reset", "namespace App;" + stopped + compile_time + main(), "semantic", token="main")
add("last-noncompleting", "namespace App;" + main() + stopped)
add("compile-time-after-stop", "namespace App;" + main() + stopped + compile_time)
add("ordinary-call-local-flow", 'namespace App;let fail:Function():Int=function():Int{panic{"stop"}};'
    + "let value:Int=fail();" + main())
add("function-creation-completes", 'namespace App;let fail:Function():Int=function():Int{panic{"stop"}};'
    + main("7"))
add("unused-module-unreachable", "namespace App;" + main(), "semantic", token="later",
    other="namespace App\\Other;" + stopped + "let later:Int=0;")
add("module-boundary-resets-flow", "namespace App;" + main(),
    other="namespace App\\Other;" + stopped)
add("unused-module-last-stop", "namespace App;" + main(),
    other="namespace App\\Other;let earlier:Int=1;" + stopped)


def run(case, command, path, output, source, expected, phase, token):
    argv = [str(compiler), command, str(path)]
    if command == "build":
        argv += ["-o", str(output)]
    result = subprocess.run(argv, capture_output=True, timeout=120)
    stderr = result.stderr.decode()
    good = result.returncode == expected and not result.stdout
    good = good and (not stderr if expected == 0 else ("mgnc: " + phase + ":") in stderr)
    # Refused builds must leave a preexisting destination untouched.
    if command == "build" and expected:
        good = good and output.read_bytes() == b"preserved destination\n"
    if token:
        start = source.index(token)
        good = good and f"[{start},{start + len(token)})" in stderr
    records.append(dict(case=case, command=command, exit=result.returncode,
                        stderr=stderr.replace(str(path.parent), "<fixture>"), passed=good))
    return result


with tempfile.TemporaryDirectory(prefix="v150-review-flow-") as temporary:
    root = Path(temporary)
    for name, text, phase, native, exit_code, token, other in cases:
        project = root / name
        (project / "src").mkdir(parents=True)
        source = project / "src/app.mgn"
        source.write_text(text)
        manifest = project / "mognitio.toml"
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        if other:
            (project / "src/Other").mkdir()
            (project / "src/Other/other.mgn").write_text(other)
        # Exercise both public input forms, plus whole-project unused sources.
        inputs = [("project", manifest)] if other else [("single", source), ("project", manifest)]
        before = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in project.rglob("*") if p.is_file()}
        for form, path in inputs:
            output = project / "program"
            run(name + "-" + form, args.command, path, output, other or text,
                1 if phase else 0, phase, token)
            if form == "project":
                continue
            if not native or phase:
                output.write_bytes(b"preserved destination\n")
            built = run(name + "-" + form, "build", path, output, other or text,
                        0 if native and phase is None else 1, phase or "unsupported", token)
            if built.returncode == 0:
                result = subprocess.run([str(output)], capture_output=True, timeout=10)
                records.append(dict(case=name + "-" + form, command="execute",
                                    exit=result.returncode,
                                    passed=result.returncode == exit_code and not result.stdout and not result.stderr))
            if output.exists():
                output.unlink()
        after = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in project.rglob("*") if p.is_file()}
        records.append(dict(case=name, command="inputs-unchanged", passed=before == after))

result = dict(compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
              cases=len(cases), records=records, passed=all(row["passed"] for row in records))
args.evidence.write_text(json.dumps(result, indent=2) + "\n")
assert result["passed"], [row for row in records if not row["passed"]]
print("V150_REVIEW_FLOW_OK cases=" + str(len(cases)) + " checks=" + str(len(records)))
