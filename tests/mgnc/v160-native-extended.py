#!/usr/bin/env python3
"""Control, lifetime, module-order, identity and publication observations."""
import argparse,hashlib,json,os,shutil,stat,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.compiler=a.compiler.resolve();a.output=a.output.resolve();a.output.mkdir()
records=[]
def record(name,result,**extra):
 records.append({"case":name,"exit":result.returncode,"stdout_hex":result.stdout.hex(),"stderr_hex":result.stderr.hex(),**extra})
def call(command,status=0,stdout=b"",stderr=b"",cwd=None,preexec_fn=None):
 r=subprocess.run(command,capture_output=True,cwd=cwd,preexec_fn=preexec_fn,timeout=180)
 assert r.returncode==status and r.stdout==stdout and (stderr is None or r.stderr==stderr),(command,r.returncode,r.stdout,r.stderr)
 return r
def build(source,target):
 return call([a.compiler,"build",source,"-o",target])
def snapshot(folder):
 return {p.relative_to(folder).as_posix():(p.read_bytes(),stat.S_IMODE(p.stat().st_mode),p.stat().st_dev,p.stat().st_ino) for p in folder.rglob("*") if p.is_file() and not p.is_symlink()}
# Repeated stdin consumption and managed values across control transfers.
root=a.output/"extended";shutil.copytree(HERE/"fixtures/v160-extended",root)
for source in sorted(root.glob("*.mgn")):build(source,root/source.stem)
for index,c in enumerate(json.loads((root/"cases.json").read_text())):
 for stress in (False,True):
  command=[root/c["name"],*c["args"]]
  if stress:command=[sys.executable,HERE/"v160-native-observe.py","--stress","--report",root/f"stress-{index}.json","--",*command]
  r=subprocess.run(command,input=bytes.fromhex(c["stdin_hex"]),capture_output=True,cwd=root,timeout=180)
  assert (r.returncode,r.stdout,r.stderr)==(c["status"],bytes.fromhex(c["stdout_hex"]),b""),(index,stress,r.returncode,r.stdout,r.stderr)
  record(f"control-{index}-stress-{stress}",r)
# Module order, unreachable marker suppression, failure stop and relocation.
original=a.output/"original";relocated=a.output/"relocated"
shutil.copytree(HERE/"fixtures/v160-marker-diamond",original);shutil.copytree(original,relocated)
images=[]
for index,project in enumerate((original,original,relocated)):
 image=a.output/f"module-{index}";build(project/"mognitio.toml",image);images.append(image.read_bytes())
 record(f"module-order-{index}",call([image],5,b"BATZIM"))
assert images[0]==images[1]==images[2]
failure=a.output/"failure";shutil.copytree(HERE/"fixtures/v160-marker-failure",failure)
build(failure/"mognitio.toml",a.output/"failed-module")
record("module-failure-stop",call([a.output/"failed-module"],4,b"BA",b"panic: stop\n"))
# Publication preserves existing object identities and source membership.
root=a.output/"protection";root.mkdir()
source=root/"input.mgn";source.write_text("namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{0};\n")
project=root/"project";(project/"src/nested").mkdir(parents=True)
manifest=project/"mognitio.toml";manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
(project/"src/app.mgn").write_bytes(source.read_bytes())
targets=[("source",source),("manifest",manifest)]
for name in ("existing","directory","symlink","dangling","hardlink"):
 target=root/name
 if name=="existing":target.write_bytes(b"original")
 elif name=="directory":target.mkdir()
 elif name=="symlink":target.symlink_to(source)
 elif name=="dangling":target.symlink_to(root/"absent")
 else:os.link(source,target)
 targets.append((name,target))
before=snapshot(root)
for name,target in targets:
 record("protect-"+name,call([a.compiler,"build",manifest,"-o",target],2,stderr=None))
 assert snapshot(root)==before
 assert target.is_symlink() if name in ("symlink","dangling") else target.exists()
alias=root/"source-alias";alias.symlink_to(project/"src",target_is_directory=True)
for name,target,cwd in (("direct",project/"src/new.mgn",None),("nested",project/"src/nested/new.mgn",None),("alias",alias/"new.mgn",None),("relative","new.mgn",project/"src/nested")):
 r=call([a.compiler,"build",manifest,"-o",target],2,stderr=None,cwd=cwd)
 assert b"next project source set" in r.stderr
 assert not (Path(cwd)/target if cwd else target).exists()
 record("membership-"+name,r)
build(manifest,project/"src/program");record("non-source-output",call([project/"src/program"]))
# Equal bytes do not imply identity; hardlink and symlink duplicates do.
for kind in ("separate","hardlink","symlink"):
 copy=root/("identity-"+kind);shutil.copytree(project,copy)
 (copy/"src/Other").mkdir();first=copy/"src/Other/one.mgn";second=copy/"src/Other/two.mgn"
 first.write_text("namespace App\\Other;\n")
 if kind=="separate":second.write_bytes(first.read_bytes())
 elif kind=="hardlink":os.link(first,second)
 else:second.symlink_to(first)
 original_bytes=snapshot(copy)
 for verb in ("check","lower"):
  r=call([a.compiler,verb,copy/"mognitio.toml"],0 if kind=="separate" else 2,stderr=b"" if kind=="separate" else None)
  if kind!="separate":assert b"identity" in r.stderr or b"same file" in r.stderr,(kind,r.stderr)
  assert snapshot(copy)==original_bytes
  record("identity-"+kind+"-"+verb,r)
# Lowering is read-only and never executes user initializers.
marker=root/"marker";marker.write_bytes(b"original")
readonly=root/"readonly.mgn";readonly.write_text('namespace App;use Std\\Io\\{writeTextFile,IoError};let effect:Result<Unit,IoError>=writeTextFile("marker","changed");let main:Function(List<String>):Int=function(args:List<String>):Int{0};let stopped:Unit=panic{"must not run"};\n')
for verb in ("check","lower"):
 r=call([a.compiler,verb,readonly],cwd=root);assert marker.read_bytes()==b"original";record("readonly-"+verb,r)
bad=root/"bad.mgn";bad.write_text("namespace App;let value:Int=true;\n")
r=call([a.compiler,"build",bad,"-o",root/"missing/target"],1,stderr=None);assert b"type:" in r.stderr;record("static-before-output",r)
r=call([a.compiler,"check",bad],2,stderr=None,preexec_fn=lambda:os.close(2));record("diagnostic-write-failure",r)
# Keep portable summaries; exact stderr bytes remain in the local raw report.
(a.output/"results.json").write_text(json.dumps({"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":records},indent=2)+"\n")
print(f"V160_NATIVE_EXTENDED_OK checks={len(records)}")
