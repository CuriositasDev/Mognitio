"""Run the LSP coordinator with one pinned native compiler and owned snapshot directories."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.lsp.server import Server


class NativeServer(Server):
    def __init__(self, payload, identity, compiler):
        super().__init__(payload, identity)
        self.compiler = compiler
        self.scratch = tempfile.TemporaryDirectory(prefix="mgn-lsp-jobs-")

    def start_worker(self, generation):
        tools = self.payload / "tools"
        directory = tempfile.TemporaryDirectory(prefix=f"{generation}-", dir=self.scratch.name)
        command = [sys.executable, "-I", "-B", str(tools / "lsp/worker_exec.py"), str(os.getpid()),
                   sys.executable, "-I", "-B", str(tools / "selfhost/analysis.py"), str(self.compiler),
                   self.identity["build"], str(generation), directory.name]
        try:
            worker = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except BaseException:
            directory.cleanup()
            raise
        return worker, directory.cleanup

    def run(self):
        try:
            return super().run()
        finally:
            self.scratch.cleanup()
