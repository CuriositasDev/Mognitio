#!/usr/bin/env python3
"""Check suite output, process exit aggregation, and reporting failures."""
from pathlib import Path
import os
import errno
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
        write = Output.write
        for marker in (b"PASS ", b": test:", b": assertion:", b"FAIL ", b"tests: "):
            with self.subTest(marker=marker):
                fired = False
                def interrupt(stream, data):
                    nonlocal fired
                    write(stream, data)
                    if not fired and marker in data:
                        fired = True
                        os.kill(os.getpid(), signal.SIGINT)
                with patch.object(Output, "write", interrupt):
                    code, out, err = self.invoke(2)
                self.assertTrue(fired)
                self.assertEqual(code, 2)
                self.assertEqual(out.count(b"PASS "), 1)
                self.assertEqual(out.count(b"tests: "), 1)
                if marker != b"PASS ":
                    self.assertEqual(out.count(b"FAIL "), 1)
                    self.assertEqual(err.count(b": test:"), 1)
                    self.assertEqual(err.count(b": assertion:"), 1)

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
