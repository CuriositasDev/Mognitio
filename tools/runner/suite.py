"""Render and aggregate already classified native test results."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import fcntl
import os
import select
import stat

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


@dataclass(slots=True)
class LineProgress:
    # Keep the last syscall's return value itself. Adding it to a large byte
    # offset or slicing a view can allocate, so do both before the next write.
    base: int = 0
    count: int = 0
    done: bool = False


@contextmanager
def report_fd(fd, flags):
    # A reopened FIFO has an independent file description. Shell pipelines
    # commonly share the original description with other processes.
    private = None
    mode = os.fstat(fd).st_mode
    try:
        if (not flags & os.O_NONBLOCK and (flags & os.O_ACCMODE) != os.O_RDONLY
                and stat.S_ISFIFO(mode)):
            with _defer_interrupts():
                try:
                    private = os.open(f"/proc/self/fd/{fd}", os.O_WRONLY | os.O_NONBLOCK)
                except OSError:
                    pass  # An inherited pipe may have no permission to reopen it.
        if private is None:
            yield fd, not (flags & os.O_NONBLOCK or stat.S_ISREG(mode))
        else:
            yield private, False
    finally:
        if private is not None:
            with _defer_interrupts():
                os.close(private)


class Output:
    def __init__(self, fd):
        self.fd = fd
        self.failed = False
        self.recovering = False

    def write(self, data, progress=None):
        if self.failed:
            raise OSError("Test report stream is unavailable")
        if progress is None:
            progress = LineProgress()
        if progress.done or not data:
            return
        try:
            flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
            with report_fd(self.fd, flags) as (fd, set_nonblocking):
                while not progress.done:
                    start = progress.base + progress.count
                    remaining = len(data) - start
                    chunk = memoryview(data)[start:] if start else data
                    try:
                        self._write_chunk(fd, set_nonblocking, chunk, start, remaining, progress)
                    except BlockingIOError:
                        if self.recovering or flags & os.O_NONBLOCK:
                            raise
                        waiter = select.poll()
                        waiter.register(fd, select.POLLOUT)
                        waiter.poll()
        except OSError:
            self.failed = True
            raise

    def _write_chunk(self, fd, set_nonblocking, chunk, start, remaining, progress):
        with _defer_interrupts():
            if set_nonblocking:
                os.set_blocking(fd, False)
            try:
                # Store the count and completion before restoring
                # flags or delivering any deferred signal.
                progress.base = start
                progress.count = 0
                try:
                    count = os.write(fd, chunk)
                except MemoryError:
                    # The syscall wrapper could not return a count.
                    # Its effect is unknown, so never replay it.
                    self.failed = True
                    raise
                if count == 0:
                    raise OSError("Cannot write test report")
                progress.count = count
                progress.done = count == remaining
            finally:
                if set_nonblocking:
                    os.set_blocking(fd, True)


FAILURES = (OSError, ProtocolError, KeyboardInterrupt, MemoryError)
STATES = ("passed", "failed", "errors", "aborted", "not_run")
LABELS = {"passed": "PASS", "failed": "FAIL", "errors": "ERROR", "aborted": "ABORTED"}


@dataclass
class Report:
    case: Case
    outcome: Outcome
    context: LineProgress = field(default_factory=LineProgress)
    assertion: LineProgress = field(default_factory=LineProgress)
    result: LineProgress = field(default_factory=LineProgress)

    def display(self, out, err):
        identity = one_line(self.case.identity)
        outcome = self.outcome
        if outcome.state != "passed" and not err.failed:
            if not self.context.done:
                message = f"{identity}; kind={outcome.kind or outcome.state}; stage={outcome.stage}"
                data = self.case.declaration.render("test", message)
                err.write(data, self.context)
            if outcome.site is not None and not self.assertion.done:
                data = self.case.sites[outcome.site].render("assertion", "assertion failed")
                err.write(data, self.assertion)
        if not out.failed and not self.result.done:
            detail = " " + outcome.kind if outcome.kind else ""
            data = f"{LABELS[outcome.state]}{detail} {identity}\n".encode()
            out.write(data, self.result)


def run_suite(image, cases, stdout_fd=1, stderr_fd=2, *, cleanup=None):
    """Run one freshly spawned image per ordinal in the compiler's ordered plan."""
    out, err = Output(stdout_fd), Output(stderr_fd)
    summary_progress = LineProgress()
    reports = []
    primary = None

    def diagnose(error):
        if not err.failed:
            err.write(f"mgn: {one_line(str(error) or type(error).__name__)}\n".encode())

    def record(error):
        nonlocal primary
        out.recovering = err.recovering = True
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

    result = 0

    def finish():
        nonlocal result
        counts = dict.fromkeys(STATES, 0)
        for row in reports:
            counts[row.outcome.state] += 1
            if row.outcome.kind == "abnormal":
                result = 6
            elif row.outcome.state == "errors" and result != 6:
                result = 4
            elif row.outcome.state == "failed" and result == 0:
                result = 5
            if row.outcome.state != "not_run" and not row.result.done:
                if not attempt(row.display, out, err):
                    attempt(row.display, out, err)
        if not summary_progress.done and not out.failed and (primary is None or counts["not_run"] < len(reports) or not cases):
            summary = " ".join(f"{state}={counts[state]}" for state in STATES)
            out.write(f"tests: total={len(cases)} {summary}\n".encode(), summary_progress)

    if not attempt(finish) and not out.failed:
        attempt(finish)
    if primary is not None:
        attempt(diagnose, primary)
        if isinstance(primary, OSError) and primary.errno == errno.ENOMEM:
            return 3
        return 3 if isinstance(primary, (ProtocolError, MemoryError)) else 2
    return result
