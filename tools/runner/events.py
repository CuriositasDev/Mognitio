"""Decode the native test event channel and commit outcomes to the parent ledger."""
from dataclasses import dataclass
import struct

RECORD = struct.Struct("<4sHHQQIIQ")
NO_SITE = (1 << 64) - 1
KINDS = ("success", "assertion", "panic", "overflow", "division-by-zero",
         "remainder-by-zero", "string-index-out-of-bounds", "string-size-overflow",
         "list-length-overflow", "allocation-failed", "bytes-length-overflow")
STAGES = ("unknown", "initialization", "body")


class ProtocolError(Exception):
    """Invalid compiler-generated records or contradictory process evidence."""


@dataclass
class Outcome:
    ordinal: int
    site_count: int
    state: str = "not_run"
    stage: str = "unknown"
    kind: str | None = None
    site: int | None = None

    def abort(self):
        if self.state == "running":
            self.state = "aborted"


class Events:
    def __init__(self, outcome):
        self.outcome = outcome
        self.buffer = bytearray()
        self.sequence = 0
        self.ready = False
        self.stage = 0
        self.terminal = None
        self.eof = False

    def feed(self, data):
        if self.eof:
            raise ProtocolError("Event after EOF")
        self.buffer.extend(data)
        offset = 0
        while len(self.buffer) - offset >= RECORD.size:
            self._accept(*RECORD.unpack_from(self.buffer, offset))
            offset += RECORD.size
        del self.buffer[:offset]

    def _accept(self, magic, version, tag, ordinal, sequence, stage, kind, site):
        if (magic != b"MGNT" or version != 4 or ordinal != self.outcome.ordinal
                or sequence != self.sequence or self.terminal is not None):
            raise ProtocolError("Invalid test event header or sequence")
        if tag == 1:
            if self.ready or stage or kind or site != NO_SITE:
                raise ProtocolError("Invalid ready event")
            self.ready = True
        elif tag == 2:
            if (self.outcome.state != "running" or stage != self.stage + 1
                    or stage not in (1, 2) or kind or site != NO_SITE):
                raise ProtocolError("Invalid test stage")
            self.stage = stage
            self.outcome.stage = STAGES[stage]
        elif tag == 3:
            if (self.outcome.state != "running" or stage != self.stage or stage not in (1, 2)
                    or kind >= len(KINDS) or (kind == 0 and stage != 2)):
                raise ProtocolError("Invalid terminal event")
            if (kind == 1 and site >= self.outcome.site_count) or (kind != 1 and site != NO_SITE):
                raise ProtocolError("Invalid terminal site")
            self.terminal = kind, site
        else:
            raise ProtocolError("Unknown test event")
        self.sequence += 1

    def commit(self, returncode):
        """Commit once event EOF and a reaped process agree, before displaying results."""
        if not self.eof or returncode is None or self.outcome.state not in ("not_run", "running"):
            return
        if returncode == 124:
            raise OSError("Test report transport failed")
        if returncode == 123:
            raise ProtocolError("Test child detected an internal runtime inconsistency")
        if self.outcome.state == "not_run":
            raise OSError("Test image exited before execution started")
        if returncode < 0 or self.buffer or self.terminal is None:
            self.outcome.kind = "abnormal"
            self.outcome.state = "errors"
            return
        kind, site = self.terminal
        expected = {0: 0, 1: 5}.get(kind, 4)
        if returncode != expected:
            raise ProtocolError("Test terminal disagrees with process status")
        self.outcome.kind = KINDS[kind] if kind else None
        self.outcome.site = site if kind == 1 else None
        self.outcome.state = {0: "passed", 1: "failed"}.get(kind, "errors")
