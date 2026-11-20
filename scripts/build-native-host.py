#!/usr/bin/env python3
"""Rebuild the finite-file-limit application adapter from pinned build-only inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, headers, output):
    lock = json.loads((ROOT / "packaging/native-host-lock.json").read_bytes())
    if sha(source) != lock["asmjit"]["sha256"] or sha(headers) != lock["pythonHeaders"]["sha256"]:
        raise ValueError("Native host build input differs from lock")
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    cxx = shutil.which("g++")
    if not cxx or subprocess.check_output([cxx, "-dumpfullversion"], text=True).strip() != lock["compiler"]:
        raise ValueError("Unexpected native host C++ compiler")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mgn-host-", dir=output.parent) as tmp:
        work = Path(tmp)
        upstream = work / "upstream"
        with tarfile.open(source, "r:xz") as archive:
            archive.extractall(upstream, filter="data")
        roots = [p for p in upstream.iterdir() if p.is_dir()]
        if len(roots) != 1 or sha(roots[0] / "LICENSE.md") != lock["asmjit"]["noticeSha256"]:
            raise ValueError("Invalid AsmJit source tree")
        src = roots[0]
        include = work / "headers/usr/include"
        subprocess.run(["dpkg-deb", "-x", headers, work / "headers"], check=True)
        flags = [f"-ffile-prefix-map={work}=.", f"-ffile-prefix-map={ROOT}=.", "-frandom-seed=mognitio-host"]
        env = dict(os.environ, LC_ALL="C", SOURCE_DATE_EPOCH="0", TZ="UTC")
        cmake = work / "build"
        subprocess.run(["cmake", "-S", src, "-B", cmake, "-DASMJIT_STATIC=ON", "-DASMJIT_TEST=OFF",
                        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_BUILD_TYPE=Release", "-DASMJIT_NO_AARCH64=ON",
                        "-DASMJIT_NO_COMPILER=ON", "-DASMJIT_NO_BUILDER=ON", "-DCMAKE_CXX_COMPILER="+cxx,
                        "-DCMAKE_CXX_FLAGS="+" ".join(flags)], check=True, env=env)
        subprocess.run(["cmake", "--build", cmake, "--parallel", "3"], check=True, env=env)
        target = work / "_application.abi3.so"
        subprocess.run([cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-fvisibility=hidden", *flags, "-I"+str(include / "python3.14"), "-I"+str(include),
                        "-I"+str(src / "src"), ROOT / "tools/native/application.cpp", cmake / "libasmjit.a",
                        "-Wl,--build-id=none", "-Wl,--exclude-libs,ALL", "-o", target], check=True, env=env)
        if sha(target) != lock["adapterSha256"]:
            raise ValueError("Rebuilt native adapter differs from the qualified digest")
        target.chmod(0o644)
        os.link(target, output)
    print(sha(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asmjit-source", type=Path, required=True)
    parser.add_argument("--python-headers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.asmjit_source.resolve(), args.python_headers.resolve(), args.output.absolute())
