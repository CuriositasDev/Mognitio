"""Qualify the bootstrap seed, produce independent native generations, and verify raw B."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/mgnc"))
from tools.selfhost.freeze import IDENTITY, canonical, sha
from v180_evidence import Store, candidate, compare_files, file_record, identity, ledger, require, source_set, validate_graph
from v180_runner import run_edge

PARENTS = {"A": None, "B": "A", "B-repeat": "A", "C": "B", "C-repeat": "B"}


def validate_frozen(root):
    record = json.loads((root / "build-identity.json").read_bytes())
    inputs = record["inputs"]
    require(inputs["format"] == 2 and inputs["target"] == "linux-amd64" and
            record["build"] == sha(canonical(inputs)), "Invalid build identity")
    inventory = record["inventory"]
    require(sha(canonical(inventory)) == inputs["source"], "Invalid input inventory")
    expected = {row["path"] for row in inventory}
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Link in frozen candidate")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), "Special file in frozen candidate")
    require(actual == expected | {"build-identity.json"}, "Candidate input closure differs")
    for row in inventory:
        path = root / row["path"]
        data = path.read_bytes()
        require((path.stat().st_mode & 0o7777) == row["mode"], "Frozen mode differs: " + row["path"])
        if row["path"] == ("compiler/mgnc" / IDENTITY).as_posix():
            require(sha(data) == record["generatedIdentitySha256"], "Generated compiler identity differs")
            for field, value in (("build", record["build"]), ("upstream", record["version"]), ("source", inputs["source"])):
                value_bytes = f'public let {field}:String="{value}";'.encode()
                require(data.count(value_bytes) == 1, "Invalid frozen identity: " + field)
                data = data.replace(value_bytes, f'public let {field}:String="";'.encode())
        require(sha(data) == row["sha256"] and len(data) == row["bytes"], "Frozen input differs: " + row["path"])
    return record


def restore_seed(archive, directory, lock):
    require(file_record(archive)["sha256"] == lock["sha256"] and archive.stat().st_size == lock["bytes"],
            "Bootstrap archive differs from the qualified seed")
    with tarfile.open(archive, "r:gz") as package:
        for item in package:
            parts = Path(item.name).parts
            require(parts and parts[0] == "seed" and ".." not in parts and (item.isfile() or item.isdir()),
                    "Unexpected qualified seed member")
        # The qualified ledger includes ordinary permission bits (including
        # group-write). Preserve them after the archive path/type checks.
        def member_filter(item, destination):
            checked = tarfile.data_filter(item, destination)
            return checked.replace(mode=item.mode & 0o777)
        package.extractall(directory, filter=member_filter)
    seed = directory / "seed"
    require(sha((seed / "manifest.json").read_bytes()) == lock["manifestSha256"], "Seed manifest differs")
    subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/freeze-seed.py"), "--verify", str(seed)], check=True)
    return seed


def verified_b(root):
    frozen = validate_frozen(root / "inputs")
    graph = json.loads((root / "generations.json").read_bytes())
    store = Store(root / "objects")
    record = store.get(graph["candidate"], "Candidate")
    require(record["implementation"] == frozen["build"], "Generation graph belongs to another build")
    t = source_set(root / "inputs/compiler/mgnc", "T1", frozen["inputs"]["commit"])
    require(store.get(record["sources"]["T1"], "SourceSet") == t, "Generation source differs")
    require(store.get(record["seed"], "Seed")["archive"] == frozen["inputs"]["seed"], "Generation seed differs")
    roles = validate_graph(store, graph["candidate"], list(graph["edges"].values()), complete=True)
    require(roles == graph["edges"] and roles.keys() == PARENTS.keys(), "Unexpected generation roles")
    for role, edge in roles.items():
        path = root / role / "output/compiler"
        item = store.get(edge, "BuildEdge")
        expected = store.get(item["artifact"], "Artifact")["file"]
        require(file_record(path) == expected, "Generation output differs: " + role)
        if role not in ("A", "B"):
            require(compare_files(root / "B/output/compiler", path)["status"] == "Passed", "Raw B differs from " + role)
    return frozen, root / "B/output/compiler"


def mountpoints(root):
    root.mkdir()
    for name in ("proc", "dev", "input", "output", "tmp", "home/test", "seed", "lib/x86_64-linux-gnu", "bin", "lib64"):
        (root / name).mkdir(parents=True)
    for name in ("compiler", "bin/sh", "lib64/ld-linux-x86-64.so.2"):
        (root / name).touch()


def generate(root, archive):
    frozen = validate_frozen(root / "inputs")
    require(platform.machine() == "x86_64" and sys.platform == "linux", "Expected Linux amd64")
    require(set(root.iterdir()) == {root / "inputs"}, "Use a fresh generation directory containing only inputs")
    os.umask(0o022)
    seed = restore_seed(archive, root, frozen["inputs"]["seed"])
    store = Store(root / "objects")
    userland = root / "userland"
    mountpoints(userland)
    source = root / "inputs/compiler/mgnc"
    revision = frozen["inputs"]["commit"]
    key = candidate(store, sources={"T1":store.put(source_set(source, "T1", revision))},
                    runtime=store.put(source_set(source / "src", "runtime", revision)),
                    seed=store.put(dict(schema=1, kind="Seed", ledger=identity(ledger(seed)), archive=frozen["inputs"]["seed"])),
                    target={"triple":"linux-amd64", "abi":"inherited-1.7"},
                    conditions=dict(bootstrap_mode=0o700, native_mode=0o755, umask=0o022, guard_wall=3600, guard_rss=8192*1024**2),
                    implementation=frozen["build"], authority="qualified-seed-and-frozen-candidate")
    edges = {}
    for role, parent in PARENTS.items():
        edge, passed = run_edge(store, key, role, source, userland, root / role,
                                seed_root=seed if parent is None else None, parent=edges.get(parent),
                                ancestors=list(edges.values()))
        require(passed, f"Generation {role} failed: {edge}")
        edges[role] = edge
    (root / "generations.json").write_bytes(canonical({"candidate":key,"edges":edges}) + b"\n")
    ident, image = verified_b(root)
    print(ident["build"], image)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--seed-archive", type=Path, required=True)
    args = parser.parse_args()
    generate(args.directory.resolve(), args.seed_archive.resolve())
