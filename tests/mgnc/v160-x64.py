#!/usr/bin/env python3
"""Check instruction bytes against independently fixed AMD64 vectors."""
import argparse,shutil,subprocess,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument("--seed",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args();args.output.mkdir()
project=args.output/"project";(project/"src").mkdir(parents=True)
(project/"mognitio.toml").write_text('[project]\nname = "instructionprobe"\nroot_namespace = "Mgnc"\n')
for module in ("Data","IntMap","Machine","Encode","Fields","WholeX64"):shutil.copytree(ROOT/"compiler/mgnc/src"/module,project/"src"/module)
shutil.copyfile(ROOT/"tests/mgnc/harnesses/v160-x64.mgn",project/"src/instructionprobe.mgn")
binary=args.output/"emitter";p=args.output/"vectors"
result=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(result.returncode,result.stdout,result.stderr)
result=subprocess.run([binary,p],capture_output=True,timeout=30)
assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(result.returncode,result.stdout,result.stderr)
hexes=['48b83c00000000000000','48bf0000000000000000','0f05','4d89f1','4d8b95b8ffffff','4c89a42428000000','4d8d842440000000','49bbfdffffffffffffff','4d01f5','4981ff11000000','49c1e803','4d0fafe1','49f7da','4157415f','41ffd3','4d0fb69101000000','4088b42403000000','410f95c14d0fb6c9']
expected=b''.join(bytes.fromhex(h) for h in hexes);expected+=b'\x48\xb8'+struct.pack('<Q',4194424+len(expected)+10)
actual=p.read_bytes()[120:];assert actual==expected,(actual.hex(),expected.hex());result=subprocess.run([p],capture_output=True);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b'')
print('X64_VECTORS_OK vectors=19 independent_bytes=true elf_execution=true')
