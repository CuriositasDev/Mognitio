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
PLACEHOLDER = b'public let build:String="";'
COMPILER = ("compiler/mgnc",)
GENERATION = ("tests/mgnc/generate*.py", "tests/mgnc/grammar.txt", "src", "mognitio.asd")
PACKAGING = ("tools", "packaging", "bin", "scripts", "VERSION")
INPUTS = COMPILER + GENERATION + PACKAGING



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


def freeze(root, destination, receipt, target="linux-amd64"):
    root = root.resolve()
    destination = destination.resolve()
    seed = seed_identity(receipt)
    if any(destination.is_relative_to(root / prefix) for prefix in
           (*COMPILER, "tests/mgnc", "src", *PACKAGING, ".git")) or destination == root:
        raise ValueError("The frozen candidate would overlap a build input")
    if target != "linux-amd64":
        raise ValueError("Unsupported target")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root))
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
                continue  # A tracked file deleted in this working copy.
            mode = source.lstat().st_mode
            if not stat.S_ISREG(mode) or any(p.is_symlink() for p in source.parents if p.is_relative_to(root)):
                raise ValueError(f"Expected regular input: {name}")
            data = source.read_bytes()
            bits = 0o755 if mode & 0o111 else 0o644
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
        inputs = {"format":1, "target":target, "commit":revision, "dirty":dirty,
                  "source":source_fingerprint, "compiler":sha(canonical(compiler)),
                  "host":sha(canonical(host)), "generators":sha(canonical(generated)),
                  "seed":seed, "baseVersion":(staged / "VERSION").read_text().strip(),
                  "compilerMode":"native", "umask":"022"}
        build = sha(canonical(inputs))
        source = staged / "compiler/mgnc" / IDENTITY
        data = source.read_bytes()
        if data.count(PLACEHOLDER) != 1:
            raise ValueError("Expected one empty build identity in compiler source")
        source.write_bytes(data.replace(PLACEHOLDER, f'public let build:String="{build}";'.encode()))
        record = {"build":build, "inputs":inputs, "inventory":inventory, "generatedIdentitySha256":sha(source.read_bytes())}
        (staged / "build-identity.json").write_bytes(canonical(record) + b"\n")
        staged.rename(destination)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed-receipt", required=True, type=Path,
                        help="Receipt of the independently verified bootstrap seed")
    args = parser.parse_args()
    print(freeze(ROOT, args.output, args.seed_receipt)["build"])
