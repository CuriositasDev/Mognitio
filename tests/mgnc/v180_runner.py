#!/usr/bin/env python3
"""Run one immutable generation edge in a non-root, seed-free native namespace."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import v180_observer
from v180_evidence import (Store, canonical, candidate, compare_files, digest,
                          file_record, identity, ledger, require, source_set,
                          validate_graph, verify_sources)

FORBIDDEN = {"mgn", "mgnc", "sbcl", "gcc", "cc", "clang", "as", "ld", "python3"}


def namespace(userland, source, output, *, builder=None, seed=None, input_path="/input"):
    require(os.getuid() != 0, "non-root execution required")
    require((builder is None) != (seed is None), "one producer required")
    require(not any(output.iterdir()), "generation output must start empty")
    require(input_path.startswith("/") and ".." not in Path(input_path).parts,
            "invalid namespace input path")
    for path in userland.rglob("*"):
        require(path.name not in FORBIDDEN, "forbidden tool in userland")
    args = ["bwrap", "--as-pid-1", "--unshare-user", "--uid", str(os.getuid()), "--gid", str(os.getgid()),
            "--unshare-pid", "--unshare-net", "--unshare-ipc", "--die-with-parent",
            "--ro-bind", str(userland), "/", "--proc", "/proc", "--dev", "/dev",
            "--ro-bind", str(source), input_path, "--bind", str(output), "/output",
            "--tmpfs", "/tmp", "--dir", "/home/test", "--chdir", "/output",
            "--clearenv", "--setenv", "PATH", "/unavailable", "--setenv", "HOME", "/home/test",
            "--setenv", "LANG", "C.UTF-8"]
    if seed is not None:
        args += ["--ro-bind", str(seed), "/seed",
                 "--ro-bind", str(seed/"runtime/dash"), "/bin/sh",
                 "--ro-bind", str(seed/"runtime"), "/lib/x86_64-linux-gnu",
                 "--ro-bind", str(seed/"runtime/ld-linux-x86-64.so.2"), "/lib64/ld-linux-x86-64.so.2"]
    else:
        args += ["--ro-bind", str(builder), "/compiler"]
    return args



def validate_generation_candidate(store, candidate_id):
    """Bind this runner's actual target, runtime source and fixed generation policy."""
    cand = store.get(candidate_id, "Candidate")
    require(cand["target"] == {"triple": "linux-amd64", "abi": "inherited-1.7"},
            "unsupported generation target or ABI")
    expected = dict(bootstrap_mode=0o700, native_mode=0o755, umask=0o022,
                    guard_wall=3600, guard_rss=8192*1024**2)
    require(cand["conditions"] == expected, "generation conditions do not match runner")
    seed = store.get(cand["seed"], "Seed")
    require(isinstance(seed.get("ledger"), str) and len(seed["ledger"]) == 64
            and all(c in "0123456789abcdef" for c in seed["ledger"]), "invalid seed ledger")
    whole = store.get(cand["sources"]["T1"], "SourceSet")
    runtime = store.get(cand["runtime"], "SourceSet")
    require(whole["role"] == "T1" and runtime["role"] == "runtime",
            "runtime/source role mismatch")
    files = [dict(row, path=row["path"][4:]) for row in whole["files"]
             if row["path"].startswith("src/")]
    require(bool(files) and runtime["files"] == files,
            "runtime is not the complete candidate compiler source subtree")
    serialized = "".join(f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n" for row in files)
    require(runtime["inventory_sha256"] == digest(serialized.encode())
            and runtime["bytes"] == sum(row["bytes"] for row in files)
            and runtime["revision"] == whole["revision"], "runtime inventory binding mismatch")
    return cand


def run_edge(store, candidate_id, role, source_root, userland, run_root,
             *, seed_root=None, parent=None, ancestors=(), input_path="/input"):
    cand = validate_generation_candidate(store, candidate_id)
    mask = os.umask(0o022)
    os.umask(mask)
    require(mask == cand["conditions"]["umask"], "process umask does not match candidate")
    require(role in ("A", "B", "C", "B-repeat", "C-repeat", "D0", "D1"), "unknown edge role")
    source_role = "O0" if role == "D0" else "O1" if role == "D1" else "T1"
    source_id = cand["sources"][source_role]
    source = store.get(source_id, "SourceSet")
    verify_sources(source_root, source)
    require(not run_root.exists(), "attempt already exists")
    run_root.mkdir(parents=True)
    output = run_root/"output"
    output.mkdir()
    builder_role = {"A":"S", "B":"A", "C":"B", "B-repeat":"A", "C-repeat":"B",
                    "D0":"A", "D1":"A"}[role]
    builder = None
    if role == "A":
        require(parent is None and seed_root is not None, "bootstrap producer mismatch")
        seed = store.get(cand["seed"], "Seed")
        require(identity(ledger(seed_root)) == seed["ledger"], "seed changed")
        builder_id = cand["seed"]
    else:
        require(seed_root is None and parent is not None, "native edge cannot mount seed")
        parent_edge = store.get(parent, "BuildEdge")
        validate_graph(store, candidate_id, list(ancestors))
        require(parent in ancestors and parent_edge["role"] == builder_role, "wrong parent generation")
        builder_id = parent_edge["artifact"]
        artifact = store.get(builder_id, "Artifact")
        # Location is an external receipt, never part of the artifact identity.
        location = json.loads((store.root.parent/"locations"/(parent+".json")).read_text())
        builder = Path(location["path"])
        require(file_record(builder) == artifact["file"], "producer artifact changed")
    environment = dict(schema=1,kind="Environment",userland=ledger(userland),
                       kernel=os.uname().release,uid=os.getuid(),gid=os.getgid())
    env_id = store.put(environment)
    builder_before = file_record(builder) if builder is not None else identity(ledger(seed_root))
    before = ledger(source_root)
    command = namespace(userland, source_root, output, builder=builder, seed=seed_root, input_path=input_path)
    command += ["/seed/bin/mgn" if role == "A" else "/compiler",
                "build", input_path+"/mognitio.toml", "-o", "/output/compiler"]
    (run_root/"request.json").write_bytes(canonical(dict(candidate=candidate_id,role=role,
        source=source_id,builder=builder_id,environment=env_id,command=command,
        observer=file_record(Path(v180_observer.__file__)))))
    observation = v180_observer.observe(command, run_root/"raw", timeout=3600,
                                        rss_limit=8192*1024**2)
    image = output/"compiler"
    unchanged = before == ledger(source_root) and builder_before == (file_record(builder) if builder is not None else identity(ledger(seed_root)))
    passed = (observation["exit"] == 0 and observation["signal"] is None
              and observation["cutoff"] is None and observation["harness_failure"] is None
              and observation["descendant_residue"] == observation["unreaped_descendants"] == 0
              and (run_root/"raw/stdout").read_bytes() == (run_root/"raw/stderr").read_bytes() == b""
              and unchanged and image.is_file() and not image.is_symlink())
    artifact_id = None
    if passed:
        data = image.read_bytes()
        passed = (data[:7] == b"\x7fELF\x02\x01\x01" and data[16:20] == b"\x02\x00\x3e\x00"
                  and file_record(image)["mode"] == (0o700 if role == "A" else 0o755) and list(output.iterdir()) == [image])
    if passed:
        artifact_id = store.put(dict(schema=1,kind="Artifact",candidate=candidate_id,role=role,
                                     file=file_record(image)))
    raw_id = store.put(dict(schema=1,kind="Raw",files=ledger(run_root)))
    obs_id = store.put(dict(schema=1,kind="Observation",candidate=candidate_id,
        status="Passed" if passed else "Failed",exit=observation["exit"],signal=observation["signal"],
        cutoff=observation["cutoff"],harness_failure=observation["harness_failure"],
        residue=observation["descendant_residue"]+observation["unreaped_descendants"],
        inputs_unchanged=unchanged,builder=builder_id,source=source_id,output=artifact_id,
        raw=raw_id,environment=env_id,measurement=observation))
    edge_id = store.put(dict(schema=1,kind="BuildEdge",candidate=candidate_id,role=role,
        builder_role=builder_role,source_role=source_role,source=source_id,producer=parent,
        builder=builder_id,artifact=artifact_id,status="Passed" if passed else "Failed",
        observation=obs_id))
    (run_root/"receipt.json").write_bytes(canonical(dict(edge=edge_id,status="Passed" if passed else "Failed")))
    if passed:
        locations=store.root.parent/"locations"
        locations.mkdir(exist_ok=True)
        with (locations/(edge_id+".json")).open("xb") as stream:
            stream.write(canonical(dict(path=str(image.resolve()),edge=edge_id)))
        validate_graph(store,candidate_id,[*ancestors,edge_id])
    return edge_id, passed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--store",type=Path,required=True)
    parser.add_argument("--candidate",required=True)
    parser.add_argument("--role",required=True)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--userland",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=Path)
    parser.add_argument("--parent")
    parser.add_argument("--ancestor",action="append",default=[])
    parser.add_argument("--input-path",default="/input")
    args=parser.parse_args()
    edge,passed=run_edge(Store(args.store),args.candidate,args.role,args.source.resolve(),
        args.userland.resolve(),args.output.resolve(),seed_root=args.seed.resolve() if args.seed else None,
        parent=args.parent,ancestors=args.ancestor,input_path=args.input_path)
    print(json.dumps(dict(edge=edge,status="Passed" if passed else "Failed")))
    raise SystemExit(0 if passed else 1)


if __name__=="__main__":
    main()
