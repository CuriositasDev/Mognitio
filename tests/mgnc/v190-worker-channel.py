#!/usr/bin/env python3
"""Exercise an identity-bearing native compiler through its public and private entries."""
import argparse
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.selfhost.client import EXEC_NAME, WorkerError, request


def check(compiler, build):
    def query(profile, **args):
        return request(compiler, build, profile, timeout=10, **args)

    assert query("identity").status == "ok"
    # Keep a Unix socket open without ever sending data. A direct launch must
    # reject its missing command promptly even with both standard streams on it.
    left, right = socket.socketpair()
    with left, right:
        result = subprocess.run([compiler], stdin=right, stdout=right, stderr=subprocess.PIPE,
                                pass_fds=(right.fileno(),), timeout=3)
        assert result.returncode == 2 and b"mgnc: cli:" in result.stderr, result
    result = subprocess.run([EXEC_NAME], executable=compiler, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=3)
    assert (result.returncode, result.stdout, result.stderr) == (3, b"", b""), result
    left, right = socket.socketpair(type=socket.SOCK_SEQPACKET)
    with left, right, subprocess.Popen([EXEC_NAME], executable=compiler, stdin=right,
                                        stdout=right, stderr=subprocess.PIPE) as process:
        right.close()
        left.settimeout(3)
        prefix = b"MGN-WORKER/1\0" + build.encode() + b"\0"
        assert left.recv(128) == prefix
        # Give only an oversized length. The child must reject it immediately,
        # without an end-of-stream or any payload.
        left.send(b"8193")
        left.send(b"")
        assert left.recv(128) == b""
        assert process.wait(timeout=3) == 3 and process.stderr.read() == b""
    try:
        request(compiler, "0" * 64 if build != "0"*64 else "1"*64, "identity", timeout=3)
    except WorkerError:
        pass
    else:
        raise AssertionError("Mismatched build accepted")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        manifest = root / "mognitio.toml"
        manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
        file = src / "checks.mgn"
        text = 'namespace App;\n// 🐈\n@test let ok:Function():Unit=function():Unit{assert true;};\n'
        file.write_text(text)
        assert query("analysis", path=manifest, generation="3").status == "ok"
        plan = query("tests", path=manifest)
        assert plan.status == "plan"
        assert plan.fields == ("1", "0", "src/checks.mgn", "App", "ok", str(text.encode().index(b"@"))), plan
        file.write_text("namespace App;\nlet unused:Int=true;\n")
        diagnostic = query("analysis", path=manifest, generation="4")
        assert diagnostic.status == "diagnostic" and diagnostic.fields[:3] == ("1", "src/checks.mgn", "type"), diagnostic
        assert query("syntax", path=file, generation="4").status == "ok"
        file.write_text("namespace App;\nlet = ;\n")
        assert query("syntax", path=file, generation="5").status == "diagnostic"
        public = subprocess.run([compiler, "check", manifest], capture_output=True, timeout=10)
        assert public.returncode == 2, public
    print("Native public startup, private handshake, identity, test plan and snapshot diagnostics passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("build")
    args = parser.parse_args()
    check(args.compiler.resolve(), args.build)
