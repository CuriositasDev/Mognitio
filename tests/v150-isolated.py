#!/usr/bin/env python3
"""Run an API-using ELF in a mount namespace containing no compiler or Lisp."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
bwrap = shutil.which("bwrap")
assert bwrap, "bubblewrap is required for the standalone isolation gate"
with tempfile.TemporaryDirectory(prefix="mgn-v150-isolated-") as temp:
    root = Path(temp)
    (root/"src").mkdir()
    (root/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="App"\n')
    (root/"src/app.mgn").write_text(r"""
namespace App;
use Std\Io\{inspectPath,PathInfo,PathInfoError,DirectoryEntryKind};
let main:Function(List<String>):Int=function(args:List<String>):Int{
  branch on inspectPath("/input"){
    Result<PathInfo,PathInfoError>::Ok(p:PathInfo)=>{
      assert p->identity==p->identity;
      assert branch on p->kind{DirectoryEntryKind::File=>true,DirectoryEntryKind::Directory=>false,DirectoryEntryKind::Symlink=>false,DirectoryEntryKind::Other=>false};0
    },
    Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>panic{e->subject}
  }
};
""")
    data = root/"input"
    data.write_bytes(b"metadata only")
    image = root/"app"
    commands = [
        [ROOT/"bin/mgn", "build", root/"mognitio.toml", "-o", image],
        [bwrap, "--unshare-user", "--uid", "1000", "--gid", "1000", "--unshare-net",
         "--tmpfs", "/", "--ro-bind", image, "/program", "--ro-bind", data, "/input",
         "--chdir", "/", "--clearenv", "--setenv", "PATH", "/absent", "/program"],
    ]
    for command in commands:
        result = subprocess.run(list(map(str, command)), capture_output=True, timeout=60)
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), result
    assert data.read_bytes() == b"metadata only"
    print("V150_ISOLATED_OK files=2 compiler_absent=true lisp_absent=true elf_sha256="+hashlib.sha256(image.read_bytes()).hexdigest())
