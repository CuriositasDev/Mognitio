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
def report_fd(fd, blocking_pipe):
    private = None
    try:
        if blocking_pipe:
            with _defer_interrupts():
                try:
                    private = os.open(f"/proc/self/fd/{fd}", os.O_WRONLY | os.O_NONBLOCK)
                except OSError:
                    pass  # The original write end can remain usable when reopening fails.
        yield private if private is not None else fd
    finally:
        if private is not None:
            with _defer_interrupts():
                os.close(private)


def write_shared_pipe(fd, data):
    # NOWAIT is per call. Named FIFOs on some supported kernels lack it.
    try:
        return os.pwritev(fd, (data,), -1, os.RWF_NOWAIT)
    except OSError as error:
        if error.errno not in (errno.EOPNOTSUPP, errno.ENOSYS, errno.ESPIPE):
            raise

    # Stage at most one atomic pipe write. Only the splice commits bytes to
    # the report stream, and both pipes keep their original status flags.
    reader, writer = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        size = os.write(writer, memoryview(data)[:select.PIPE_BUF])
        return os.splice(reader, fd, size, flags=os.SPLICE_F_NONBLOCK)
    finally:
        os.close(reader)
        os.close(writer)


class Output:
    def __init__(self, fd):
        self.fd = fd
        self.failed = False
        self.recovering = False
        self.pending = None

    def write(self, data, progress=None):
        if self.failed:
            raise OSError("Test report stream is unavailable")
        # Finish the record that owns this stream before admitting any other
        # record, including a secondary diagnostic generated during recovery.
        if self.pending is not None:
            self._flush()
        if progress is None:
            progress = LineProgress()
        if progress.done or not data:
            return
        self.pending = data, progress
        self._flush()

    def _flush(self):
        data, progress = self.pending
        if not progress.done:
            try:
                self._emit(data, progress)
            except OSError:
                self.failed = True
                raise
        self.pending = None

    def _emit(self, data, progress):
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        mode = os.fstat(self.fd).st_mode
        blocking = not flags & os.O_NONBLOCK
        blocking_pipe = blocking and stat.S_ISFIFO(mode)
        writable_pipe = blocking_pipe and (flags & os.O_ACCMODE) != os.O_RDONLY
        set_nonblocking = blocking and not blocking_pipe and not stat.S_ISREG(mode)
        with report_fd(self.fd, writable_pipe) as fd:
            write = write_shared_pipe if blocking_pipe and fd == self.fd else os.write
            while not progress.done:
                start = progress.base + progress.count
                remaining = len(data) - start
                chunk = memoryview(data)[start:] if start else data
                try:
                    self._write_chunk(write, fd, set_nonblocking, chunk, start, remaining, progress)
                except BlockingIOError:
                    if self.recovering or not blocking:
                        raise
                    waiter = select.poll()
                    waiter.register(fd, select.POLLOUT)
                    waiter.poll()

    def _write_chunk(self, write, fd, set_nonblocking, chunk, start, remaining, progress):
        with _defer_interrupts():
            if set_nonblocking:
                os.set_blocking(fd, False)
            try:
                progress.base = start
                progress.count = 0
                try:
                    count = write(fd, chunk)
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
    secondary = []

    def diagnose(error):
        if not err.failed:
            try:
                err.write(f"mgn: {one_line(str(error) or type(error).__name__)}\n".encode())
            except FAILURES:
                pass

    def record(error):
        nonlocal primary
        out.recovering = err.recovering = True
        if primary is None:
            primary = error
        else:
            try:
                secondary.append(error)
            except MemoryError:
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
        # stdout and stderr may have been redirected to the same destination.
        # Finish the suite records before rendering queued command diagnostics.
        for error in secondary:
            diagnose(error)
        diagnose(primary)
        if isinstance(primary, OSError) and primary.errno == errno.ENOMEM:
            return 3
        return 3 if isinstance(primary, (ProtocolError, MemoryError)) else 2
    return result
