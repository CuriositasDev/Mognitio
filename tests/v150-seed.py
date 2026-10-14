#!/usr/bin/env python3
"""Verify, restore and execute a seed without its original checkout or host Lisp."""
import argparse,hashlib,importlib.util,json,subprocess,tarfile,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--bundle",type=Path,required=True);p.add_argument("--receipt",type=Path,required=True)
args=p.parse_args();receipt=json.loads(args.receipt.read_text())
assert hashlib.sha256(args.bundle.read_bytes()).hexdigest()==receipt["sha256"]
assert args.bundle.stat().st_size==receipt["bytes"]
with tempfile.TemporaryDirectory(prefix="mgn-seed-restore-") as temp:
    work=Path(temp)
    with tarfile.open(args.bundle) as archive: archive.extractall(work,filter="data")
    seed=work/"seed"
    assert hashlib.sha256((seed/"manifest.json").read_bytes()).hexdigest()==receipt["manifestSha256"]
    # The safe tar filter removes group-write bits; restore declared regular-file modes
    # only after authenticating the manifest against the external receipt.
    for item in json.loads((seed/"manifest.json").read_text())["components"]:
        path=seed/item["path"]
        assert path.resolve().is_relative_to(seed.resolve()) and not path.is_symlink()
        path.chmod(item["mode"])
    spec=importlib.util.spec_from_file_location("freeze_seed",seed/"freeze-seed.py")
    tool=importlib.util.module_from_spec(spec)
    # Avoid a .pyc file modifying the immutable component inventory.
    import sys
    sys.dont_write_bytecode=True
    spec.loader.exec_module(tool)
    manifest=tool.verify(seed)
    assert manifest["sourceCommit"]==receipt["sourceCommit"]
    launcher=seed/"bin/mgn";original=launcher.read_bytes()
    launcher.write_bytes(original+b"\n")
    try:
        tool.verify(seed)
        raise AssertionError("Modified seed passed verification")
    except ValueError: pass
    launcher.write_bytes(original)
    tool.verify(seed)
    fixture=work/"project";(fixture/"src").mkdir(parents=True)
    (fixture/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="App"\n')
    (fixture/"src/app.mgn").write_text(r"""
namespace App;
use Std\Io\{inspectPath,FileIdentity,PathInfo,PathInfoError,DirectoryEntryKind};
let main:Function(List<String>):Int=function(args:List<String>):Int{
  let first:PathInfo=branch on inspectPath("/project/input"){
    Result<PathInfo,PathInfoError>::Ok(info:PathInfo)=>info,
    Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>panic{e->subject}
  };
  let second:PathInfo=branch on inspectPath("/project/input"){
    Result<PathInfo,PathInfoError>::Ok(info:PathInfo)=>info,
    Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>panic{e->subject}
  };
  assert first->identity==second->identity;
  assert branch on first->kind{DirectoryEntryKind::File=>true,DirectoryEntryKind::Directory=>false,DirectoryEntryKind::Symlink=>false,DirectoryEntryKind::Other=>false};
  0
};
""")
    (fixture/"input").write_bytes(b"metadata fixture")
    namespace=["bwrap","--unshare-user","--uid","1000","--gid","1000","--unshare-net","--tmpfs","/",
        "--ro-bind",str(seed),"/seed","--bind",str(fixture),"/project","--proc","/proc","--dev","/dev",
        "--tmpfs","/tmp","--chdir","/project","--clearenv","--setenv","HOME","/tmp","--setenv","PATH","/absent"]
    command=["/seed/runtime/ld-linux-x86-64.so.2","--library-path","/seed/runtime",
             "/seed/runtime/dash","/seed/bin/mgn"]
    for action in [["run","/project/mognitio.toml"],["build","/project/mognitio.toml","-o","/project/program"]]:
        result=subprocess.run(namespace+command+action,capture_output=True,timeout=60)
        assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),result
    result=subprocess.run(["bwrap","--unshare-user","--uid","1000","--gid","1000","--unshare-net","--tmpfs","/",
        "--bind",str(fixture),"/project","--chdir","/project","--clearenv","/project/program"],
        capture_output=True,timeout=10)
    assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),result
    print("SEED_RESTORE_OK components="+str(len(manifest["components"]))+" mutation_rejected=true isolated_run=true isolated_build=true independent_elf=true")
