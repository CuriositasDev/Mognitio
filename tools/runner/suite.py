"""Render and aggregate already classified native test results."""
from collections import Counter
from dataclasses import dataclass
import os

from .events import Outcome, ProtocolError
from .supervisor import supervise


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


def run_suite(image, cases, stdout_fd=1, stderr_fd=2):
    """Run one freshly spawned image per ordinal in the compiler's ordered plan."""
    out, err = Output(stdout_fd), Output(stderr_fd)
    outcomes = [Outcome(index, len(case.sites)) for index, case in enumerate(cases)]
    primary = None

    def record_error(error):
        nonlocal primary
        if primary is None:
            primary = error

    def try_write(output, data):
        if not output.failed:
            try:
                output.write(data)
            except OSError as error:
                record_error(error)

    displayed = 0

    def report(case, outcome):
        identity = one_line(case.identity)
        if outcome.state != "passed" and not err.failed:
            message = f"{identity}; kind={outcome.kind or outcome.state}; stage={outcome.stage}"
            try_write(err, case.declaration.render("test", message))
            if outcome.site is not None:
                try_write(err, case.sites[outcome.site].render("assertion", "assertion failed"))
        if not out.failed:
            label = {"passed": "PASS", "failed": "FAIL", "errors": "ERROR", "aborted": "ABORTED"}[outcome.state]
            detail = " " + outcome.kind if outcome.kind else ""
            try_write(out, f"{label}{detail} {identity}\n".encode())

    try:
        for case, outcome in zip(cases, outcomes):
            ident = one_line(case.identity)
            def application(stream, chunk):
                escaped = "".join(ESCAPES[byte] for byte in chunk)
                err.write(f'output {ident} {stream}: "{escaped}"\n'.encode())

            supervise(image, [str(outcome.ordinal)], outcome, application, err.write)
            report(case, outcome)
            displayed += 1
            if primary is not None:
                break
    except (OSError, ProtocolError, KeyboardInterrupt, MemoryError) as error:
        record_error(error)

    counts = Counter(outcome.state for outcome in outcomes)
    if primary is None or counts["not_run"] < len(cases):
        for case, outcome in zip(cases[displayed:], outcomes[displayed:]):
            if outcome.state == "not_run":
                break
            report(case, outcome)
        if not out.failed:
            summary = " ".join(f"{state}={counts[state]}" for state in ("passed", "failed", "errors", "aborted", "not_run"))
            try_write(out, f"tests: total={len(cases)} {summary}\n".encode())
    if primary is not None:
        try_write(err, f"mgn: {one_line(str(primary) or type(primary).__name__)}\n".encode())
        return 3 if isinstance(primary, (ProtocolError, MemoryError)) else 2
    if any(outcome.kind == "abnormal" for outcome in outcomes):
        return 6
    if counts["errors"]:
        return 4
    return 5 if counts["failed"] else 0
