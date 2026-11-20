"""Freeze the compiler source, embedded identity, and host input inventory before bootstrap."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = Path("src/ToolchainIdentity/identity.mgn")
COMPILER = ("compiler/mgnc",)
GENERATION = ("tests/mgnc/generate*.py", "tests/mgnc/grammar.txt", "src", "mognitio.asd")
PACKAGING = ("tools", "packaging", "bin", "scripts", "VERSION")
OBSERVERS = tuple("tests/mgnc/" + name for name in (
    "v180_runner.py", "v180_evidence.py", "v180_observer.py", "v160_measurelib.py", "v150_measurelib.py"))
INPUTS = COMPILER + GENERATION + PACKAGING + OBSERVERS



def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def seed_identity(receipt):
    record = json.loads(receipt.read_bytes())
    if (record.get("schema") != 1 or
            any(not re.fullmatch("[0-9a-f]{64}", str(record.get(key))) for key in ("sha256", "manifestSha256")) or
            not re.fullmatch("[0-9a-f]{40}", str(record.get("sourceCommit"))) or
            type(record.get("bytes")) is not int or record["bytes"] <= 0):
        raise ValueError("Invalid qualified seed receipt")
    return {key: record[key] for key in ("bytes", "sha256", "manifestSha256", "sourceCommit")}


def freeze(root, destination, receipt, target="linux-amd64", mode="development"):
    root = root.resolve()
    destination = destination.resolve()
    seed = seed_identity(receipt)
    if any(destination.is_relative_to(root / prefix) for prefix in
           (*COMPILER, "tests/mgnc", "src", *PACKAGING, ".git")) or destination == root:
        raise ValueError("The frozen candidate would overlap a build input")
    if mode not in ("development", "release"):
        raise ValueError("Unsupported build mode")
    if target != "linux-amd64":
        raise ValueError("Unsupported target")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root))
    if mode == "release" and dirty:
        raise ValueError("Release build requires a clean source tree")
    tracked = {}
    if mode == "release":
        tree = subprocess.check_output(["git", "ls-tree", "-r", "-z", revision], cwd=root)
        for entry in filter(None, tree.split(b"\0")):
            metadata, name = entry.split(b"\t", 1)
            bits, kind, oid = metadata.split()
            tracked[name] = (bits, oid)
    entries = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others",
                                       "--exclude-standard", "--", *INPUTS], cwd=root).split(b"\0")
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        staged = Path(temp) / "frozen"
        staged.mkdir()
        inventory = []
        for raw in sorted(set(filter(None, entries))):
            name = Path(os.fsdecode(raw))
            source = root / name
            if not source.exists() and not source.is_symlink():
                if mode == "release":
                    raise ValueError(f"Missing candidate input: {name}")
                continue  # A tracked file deleted in this working copy.
            file_mode = source.lstat().st_mode
            if not stat.S_ISREG(file_mode) or any(p.is_symlink() for p in source.parents if p.is_relative_to(root)):
                raise ValueError(f"Expected regular input: {name}")
            data = source.read_bytes()
            bits = 0o755 if file_mode & 0o111 else 0o644
            if mode == "release":
                blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest().encode()
                if tracked.get(raw) != (b"100755" if bits == 0o755 else b"100644", blob):
                    raise ValueError(f"Candidate input differs from its commit: {name}")
            inventory.append({"path":name.as_posix(), "mode":bits, "sha256":sha(data), "bytes":len(data)})
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(bits)
        source_fingerprint = sha(canonical(inventory))
        def subset(prefixes):
            return [row for row in inventory if any(row["path"] == prefix or
                    row["path"].startswith(prefix + "/") for prefix in prefixes)]
        compiler = subset(COMPILER)
        host = subset(PACKAGING)
        generated = [row for row in inventory if row not in compiler and row not in host]
        version = (staged / "VERSION").read_text().strip()
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
            raise ValueError("VERSION must be a plain release version")
        if seed != json.loads((staged / "packaging/native-seed.json").read_bytes()):
            raise ValueError("Seed identity differs from the qualified bootstrap lock")
        inputs = {"format":2, "mode":mode, "target":target, "commit":revision, "dirty":dirty,
                  "source":source_fingerprint, "compiler":sha(canonical(compiler)),
                  "host":sha(canonical(host)), "generators":sha(canonical(generated)),
                  "seed":seed, "baseVersion":version,
                  "compilerMode":"native", "umask":"022"}
        build = sha(canonical(inputs))
        source = staged / "compiler/mgnc" / IDENTITY
        data = source.read_bytes()
        wire = version if mode == "release" else (
            version + "-dev.0+g" + revision + (".dirty" if dirty else "") +
            ".s" + source_fingerprint + ".b" + build)
        for field, value in (("build", build), ("upstream", wire), ("source", source_fingerprint)):
            placeholder = f'public let {field}:String="";'.encode()
            if data.count(placeholder) != 1:
                raise ValueError(f"Expected one empty compiler identity field: {field}")
            data = data.replace(placeholder, f'public let {field}:String="{value}";'.encode())
        source.write_bytes(data)
        record = {"build":build, "version":wire, "inputs":inputs, "inventory":inventory, "generatedIdentitySha256":sha(source.read_bytes())}
        (staged / "build-identity.json").write_bytes(canonical(record) + b"\n")
        staged.rename(destination)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed-receipt", required=True, type=Path,
                        help="Receipt of the independently verified bootstrap seed")
    parser.add_argument("--mode", choices=("release", "development"), default="development")
    args = parser.parse_args()
    print(freeze(ROOT, args.output, args.seed_receipt, mode=args.mode)["build"])
