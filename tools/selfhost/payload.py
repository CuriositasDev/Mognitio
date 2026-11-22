"""Validate the closed native payload and the build identity embedded before bootstrap."""
import hashlib
import json
from pathlib import Path
import stat

from .client import request

COMPONENTS = ("compiler", "frontend", "stdlib", "runner", "lsp", "cli")
SOURCES = {
    "bin/mgn": "packaging/native/mgn",
    "bin/mognitio-lsp": "packaging/native/mognitio-lsp",
    "ASMJIT-LICENSE.txt": "packaging/native/ASMJIT-LICENSE.txt",
    "host-lock.json": "packaging/native-host-lock.json",
    "NOTICES.txt": "packaging/native/NOTICES.txt",
    "catalog/catalog-inputs.json": "compiler/mgnc/catalog-inputs.json",
    "catalog/catalog.mgn": "compiler/mgnc/src/Catalog/catalog.mgn",
}
for group, modules in {
    "selfhost": ("analysis", "client", "command", "entry", "language_server", "payload", "publication", "resident", "testplan"),
    "runner": ("events", "suite", "supervisor"),
    "lsp": ("budget", "framing", "projection", "server", "snapshot", "worker_exec"),
}.items():
    for name in modules:
        path = f"tools/{group}/{name}.py"
        SOURCES[path] = path
COMPILER = "runtime/compiler"
HOST = "tools/selfhost/_application.abi3.so"
MEMBERS = set(SOURCES) | {COMPILER, HOST, "identity.json", "inventory.json"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_info(path):
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("Expected a regular payload file")
    data = path.read_bytes()
    return {"size":len(data), "sha256":sha(data), "mode":stat.S_IMODE(mode)}


def payload_identity(root):
    paths = list(root.rglob("*"))
    expected_dirs = {p.as_posix() for name in MEMBERS for p in Path(name).parents if p != Path(".")}
    if {p.relative_to(root).as_posix() for p in paths} != MEMBERS | expected_dirs | {"payload.json"}:
        raise ValueError("Native payload file closure mismatch")
    for subdir in expected_dirs:
        mode = (root / subdir).lstat().st_mode
        if not stat.S_ISDIR(mode):
            raise ValueError("Expected native payload directory")
    if file_info(root / "payload.json")["mode"] != 0o644:
        raise ValueError("Invalid payload manifest mode")
    manifest = json.loads((root / "payload.json").read_bytes())
    files = manifest["files"]
    if manifest.get("schema") != 2 or set(files) != MEMBERS:
        raise ValueError("Invalid native payload manifest")
    for name in MEMBERS:
        info = file_info(root / name)
        bits = 0o755 if name in (COMPILER, "bin/mgn", "bin/mognitio-lsp") else 0o644
        if info != files[name] or info["mode"] != bits:
            raise ValueError("Payload component mismatch: " + name)
    ident = json.loads((root / "identity.json").read_bytes())
    inputs = ident["inputs"]
    build = ident["build"]
    if (ident.get("schema") != 2 or inputs["format"] != 2 or inputs["target"] != "linux-amd64" or
            manifest["identity"] != ident or sha(canonical(inputs)) != build or
            ident["components"] != dict.fromkeys(COMPONENTS, build)):
        raise ValueError("Native build identity mismatch")
    inventory = json.loads((root / "inventory.json").read_bytes())
    if sha(canonical(inventory)) != inputs["source"]:
        raise ValueError("Source inventory identity mismatch")
    sources = {row["path"]: row for row in inventory}
    for path, original in SOURCES.items():
        row = sources[original]
        if files[path]["sha256"] != row["sha256"] or files[path]["size"] != row["bytes"]:
            raise ValueError("Payload helper belongs to a different build: " + path)
    host_lock = json.loads((root / "host-lock.json").read_bytes())
    if files[HOST]["sha256"] != host_lock["adapterSha256"]:
        raise ValueError("Native host adapter differs from its qualified build")
    embedded = request(root / COMPILER, build, "identity", timeout=10)
    if embedded.status != "ok" or embedded.fields != (ident["version"], inputs["source"]):
        raise ValueError("Embedded native compiler identity mismatch")
    return ident
