#!/usr/bin/env python3
"""Exercise the ordinary alpha CLI, standalone images and project language server."""
import argparse
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile

TESTS = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


fixtures = module("alpha_integers", TESTS / "mgnc/v200-alpha-integers.py")
protocol = module("toolchain_peer", TESTS / "v015-toolchain.py")


def invoke(command):
    run = subprocess.run(command, capture_output=True, timeout=240)
    return run.returncode, run.stdout, run.stderr


def matrix(cli, manifest, entry, directory):
    image = directory / "program"

    def compare(name, program, samples):
        entry.write_text(program)
        compiled = invoke([cli, "build", manifest, "-o", image])
        assert compiled == (0, b"", b""), (name, compiled)
        for args, status, stdout, stderr in samples:
            expected = (status, stdout, stderr)
            assert invoke([cli, "run", manifest, "--", *args]) == expected, (name, "run")
            assert invoke([image, *args]) == expected, (name, "standalone")
        print("PASS", name, flush=True)

    for name, source, status, error in fixtures.cases():
        if name.startswith("conversion-oracle-") or name in ("arithmetic-oracle", "long-literal", "io-retention"):
            continue
        compare(name, source, [([], status, b"", error)])
    checks = []
    for sa, sb in ((-1, 1), (1, -1), (-1, -1)):
        a = ("-" if sa < 0 else "") + "(h+k)"
        b = ("-" if sb < 0 else "") + "h"
        checks.append(f"assert ({a})/({b})=={sa*sb};assert ({a})%({b})==({sa})*k;")
        checks.append(f"assert ({a})==(({a})/({b}))*({b})+(({a})%({b}));")
    dynamic = fixtures.source(body="let h:Int=18446744073709551616;let k:Int=args->length();" + "".join(checks) + "0")
    compare("runtime-division", dynamic, [([], 0, b"", b""), (["one"], 0, b"", b"")])
    for name, source, _ in fixtures.invalid_cases():
        entry.write_text(source)
        before = image.read_bytes()
        mode = image.stat().st_mode
        for command in ([cli, "run", manifest], [cli, "build", manifest, "-o", image]):
            status, stdout, stderr = invoke(command)
            assert status == 1 and not stdout and b"src/app.mgn" in stderr, (name, status, stderr)
        assert image.read_bytes() == before and image.stat().st_mode == mode


def lsp(payload, directory, manifest, entry):
    protocol.PAYLOAD = payload
    uri = entry.as_uri()
    prefix = "namespace App;\nuse Std\\Numeric\\{Bits};\n"
    good = prefix + "let main:Function(List<String>):Int=function(args:List<String>):Int{discard " + "9" * 256 + ";0};\n"
    bad = prefix + "let main:Function(List<String>):Int=function(args:List<String>):Int{discard Bits<8>{256};0};\n"
    removed = bad.replace("Bits<8>{256}", "(1)->toBits()")
    entry.write_text(good)
    peer = protocol.Peer(root=directory)

    def diagnostics(version):
        result = peer.wait(lambda m: m.get("method") == "textDocument/publishDiagnostics"
                           and m["params"].get("uri") == uri and m["params"].get("version") == version)
        return result["params"]["diagnostics"]

    try:
        peer.open(uri, good)
        assert diagnostics(1) == []
        for version, text in [(2, bad), (3, removed)]:
            entry.write_text(text)
            code, stdout, stderr = invoke([payload / "bin/mgn", "run", manifest])
            match = re.search(rb"\[bytes (\d+),(\d+)\)", stderr)
            assert code == 1 and not stdout and match, stderr
            start, end = map(int, match.groups())
            peer.change(uri, text, version)
            findings = diagnostics(version)
            def position(offset):
                before = text[:offset]
                return {"line": before.count("\n"), "character": len(before.rsplit("\n", 1)[-1])}
            assert any(d["range"] == {"start": position(start), "end": position(end)} for d in findings), findings
        peer.change(uri, good, 4)
        assert diagnostics(4) == []
        peer.change(uri, good + " " * (4 * 1024 * 1024), 5)
        assert peer.tokens(uri, 25)["result"]["data"] == []
        entry.write_text(good)
        peer.change(uri, good, 6)
        assert diagnostics(6) == [] and peer.tokens(uri, 26)["result"]["data"]
        peer.change(uri, bad, 7)
        peer.send({"id": 27, "method": "textDocument/semanticTokens/full", "params": {"textDocument": {"uri": uri}}})
        peer.send({"method": "$/cancelRequest", "params": {"id": 27}})
        assert peer.wait(lambda m: m.get("id") == 27)["error"]["code"] == -32800
        peer.change(uri, good, 8)
        assert diagnostics(8) == []
        cursor = len(peer.events)
        peer.change(uri, bad, 7)
        assert peer.tokens(uri, 28)["result"]["data"]
        assert not any(m.get("method") == "textDocument/publishDiagnostics" and
                       m["params"].get("version") == 7 for m in peer.events[cursor:])
    finally:
        peer.close()
    print("PASS project CLI/LSP diagnostics, oversized input and recovery", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args()
    payload = args.payload.resolve()
    cli = payload / "bin/mgn"
    assert invoke([cli, "--version"]) == (0, b"Mognitio 2.0.0-alpha\n", b"")
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        manifest = directory / "mognitio.toml"
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        (directory / "src").mkdir()
        entry = directory / "src/app.mgn"
        matrix(cli, manifest, entry, directory)
        lsp(payload, directory, manifest, entry)


if __name__ == "__main__":
    main()
