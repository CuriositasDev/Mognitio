#!/usr/bin/env python3
"""Independent ELF/relocation vectors for colliding and sparse label IDs."""
import argparse,hashlib,json,shutil,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
project=a.output/"compiler";(project/"src").mkdir(parents=True)
shutil.copyfile(ROOT/"compiler/mgnc/mognitio.toml",project/"mognitio.toml")
for name in ["Data","Machine","Encode","EncodeChunks","Fields","IntMap"]:shutil.copytree(ROOT/"compiler/mgnc/src"/name,project/"src"/name)
shutil.copyfile(ROOT/"tests/mgnc/harnesses/v160-label-index.mgn",project/"src/mgnc.mgn")
binary=a.output/"probe";result=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),result
images=a.output/"images";images.mkdir();start=time.monotonic()
result=subprocess.run([binary,images],capture_output=True,timeout=120)
assert (result.returncode,result.stdout,result.stderr)==(0,b"V160_LABEL_INDEX_OK positive=3 rejected=9\n",b""),result
elapsed=time.monotonic()-start;rows=[]
def elf(body):
 return (b"\x7fELF\x02\x01\x01"+bytes(9)+struct.pack("<HHIQQQIHHHHHH",2,62,1,4194424,64,0,0,64,56,1,0,0,0)
         +struct.pack("<IIQQQQQQ",1,5,0,4194304,4194304,120+len(body),120+len(body),4096)+body)
for count in [128,8192]:
 body=bytearray()
 for i in range(count):
  following=0 if i+1==count else 13*(i+1);previous=0 if i==0 else 13*(i-1)
  body+=b"\x90"+struct.pack("<iQ",following-(13*i+5),4194424+previous)
 name="dense-"+str(count);data=(images/name).read_bytes();assert data==elf(body),name
 rows.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
body=b"".join(b"\x90"+struct.pack("<Q",4194424+i*9) for i in range(3))
data=(images/"sparse").read_bytes();assert data==elf(body),"sparse"
rows.append(dict(name="sparse",bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(a.output/"results.json").write_text(json.dumps(dict(positive=3,rejected=9,seconds=elapsed,images=rows),indent=2)+"\n")
print("V160_LABEL_BYTES_OK positive=3 rejected=9 seconds="+str(elapsed))
