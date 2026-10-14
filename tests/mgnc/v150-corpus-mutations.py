#!/usr/bin/env python3
"""Whole-corpus single-violation mutations, with original-path diagnostics."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--fixtures",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
records=[]
with tempfile.TemporaryDirectory(prefix="v150-corpus-mutations-") as temp:
 root=Path(temp)
 for label in ["C0","C1"]:shutil.copytree(a.fixtures/label,root/label)
 def run(label,name,path,text,phase,token=None):
  source=root/label/"src"/path;original=source.read_bytes();source.write_text(text)
  start=text.encode().index(token.encode()) if token else None
  try:
   result=subprocess.run([a.compiler,"check",root/label/"mognitio.toml"],capture_output=True,timeout=600)
   good=result.returncode==1 and not result.stdout and ("mgnc: "+phase+": src/"+path+":").encode() in result.stderr
   if token:good=good and f"[{start},{start+len(token.encode())})".encode() in result.stderr
   records.append({"corpus":label,"case":name,"path":path,"mutation_sha256":hashlib.sha256(text.encode()).hexdigest(),"exit":result.returncode,"stderr":result.stderr.decode(),"primary":None if token is None else [start,start+len(token.encode())],"passed":bool(good)})
   a.evidence.write_text(json.dumps({"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":records},indent=2)+"\n")
   print(name,bool(good),flush=True)
  finally:source.write_bytes(original)
 main=(root/"C0/src/mgnc.mgn").read_text()
 run("C0","C150-F01-type","mgnc.mgn",main+"\nlet v150Wrong:Int=true;\n","type","true")
 namespace,remaining=main.split("\n",1)
 run("C0","C150-F01-width","mgnc.mgn",namespace+"\nuse Std\\Numeric\\{Bits};\n"+remaining+"\nalias V150Width=Bits<0>;\n","type","0")
 run("C0","C150-F01-import","mgnc.mgn",main.replace("{run}","{v150MissingRun}",1),"semantic","v150MissingRun")
 width=(root/"C0/src/Width/width.mgn").read_text()
 assert len(width.encode())>500000
 run("C0","C150-F01-after-large","Width/width.mgn",width+"\nlet v150Missing:Int=v150MissingAfterLarge;\n","semantic","v150MissingAfterLarge")
 project=(root/"C1/src/Project/load.mgn").read_text()
 run("C1","C150-G11-unknown-API","Project/load.mgn",project.replace(",inspectPath,",",v150MissingAPI,",1),"semantic","v150MissingAPI")
 run("C1","SC150-C06-signature","Project/load.mgn",project.replace("inspectPath(path)","inspectPath(false)",1),"type","false")
 run("C1","SC150-C06-identity","Project/load.mgn",project.replace("seen==current->info->identity","seen<current->info->identity",1),"type")
assert all(r["passed"] for r in records),[r for r in records if not r["passed"]]
print("V150_CORPUS_MUTATIONS_OK checks="+str(len(records)))
