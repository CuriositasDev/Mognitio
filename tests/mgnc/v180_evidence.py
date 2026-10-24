"""Content-addressed evidence primitives for repeated native compiler builds.

These records describe observations, not compiler inputs. A receipt cannot turn
a failed command into a usable artifact, and identical bytes do not merge roles.
"""
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

SCHEMA = 1
STATES = {"Passed", "Failed", "NotRun", "NotAdopted"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(record):
    return digest(canonical(record))


def valid_hash(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value),
            "missing or malformed digest")
    return value


def relative(name):
    require(isinstance(name, str) and name != "" and "\\" not in name,
            "invalid relative path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts
            and str(path) == name and name != ".", "noncanonical relative path")
    name.encode("utf-8", "strict")
    return path


def file_record(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "expected regular file: " + str(path))
    data = path.read_bytes()
    return dict(bytes=len(data), mode=stat.S_IMODE(info.st_mode), sha256=digest(data))


def source_set(root, role, revision):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "invalid source root")
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().encode()):
        require(not path.is_symlink(), "source symlink")
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        relative(name)
        rows.append(dict(path=name, **file_record(path)))
    require(bool(rows), "empty source set")
    serialized = "".join(f"{r['path']}\t{r['bytes']}\t{r['sha256']}\n" for r in rows)
    return dict(schema=SCHEMA, kind="SourceSet", role=role, revision=revision,
                files=rows, inventory_sha256=digest(serialized.encode()),
                bytes=sum(r["bytes"] for r in rows))


def verify_sources(root, record):
    require(record == source_set(root, record["role"], record["revision"]),
            "source inventory changed, incomplete, or mode mismatch")


class Store:
    """Append-only objects: IDs bind canonical bytes; existing files are checked."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, record):
        require(record.get("schema") == SCHEMA and isinstance(record.get("kind"), str),
                "record schema missing")
        data = canonical(record)
        key = digest(data)
        path = self.root / (key + ".json")
        try:
            with path.open("xb") as output:
                output.write(data)
        except FileExistsError:
            require(path.read_bytes() == data and not path.is_symlink(),
                    "immutable record collision or corruption")
        return key

    def get(self, key, kind=None):
        valid_hash(key)
        path = self.root / (key + ".json")
        require(not path.is_symlink(), "record symlink")
        data = path.read_bytes()
        require(digest(data) == key, "receipt digest mismatch")
        record = json.loads(data)
        require(canonical(record) == data and record.get("schema") == SCHEMA,
                "noncanonical or unsupported receipt")
        require(kind is None or record.get("kind") == kind, "record kind mismatch")
        return record


def candidate(store, *, sources, seed, runtime, target, conditions, implementation, authority):
    require("T1" in sources, "missing whole compiler source")
    for role, key in sources.items():
        require(store.get(key, "SourceSet")["role"] == role, "source role mismatch")
    store.get(seed, "Seed")
    store.get(runtime, "SourceSet")
    for value in (target, conditions, implementation, authority):
        require(bool(value), "candidate input missing")
        canonical(value)
    return store.put(dict(schema=SCHEMA, kind="Candidate", sources=sources,
                          seed=seed, runtime=runtime, target=target, conditions=conditions,
                          implementation=implementation, authority=authority))


def validate_graph(store, candidate_id, edge_ids, *, complete=False):
    """Validate dependency roles independently of output byte equality."""
    cand = store.get(candidate_id, "Candidate")
    edges = {key: store.get(key, "BuildEdge") for key in edge_ids}
    require(len(edges) == len(edge_ids), "duplicate edge")
    active, done = set(), set()
    roles = {}
    expected = {"A": ("S", "T1"), "B": ("A", "T1"), "C": ("B", "T1"),
                "B-repeat": ("A", "T1"), "C-repeat": ("B", "T1"),
                "D0": ("A", "O0"), "D1": ("A", "O1")}

    def visit(key):
        require(key not in active, "producer cycle")
        if key in done:
            return
        require(key in edges, "missing producer edge")
        edge = edges[key]
        require(edge["candidate"] == candidate_id, "mixed candidate")
        require(edge["status"] == "Passed", "unsuccessful producer")
        role = edge["role"]
        builder_role, source_role = expected.get(role, (edge["builder_role"], edge["source_role"]))
        require(edge["builder_role"] == builder_role and edge["source_role"] == source_role,
                "producer/source role mismatch")
        require(edge["source"] == cand["sources"].get(source_role), "wrong source identity")
        valid_hash(edge["observation"])
        obs = store.get(edge["observation"], "Observation")
        store.get(obs["raw"], "Raw")
        store.get(obs["environment"], "Environment")
        require(obs["candidate"] == candidate_id and obs["status"] == "Passed",
                "observation binding/status")
        require(obs["exit"] == 0 and obs["signal"] is None and obs["cutoff"] is None
                and obs["harness_failure"] is None and obs["inputs_unchanged"]
                and obs["residue"] == 0, "invalid successful observation")
        require(obs["builder"] == edge["builder"] and obs["source"] == edge["source"]
                and obs["output"] == edge["artifact"], "observation edge mismatch")
        active.add(key)
        if builder_role == "S":
            require(edge["producer"] is None and edge["builder"] == cand["seed"],
                    "seed provenance mismatch")
        else:
            parent = edge["producer"]
            visit(parent)
            prior = edges[parent]
            require(prior["role"] == builder_role and prior["artifact"] == edge["builder"],
                    "builder provenance mismatch")
        artifact = store.get(edge["artifact"], "Artifact")
        require(artifact["candidate"] == candidate_id and artifact["role"] == role,
                "artifact role/candidate mismatch")
        valid_hash(artifact["file"]["sha256"])
        require(artifact["file"]["bytes"] > 0 and artifact["file"]["mode"] == 0o755,
                "invalid artifact")
        require(role not in roles or roles[role] == key, "ambiguous production role")
        roles[role] = key
        active.remove(key)
        done.add(key)

    for key in edges:
        visit(key)
    if complete:
        require({"A", "B", "C", "B-repeat", "C-repeat"} <= roles.keys(), "incomplete generation graph")
    return roles


def compare_files(left, right):
    a, b = Path(left).read_bytes(), Path(right).read_bytes()
    ar, br = file_record(left), file_record(right)
    offset = next((i for i, pair in enumerate(zip(a, b)) if pair[0] != pair[1]), None)
    if offset is None and len(a) != len(b):
        offset = min(len(a), len(b))
    return dict(schema=SCHEMA, kind="Comparison", left=ar, right=br,
                status="Passed" if ar == br else "Failed", first_difference=offset,
                left_context=a[max(0,(offset or 0)-8):(offset or 0)+9].hex() if offset is not None else "",
                right_context=b[max(0,(offset or 0)-8):(offset or 0)+9].hex() if offset is not None else "")


def evaluate_suite(store, candidate_id, suite_id, run_ids):
    store.get(candidate_id, "Candidate")
    suite = store.get(suite_id, "Suite")
    required = suite["cells"]
    require(len(required) == len(set(required)) and bool(required), "invalid suite cells")
    found = {}
    for key in run_ids:
        run = store.get(key, "Run")
        require(run["candidate"] == candidate_id and run["suite"] == suite_id, "run binding mismatch")
        cell = run["cell"]
        require(cell in required and cell not in found, "unexpected or duplicated cell")
        require(run["status"] in STATES, "invalid status")
        require(run["expected"] == suite["expected"][cell], "expected digest mismatch")
        if run["status"] == "Passed":
            require(bool(run["receipts"]), "missing execution evidence")
            for receipt in run["receipts"]:
                observation = store.get(receipt, "Observation")
                require(observation["candidate"] == candidate_id and observation["status"] == "Passed",
                        "unsuccessful or unrelated execution evidence")
                store.get(observation["raw"], "Raw")
        found[cell] = run["status"]
    return {cell: found.get(cell, "NotRun") for cell in required}


def ledger(root):
    """Bind lossless filesystem names, bytes, modes and link topology."""
    import base64
    root = Path(root)
    rows, groups = [], {}
    for path in sorted(root.rglob("*"), key=lambda p: os.fsencode(p.relative_to(root))):
        info = path.lstat()
        name = base64.b64encode(os.fsencode(path.relative_to(root))).decode("ascii")
        row = dict(path_b64=name, mode=stat.S_IMODE(info.st_mode))
        if stat.S_ISLNK(info.st_mode):
            row.update(type="symlink", target_b64=base64.b64encode(os.fsencode(os.readlink(path))).decode("ascii"))
        elif stat.S_ISDIR(info.st_mode):
            row.update(type="directory")
        elif stat.S_ISREG(info.st_mode):
            group = groups.setdefault((info.st_dev, info.st_ino), name)
            row.update(type="file", **file_record(path), hardlink_group=group)
        else:
            raise ValueError("live resource must be recorded separately")
        rows.append(row)
    return rows
