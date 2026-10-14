#!/usr/bin/env python3
"""Freeze an explicitly accepted Lisp compiler revision for internal bootstrap use."""
import argparse, hashlib, io, json, os, shutil, subprocess, tarfile, tempfile
from pathlib import Path

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
def inventory(root):
    rows=[]
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): raise ValueError("Seed contains a symlink")
        if path.is_file() and path != root/"manifest.json":
            rows.append({"path":path.relative_to(root).as_posix(),"bytes":path.stat().st_size,
                         "mode":path.stat().st_mode & 0o777,"sha256":digest(path)})
    return rows
def verify(root):
    record=json.loads((root/"manifest.json").read_text())
    if inventory(root)!=record["components"]: raise ValueError("Seed component inventory mismatch")
    return record

def freeze(a):
    repo=a.repository.resolve()
    commit=subprocess.check_output(["git","rev-parse",a.commit+"^{commit}"],cwd=repo,text=True).strip()
    a.output.mkdir(parents=True,exist_ok=True)
    destination=a.output.resolve()/("lisp-"+commit)
    if destination.exists(): raise ValueError("Immutable seed destination already exists")
    with tempfile.TemporaryDirectory(prefix=".freeze-",dir=a.output) as temp:
        work=Path(temp);root=work/"seed";root.mkdir();source=root/"source";source.mkdir()
        archive=subprocess.check_output(["git","archive",commit],cwd=repo)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar: tar.extractall(source,filter="data")
        env=dict(os.environ,GIT_DIR=str(repo/".git"),GIT_WORK_TREE=str(source))
        actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=source,env=env,text=True).strip()
        if actual!=commit: raise ValueError("Checkout HEAD must be the accepted source commit")
        if subprocess.check_output(["git","status","--porcelain"],cwd=source,env=env):
            raise ValueError("Export differs from the accepted source commit")
        runtime=a.runtime_root.resolve()
        command=["python3","scripts/build-toolchain.py","--runtime",str(runtime/"usr/bin/sbcl"),
                 "--core",str(runtime/"usr/lib/sbcl/sbcl.core"),"--runtime-notice",
                 str(runtime/"usr/share/doc/sbcl/copyright"),"--image-digest",a.image_digest,
                 "--mode","development","--output",str(work/"payload")]
        payload=Path(subprocess.check_output(command,cwd=source,env=env,text=True).strip())
        shutil.copytree(payload,root/"artifact")
        libs=root/"runtime";libs.mkdir();system=a.system_root.resolve()
        for name in ("ld-linux-x86-64.so.2","libc.so.6","libm.so.6","libdl.so.2","libpthread.so.0","libzstd.so.1"):
            shutil.copy2(system/"usr/lib/x86_64-linux-gnu"/name,libs/name,follow_symlinks=True)
        shutil.copy2(system/"usr/bin/dash",libs/"dash")
        shutil.copy2(system/"etc/os-release",libs/"os-release")
        shutil.copy2(runtime/"usr/lib/sbcl/sbcl.core",libs/"input-sbcl.core")
        for package in ("libc6","libzstd1","dash"):
            shutil.copy2(system/"usr/share/doc"/package/"copyright",libs/(package+"-copyright"))
        (root/"bin").mkdir()
        launcher="""#!/bin/sh
root=$(CDPATH= cd -- "ROOTPATH/.." && pwd -P) || exit 3
if ( : 9<&0 ) 2>&-; then
    exec 9<&0
    mgn_stdin_open=yes
else
    mgn_stdin_open=no
fi
mgn_launch() {
    if [ "$mgn_stdin_open" = yes ]; then
        exec "$root/runtime/ld-linux-x86-64.so.2" --library-path "$root/runtime" "$root/artifact/runtime/sbcl" --core "$root/artifact/runtime/mognitio.core" --noinform --no-sysinit --no-userinit --mognitio-argv-fd=3 3<&0 0<&9 9<&-
    else
        exec "$root/runtime/ld-linux-x86-64.so.2" --library-path "$root/runtime" "$root/artifact/runtime/sbcl" --core "$root/artifact/runtime/mognitio.core" --noinform --no-sysinit --no-userinit --mognitio-argv-fd=3 --mognitio-stdin-closed 3<&0 0</dev/null
    fi
}
{
    printf '%s\\000' "$#"
    for argument do printf '%s\\000' "$argument"; done
} | mgn_launch
""".replace("ROOTPATH","$"+"{0%/*}")
        (root/"bin/mgn").write_text(launcher);(root/"bin/mgn").chmod(0o755)
        shutil.copy2(__file__,root/"freeze-seed.py")
        dump(root/"acceptance.json",{"sourceCommit":commit,"acceptedDate":a.accepted_date,
             "authority":"Explicit user acceptance of the reviewed Lisp implementation",
             "evidence":["source/verification/v1.5.0-lisp.md","source/verification/v1.5.0-lisp/diagnostic-cumulative-ubuntu26.txt"]})
        packages=[]
        for block in (system/"var/lib/dpkg/status").read_text().split("\n\n"):
            values=dict(line.split(": ",1) for line in block.splitlines() if ": " in line and not line.startswith(" "))
            if values.get("Package") in ("libc6","libzstd1","dash"):
                packages.append({k:values[k] for k in ("Package","Version","Architecture")})
        ident=json.loads((root/"artifact/identity.json").read_text())
        normalized=[x.replace(str(runtime),"<runtime>").replace(str(work),"<staging>") for x in command]
        dump(root/"manifest.json",{"schema":1,"sourceCommit":commit,"docsRevision":a.docs_revision,
             "target":"linux-amd64","acceptance":"acceptance.json","payloadIdentity":ident["build"],"seedEntry":"bin/mgn",
             "build":{"cwd":"source","command":normalized,"env":{"SBCL_HOME":"<runtime>/usr/lib/sbcl",
                "GIT_DIR":"<repository>/.git","GIT_WORK_TREE":"source"},
                "python":subprocess.check_output(["python3","--version"],text=True).strip(),"kernel":os.uname().release},
             "systemDependencies":{"bundled":packages,"external":["Linux amd64 kernel","/bin/sh for convenience entry; bundled dash can launch explicitly"],
                "runtime":"Bundled SBCL 2.2.9, compiler core, loader and C libraries",
                "unused":"artifact/bin and artifact/lsp are retained but not used by seed entry; no Python at seed execution"},
             "components":inventory(root)})
        verify(root);root.rename(destination)
    bundle=destination.with_suffix(".tar.gz")
    with tarfile.open(bundle,"w:gz") as tar: tar.add(destination,arcname="seed")
    receipt={"schema":1,"sourceCommit":commit,"bundle":bundle.name,"bytes":bundle.stat().st_size,
             "sha256":digest(bundle),"manifestSha256":digest(destination/"manifest.json")}
    dump(destination.with_suffix(".receipt.json"),receipt);print(json.dumps(receipt))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--verify",type=Path)
    for key in ("repository","runtime-root","system-root","output"): p.add_argument("--"+key,type=Path)
    for key in ("commit","docs-revision","accepted-date","image-digest"): p.add_argument("--"+key)
    args=p.parse_args()
    if args.verify: print("SEED_COMPONENTS_OK "+verify(args.verify)["sourceCommit"])
    else: freeze(args)
