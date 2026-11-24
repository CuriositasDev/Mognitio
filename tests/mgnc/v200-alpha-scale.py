#!/usr/bin/env python3
"""Measure the alpha integer frontend, lowering, build and project LSP on Linux."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def measure(command, timing):
    completed = subprocess.run(
        ["/usr/bin/time", "-f", "%e %M", "-o", timing, *command],
        capture_output=True, timeout=120,
    )
    assert completed.returncode == 0 and not completed.stderr, (command, completed)
    seconds, rss = timing.read_text().split()
    return {"seconds": float(seconds), "max_rss_kib": int(rss)}


def lsp(payload, root):
    path = Path(__file__).resolve().parents[1] / "v015-toolchain.py"
    spec = importlib.util.spec_from_file_location("protocol", path)
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    protocol.PAYLOAD = payload
    peer = protocol.Peer(root=root)
    source = root / "src/app.mgn"
    try:
        peer.open(source.as_uri(), source.read_text())
        reply = peer.wait(lambda m: m.get("method") == "textDocument/publishDiagnostics"
                          and m["params"].get("uri") == source.as_uri()
                          and m["params"].get("version") == 1)
        assert not reply["params"]["diagnostics"], reply
    finally:
        peer.close()


def samples():
    for digits, references in ((20, 1), (100, 1), (1024, 1), (4096, 1), (100, 8)):
        n = "9" * digits
        yield f"{digits}digits-{references}refs", "", [f"assert {n}+args->length()=={n};"] * references
    for count in (1, 8, 32):
        template = "template constant<N:Int>=function():Int{N};"
        values = [10**99 + n for n in range(count)]
        yield f"100digits-{count}specializations", template, [
            f"assert constant<{n}>()=={n};" for n in values
        ]


def run(payload, out):
    compiler = payload / "runtime/compiler"
    report = {}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        entry = root / "src/app.mgn"
        entry.parent.mkdir()
        manifest = root / "mognitio.toml"
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        for name, prefix, body in samples():
            entry.write_text("namespace App;\n" + prefix + "\n"
                             + "let main:Function(List<String>):Int=function(args:List<String>):Int{"
                             + "".join(body) + "0};\n")
            row = {"source_sha256": hashlib.sha256(entry.read_bytes()).hexdigest()}
            image = root / "program"
            commands = {
                "check": [compiler, "check", manifest],
                "lower": [compiler, "lower", manifest],
                "build": [payload / "bin/mgn", "build", manifest, "-o", image],
                "project_lsp": [sys.executable, "-IB", __file__, "--payload", payload, "--lsp-project", root],
            }
            for stage, command in commands.items():
                row[stage] = measure(command, root / "time")
            subprocess.run([image], check=True, timeout=60)
            report[name] = row
    out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--lsp-project", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.lsp_project:
        lsp(args.payload.resolve(), args.lsp_project.resolve())
    else:
        run(args.payload.resolve(), args.output)
