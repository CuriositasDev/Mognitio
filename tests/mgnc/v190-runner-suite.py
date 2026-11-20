#!/usr/bin/env python3
"""Check suite output, process exit aggregation, and reporting failures."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.runner.suite import Case, Span, run_suite

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

    def invoke(self, count):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            code = run_suite(self.image, self.cases[:count], out.fileno(), err.fileno())
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
