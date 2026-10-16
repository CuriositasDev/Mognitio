#!/usr/bin/env python3
"""Compare source diagnostics around chunk boundaries with a frozen compiler."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir()
    records = []
    for size in (511, 512, 1023, 1024, 1025, 2047, 2048, 4097, 65536):
        padding = "x" * size
        prefix = "namespace App;\n//" + padding + "\r\n"
        variants = {
            "value": (prefix + 'let main:Function(List<String>):Int=function(args:List<String>):Int{discard "' + padding + '日😀\\u{1f642}\\u{0}\\\"";0};\n', 0),
            "uppercase": (prefix + 'let main:Function(List<String>):Int=function(args:List<String>):Int{discard "' + padding + '\\\\u{10FFFF}";0};\n', 0),
            "escape": (prefix + 'let value:String="' + padding + '日😀\\q";\n', 1),
            "surrogate": (prefix + 'let value:String="' + padding + '\\u{d800}";\n', 1),
            "newline": (prefix + 'let value:String="' + padding + '\r\n";\n', 1),
            "decimal": (prefix + "let value:Int=0123;\n", 1),
            "operator": (prefix + "let value:Bool=true&", 1),
        }
        for kind, (text, status) in variants.items():
            name = f"{kind}-{size}"
            path = args.output / (name + ".mgn")
            data = text.encode()
            path.write_bytes(data)
            commands = []
            for compiler in (args.reference, args.compiler):
                result = subprocess.run([compiler, "check", path], capture_output=True, timeout=120)
                commands.append((result.returncode, result.stdout, result.stderr))
            assert commands[0] == commands[1], (name, commands)
            assert (commands[1][0] == 0) == (status == 0), (name, commands[1])
            assert not commands[1][1], (name, commands[1])
            if status:
                assert b" [" in commands[1][2] and b"):" in commands[1][2], (name, commands[1])
            records.append({"case": name, "source_sha256": digest(data),
                            "status": commands[1][0], "stdout_sha256": digest(commands[1][1]),
                            "stderr_sha256": digest(commands[1][2])})
    report = {"compiler_sha256": digest(args.compiler.read_bytes()),
              "reference_sha256": digest(args.reference.read_bytes()), "cases": records}
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"V160_SOURCE_CHUNKS_OK cases={len(records)}")

if __name__ == "__main__":
    main()
