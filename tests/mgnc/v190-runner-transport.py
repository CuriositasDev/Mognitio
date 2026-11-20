#!/usr/bin/env python3
"""Exercise native event framing, start delegation, pipe draining, and ledger commits."""
import os
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.runner.events import Events, Outcome, ProtocolError
from tools.runner.supervisor import supervise

# These are child-side bytes. Keep the encoder independent of the decoder.
CHILD = """
import os, struct, sys
def event(sequence, tag, stage=0, kind=0, site=(1<<64)-1):
    return struct.pack('<IHHQQIIQ',0x544e474d,4,tag,0,sequence,stage,kind,site)
def ready():
    os.write(3,event(0,1))
    assert os.read(4,1)==b'\\x01'
def enter():
    ready()
    os.write(3,event(1,2,1)+event(2,2,2))
"""


class TransportTests(unittest.TestCase):
    def child(self, body, outcome=None, application=None, diagnostic=None):
        if outcome is None:
            outcome = Outcome(0, 2)
        supervise(sys.executable, ["-c", CHILD + "\n" + body], outcome,
                  application or (lambda stream, data: self.fail(repr((stream, data)))),
                  diagnostic or (lambda data: self.fail(repr(data))))
        return outcome

    def test_success_and_failed_assertion(self):
        for kind, code, site, expected in [(0, 0, (1 << 64)-1, "passed"), (1, 5, 1, "failed")]:
            with self.subTest(kind=kind):
                result = self.child(f"enter()\nos.write(3,event(3,3,2,{kind},{site}))\nsys.exit({code})")
                self.assertEqual((result.state, result.stage), (expected, "body"))
                self.assertEqual(result.site, 1 if kind else None)

    def test_output_pressure_and_late_diagnostic(self):
        outputs = {"stdout": bytearray(), "stderr": bytearray()}
        diagnostic = bytearray()

        def collect_diagnostic(data):
            self.assertEqual(len(outputs["stdout"]), 128 * 8192)
            self.assertEqual(len(outputs["stderr"]), 128 * 8192)
            diagnostic.extend(data)

        result = self.child("""enter()
for i in range(128):
    os.write(1,b'x'*8192)
    os.write(2,b'y'*8192)
os.write(3,event(3,3,2,2))
os.close(3)
os.write(5,b'panic payload')
sys.exit(4)""", application=lambda stream, data: outputs[stream].extend(data),
                            diagnostic=collect_diagnostic)
        self.assertEqual((result.state, result.kind), ("errors", "panic"))
        self.assertEqual(outputs, {"stdout": b"x" * (128*8192), "stderr": b"y" * (128*8192)})
        self.assertEqual(diagnostic, b"panic payload")

    def test_stopped_child_and_partial_record(self):
        for ending in ("os.write(3,b'x')", "os.kill(os.getpid(),9)"):
            result = self.child("ready()\n" + ending)
            self.assertEqual((result.state, result.kind), ("errors", "abnormal"))

    def test_malformed_events(self):
        for fault in ("os.write(3,event(0,1)+event(1,2,1))",
                      "enter()\nos.write(3,event(3,3,2,1,2))",
                      "enter()\nos.write(3,event(3,3,2,2))",
                      "enter()\nos.write(3,event(3,3,2)+event(4,2,2))"):
            with self.subTest(fault=fault), self.assertRaises(ProtocolError):
                self.child(fault)

    def test_commit_requires_all_evidence(self):
        for order in ((0, 1, 2), (0, 2, 1), (2, 0, 1)):
            with self.subTest(order=order):
                outcome = Outcome(0, 0)
                stream = Events(outcome)
                stream.feed(bytes.fromhex("4d474e5404000100") + bytes(24) + b"\xff"*8)
                outcome.state = "running"
                def record(seq, tag, stage):
                    return (bytes.fromhex("4d474e540400") + tag.to_bytes(2,"little") + bytes(8)
                            + seq.to_bytes(8,"little") + stage.to_bytes(4,"little") + bytes(4) + b"\xff"*8)
                stream.feed(record(1,2,1) + record(2,2,2))
                status = None
                for i, step in enumerate(order):
                    if step == 0:
                        for byte in record(3,3,2):
                            stream.feed(bytes([byte]))
                    elif step == 1:
                        stream.eof = True
                    else:
                        status = 0
                    stream.commit(status)
                    self.assertEqual(outcome.state, "passed" if i == 2 else "running")
                outcome.abort()
                self.assertEqual(outcome.state, "passed")

    def test_private_status_and_early_exit(self):
        for code, exception in ((0, OSError), (123, ProtocolError), (124, OSError)):
            outcome = Outcome(0, 0)
            with self.subTest(code=code), self.assertRaises(exception):
                self.child(f"sys.exit({code})", outcome)
            self.assertEqual(outcome.state, "not_run")

    def test_interrupt_at_successful_gate(self):
        original = os.write
        def write_and_interrupt(fd, data):
            written = original(fd, data)
            os.kill(os.getpid(), signal.SIGINT)
            return written
        outcome = Outcome(0, 0)
        with patch("tools.runner.supervisor.os.write", write_and_interrupt), self.assertRaises(KeyboardInterrupt):
            self.child("ready()\nimport time\ntime.sleep(30)", outcome)
        self.assertEqual(outcome.state, "aborted")


if __name__ == "__main__":
    unittest.main()
