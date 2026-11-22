#!/usr/bin/env python3
"""Compare ordinary run and the standalone executable under an inherited one-byte file limit."""
import argparse
from pathlib import Path
import resource
import signal
import subprocess
import tempfile


def limit_one():
    resource.setrlimit(resource.RLIMIT_FSIZE, (1, 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for sig in (signal.SIGPIPE, signal.SIGXFSZ):
        signal.signal(sig, signal.SIG_DFL)


def exercise(root, cli, reference):
    manifest = root / "mognitio.toml"
    manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
    (root / "src").mkdir()
    source = root / "src/app.mgn"
    kinds = ["InvalidPath", "InvalidEncoding", "NotFound", "PermissionDenied", "UnsupportedTarget",
             "BrokenPipe", "ResourceExhausted", "Other"]
    io_error = ",".join(f"IoErrorKind::{kind}=>{200+i}" for i, kind in enumerate(kinds))
    copy = '''
        let content:String=branch on readTextFile("in"){
            Result<String,IoError>::Ok(s:String)=>s,Result<String,IoError>::Err=>{return 1;}};
        branch on writeTextFile("out",content){
            Result<Unit,IoError>::Ok=>0,Result<Unit,IoError>::Err(e:IoError)=>branch on e->kind{''' + io_error + '}}'
    for name, body, expected, output in (("exit", "207", 207, None), ("write", copy, 207, b"A")):
        source.write_text("namespace App; use Std\\Io\\{readTextFile,writeTextFile,IoError,IoErrorKind};\n"
                          "let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};")
        image = root / (name+".elf")
        subprocess.run([cli, "build", manifest, "-o", image], check=True, capture_output=True, timeout=60)
        commands = [("run", [cli, "run", manifest]), ("elf", [image])]
        if reference:
            commands.append(("reference", [reference, "run", manifest]))
        for route, command in commands:
            directory = root / (name+"-"+route)
            directory.mkdir()
            (directory / "in").write_bytes(b"AB")
            result = subprocess.run(command, cwd=directory, preexec_fn=limit_one, capture_output=True, timeout=60)
            path = directory / "out"
            actual = path.read_bytes() if path.exists() else None
            assert (result.returncode, result.stdout, result.stderr, actual) == (expected, b"", b"", output), (
                name, route, result.returncode, result.stdout, result.stderr, actual)
            print(f"{name} {route}: exit={result.returncode}, output={actual!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        exercise(Path(temporary), args.cli.resolve(), args.reference.resolve() if args.reference else None)
