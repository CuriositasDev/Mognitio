#!/usr/bin/env python3
"""Create deterministic v1.5 scale cells and single-violation siblings."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--output",required=True,type=Path);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False);cells=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def entry(body="0"):return "let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};\n"
def publish(name,files,axis,size,phase=None,negative=True,detail=None):
 def save(identifier,sources,expected):
  root=a.output/identifier;(root/"src").mkdir(parents=True);manifest=b'[project]\nname="app"\nroot_namespace="App"\n';(root/"mognitio.toml").write_bytes(manifest);inventory=[]
  for path,text in sorted(sources.items()):
   payload=text.encode();dest=root/"src"/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(payload)
   inventory.append({"path":"src/"+path,"bytes":len(payload),"sha256":sha(payload)})
  cells.append({"name":identifier,"axis":axis,"size":size,"detail":detail,"source_count":len(sources),"source_bytes":sum(x["bytes"] for x in inventory),"inventory":inventory,"manifest_sha256":sha(manifest),"expected_exit":1 if expected else 0,"phase":expected})
 save(name,files,phase)
 if negative and phase is None:
  changed=dict(files);last=sorted(changed)[-1];changed[last]+="\nlet invalidTail:Int=false;\n";save(name+"-negative",changed,"type")
for size in [1,8,32,64]:
 for variant in ["chain","diamond","unreached"]:
  files={}
  for i in range(size):
   ns="App" if i==0 else "App\\M"+str(i);path="app.mgn" if i==0 else f"M{i}/module.mgn"
   targets=[] if variant=="unreached" else list(range(i+1,min(size,i+(3 if variant=="diamond" else 2))))
   uses="".join("use App\\M"+str(j)+"\\{f"+str(j)+"};\n" for j in targets)
   call="+".join("f"+str(j)+"()" for j in targets) or "0"
   body=entry(call) if i==0 else f"public let f{i}:Function():Int=function():Int{{{call}}};\n"
   files[path]="namespace "+ns+";\n"+uses+body
  assert len(files)==size
  publish(f"modules-{variant}-{size}",files,"modules",size,detail={"variant":variant,"degenerate":size==1})
for size in [10,100,1000]:
 for variant in ["public","local"]:
  names="".join(("public " if variant=="public" else "")+f"let value{i}:Int={i};\n" for i in range(size))
  queries="".join(f"discard value{i};\n" for i in range(size))+"0"
  source="namespace App;\n"+(names+entry(queries) if variant=="public" else entry(names+queries))
  assert len(re.findall(r"\blet value\d+:Int=",source))==size
  publish(f"names-{variant}-{size}",{"app.mgn":source},"names",size,detail={"variant":variant,"declarations":size,"queries":size})
for depth in [1,8,32,128]:
 shape="List<"*depth+"Int"+">"*depth
 source="namespace App;\n"+f"let identity:Function({shape}):{shape}=function(value:{shape}):{shape}{{value}};\n"+entry()
 assert shape.count("List<")==depth
 publish(f"depth-{depth}",{"app.mgn":source},"depth",depth,detail={"signature_type_depth":depth})
for size in [1,8,32,128]:
 for variant in ["type","template"]:
  for cycle in [False,True]:
   if variant=="type":
    declarations="alias A0="+(f"A{size-1}" if cycle else "Int")+";\n"
    declarations+="".join(f"alias A{i}=A{i-1};\n" for i in range(1,size))
    suffix=entry("let value:A"+str(size-1)+"=0;value")
   else:
    declarations="template f0<T>=function(value:T):T{"+(f"f{size-1}<T>(value)" if cycle else "value")+"};\n"
    declarations+="".join(f"template f{i}<T>=function(value:T):T{{f{i-1}<T>(value)}};\n" for i in range(1,size))
    suffix=entry(f"f{size-1}<Int>(0)")
   assert len(re.findall(r"^(?:alias|template) ",declarations,re.M))==size
   publish(f"dependency-{variant}-{size}"+("-cycle" if cycle else ""),{"app.mgn":"namespace App;\n"+declarations+suffix},"dependency",size,phase="semantic" if cycle else None,detail={"variant":variant,"cycle":cycle,"vertices":size})
for size in [1,8,32,64]:
 for variant in ["width","value"]:
  declaration=("use Std\\Numeric\\{Bits};\ntemplate make<N:Int>=function():Bits<N>{Bits<N>{0}};\n" if variant=="width" else "type Tag<N:Int>=product{};\ntemplate make<N:Int>=function():Tag<N>{Tag<N>{}};\n")
  body="".join(f"discard make<{i+1}>();\n" for i in range(size))+"0"
  source="namespace App;\n"+declaration+entry(body)
  assert len(set(re.findall(r"make<(\d+)>",source)))==size
  publish(f"constraints-{variant}-{size}",{"app.mgn":source},"constraints",size,detail={"variant":variant,"distinct_arguments":size})
for size in [1024,65536,1048576]:
 for variant in ["string","comment"]:
  for negative in [False,True]:
   bad="false" if negative else "0"
   base=("namespace App;\nlet padding:String=\"PADDING\";\n" if variant=="string" else "namespace App;\n//PADDING\n")+f"let tail:Int={bad};\n"+entry()
   count=size-len(base.replace("PADDING","").encode());source=base.replace("PADDING","x"*count)
   assert len(source.encode())==size
   publish(f"bytes-{variant}-{size}"+("-negative" if negative else ""),{"app.mgn":source},"bytes",size,phase="type" if negative else None,negative=False,detail={"variant":variant,"exact_source_bytes":size})
for variant,decoration in [("ascii","//ascii\n"),("scalar2","//é\n"),("scalar3","//日\n"),("scalar4","//😀\n"),("escape",'let text:String="\\u{1f600}";\n'),("crlf","//é日😀\r\n\t"),("before-large",""),("after-large",'let text:String="'+"x"*65536+'";\n')]:
 for negative in [False,True]:
  text="namespace App;\n"+decoration+entry("missingTail" if negative else "0")
  if variant=="before-large":text+='let text:String="'+"x"*65536+'";\n'
  offset=text.encode().find(b"missingTail")
  publish(f"position-{variant}"+("-negative" if negative else ""),{"app.mgn":text},"position",0,phase="semantic" if negative else None,negative=False,detail={"variant":variant,"primary_start":offset if negative else None,"primary_end":offset+11 if negative else None})
source="namespace App;\n"+entry()
publish("position-eof",{"app.mgn":source},"position",0,negative=False,detail={"variant":"eof"})
source=source[:-3]
publish("position-eof-negative",{"app.mgn":source},"position",0,phase="parse",negative=False,detail={"variant":"eof","primary_start":len(source.encode()),"primary_end":len(source.encode())})
files={}
for i in range(64):
 names=range(i*16,min((i+1)*16,1000))
 ns="App" if i==0 else f"App\\M{i}";path="app.mgn" if i==0 else f"M{i}/module.mgn"
 files[path]="namespace "+ns+";\n"+"".join(f"public let value{j}:Int={j};\n" for j in names)
deep="List<"*128+"Int"+">"*128
files["app.mgn"]+=f"let identity:Function({deep}):{deep}=function(value:{deep}):{deep}{{value}};\n"+entry()
assert len(files)==64 and sum(len(re.findall(r"\blet value\d+:Int=",v)) for v in files.values())==1000
publish("combined",files,"combined",1000,detail={"modules":64,"declarations":1000,"signature_type_depth":128})
repository=Path(__file__).resolve().parents[2]
for corpus,revision in [("C0","4908a1a91be61d64695b9e048b833637aee0aefc"),("C1",subprocess.check_output(["git","rev-parse","HEAD"],cwd=repository,text=True).strip())]:
 paths=subprocess.check_output(["git","ls-tree","-r","--name-only",revision,"compiler/mgnc/src"],cwd=repository,text=True).splitlines()
 files={str(Path(path).relative_to("compiler/mgnc/src")):subprocess.check_output(["git","show",revision+":"+path],cwd=repository).decode() for path in paths if path.endswith(".mgn")}
 publish(corpus,files,"corpus",len(files),negative=False,detail={"revision":revision})
 row=cells[-1]
 original_manifest=subprocess.check_output(["git","show",revision+":compiler/mgnc/mognitio.toml"],cwd=repository)
 (a.output/corpus/"mognitio.toml").write_bytes(original_manifest);row["manifest_sha256"]=sha(original_manifest)
 inventory_hash=sha("".join(item["sha256"]+"  compiler/mgnc/"+item["path"]+"\n" for item in row["inventory"]).encode())
 row["inventory_sha256"]=inventory_hash
 if corpus=="C0":
  assert len(files)==57 and row["source_bytes"]==823559
  assert inventory_hash=="9f0a7f789d99d91da9257f7a7d816d437961eadf540c3f78c1c0adfa5460e177"
manifest={"schema":1,"generator":"python3 tests/mgnc/v150-scale-fixtures.py --output FIXTURES","seed":150,"cells":cells}
(a.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
print("V150_SCALE_FIXTURES_OK cells="+str(len(cells)))
