#!/usr/bin/env python3
"""Check suite output, process exit aggregation, and reporting failures."""
from pathlib import Path
import os
import errno
import fcntl
import select
import subprocess
import signal
from unittest.mock import patch
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.runner.suite import Case, Output, Report, Span, run_suite
from tools.selfhost.publication import Artifact

CHILD = """#!/usr/bin/python3
import os, struct, sys
ordinal = int(sys.argv[1])
def put(seq, tag, stage=0, kind=0, site=2**64-1):
    os.write(3,struct.pack('<IHHQQIIQ',0x544e474d,4,tag,ordinal,seq,stage,kind,site))
put(0,1)
assert os.read(4,1)==b'\\x01'
put(1,2,1)
put(2,2,2)
if ordinal==0:
    os.write(1,b'PASS\\n\\0\\xff')
    put(3,3,2)
elif ordinal==1:
    put(3,3,2,1,0)
    sys.exit(5)
elif ordinal==2:
    put(3,3,2,2)
    os.write(5,b'failure\\n')
    sys.exit(4)
else:
    os.kill(os.getpid(),9)
"""


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "test-child"
        self.image.write_text(CHILD)
        self.image.chmod(0o755)
        pos = Span("src/a.mgn", 2, 3, 12, 18)
        self.cases = [Case(f"src/a.mgn::App::{name}", pos, (pos,)) for name in ("a", "b", "c", "d")]

    def invoke(self, count, **kwargs):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            code = run_suite(self.image, self.cases[:count], out.fileno(), err.fileno(), **kwargs)
            out.seek(0)
            err.seek(0)
            return code, out.read(), err.read()

    def test_results(self):
        for count, expected in enumerate((0, 0, 5, 4, 6)):
            with self.subTest(count=count):
                code, out, err = self.invoke(count)
                self.assertEqual(code, expected)
                summary = f"tests: total={count} passed={int(count>=1)} failed={int(count>=2)} errors={max(count-2,0)} aborted=0 not_run=0\n"
                self.assertTrue(out.endswith(summary.encode()), out)
                if count:
                    self.assertIn(b'stdout: "PASS\\n\\0\\xFF"', err)
                if count >= 2:
                    self.assertIn(b"FAIL assertion src/a.mgn::App::b\n", out)
                    self.assertIn(b"src/a.mgn:2:3: assertion: assertion failed [bytes 12,18)", err)
                if count >= 3:
                    self.assertIn(b"failure\n", err)

    def test_spawn_failure(self):
        self.image.unlink()
        code, out, err = self.invoke(2)
        self.assertEqual((code, out), (2, b""))
        self.assertTrue(err)

    def test_artifact_removal_failure(self):
        artifact = Artifact()
        image = Path(artifact.prepare([self.image]))
        image.write_bytes(b"private")
        self.addCleanup(image.parent.rmdir)
        self.addCleanup(image.unlink)
        with patch("os.unlink", side_effect=PermissionError(errno.EACCES, "denied")):
            code, out, err = self.invoke(1, cleanup=artifact.cleanup)
        self.assertEqual(code, 2)
        self.assertIn(b"total=1 passed=1", out)
        self.assertIn(os.fsencode(image), err)
        self.assertTrue(image.exists())

    def test_signal_after_each_report_write(self):
        write = os.write
        for marker in (b"PASS ", b": test:", b": assertion:", b"FAIL ", b"tests: "):
            with self.subTest(marker=marker):
                fired = False
                def interrupt(fd, data):
                    nonlocal fired
                    count = write(fd, data)
                    if not fired and marker in bytes(data):
                        fired = True
                        os.kill(os.getpid(), signal.SIGINT)
                    return count
                previous = signal.signal(signal.SIGINT, signal.default_int_handler)
                self.addCleanup(signal.signal, signal.SIGINT, previous)
                with patch.object(os, "write", interrupt):
                    code, out, err = self.invoke(2)
                self.assertTrue(fired)
                self.assertEqual(code, 2)
                self.assertEqual(out.count(b"PASS "), 1)
                self.assertEqual(out.count(b"tests: "), 1)
                if marker != b"PASS ":
                    self.assertEqual(out.count(b"FAIL "), 1)
                    self.assertEqual(err.count(b": test:"), 1)
                    self.assertEqual(err.count(b": assertion:"), 1)

    def test_interrupt_while_summary_pipe_is_full(self):
        script = """
import os, signal, sys
from tools.runner.suite import run_suite
from tools.selfhost.command import interruptible
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal.SIG_DFL)
with interruptible():
    result = run_suite(None, [], cleanup=lambda record: os.write(2, b'ready\\n'))
sys.exit(result)
"""
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                reader, writer = os.pipe()
                with os.fdopen(reader, "rb", buffering=0), os.fdopen(writer, "wb", buffering=0):
                    capacity = fcntl.fcntl(writer, fcntl.F_GETPIPE_SZ)
                    self.assertEqual(os.write(writer, b"x" * capacity), capacity)
                    with subprocess.Popen([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
                                          stdout=writer, stderr=subprocess.PIPE) as child:
                        try:
                            self.assertTrue(select.select([child.stderr], [], [], 5)[0])
                            self.assertEqual(child.stderr.readline(), b"ready\n")
                            with self.assertRaises(subprocess.TimeoutExpired):
                                child.wait(timeout=0.1)
                            self.assertTrue(os.get_blocking(writer))
                            child.send_signal(sig)
                            self.assertEqual(child.wait(timeout=3), 2)
                        finally:
                            if child.poll() is None:
                                child.kill()
                    self.assertTrue(os.get_blocking(writer))

    def test_pipe_resumes_after_partial_write(self):
        reader, writer = os.pipe()
        with os.fdopen(reader, "rb", buffering=0) as source, os.fdopen(writer, "wb", buffering=0):
            capacity = fcntl.fcntl(writer, fcntl.F_GETPIPE_SZ)
            size = capacity * 3 + 13
            script = ("from tools.runner.suite import Output; import sys; "
                      "Output(1).write(b'x' * int(sys.argv[1]) + b'end')")
            with subprocess.Popen([sys.executable, "-c", script, str(size)],
                                  cwd=Path(__file__).resolve().parents[2], stdout=writer) as child:
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=0.1)
                    self.assertTrue(os.get_blocking(writer))
                    data = bytearray()
                    while len(data) < size + 3:
                        self.assertTrue(select.select([reader], [], [], 3)[0])
                        data.extend(source.read(4096))
                    self.assertEqual(child.wait(timeout=3), 0)
                    self.assertEqual(data, b"x" * size + b"end")
                finally:
                    if child.poll() is None:
                        child.kill()
            self.assertTrue(os.get_blocking(writer))

    def test_memory_failure_after_result_write(self):
        write = Output.write
        fired = False
        def exhaust(stream, data, progress=None):
            nonlocal fired
            write(stream, data, progress)
            if not fired and data.startswith(b"PASS "):
                fired = True
                raise MemoryError("after complete write")
        with patch.object(Output, "write", exhaust):
            code, out, err = self.invoke(1)
        self.assertTrue(fired)
        self.assertEqual(code, 3)
        self.assertEqual(out.count(b"PASS "), 1)
        self.assertIn(b"total=1 passed=1", out)
        self.assertIn(b"after complete write", err)

    def test_memory_failure_after_partial_result_write(self):
        write = os.write
        state = "initial"
        def short(fd, data):
            nonlocal state
            if state == "initial" and bytes(data).startswith(b"PASS "):
                state = "short"
                return write(fd, data[:3])
            return write(fd, data)
        def view(data):
            nonlocal state
            if state == "short":
                state = "interrupted"
                raise MemoryError("resuming partial write")
            return memoryview(data)
        with patch.object(os, "write", short), patch("tools.runner.suite.memoryview", view, create=True):
            code, out, err = self.invoke(1)
        self.assertEqual(state, "interrupted")
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[0], b"PASS src/a.mgn::App::a")
        self.assertIn(b"total=1 passed=1", out)
        self.assertIn(b"resuming partial write", err)

    def test_secondary_resource_failure_preserves_io_failure(self):
        def fail(image, arguments, outcome, application, diagnostic):
            outcome.state = "aborted"
            raise OSError(errno.EIO, "primary capture failure")
        display = Report.display
        calls = 0
        def exhaust(row, out, err):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise MemoryError("secondary reporting failure")
            display(row, out, err)
        with patch("tools.runner.suite.supervise", fail), patch.object(Report, "display", exhaust):
            code, out, err = self.invoke(2)
        self.assertEqual(code, 2)
        self.assertIn(b"aborted=1 not_run=1", out)
        self.assertIn(b"primary capture failure", err)
        self.assertIn(b"secondary reporting failure", err)

    def test_write_failure(self):
        with open("/dev/full", "wb", buffering=0) as out, tempfile.TemporaryFile() as err:
            code = run_suite(self.image, self.cases, out.fileno(), err.fileno())
            err.seek(0)
            data = err.read()
        self.assertEqual(code, 2)
        self.assertIn(b"mgn: ", data)
        self.assertNotIn(b"assertion failed", data)


if __name__ == "__main__":
    unittest.main()
