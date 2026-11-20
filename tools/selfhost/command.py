"""Prepare and execute normal build and run commands with the paired native compiler."""
from contextlib import contextmanager
import os
import signal
import subprocess

from .client import WorkerError, request
from .publication import Artifact


class UsageError(Exception):
    pass


class Interrupted(BaseException):
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


def report(code, message):
    data = ("mgn: " + message + "\n").encode("utf-8", "backslashreplace")
    try:
        while data:
            size = os.write(2, data)
            data = data[size:]
    except OSError:
        pass
    return code


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
        raise UsageError("Expected run or build and an explicit mognitio.toml")
    command, raw_manifest = argv[:2]
    manifest = path_arg(raw_manifest)
    if manifest.startswith("-") or os.path.basename(manifest) != "mognitio.toml":
        raise UsageError("Expected an explicit mognitio.toml")
    if command == b"build" and len(argv) == 4 and argv[2] == b"-o":
        output, arguments = path_arg(argv[3]), []
    elif command == b"run" and (len(argv) == 2 or argv[2] == b"--"):
        output, arguments = None, argv[3:]
    else:
        raise UsageError("Expected run <manifest> [-- arguments...] or build <manifest> -o <artifact>")
    with Artifact(output) as artifact:
        def ready(inputs):
            # Linux argv bytes belong to the generated program. Decode solely
            # for validation after the complete project passed static checking.
            for arg in arguments:
                try:
                    arg.decode("utf-8", "strict")
                except UnicodeDecodeError as error:
                    raise UsageError("Invalid UTF-8 in application argument") from error
            return artifact.prepare(inputs)

        result = request(compiler, build, "build", path=manifest, on_ready=ready)
        if result.status == "diagnostic":
            status, path, phase, message, known, start, end, line, column, operation, kind, io_phase = result.fields
            location = f"{line}:{column} [{start},{end})" if known == "1" else "position unknown"
            cause = " / ".join(value for value in (operation, kind, io_phase) if value)
            detail = f" ({cause})" if cause else ""
            return report(int(status), f"{phase}: {path!r}: {location}: {message}{detail}")
        if result.status == "publication":
            return report(2, result.fields[1].rstrip("\n"))
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
        return report(2, str(error))
    except Interrupted as interrupt:
        return -interrupt.signum
    except (WorkerError, ValueError) as error:
        return report(3, f"compiler: {error}")
    except OSError as error:
        return report(2, f"I/O: {error}")


def exit_status(status):
    if status < 0:
        sig = -status
        if sig not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(sig, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {sig})
        os.kill(os.getpid(), sig)
    return status
