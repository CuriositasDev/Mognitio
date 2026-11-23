"""Prepare and execute normal build and run commands with the paired native compiler."""
from contextlib import contextmanager
import errno
import os
import signal
import resource
import sys
from pathlib import Path
import subprocess

from .client import WorkerError, request
from .publication import Artifact
from .testplan import cases_from
from ..runner.suite import run_suite


class UsageError(Exception):
    origin = "mgn"


class ArgumentEncodingError(UsageError):
    origin = "runtime"


class Interrupted(KeyboardInterrupt):
    def __init__(self, signum):
        self.signum = signum


@contextmanager
def interruptible():
    def interrupt(signum, frame):
        raise Interrupted(signum)

    saved = {}
    try:
        for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(sig)
            if previous != signal.SIG_IGN:
                saved[sig] = signal.signal(sig, interrupt)
        yield
    finally:
        for sig, previous in saved.items():
            signal.signal(sig, previous)


def report(code, message, origin="mgn"):
    data = (origin + ": " + message + "\n").encode("utf-8", "backslashreplace")
    try:
        while data:
            size = os.write(2, data)
            data = data[size:]
    except OSError:
        pass
    return code


def one_line(text):
    escaped = {"\\": "\\\\", "\n": "\\n", "\r": "\\r"}
    return "".join(escaped.get(ch, f"\\u{ord(ch):04X}" if ord(ch) < 32 or
                               ord(ch) in (127, 0x2028, 0x2029) else ch) for ch in text)


def compiler_diagnostic(fields):
    status, path, phase, message, known, start, end, line, column, operation, kind, io_phase = fields[:12]
    phase = "lex" if phase == "lexical" else phase
    source = one_line(path)
    cause = " / ".join(one_line(value) for value in (operation, kind, io_phase) if value)
    detail = f" ({cause})" if cause else ""
    if known == "1":
        lines = [f"{source}:{line}:{column}: {phase}: {one_line(message)} [bytes {start},{end}){detail}"]
    else:
        lines = [f"{source}: {phase}: {one_line(message)} (position unknown){detail}"]
    for i in range(12, len(fields), 6):
        path, note, start, end, line, column = fields[i:i+6]
        lines.append(f"{one_line(path)}:{line}:{column}: {phase}: {one_line(note)} [bytes {start},{end})")
    return int(status), "\n".join(lines)


def path_arg(raw):
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise UsageError("Invalid UTF-8 in path") from error
    if not text or "\0" in text:
        raise UsageError("Invalid path")
    return text


def application(image, arguments):
    with subprocess.Popen([os.fsencode(image), *arguments], close_fds=True) as child:
        try:
            return child.wait()
        except Interrupted as interrupt:
            if child.poll() is None:
                child.send_signal(interrupt.signum)
            raise
        finally:
            if child.poll() is None:
                try:
                    child.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def prepare_and_run(compiler, build, argv):
    if len(argv) < 2:
        raise UsageError("Expected run, build or test and an explicit mognitio.toml")
    command, raw_manifest = argv[:2]
    manifest = path_arg(raw_manifest)
    if manifest.startswith("-") or os.path.basename(manifest) != "mognitio.toml":
        raise UsageError("Expected an explicit mognitio.toml")
    if command == b"build" and len(argv) == 4 and argv[2] == b"-o":
        output, arguments = path_arg(argv[3]), []
    elif command == b"test" and len(argv) == 2:
        output, arguments = None, []
    elif command == b"run" and (len(argv) == 2 or argv[2] == b"--"):
        output, arguments = None, argv[3:]
    else:
        raise UsageError("Expected test <manifest>, run <manifest> [-- arguments...] or build <manifest> -o <artifact>")
    if command == b"run" and resource.getrlimit(resource.RLIMIT_FSIZE)[0] != resource.RLIM_INFINITY:
        runner = Path(__file__).with_name("resident.py")
        return application(sys.executable, [b"-I", b"-B", os.fsencode(runner), os.fsencode(manifest), *arguments])
    # Setup can fail after creating the private directory but before a suite
    # owns it. Preserve that failure and identify any remaining private names.
    def cleanup_diagnostic(error):
        report(2, str(error))

    with Artifact(output, on_cleanup_error=cleanup_diagnostic if command == b"test" else None) as artifact:
        def ready(inputs):
            # Linux argv bytes belong to the generated program. Decode solely
            # for validation after the complete project passed static checking.
            for arg in arguments:
                try:
                    arg.decode("utf-8", "strict")
                except UnicodeDecodeError as error:
                    raise ArgumentEncodingError("invalid UTF-8 runtime argument") from error
            return artifact.prepare(inputs)

        profile = "suite" if command == b"test" else "build"
        result = request(compiler, build, profile, path=manifest, on_ready=ready)
        if result.status == "diagnostic":
            status, message = compiler_diagnostic(result.fields)
            return report(status, message)
        if result.status == "publication":
            return report(2, result.fields[1].rstrip("\n"))
        if command == b"test":
            cases = cases_from(result.fields)
            if cases:
                artifact.verify_image()
            return run_suite(artifact.leaf, cases, cleanup=artifact.cleanup)
        if output is not None:
            artifact.publish()
            return 0
        artifact.verify_image()
        return application(artifact.leaf, arguments)


def compile_command(compiler, build, argv):
    try:
        with interruptible():
            return prepare_and_run(compiler, build, argv)
    except UsageError as error:
        return report(2, str(error), error.origin)
    except Interrupted as interrupt:
        return -interrupt.signum
    except (MemoryError, WorkerError, ValueError) as error:
        return report(3, f"compiler: {error}")
    except OSError as error:
        if error.errno == errno.ENOMEM:
            return report(3, "Compiler memory exhausted")
        return report(2, f"I/O: {error}")


def exit_status(status):
    if status < 0:
        sig = -status
        if sig not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(sig, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {sig})
        os.kill(os.getpid(), sig)
    return status
