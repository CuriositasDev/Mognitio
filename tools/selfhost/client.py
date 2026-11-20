"""Use the private sequenced-packet channel of an identity-bearing compiler."""
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import re
import secrets
import selectors
import socket
import subprocess
import time

EXEC_NAME = "mognitio-compiler-worker-v1"
MAX_REQUEST = 8192
MAX_REPLY = 64 * 1024 * 1024
MAX_PACKET = 128 * 1024
MAX_DIAGNOSTIC = 64 * 1024


class WorkerError(Exception):
    pass


@dataclass(frozen=True)
class Reply:
    status: str
    fields: tuple[str, ...]


def decimal(value, maximum):
    if not re.fullmatch(r"0|[1-9][0-9]{0,8}", value) or int(value) > maximum:
        raise WorkerError("Invalid count in compiler response")
    return int(value)


def decode_fields(data):
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as fault:
        raise WorkerError("Invalid UTF-8 in compiler response") from fault
    fields = []
    pos = 0
    while pos < len(text):
        colon = text.find(":", pos, pos + 10)
        if colon < 0:
            raise WorkerError("Missing counted field length")
        length = decimal(text[pos:colon], MAX_REPLY)
        pos = colon + 1
        end = pos + length
        if end > len(text):
            raise WorkerError("Incomplete counted field")
        fields.append(text[pos:end])
        pos = end
    return tuple(fields)


def inspect_reply(wire, expected):
    pieces = bytes(wire).split(b"\0", 6)
    if len(pieces) != 7 or pieces[:5] != expected:
        raise WorkerError("Compiler response does not identify this request")
    try:
        return Reply(pieces[5].decode("ascii"), decode_fields(pieces[6]))
    except UnicodeDecodeError as fault:
        raise WorkerError("Invalid compiler status") from fault


def validate(reply, profile, stage):
    fields = reply.fields
    if reply.status == "diagnostic":
        if len(fields) != 12 or fields[0] not in ("1", "2", "3") or fields[4] not in ("0", "1"):
            raise WorkerError("Invalid compiler diagnostic")
        start, end, line, column = (decimal(v, 999999999) for v in fields[5:9])
        if end < start or not line or not column:
            raise WorkerError("Invalid diagnostic span")
    elif reply.status == "analysis" and profile in ("syntax", "analysis"):
        allowed = ("syntax",) if profile == "syntax" else ("checked", "partial")
        if not fields or fields[0] not in allowed:
            raise WorkerError("Invalid analysis completion state")
    elif reply.status == "plan" and profile == "tests":
        if not fields or len(fields) != 1 + 5 * decimal(fields[0], MAX_REPLY // 10):
            raise WorkerError("Invalid test plan size")
        for index in range(int(fields[0])):
            ordinal, path, namespace, name, offset = fields[1+5*index:6+5*index]
            if ordinal != str(index) or not path or not name or not namespace:
                raise WorkerError("Invalid test case identity")
            decimal(offset, 999999999)
    elif reply.status == "suite" and profile == "suite":
        if (len(fields) < 3 or fields[0] != (stage or "") or (not stage and fields != ("", "0", "0"))
                or (stage and fields[1] == "0")):
            raise WorkerError("Unexpected suite artifact")
    elif reply.status == "built" and profile == "build":
        if not stage or fields != (stage,):
            raise WorkerError("Unexpected compiler artifact")
    elif reply.status == "publication" and profile in ("build", "suite"):
        if not stage or len(fields) != 2 or fields[0] != stage:
            raise WorkerError("Unexpected publication result")
    elif reply.status != "ok" or profile not in ("syntax", "identity", "analysis") or fields:
        raise WorkerError("Unexpected compiler result")
    return reply


def packet(sock, data):
    if sock.send(data) != len(data):
        raise WorkerError("Incomplete control packet")


def offer(sock, data):
    if not 0 < len(data) <= MAX_REQUEST:
        raise WorkerError("Request exceeds the control limit")
    count = str(len(data)).encode()
    packet(sock, count)
    packet(sock, b"")
    return b"MGN-BODY/1\0" + count + b"\0"


def send_body(sock, body):
    # Keep each record below both native implementations' stdin scratch size.
    for start in range(0, len(body), 256):
        packet(sock, body[start:start + 256])
    packet(sock, b"")


def request(compiler, build, profile, *, path="", generation="", timeout=None, on_ready=None):
    if not re.fullmatch("[0-9a-f]{64}", build):
        raise ValueError("Invalid compiler identity")
    if profile not in ("identity", "analysis", "syntax", "tests", "build", "suite"):
        raise ValueError("Unsupported worker profile")
    if (bool(generation) != (profile in ("analysis", "syntax"))
            or bool(path) != (profile != "identity") or (on_ready is not None) != (profile in ("build", "suite"))):
        raise ValueError("Incorrect worker request fields")
    rid = secrets.token_hex(16)
    parts = ["MGN-REQUEST/1", build, rid, profile, generation, os.fspath(path)]
    if any("\0" in part for part in parts):
        raise ValueError("NUL in worker control field")
    body = ("\0".join(parts) + "\0").encode()
    expected = [s.encode() for s in ("MGN-RESULT/1", build, rid, profile, generation)]
    prepared = b"MGN-PREPARED/1\0" + rid.encode() + b"\0"
    deadline = None if timeout is None else time.monotonic() + timeout

    def remaining():
        if deadline is None:
            return None
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Compiler request timed out")
        return value

    parent, child = socket.socketpair(type=socket.SOCK_SEQPACKET)
    guard = Path(__file__).resolve().parents[1] / "lsp/worker_exec.py"
    launch = [sys.executable, "-I", "-B", str(guard), str(os.getpid()), "--argv0", EXEC_NAME,
              os.path.abspath(compiler)]
    with parent, child, subprocess.Popen(launch, stdin=child, stdout=child,
                                        stderr=subprocess.PIPE, close_fds=True) as process:
        try:
            child.close()
            wire = bytearray()
            diagnostics = bytearray()
            hello = b"MGN-WORKER/1\0" + build.encode() + b"\0"
            admission = None
            greeted = False
            stage = None
            with selectors.DefaultSelector() as poll:
                poll.register(parent, selectors.EVENT_READ, "control")
                poll.register(process.stderr, selectors.EVENT_READ, "stderr")
                while poll.get_map():
                    for key, mask in poll.select(remaining()):
                        if key.data == "stderr":
                            data = os.read(key.fd, 16384)
                            if not data:
                                poll.unregister(key.fileobj)
                            diagnostics.extend(data)
                            if len(diagnostics) > MAX_DIAGNOSTIC:
                                raise WorkerError("Compiler diagnostic stream exceeds limit")
                            continue
                        data, ancillary, flags, address = parent.recvmsg(MAX_PACKET)
                        if flags & socket.MSG_TRUNC:
                            raise WorkerError("Oversized compiler response packet")
                        if not data:
                            poll.unregister(parent)
                            continue
                        parent.settimeout(remaining())
                        if not greeted:
                            if data != hello:
                                raise WorkerError("Compiler handshake mismatch")
                            greeted = True
                            admission = offer(parent, body)
                        elif admission is not None:
                            if data != admission:
                                raise WorkerError("Compiler refused frame length")
                            send_body(parent, body)
                            admission = None
                        elif data == prepared:
                            ready = inspect_reply(wire, expected)
                            if (on_ready is None or stage is not None or ready.status != "ready" or
                                    not ready.fields or decimal(ready.fields[0], MAX_REPLY // 2) != len(ready.fields)-1
                                    or not ready.fields[1:] or ready.fields[1] != os.fspath(path)):
                                raise WorkerError("Unexpected compiler preparation")
                            stage = os.fspath(on_ready(ready.fields[1:]))
                            if not stage or "\0" in stage:
                                raise WorkerError("Invalid staging path")
                            body = stage.encode()
                            admission = offer(parent, body)
                            wire.clear()
                        else:
                            if not wire and data.startswith(b"MGN-RESULT/1\0"):
                                wire.extend(data)
                            elif wire and data.startswith(b"R"):
                                wire.extend(data[1:])
                            else:
                                raise WorkerError("Unexpected control packet in compiler result")
                            if len(wire) > MAX_REPLY:
                                raise WorkerError("Compiler response exceeds limit")
            code = process.wait(timeout=remaining())
            if code or diagnostics or not greeted or admission is not None:
                raise WorkerError(f"Compiler worker failed (exit {code}): {bytes(diagnostics)!r}")
            return validate(inspect_reply(wire, expected), profile, stage)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
