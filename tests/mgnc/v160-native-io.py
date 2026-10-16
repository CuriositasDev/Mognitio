import subprocess,sys,json,time,os
from pathlib import Path
A=Path(sys.argv[1]);r=Path(__file__).with_name("fixtures")/"v160-io";out=Path(sys.argv[2]);out.mkdir()
bins={}
for source in sorted(r.glob("*.mgn")):
 target=out/source.stem
 result=subprocess.run([A,"build",source,"-o",target],capture_output=True,timeout=180)
 assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(source.name,result.returncode,result.stdout,result.stderr)
 bins[source.stem]=target
 print("emitted",source.stem,flush=True)
def run(name,args=(),data=b"",status=0,stdout=b"",stderr=b""):
 result=subprocess.run([bins[name],*map(str,args)],input=data,capture_output=True,timeout=60)
 assert (result.returncode,result.stdout,result.stderr)==(status,stdout,stderr),(name,args,result.returncode,result.stdout[:300],result.stderr[:300])
 print("PASS",name,list(map(str,args)),len(data),flush=True)
run("streams",stdout="hello 日本😀\0\n".encode(),stderr=b"err")
run("indirect",stdout=b"fieldparam")
run("ignore");run("invalid-order",status=4,stderr=b"panic: argument\n")
run("panic-output",status=4,stdout=b"before",stderr="firstpanic: 日本\0last\n".encode())
run("error-data",status=64)
for data in [b"",b"abc","日本😀\0\r\n\ufeff".encode(),("a"*4095+"😀"+"日"*6000).encode()]:
 run("stdin",data=data,stdout=data)
for data in [b"\xff",b"\xc0\x80",b"\xed\xa0\x80",b"\xf4\x90\x80\x80",b"a"*4095+b"\xe3\x81",b"\xe3\x81\x00"]:
 run("stdin",data=data,status=97)
path=out/"data.txt";data="BOM\ufeff\nNUL\0😀".encode();path.write_bytes(data);run("read",[path],stdout=data)
link=out/"link";link.symlink_to(path);run("read",[link],stdout=data)
run("read",[""],status=64);run("read",[out/"missing"],status=82);run("read",[out],status=84)
run("write",[path]);assert path.read_bytes()=="new 日本😀\0\r\n".encode()
run("write",[""],status=64);run("write",[out],status=84)
path.write_bytes("日本😀x".encode());run("repeat",[path])
path.write_bytes(b"\xff");run("read",[path],status=97)
print("IO_CASES_OK",flush=True)
