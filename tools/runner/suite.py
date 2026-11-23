"""Render and aggregate already classified native test results."""
from dataclasses import dataclass
import errno
import os

from .events import Outcome, ProtocolError
from .supervisor import _defer_interrupts, supervise


def one_line(text):
    result = []
    for char in text:
        if char in "\\\n\r":
            result.append({"\\": "\\\\", "\n": "\\n", "\r": "\\r"}[char])
        elif ord(char) < 32 or char in "\x7f\u2028\u2029":
            result.append(f"\\u{ord(char):04X}")
        else:
            result.append(char)
    return "".join(result)


def escaped_byte(byte):
    special = {0: "\\0", 9: "\\t", 10: "\\n", 13: "\\r", 34: '\\"', 92: "\\\\"}
    return special.get(byte, chr(byte) if 32 <= byte < 127 else f"\\x{byte:02X}")


ESCAPES = tuple(escaped_byte(byte) for byte in range(256))


@dataclass(frozen=True)
class Span:
    path: str
    line: int
    column: int
    start: int
    end: int

    def render(self, phase, message):
        return (f"{one_line(self.path)}:{self.line}:{self.column}: {phase}: {message} "
                f"[bytes {self.start},{self.end})\n").encode()


@dataclass(frozen=True)
class Case:
    identity: str
    declaration: Span
    sites: tuple[Span, ...]


class Output:
    def __init__(self, fd):
        self.fd = fd
        self.failed = False

    def write(self, data):
        if self.failed:
            raise OSError("Test report stream is unavailable")
        remaining = memoryview(data)
        try:
            while remaining:
                count = os.write(self.fd, remaining)
                if count == 0:
                    raise OSError("Cannot write test report")
                remaining = remaining[count:]
        except OSError:
            self.failed = True
            raise


FAILURES = (OSError, ProtocolError, KeyboardInterrupt, MemoryError)
STATES = ("passed", "failed", "errors", "aborted", "not_run")
LABELS = {"passed": "PASS", "failed": "FAIL", "errors": "ERROR", "aborted": "ABORTED"}


@dataclass
class Report:
    case: Case
    outcome: Outcome
    context: bool = False
    assertion: bool = False
    result: bool = False

    def display(self, out, err):
        identity = one_line(self.case.identity)
        outcome = self.outcome
        if outcome.state != "passed" and not err.failed:
            if not self.context:
                message = f"{identity}; kind={outcome.kind or outcome.state}; stage={outcome.stage}"
                data = self.case.declaration.render("test", message)
                with _defer_interrupts():
                    err.write(data)
                    self.context = True
            if outcome.site is not None and not self.assertion:
                data = self.case.sites[outcome.site].render("assertion", "assertion failed")
                with _defer_interrupts():
                    err.write(data)
                    self.assertion = True
        if not out.failed and not self.result:
            detail = " " + outcome.kind if outcome.kind else ""
            data = f"{LABELS[outcome.state]}{detail} {identity}\n".encode()
            with _defer_interrupts():
                out.write(data)
                self.result = True


def run_suite(image, cases, stdout_fd=1, stderr_fd=2, *, cleanup=None):
    """Run one freshly spawned image per ordinal in the compiler's ordered plan."""
    out, err = Output(stdout_fd), Output(stderr_fd)
    reports = []
    primary = None

    def diagnose(error):
        if not err.failed:
            err.write(f"mgn: {one_line(str(error) or type(error).__name__)}\n".encode())

    def record(error):
        nonlocal primary
        if primary is None:
            primary = error
        else:
            try:
                diagnose(error)
            except FAILURES:
                pass

    def attempt(action, *args):
        try:
            action(*args)
            return True
        except FAILURES as error:
            record(error)
            return False

    try:
        reports = [Report(case, Outcome(i, len(case.sites))) for i, case in enumerate(cases)]
        for row in reports:
            ident = one_line(row.case.identity)

            def application(stream, chunk):
                escaped = "".join(ESCAPES[byte] for byte in chunk)
                err.write(f'output {ident} {stream}: "{escaped}"\n'.encode())

            supervise(image, [str(row.outcome.ordinal)], row.outcome, application, err.write)
            row.display(out, err)
    except FAILURES as error:
        record(error)
    finally:
        if cleanup is not None:
            try:
                with _defer_interrupts():
                    cleanup(record)
            except FAILURES as error:
                record(error)

    summary_sent = False
    result = 0

    def finish():
        nonlocal summary_sent, result
        counts = dict.fromkeys(STATES, 0)
        for row in reports:
            counts[row.outcome.state] += 1
            if row.outcome.kind == "abnormal":
                result = 6
            elif row.outcome.state == "errors" and result != 6:
                result = 4
            elif row.outcome.state == "failed" and result == 0:
                result = 5
            if row.outcome.state != "not_run" and not row.result:
                if not attempt(row.display, out, err):
                    attempt(row.display, out, err)
        if not summary_sent and not out.failed and (primary is None or counts["not_run"] < len(reports) or not cases):
            summary = " ".join(f"{state}={counts[state]}" for state in STATES)
            with _defer_interrupts():
                out.write(f"tests: total={len(cases)} {summary}\n".encode())
                summary_sent = True

    if not attempt(finish) and not out.failed:
        attempt(finish)
    if primary is not None:
        attempt(diagnose, primary)
        if isinstance(primary, OSError) and primary.errno == errno.ENOMEM:
            return 3
        return 3 if isinstance(primary, (ProtocolError, MemoryError)) else 2
    return result
