"""Own one private native artifact from preparation through execution or replacement."""
import errno
import os
from pathlib import Path
import stat
import struct
import tempfile


def identity(st):
    return st.st_dev, st.st_ino


def regular_input(path):
    st = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode):
        raise OSError(errno.EINVAL, "Compiler input is no longer a regular file", path)
    return identity(st)


class Artifact:
    def __init__(self, output=None):
        self.output = output
        self.directory = None
        self.leaf = None
        self.inputs = {}
        self.parent = None
        self.name = None
        self.source_root = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.directory is None:
            return
        # Only these two private names are ours. A cleanup failure cannot
        # reverse a completed replacement or an application's exit status.
        for remove, path in ((os.unlink, self.leaf), (os.rmdir, self.directory)):
            try:
                remove(path)
            except OSError:
                pass

    def prepare(self, paths):
        if self.directory is not None or not paths:
            raise ValueError("Invalid artifact preparation")
        self.inputs = {p: regular_input(p) for p in paths}
        if self.output is not None:
            parent, self.name = os.path.split(self.output)
            if self.name in ("", ".", ".."):
                raise OSError(errno.EINVAL, "Invalid output name", self.output)
            self.parent = Path(parent or ".").resolve(strict=True)
            self.source_root = regular_directory(Path(paths[0]).parent / "src")
            self.validate_destination()
        self.directory = Path(tempfile.mkdtemp(prefix=".mgn-", dir=self.parent))
        self.leaf = self.directory / "artifact"
        return str(self.leaf)

    def validate_destination(self):
        if any(regular_input(p) != before for p, before in self.inputs.items()):
            raise OSError(errno.ESTALE, "Project input changed before publication")
        parent = Path(os.path.dirname(self.output) or ".").resolve(strict=True)
        if regular_directory(parent) != regular_directory(self.parent):
            raise OSError(errno.ESTALE, "Output directory changed", self.output)
        if self.name.endswith(".mgn") and any(regular_directory(p) == self.source_root
                                              for p in (parent, *parent.parents)):
            raise OSError(errno.EINVAL, "Output would become a project source", self.output)
        try:
            target = os.stat(parent / self.name, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(target.st_mode) or identity(target) in self.inputs.values():
            raise OSError(errno.EINVAL, "Output aliases an input or is not a regular file", self.output)

    def verify_image(self):
        with os.fdopen(os.open(self.leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            st = os.fstat(stream.fileno())
            header = stream.read(64) if stat.S_ISREG(st.st_mode) else b""
            if (len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01"
                    or header[16:20] != b"\x02\x00\x3e\x00" or not st.st_mode & stat.S_IXUSR):
                raise ValueError("Compiler returned an invalid native executable")
            phoff = struct.unpack_from("<Q", header, 32)[0]
            size, count = struct.unpack_from("<HH", header, 54)
            if size != 56 or not count or phoff + size*count > st.st_size:
                raise ValueError("Incomplete native program headers")
            stream.seek(phoff)
            types = {struct.unpack_from("<I", stream.read(size))[0] for _ in range(count)}
            if 1 not in types or types.intersection((2, 3)):
                raise ValueError("Native program requires an external loader")
            os.fchmod(stream.fileno(), 0o700)

    def publish(self):
        self.verify_image()
        self.validate_destination()
        try:
            os.replace(self.leaf, self.parent / self.name)
        except OSError as fault:
            if fault.errno == errno.EIO:
                raise OSError(errno.EIO, "Replacement outcome is unknown", self.output) from fault
            raise


def regular_directory(path):
    st = os.stat(path)
    if not stat.S_ISDIR(st.st_mode):
        raise NotADirectoryError(path)
    return identity(st)
