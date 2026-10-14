#!/usr/bin/env python3
"""Exercise the public path API through host/native CLI and real OS fixtures."""
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/mgn"
IMPORTS = r"use Std\Io\{inspectPath,FileIdentity,PathInfo,PathInfoError,DirectoryEntryKind,IoErrorKind,readStdin,writeStdout,IoError};"
checks = 0
def run(command, **kwargs):
    global checks
    result = subprocess.run(list(map(str, command)), capture_output=True, timeout=60, **kwargs)
    assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), (command, result.returncode, result.stdout, result.stderr)
    checks += 1
def literal(value):
    return json.dumps(str(value), ensure_ascii=False)
def get(path):
    return "branch on inspectPath("+path+"){Result<PathInfo,PathInfoError>::Ok(found:PathInfo)=>found,Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>panic{e->subject}}"

with tempfile.TemporaryDirectory(prefix="mgn-v150-") as temp:
    root = Path(temp)
    (root / "src").mkdir()
    manifest = root / "mognitio.toml"
    manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
    source = root / "src/app.mgn"
    image = root / "app"
    def compile(body, extra=""):
        source.write_text("namespace App;"+IMPORTS+extra+
            "let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};\n")
        run([CLI, "build", manifest, "-o", image])
    def commands(args=()):
        return [[CLI, "run", manifest, "--", *args], [image, *args]]
    def pair(body):
        compile(body)
        for cmd in commands(): run(cmd, cwd=root)

    # A single argv-driven image preserves unusual path bytes exactly.
    compile('let path:String=branch on args->at(0){Result<String,IndexError>::Ok(v:String)=>v,Result<String,IndexError>::Err=>panic{"arg"}};'
        'let expected:String=branch on args->at(1){Result<String,IndexError>::Ok(v:String)=>v,Result<String,IndexError>::Err=>panic{"arg"}};'
        'let actual:String=branch on inspectPath(path){Result<PathInfo,PathInfoError>::Ok(p:PathInfo)=>branch on p->kind{'
        'DirectoryEntryKind::File=>"File",DirectoryEntryKind::Directory=>"Directory",DirectoryEntryKind::Symlink=>"Symlink",DirectoryEntryKind::Other=>"Other"},'
        'Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>{assert e->subject==path;branch on e->kind{'+
        ",".join('IoErrorKind::'+x+'=>'+literal(x) for x in ["InvalidPath","InvalidEncoding","NotFound","PermissionDenied","UnsupportedTarget","BrokenPipe","ResourceExhausted","Other"])+
        '}}};assert actual==expected;0')
    file = root / "file"
    file.write_bytes(b"unchanged")
    blocked = root / "blocked"
    blocked.mkdir()
    (blocked / "hidden").write_bytes(b"hidden")
    (root / "to-blocked").symlink_to(blocked / "hidden")
    (root / "loop").symlink_to("loop")
    (root / "directory-link").symlink_to(root, target_is_directory=True)
    pipe = root / "fifo"
    os.mkfifo(pipe)
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(str(root / "socket"))
    cases = [(str(root / "socket"), "Other"), (str(pipe), "Other"), ("file", "File"),
             ("./directory-link/../"+root.name+"/file", "File"), ("directory-link/./file", "File"),
             ("directory-link///", "Symlink"), ("directory-link/.", "Directory"),
             ("loop/child", "Other"), ("x"*256, "InvalidPath"), ("file/child", "UnsupportedTarget"),
             ("missing///", "NotFound"), ("", "InvalidPath"), ("to-blocked///", "Symlink"),
             ("blocked/hidden", "PermissionDenied")]
    for name in ["日本語 é 😀", "white space", "line\nbreak", "tab\tname", r"back\slash", "~literal"]:
        (root / name).write_bytes(b"same")
        cases.append((name, "File"))
    blocked.chmod(0)
    try:
        for path, expected in cases:
            for cmd in commands([path, expected]):
                run(cmd, cwd=root)
        assert file.read_bytes() == b"unchanged"
    finally:
        blocked.chmod(0o700)
        sock.close()

    # The native image runs with no compiler or Lisp available on PATH.
    run([image, str(file), "File"], env={"PATH": "/nonexistent"}, cwd=root)

    # Empty/NUL rejection follows one argument evaluation, with no path syscall.
    pair(r'var calls:Int=0;discard inspectPath({calls=calls+1;""});assert calls==1;'
         r'let nul:String="\0";'
         r'branch on inspectPath(nul){Result<PathInfo,PathInfoError>::Ok=>1,Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>{assert e->subject==nul;assert branch on e->kind{IoErrorKind::InvalidPath=>true,IoErrorKind::InvalidEncoding=>false,IoErrorKind::NotFound=>false,IoErrorKind::PermissionDenied=>false,IoErrorKind::UnsupportedTarget=>false,IoErrorKind::BrokenPipe=>false,IoErrorKind::ResourceExhausted=>false,IoErrorKind::Other=>false};0}}')

    # Observation pairs straddle an external rename/content change/deletion.
    old = root / "old"
    new = root / "new"
    for mutation in ("rename-and-write", "delete"):
        check = ('let after:PathInfo='+get(literal(new))+';assert held==after->identity;'
                 if mutation == "rename-and-write" else "")
        compile('let before:PathInfo='+get(literal(old))+';'
            'let held:FileIdentity=before->identity;let copy:FileIdentity=held;'
            'discard writeStdout("ready");discard readStdin();'+check+
            'assert held==copy;assert !(held!=copy);0')
        for cmd in commands():
            old.write_bytes(b"before")
            process = subprocess.Popen(list(map(str, cmd)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root)
            try:
                with selectors.DefaultSelector() as select:
                    select.register(process.stdout, selectors.EVENT_READ)
                    assert select.select(20), "missing ready signal"
                    assert os.read(process.stdout.fileno(), 5) == b"ready"
                if mutation == "rename-and-write":
                    old.rename(new)
                    new.write_bytes(b"changed")
                else:
                    old.unlink()
                process.stdin.close()
                assert process.wait(timeout=20) == 0
                assert process.stdout.read() == process.stderr.read() == b""
                checks += 1
            finally:
                if process.poll() is None: process.kill(); process.wait()
                if new.exists(): new.unlink()

    # Filesystems are physically distinct; identity includes both OS words.
    with tempfile.TemporaryDirectory(prefix="mgn-v150-", dir="/dev/shm") as shared:
        peer = Path(shared) / "file"
        peer.write_bytes(b"unchanged")
        assert file.stat().st_dev != peer.stat().st_dev
        pair('let a:PathInfo='+get(literal(file))+';let b:PathInfo='+get(literal(peer))+';assert a->identity!=b->identity;0')

    # The ordinary native test runner uses the same API and error value.
    source.write_text("namespace App;"+IMPORTS+
        '@test let path:Function():Unit=function():Unit{let p:PathInfo='+get(literal(file))+
        ';assert p->identity==p->identity;unit};')
    result = subprocess.run([str(CLI), "test", str(manifest)], capture_output=True, timeout=60)
    assert result.returncode == 0 and result.stderr == b"" and b"total=1 passed=1" in result.stdout, result
    checks += 1
print(f"v1.5 path inspection integration checks={checks} failures=0")
