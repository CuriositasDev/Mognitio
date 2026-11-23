#!/usr/bin/env python3
"""Run a mainless project through the native suite generator and parent runner."""
from pathlib import Path
import os
import shutil
import subprocess
from unittest.mock import patch
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def exercise(compiler, build, root):
    src = root / "src"
    src.mkdir()
    manifest = root / "mognitio.toml"
    manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
    def invoke():
        return subprocess.run([sys.executable, ROOT / "tests/mgnc/v190-normal-commands.py", "--child",
                               compiler, build, "test", manifest], capture_output=True, cwd=root, timeout=30)
    common = src / "app.mgn"
    common.write_text("namespace App;\nlet main:Int=6;\n")
    zero = invoke()
    assert (zero.returncode, zero.stdout, zero.stderr) == (0, b"tests: total=0 passed=0 failed=0 errors=0 aborted=0 not_run=0\n", b""), zero
    common.write_text("namespace App; @test let ordinary:Function():Unit=function():Unit{assert true;};")
    simple = invoke()
    assert simple.returncode == 0 and b"total=1 passed=1" in simple.stdout, simple
    common.write_text("namespace App; @test let first:Function():Unit=function():Unit{}; "
                      "@test let second:Function():Unit=function():Unit{};")
    injected = subprocess.run([sys.executable, __file__, "--fail-first-map", compiler, build, manifest],
                              capture_output=True, cwd=root, timeout=30)
    assert injected.returncode == 4, injected
    assert b"ERROR allocation-failed src/app.mgn::App::first" in injected.stdout, injected
    assert b"PASS src/app.mgn::App::second" in injected.stdout and b"passed=1 failed=0 errors=1" in injected.stdout, injected
    assert b"stage=initialization" in injected.stderr and b"allocation failure" in injected.stderr, injected
    common.write_text("namespace App;\nlet main:Int=6;\n")
    for name in ("Checks", "Broken", "Unused"):
        (src / name).mkdir()
    (src / "Unused/other.mgn").write_text('namespace App\\Unused;\nlet never:Int=panic{"unreachable initializer"};\n')
    (src / "Broken/init.mgn").write_text(r'''namespace App\Broken;
@test let blocked:Function():Unit=function():Unit{panic{"unreached body"};};
let problem:Int=panic{"init failure"};
''')
    case_file = src / "Checks/cases.mgn"
    contents = r'''namespace App\Checks;
use Std\Io\{writeStdout,IoError};
let observe:Result<Unit,IoError>=writeStdout("I");
var counter:Int=0;
@test let clean:Function():Unit=function():Unit{assert counter==0;discard writeStdout("panic");};
@test let fail:Function():Unit=function():Unit{assert false;};
@test let crash:Function():Unit=function():Unit{panic{"body failure"};};
'''
    case_file.write_text(contents)
    r = invoke()
    assert r.returncode == 4, r
    assert b"tests: total=4 passed=1 failed=1 errors=2 aborted=0 not_run=0\n" in r.stdout, r
    assert b"unreachable initializer" not in r.stderr and b"unreached body" not in r.stderr
    assert b"init failure" in r.stderr and b"body failure" in r.stderr and b"initialization" in r.stderr, r
    index = contents.encode().index(b"assert false;")
    assert f"[bytes {index},{index+len('assert false;')})".encode() in r.stderr, r
    assert r.stdout.index(b"::blocked") < r.stdout.index(b"::clean") < r.stdout.index(b"::fail") < r.stdout.index(b"::crash"), r
    (src / "Broken/init.mgn").unlink()
    case_file.write_text(r"""namespace App\Checks;
var zero:Int=0;
@test let division:Function():Unit=function():Unit{discard 6/zero;};
@test let remainder:Function():Unit=function():Unit{discard 6%zero;};
@test let overflow:Function():Unit=function():Unit{discard 9223372036854775807+(zero+1);};
""")
    arithmetic = invoke()
    assert arithmetic.returncode == 4 and b"total=3 passed=0 failed=0 errors=3" in arithmetic.stdout, arithmetic
    assert arithmetic.stderr.count(b"runtime error: division by zero") == 2 and b"runtime error: integer overflow" in arithmetic.stderr, arithmetic
    # Error in a module with no discovered tests invalidates the entire plan.
    (src / "Unused/other.mgn").write_text('namespace App\\Unused;\nlet invalid:Int=false;\n')
    negative = invoke()
    assert negative.returncode == 1 and not negative.stdout and b"src/Unused/other.mgn" in negative.stderr, negative
    assert b"body failure" not in negative.stderr and not list(root.glob(".mgn-*"))
    print("Native suite passed mainless empty and nonempty, isolated closures, stages, assertion spans, priority and early failure")


if __name__ == "__main__":
    if sys.argv[1] == "--fail-first-map":
        sys.path.insert(0, str(ROOT))
        from tools.runner.supervisor import supervise
        from tools.selfhost.command import compile_command
        tracer = shutil.which("strace")
        if tracer is None:
            raise RuntimeError("The first mmap failure fixture requires strace")
        def one_failed_child(image, arguments, outcome, application, diagnostic):
            if outcome.ordinal == 0:
                arguments = ["-qq", "-o", os.devnull, "-e", "inject=mmap:error=ENOMEM:when=1",
                             "--", os.fspath(image), *arguments]
                image = tracer
            supervise(image, arguments, outcome, application, diagnostic)
        with patch("tools.runner.suite.supervise", one_failed_child):
            sys.exit(compile_command(sys.argv[2], sys.argv[3], [b"test", os.fsencode(sys.argv[4])]))
    with tempfile.TemporaryDirectory() as tmp:
        exercise(Path(sys.argv[1]).resolve(), sys.argv[2], Path(tmp))
