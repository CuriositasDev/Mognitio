"""Installed native command and language-server entries."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.selfhost.client import WorkerError
from tools.selfhost.command import compile_command, exit_status, report
from tools.selfhost.payload import COMPILER, payload_identity


def main(tool, argv):
    try:
        ident = payload_identity(ROOT)
        if argv == ["--version"]:
            print(("Mognitio" if tool == "mgn" else "mognitio-lsp") + " " + ident["version"])
            return 0
        if tool == "mgn":
            return compile_command(ROOT / COMPILER, ident["build"], [os.fsencode(a) for a in argv])
        if tool != "mognitio-lsp" or argv != ["--stdio"]:
            print("usage: mognitio-lsp --stdio | --version", file=sys.stderr)
            return 2
        from tools.selfhost.language_server import NativeServer
        if os.getpgrp() != os.getpid():
            os.setsid()
        with tempfile.TemporaryDirectory(prefix="mognitio-lsp-") as tmp:
            session = Path(tmp) / "payload"
            shutil.copytree(ROOT, session, symlinks=True)
            if payload_identity(session) != ident:
                raise ValueError("Payload generation changed during session setup")
            from framing import FrameError
            try:
                return NativeServer(session, ident, session / COMPILER).run()
            except FrameError as error:
                print("mognitio-lsp: " + str(error), file=sys.stderr)
                return 3
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, WorkerError, subprocess.SubprocessError) as error:
        if tool == "mgn":
            return report(3, str(error))
        print("mognitio-lsp: " + str(error), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(exit_status(main(sys.argv[1], sys.argv[2:])))
