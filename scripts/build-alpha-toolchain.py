#!/usr/bin/env python3
"""Build a reproducible, non-release alpha payload with the pinned native 1.9 seed."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.selfhost.bootstrap import validate_frozen
from tools.selfhost.freeze import freeze
from tools.selfhost.payload import COMPILER, HOST, canonical, file_info, payload_identity, sha


def build(archive, manifest, graph, destination):
    lock = json.loads((ROOT / "packaging/alpha-seed.json").read_bytes())
    receipt = lock["receipt"]
    if (file_info(archive)["sha256"] != receipt["sha256"] or archive.stat().st_size != receipt["bytes"]
            or sha(manifest.read_bytes()) != receipt["manifestSha256"]):
        raise ValueError("Seed inputs differ from the pinned signed release")
    if graph.exists() or destination.exists() or destination.is_relative_to(graph):
        raise ValueError("Use fresh, separate graph and payload directories")
    graph.mkdir(parents=True)
    os.umask(0o022)
    with tempfile.TemporaryDirectory(dir=graph) as directory:
        staging = Path(directory)
        with tarfile.open(archive, "r:gz") as package:
            package.extractall(staging, filter="data")
        seed = staging / "mognitio/payload"
        seed_id = payload_identity(seed)
        if (seed_id != json.loads(manifest.read_bytes())["identity"]
                or seed_id["version"] != lock["version"] or seed_id["build"] != lock["build"]
                or seed_id["inputs"]["commit"] != receipt["sourceCommit"]
                or file_info(seed / COMPILER)["sha256"] != lock["compilerSha256"]):
            raise ValueError("Seed payload identity mismatch")
        receipt_path = graph / "seed-receipt.json"
        receipt_path.write_bytes(canonical(receipt) + b"\n")
        source = graph / "inputs"
        freeze(ROOT, source, receipt_path, mode="alpha")
        frozen = validate_frozen(source)
        target = graph / "A"
        target.mkdir()
        image = target / "compiler"
        subprocess.run([seed / "bin/mgn", "build", "compiler/mgnc/mognitio.toml", "-o", image],
                       cwd=source, check=True)
        if validate_frozen(source) != frozen:
            raise ValueError("Frozen inputs changed during generation")
        stage = runpy.run_path(str(source / "scripts/build-native-toolchain.py"))["stage_payload"]
        stage(source, destination, seed / HOST, frozen, image, input_mode=0o700)
        edge = {"role": "A", "build": frozen["build"], "source": frozen["inputs"]["source"],
                "producer": lock["build"], "producerCompiler": file_info(seed / COMPILER),
                "adapter": file_info(seed / HOST), "output": file_info(image),
                "payloadManifest": file_info(destination / "payload.json")}
        (graph / "generation.json").write_bytes(canonical(edge) + b"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-archive", required=True, type=Path)
    parser.add_argument("--seed-manifest", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.seed_archive.resolve(), args.seed_manifest.resolve(), args.graph.resolve(), args.output.resolve())
