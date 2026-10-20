#!/usr/bin/env python3
"""Exercise closed specialization identities for unused named witnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = r"""namespace App\Model;
public type Value = product { value: Int; };
public contract Show { show(self: Self): Int; }
public witness Proof = Value implements Show {
    show(self: Self): Int { self->value }
}
"""
def entry(imports, body):
    return ("namespace App;\n" + imports + "\n"
            "let main: Function(List<String>): Int = function(args: List<String>): Int { "
            + body + " };\n")

CASES = [
    ("unused-import", MODEL, entry(r"use App\Model\{Value, Show, Proof};", "0"), 0, {}),
    ("unused-alias", MODEL, entry(r"use App\Model\{Proof as Evidence};", "0"), 0, {}),
    ("unreachable-module", MODEL, entry("", "0"), 0, {}),
    ("used-dispatch", MODEL, entry(r"use App\Model\{Value, Show, Proof};",
       "let packed: Show = Show(Value { value: 7 }); packed->show()"), 7, {}),
    ("missing-visible-evidence", MODEL, entry(r"use App\Model\{Value, Show};",
       "let packed: Show = Show(Value { value: 7 }); packed->show()"), 1, {}),
    ("duplicate-unreachable-pair", MODEL, entry("", "0"), 1, {
        "Other/duplicate.mgn": r"""namespace App\Other;
use App\Model\{Value, Show};
witness Duplicate = Value implements Show { show(self: Self): Int { self->value } }
"""}),
    ("hidden-implementation", MODEL.replace("public type Value", "type Value").replace(
       "public witness Proof", "witness Proof") + """
public let make: Function(): Show = function(): Show { Show(Value { value: 9 }) };
""", entry(r"use App\Model\{Show, make};", "make()->show()"), 9, {}),
    ("unused-nested-signature", r"""namespace App\Model;
public type Data = product { value: String; };
public type Value = product { value: Data; };
public contract Show { show(self: Self): Data; }
public witness Proof = Value implements Show { show(self: Self): Data { self->value } }
""", entry(r"use App\Model\{Proof};", "0"), 0, {}),
    ("multiple-pairs", MODEL + """
public type Second = product { value: Int; };
public witness SecondProof = Second implements Show {
    show(self: Self): Int { self->value }
}
""", entry(r"use App\Model\{Value, Show, Proof, Second, SecondProof};",
       "let a: Show = Show(Value { value: 4 }); "
       "let b: Show = Show(Second { value: 5 }); a->show() + b->show()"), 9, {}),
]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=ROOT / "bin/mgn")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
    records = []
    with tempfile.TemporaryDirectory(prefix="mgn-witness-specialization-") as temporary:
        work = Path(temporary)
        for name, model, source, expected, extra in CASES:
            project = work / name
            (project / "src/Model").mkdir(parents=True)
            manifest = project / "mognitio.toml"
            manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
            (project / "src/Model/model.mgn").write_text(model)
            (project / "src/app.mgn").write_text(source)
            for relative, text in extra.items():
                target = project / "src" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            inputs = {str(p.relative_to(project)): sha(p) for p in project.rglob("*") if p.is_file()}
            artifact = project / "program"
            if expected == 1:
                artifact.write_bytes(b"preserved existing output")
            commands = [("run", [str(compiler), "run", str(manifest)], expected),
                        ("build", [str(compiler), "build", str(manifest), "-o", str(artifact)],
                         1 if expected == 1 else 0)]
            if expected != 1:
                commands.append(("native", [str(artifact)], expected))
            for mode, command, status in commands:
                result = subprocess.run(command, capture_output=True, timeout=90)
                passed = result.returncode == status and result.stdout == b""
                if expected == 1:
                    passed = passed and b"semantic:" in result.stderr
                    passed = passed and artifact.read_bytes() == b"preserved existing output"
                else:
                    passed = passed and result.stderr == b""
                    if mode == "build":
                        passed = passed and artifact.read_bytes().startswith(b"\x7fELF")
                row = {"case": name, "mode": mode, "exit": result.returncode,
                       "stdout_hex": result.stdout.hex(), "stderr_hex": result.stderr.hex(), "passed": bool(passed)}
                records.append(row)
                if args.output:
                    (args.output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
                assert passed, row
                assert all(sha(project / relative) == digest for relative, digest in inputs.items()), name
    print("WITNESS_SPECIALIZATION_OK cases=" + str(len(CASES)) + " observations=" + str(len(records)))

if __name__ == "__main__":
    main()
