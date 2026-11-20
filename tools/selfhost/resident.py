"""Execute a checked Mognitio application with the caller's finite file-size limit."""
from array import array
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.selfhost.client import decimal, request, WorkerError
from tools.selfhost.command import compiler_diagnostic, report
from tools.selfhost.payload import COMPILER, payload_identity


class CompileFailure(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def compile_project(manifest):
    ident = payload_identity(ROOT)
    body = bytearray()
    references = array("I")
    size = None

    def receive(fields):
        nonlocal size
        if size is None and len(fields) == 1:
            size = decimal(fields[0], 999999999)
            if not size:
                raise WorkerError("Empty application")
        elif size is not None and len(fields) == 2 and fields[0] == "bytes":
            value = bytes.fromhex(fields[1])
            if references or not value or len(body) + len(value) > size:
                raise WorkerError("Invalid application extent")
            body.extend(value)
        elif size is not None and len(body) == size and len(fields) == 2 and fields[0] == "reference":
            offset = decimal(fields[1], size)
            if offset + 8 > size or references and offset < references[-1]+8:
                raise WorkerError("Invalid application reference")
            references.append(offset)
        else:
            raise WorkerError("Unexpected compiler application field")

    reply = request(ROOT / COMPILER, ident["build"], "application", path=manifest, on_application=receive)
    if reply.status == "diagnostic":
        raise CompileFailure(*compiler_diagnostic(reply.fields))
    if reply.status != "application" or len(body) != size:
        raise WorkerError("Incomplete application")
    return bytes(body), references.tobytes()


def main():
    from tools.selfhost import _application
    try:
        return _application.run_project(sys.argv[1], tuple(os.fsencode(v) for v in sys.argv[2:]))
    except CompileFailure as error:
        return report(error.status, str(error))
    except (ValueError, OSError, WorkerError, RuntimeError, MemoryError) as error:
        return report(3, str(error))


if __name__ == "__main__":
    # The new process has the original application streams and no compiler fd.
    # Import by its package name so the native entry and CLI share exception types.
    from tools.selfhost.resident import main
    sys.exit(main())
