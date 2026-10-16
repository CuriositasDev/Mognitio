import subprocess,sys,os,resource
from pathlib import Path
root=Path(sys.argv[1]).resolve()
fault=Path(__file__).with_name("syscall-fault.py")
data=root/"fault-data";data.write_bytes(b"abcd")
cases=[
 ("read",2,1,2,False,82),("read",2,1,13,False,83),("read",262,1,5,False,87),
 ("read",5,1,5,False,87),("read",0,1,5,False,103),
 ("read",0,1,4,False,0),("read",3,1,5,True,119),
 ("read",3,1,2,True,114),("read",3,1,4,True,119),
 ("read",11,1,5,True,103),("read",11,2,5,True,119),("write",77,1,5,False,87),
 ("write",1,1,5,False,103),("write",1,1,4,False,0),
 ("write",3,1,28,True,118),("streams",1,1,32,False,0),
]
for index,(name,call,ordinal,error,after,status) in enumerate(cases):
 args=[sys.executable,str(fault),"--syscall",str(call),"--ordinal",str(ordinal),"--errno",str(error)]
 if after:args+=["--after"]
 args+=["--",str(root/name)]
 if name in ("read","write"):args+=[str(data)]
 data.write_bytes(b"abcd")
 result=subprocess.run(args,capture_output=True,timeout=30)
 assert result.returncode==status,(index,args,result.returncode,result.stdout,result.stderr)
 print(index,name,call,error,"PASS",status,flush=True)
# Broken pipes stay ordinary errors and borrowed streams survive repeated calls.
readfd,writefd=os.pipe();os.close(readfd)
result=subprocess.run([root/"streams"],stdout=writefd,stderr=subprocess.PIPE,timeout=30);os.close(writefd)
assert result.returncode==0 and result.stderr==b"err",result
# File size limits produce an error instead of SIGXFSZ.
limited=root/"limited"
def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(4,4))
result=subprocess.run([root/"write",limited],capture_output=True,preexec_fn=limit,timeout=30)
assert result.returncode==103 and limited.read_bytes()==b"new ",(result.returncode,result.stderr,limited.read_bytes())
print("IO_SYSCALL_FAULTS_OK",flush=True)

ownership=Path(__file__).with_name("v160-native-ownership.py")
for mode,secondary,reuse in [
 ("first-buffer","",False),("grow-buffer","",False),("site3","",False),("site8","",False),
 ("first-buffer","close",False),("grow-buffer","munmap",False),("site3","munmap",False),("site3","",True)]:
 data.write_bytes(b"abcd")
 report=root/("ownership-"+mode+"-"+(secondary or "none")+("-reuse" if reuse else "")+".json")
 args=[sys.executable,ownership,"--mode",mode,"--report",report]
 if secondary:args+=["--secondary",secondary]
 if reuse:args+=["--reuse"]
 args+=[root/"read",data]
 result=subprocess.run(args,capture_output=True,timeout=30)
 assert (result.returncode,result.stdout,result.stderr)==(0,b"",b"runtime error: allocation failure\n"),(mode,secondary,reuse,result.returncode,result.stdout,result.stderr)
 print("OWNERSHIP",mode,secondary,reuse,"PASS",flush=True)
print("V160_IO_FAULTS_OK syscall=18 ownership=8",flush=True)
