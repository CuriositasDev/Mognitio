#!/usr/bin/env python3
"""Exercise private normal-command preparation against an actual native compiler."""
import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.selfhost.command import compile_command, exit_status
from tools.selfhost.publication import Artifact


def exercise(compiler, build, root):
    src = root / "src"
    src.mkdir()
    manifest = root / "mognitio.toml"
    manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
    entry = src / "app.mgn"
    entry.write_text(r'''namespace App;
use Std\Io\{writeStdout,writeStderr};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 loop over(args as arg:String){discard writeStdout("["+arg+"]");};
 discard writeStderr("application\n");5
};
''')
    output = root / "output"
    output.write_bytes(b"old")
    output.chmod(0o640)
    def run(*args, preexec_fn=None):
        return subprocess.run([sys.executable, __file__, "--child", compiler, build, *args],
                              cwd=root, capture_output=True, preexec_fn=preexec_fn, timeout=30)

    cmd = ("build", "mognitio.toml", "-o")
    result = run(*cmd, output)
    assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), result
    image = output.read_bytes()
    assert image.startswith(b"\x7fELF") and stat.S_IMODE(output.stat().st_mode) == 0o700
    result = run(*cmd, "output2")
    assert result.returncode == 0 and (root / "output2").read_bytes() == image, result
    args = ("", "--", "猫")
    result = run("run", manifest, "--", *args)
    native = subprocess.run([output, *args], cwd=root, capture_output=True)
    assert (result.returncode, result.stdout, result.stderr) == (native.returncode, native.stdout, native.stderr)
    assert result.returncode == 5 and result.stdout == "[][--][猫]".encode() and result.stderr == b"application\n", result

    alias = root / "alias"
    alias.hardlink_to(entry)
    link = root / "symlink"
    link.symlink_to(output)
    fifo = root / "fifo"
    os.mkfifo(fifo)
    bad_targets = (manifest, entry, alias, link, fifo, src / "future.mgn", src, root / "missing" / "leaf")
    for target in bad_targets:
        result = run(*cmd, target)
        assert result.returncode == 2 and not result.stdout, (target, result)
    assert output.read_bytes() == image and not (src / "future.mgn").exists()
    invalid_run = run("run", manifest, "--", b"\xff")
    invalid_image = subprocess.run([output, b"\xff"], capture_output=True)
    assert (invalid_run.returncode, invalid_run.stdout, invalid_run.stderr) == (
        invalid_image.returncode, invalid_image.stdout, invalid_image.stderr) == (
        2, b"", b"runtime: invalid UTF-8 runtime argument\n")
    native_source = entry.read_bytes()
    entry.write_bytes(b"namespace App;\nlet bad:Int=true;\n")
    assert run("run", manifest, "--", b"\xff").returncode == 1
    assert run(*cmd, output).returncode == 1 and output.read_bytes() == image
    assert run("build", "missing", "-o", output).returncode == 2
    entry.write_bytes(native_source)
    assert not list(root.glob(".mgn-*"))
    # Check an uncertain atomic rename without assuming the old or new version
    # won. Cleanup must never remove the final name.
    for replaced in (False, True):
        output.write_bytes(b"old")
        with Artifact(str(output)) as staged:
            stage = Path(staged.prepare([str(manifest), str(entry)]))
            stage.write_bytes(image)
            stage.chmod(0o700)
            real_replace = os.replace
            def fault(source, destination):
                if replaced:
                    real_replace(source, destination)
                raise OSError(errno.EIO, "test injection")
            try:
                with patch.object(os, "replace", fault):
                    staged.publish()
            except OSError as error:
                assert "unknown" in str(error)
            else:
                raise AssertionError("Uncertain rename returned success")
        assert output.read_bytes() == (image if replaced else b"old")
        assert not list(root.glob(".mgn-*"))
    print("Native build/run parity, static ordering, publication protections and uncertain rename passed")


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        sys.exit(exit_status(compile_command(sys.argv[2], sys.argv[3], list(map(os.fsencode, sys.argv[4:])))))
    with tempfile.TemporaryDirectory() as tmp:
        exercise(Path(sys.argv[1]).resolve(), sys.argv[2], Path(tmp))
