#!/usr/bin/env python3
"""Compare native compiler frontend profiles on identical project sources."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = '[project]\nname="app"\nroot_namespace="App"\n'


def exercise(probe, project):
    sources = project / "src"
    sources.mkdir(parents=True)
    manifest = project / "mognitio.toml"
    manifest.write_text(MANIFEST, encoding="utf-8")

    def run(profile, status, output=b"", error=None):
        result = subprocess.run([probe, profile, manifest], capture_output=True, timeout=180)
        assert (result.returncode, result.stdout) == (status, output), (profile, result)
        if error is None:
            assert result.stderr == b"", (profile, result.stderr)
        else:
            assert error in result.stderr, (profile, result.stderr)

    run("tests", 0)
    run("analysis", 0)
    run("ordinary", 2, error=b"entry source is missing")

    def test_source(name, exported=False):
        qualifier = "public " if exported else ""
        return f'@test {qualifier}let {name}:Function():Unit=function():Unit{{panic{{"not run"}}}};\n'

    first = "namespace App;\n// 日本語\n"
    second = r"namespace App\Checks;" + "\n"
    checks = sources / "Checks"
    checks.mkdir()
    (checks / "b.mgn").write_text(second + test_source("same", True), encoding="utf-8")
    prefix = first + r"use App\Checks\{same as other};" + "\n"
    local = prefix + test_source("z") + test_source("same")
    (sources / "list.mgn").write_text(local, encoding="utf-8")
    expected = (
        f"0 src/Checks/b.mgn::App\\Checks::same {len(second.encode())}\n"
        f"1 src/list.mgn::App::z {len(prefix.encode())}\n"
        f"2 src/list.mgn::App::same {len((prefix + test_source('z')).encode())}\n"
    ).encode()
    run("tests", 0, expected)
    run("analysis", 0)
    run("ordinary", 2, error=b"entry source is missing")
    entry = sources / "app.mgn"
    entry.write_text(first + "let main:Int=1;\n", encoding="utf-8")
    run("tests", 0, expected)
    run("analysis", 0)
    run("ordinary", 1, error=b"main must have type")
    entry.write_text(first + "let main:Function(List<String>):Int=function(args:List<String>):Int{0};\n", encoding="utf-8")
    run("ordinary", 0)
    bad = sources / "unused.mgn"
    bad.write_text(first + "let unused:Function():Unit=function():Unit{assert 1;};\n", encoding="utf-8")
    for profile in ("ordinary", "analysis", "tests"):
        run(profile, 1, error=b"src/unused.mgn")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", type=Path, help="Compiler used to build the probe from source")
    group.add_argument("--probe", type=Path, help="Previously built profile probe")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if args.seed:
            compiler = work / "compiler"
            shutil.copytree(ROOT / "compiler/mgnc", compiler)
            shutil.copyfile(ROOT / "tests/mgnc/harnesses/v190-project-profiles.mgn", compiler / "src/mgnc.mgn")
            probe = work / "profile-probe"
            subprocess.run([args.seed.resolve(), "build", compiler / "mognitio.toml", "-o", probe], check=True, timeout=1800)
        else:
            probe = args.probe.resolve()
        exercise(probe, work / "app")
    print("Native project profiles and test discovery passed")


if __name__ == "__main__":
    main()
