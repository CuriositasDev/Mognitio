#!/usr/bin/env python3
"""Package only a byte-verified fixed-point compiler and its frozen runtime inputs."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.selfhost.bootstrap import verified_b
from tools.selfhost.payload import COMPONENTS, COMPILER, HOST, SOURCES, canonical, file_info, payload_identity


def build(generations, destination, adapter):
    frozen, image = verified_b(generations)
    stage_payload(generations / "inputs", destination, adapter, frozen, image)


def stage_payload(source, destination, adapter, frozen, image, *, input_mode=0o755):
    input_info = file_info(image)
    if input_info["mode"] != input_mode:
        raise ValueError("Unexpected compiler image mode")
    dest = destination.resolve()
    if dest.exists() or dest.is_relative_to(source.parent):
        raise ValueError("Use a fresh payload destination outside the generation graph")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        staged = Path(tmp) / "payload"
        staged.mkdir()
        for name, original in SOURCES.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / original, target)
            target.chmod(0o755 if name.startswith("bin/") else 0o644)
        helper = staged / HOST
        shutil.copyfile(adapter, helper)
        helper.chmod(0o644)
        compiler = staged / COMPILER
        compiler.parent.mkdir()
        shutil.copyfile(image, compiler)
        compiler.chmod(0o755)
        if file_info(compiler) != dict(input_info, mode=0o755):
            raise ValueError("Staged compiler differs from the verified input image")
        ident = dict(schema=2, inputs=frozen["inputs"], version=frozen["version"], build=frozen["build"],
                     components=dict.fromkeys(COMPONENTS, frozen["build"]))
        (staged / "identity.json").write_bytes(canonical(ident)+b"\n")
        (staged / "inventory.json").write_bytes(canonical(frozen["inventory"])+b"\n")
        for path in [staged, *staged.rglob("*")]:
            if path.is_dir():
                path.chmod(0o755)
            elif path.name in ("identity.json", "inventory.json"):
                path.chmod(0o644)
        files = {p.relative_to(staged).as_posix(): file_info(p) for p in staged.rglob("*") if p.is_file()}
        manifest = staged / "payload.json"
        manifest.write_bytes(canonical(dict(schema=2, identity=ident, files=files))+b"\n")
        manifest.chmod(0o644)
        payload_identity(staged)
        for tool, title in (("mgn", "Mognitio"), ("mognitio-lsp", "mognitio-lsp")):
            probe = subprocess.run([staged / "bin" / tool, "--version"], capture_output=True, timeout=15)
            if probe.returncode or probe.stderr or probe.stdout != f"{title} {ident['version']}\n".encode():
                raise ValueError("Installed version mismatch: "+tool)
        staged.rename(dest)
    print(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-adapter", type=Path, required=True)
    args = parser.parse_args()
    build(args.generations.resolve(), args.output, args.host_adapter)
