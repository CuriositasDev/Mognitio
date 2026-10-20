#!/usr/bin/env python3
"""Observe partial stdin consumption and short stream writes followed by failure."""
import argparse
import hashlib
import json
import resource
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--compiler", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
a.compiler = a.compiler.resolve()
a.output.mkdir()
here = Path(__file__).resolve().parent
# Reuse the independently defined IoError code oracle from the frozen I/O fixture.
prefix = (here / "fixtures/v160-io/stdin.mgn").read_text().split("let main:")[0]
sources = {
    "read-progress": prefix + """let main:Function(List<String>):Int=function(args:List<String>):Int{
 branch on readStdin(){Result<String,IoError>::Ok(value:String)=>{return 1;},
 Result<String,IoError>::Err(error:IoError)=>{branch when{code(error)!=103=>{return 2;},else=>unit};}};
 branch on readStdin(){Result<String,IoError>::Ok(value:String)=>{discard writeStdout(value);0},
 Result<String,IoError>::Err(error:IoError)=>3}
};""",
    "write-progress": prefix + """let main:Function(List<String>):Int=function(args:List<String>):Int{
 let writer:Function(String):Result<Unit,IoError>=branch when{args->length()==0=>writeStdout,else=>writeStderr};
 branch on writer("abcdefgh"){Result<Unit,IoError>::Ok(value:Unit)=>0,
 Result<Unit,IoError>::Err(error:IoError)=>code(error)}
};""",
}
sources["list-streams"] = prefix + """let main:Function(List<String>):Int=function(args:List<String>):Int{
 let writers:List<Function(String):Result<Unit,IoError>>=List<Function(String):Result<Unit,IoError>>[writeStdout,writeStderr];
 loop over(writers as writer:Function(String):Result<Unit,IoError>){discard writer("list");};0
};
"""
records = []
for name, text in sources.items():
    source = a.output / (name + ".mgn")
    source.write_text(text)
    image = a.output / name
    built = subprocess.run([a.compiler, "build", source, "-o", image], capture_output=True, timeout=120)
    assert (built.returncode, built.stdout, built.stderr) == (0, b"", b""), built
    records.append(dict(name=name, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        artifact_sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
# The frozen runtime reads a 4096-byte initial chunk. The injected second read
# fails before consuming anything, so the next API call must see only the tail.
data = b"x" * 4096 + b"tail"
result = subprocess.run([sys.executable, here / "syscall-fault.py", "--syscall", "0",
                         "--ordinal", "2", "--errno", "5", "--", a.output / "read-progress"],
                        input=data, capture_output=True, timeout=120)
assert (result.returncode, result.stdout, result.stderr) == (0, b"tail", b""), result
records.append(dict(name="partial-read-then-retry", exit=result.returncode,
                    stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex(), passed=True))


def limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (4, 4))


for stream in ("stdout", "stderr"):
    path = a.output / (stream + ".bytes")
    with path.open("wb") as output:
        options = dict(stdout=output, stderr=subprocess.PIPE) if stream == "stdout" else dict(stdout=subprocess.PIPE, stderr=output)
        args = [] if stream == "stdout" else ["stderr"]
        result = subprocess.run([a.output / "write-progress", *args], preexec_fn=limit,
                                timeout=120, **options)
    other = result.stderr if stream == "stdout" else result.stdout
    assert result.returncode == 103 and path.read_bytes() == b"abcd" and other == b"", (stream, result)
    records.append(dict(name="short-" + stream + "-then-failure", exit=result.returncode,
                        prefix_hex=path.read_bytes().hex(), other_hex=other.hex(), passed=True))
for stress in (False, True):
    command = [a.output / "list-streams"]
    observation = a.output / "list-streams-stress.json"
    if stress:
        command = [sys.executable, here / "v160-native-observe.py", "--stress",
                   "--report", observation, "--", *command]
    result = subprocess.run(command, capture_output=True, timeout=120)
    assert (result.returncode, result.stdout, result.stderr) == (0, b"list", b"list"), result
    state = json.loads(observation.read_text()) if stress else None
    if stress:
        assert state["stress"] and state["heap"]["collections"] > 0 and state["heap"]["primary"] == 0
    records.append(dict(name="stream-functions-in-list", stress=stress, exit=result.returncode,
                        stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex(),
                        observation=state, passed=True))

(a.output / "results.json").write_text(json.dumps(dict(
    compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest(), records=records), indent=2) + "\n")
print("V160_STREAM_BOUNDARIES_OK checks=5")
