#!/usr/bin/env python3
"""Generate and run native values without the compiler toolchain or sources."""
import argparse,json,hashlib,subprocess,tempfile,sys,os,struct,stat
from pathlib import Path
from isolated import prefix
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path,required=True);p.add_argument("--userland",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
def elf(data):
 assert data[:16]==b"\x7fELF\x02\x01\x01"+bytes(9)
 assert struct.unpack_from("<HHIQQQIHHHHHH",data,16)==(2,62,1,0x400078,64,0,0,64,56,1,0,0,0)
 assert struct.unpack_from("<IIQQQQQQ",data,64)==(1,5,0,0x400000,0x400000,len(data),len(data),4096)
def inventory(root):
 rows=[]
 for path in sorted(root.rglob("*")):
  if path.is_symlink():rows.append([str(path.relative_to(root)),"link",os.readlink(path)])
  elif path.is_file():rows.append([str(path.relative_to(root)),stat.S_IMODE(path.stat().st_mode),hashlib.sha256(path.read_bytes()).hexdigest()])
 return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),len(rows)
environment_hash,environment_files=inventory(a.userland)
records=[];runtime=a.output/"runtime";runtime.mkdir()
for name,c in json.loads((HERE/"v160-native-values.json").read_text()).items():
 folder=a.output/name;folder.mkdir();(folder/"input.mgn").write_text(c["source"])
 r=subprocess.run(prefix(a.userland,a.compiler,folder)+["/emitter","build","input.mgn","-o","program"],capture_output=True,timeout=180,umask=0o022)
 assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),(name,"build",r.returncode,r.stdout,r.stderr)
 x=folder/"program";elf(x.read_bytes());assert stat.S_IMODE(x.stat().st_mode)==0o755
 r=subprocess.run(prefix(a.userland,x,runtime)+["/emitter",*c["args"]],capture_output=True,timeout=120)
 assert (r.returncode,r.stdout,r.stderr)==(c["status"],c["stdout"].encode(),c["stderr"].encode()),(name,"run",r.returncode,r.stdout,r.stderr)
 records.append({"name":name,"source_sha256":hashlib.sha256(c["source"].encode()).hexdigest(),"artifact_sha256":hashlib.sha256(x.read_bytes()).hexdigest(),"mode":"0755","build_umask":"0022","exit":r.returncode,"stdout_hex":r.stdout.hex(),"stderr_hex":r.stderr.hex()})
 print(name,"PASS",flush=True)
assert not list(runtime.iterdir())
assert inventory(a.userland)==(environment_hash,environment_files)
(a.output/"results.json").write_text(json.dumps({"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"userland_inventory_sha256":environment_hash,"userland_files":environment_files,"userland_unchanged":True,"userland_release":(a.userland/"etc/os-release").read_text(),"records":records},indent=2)+"\n")
print("V160_NATIVE_ISOLATION_OK cases=41",flush=True)
