#!/usr/bin/env python3
"""Freeze independent scale axes and their expected observations."""
import argparse,hashlib,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
 rows=[]
 def save(name,files,status=0,stdout=b"",negative=False,axis="",size=0):
  folder=a.output/name;folder.mkdir()
  files={"mognitio.toml":'[project]\nname="app"\nroot_namespace="App"\n',**files}
  inventory=[]
  for path,text in sorted(files.items()):
   target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);data=text.encode();target.write_bytes(data)
   inventory.append({"path":path,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
  rows.append({"name":name,"axis":axis,"size":size,"negative":negative,"build_status":1 if negative else 0,"run_status":status,"stdout_sha256":hashlib.sha256(stdout).hexdigest(),"stdout_bytes":len(stdout),"stderr_hex":"","inventory":inventory})
 def program(body,decl=""):return "namespace App;\n"+decl+"\nlet main:Function(List<String>):Int=function(args:List<String>):Int{discard args;"+body+"};\n"
 for n in (8,32,128):
  files={}
  for index in range(n-1):
   deps=[]
   if index>0:deps.append(index-1)
   if index>1 and index%3==0:deps.append(index-2)
   imports="".join("use App\\M"+str(d)+"\\{v"+str(d)+"};" for d in deps)
   expr="0" if not deps else "v"+str(deps[0])+"+1"
   files[f"src/M{index}/value.mgn"]=f"namespace App\\M{index};{imports}public let v{index}:Int={expr};\n"
  files["src/app.mgn"]=program("v"+str(n-2)+"%251",f"use App\\M{n-2}\\{{v{n-2}}};")
  save(f"modules-{n}",files,(n-2)%251,axis="modules",size=n)
  bad=dict(files);bad[f"src/M{n-2}/value.mgn"]=bad[f"src/M{n-2}/value.mgn"].replace(f":Int=",":Int=true&&",1)
  save(f"modules-{n}-late-error",bad,negative=True,axis="modules",size=n)
 for n in (16,64,256):
  decl="type Tag<N:Int,T>=product{value:T;};template make<N:Int,T>=function(value:T):Function():Tag<N,T>{function():Tag<N,T>{Tag<N,T>{value:value}}};"
  body="var total:Int=0;"
  for index in range(n):body+=f"let fn{index}:Function():Tag<{index},Int>=make<{index},Int>({index});total=total+fn{index}()->value;"
  body+="total%251";source=program(body,decl)
  save(f"specializations-{n}",{"src/app.mgn":source},sum(range(n))%251,axis="specializations",size=n)
  bad=source.replace("namespace App;","namespace App;use Std\\Numeric\\{Bits};template bad<N:Int>=function():Bits<N>{Bits<N>{0}};",1)
  bad=bad.replace("total%251","discard bad<0>();total%251")
  save(f"specializations-{n}-late-width",{"src/app.mgn":bad},negative=True,axis="specializations",size=n)
  decl="".join(f"let f{i}:Function(Int):Function():Int=function(value:Int):Function():Int{{function():Int{{loop{{break value+{i};}}}}}};" for i in range(n))
  body="var total:Int=0;"+"".join(f"let g{i}:Function():Int=f{i}(1);total=total+g{i}();" for i in range(n))+"total%251"
  source=program(body,decl);save(f"closures-{n}",{"src/app.mgn":source},sum(range(1,n+1))%251,axis="closures",size=n)
  bad=source.replace("namespace App;","namespace App;use Std\\Io\\{joinPath};",1).replace("total%251",'discard joinPath("a","b");total%251')
  save(f"closures-{n}-late-unsupported",{"src/app.mgn":bad},negative=True,axis="closures",size=n)
 for size in (4096,16384,65536):
  text="x"*(size-10)+"日本😀";assert len(text.encode())==size
  source=program('discard writeStdout(text);0',r'use Std\Io\{writeStdout};let text:String="'+text+'";')
  save(f"text-{size}",{"src/app.mgn":source},stdout=text.encode(),axis="text-bytes",size=size)
  bad=source.replace('let main:', 'let invalid:Int=true;\nlet main:')
  save(f"text-{size}-late-error",{"src/app.mgn":bad},negative=True,axis="text-bytes",size=size)
  count=(size-1)//2;values=[i%10 for i in range(count)];payload=",".join(map(str,values));assert len(payload)<=size
  source=program("let values:List<Int>=List<Int>["+payload+"];var total:Int=0;loop over(values as item:Int){total=(total+item)%251;};total")
  save(f"list-{size}",{"src/app.mgn":source},sum(values)%251,axis="list-source-bytes",size=size)
  bad=source.replace("};\n","};\nlet invalid:Int=true;\n")
  save(f"list-{size}-late-error",{"src/app.mgn":bad},negative=True,axis="list-source-bytes",size=size)

 # Combine the independent dimensions without substituting for their cells.
 n=32;files={}
 for index in range(n-1):
  imports="" if index==0 else f"use App\\M{index-1}\\{{v{index-1}}};"
  expr="0" if index==0 else f"v{index-1}+1"
  files[f"src/M{index}/value.mgn"]=f"namespace App\\M{index};{imports}public let v{index}:Int={expr};\n"
 text="x"*(16384-10)+"日本😀"
 decl='use Std\\Io\\{writeStdout};use App\\M30\\{v30};let text:String="'+text+'";'
 decl+="type Tag<N:Int,T>=product{value:T;};template make<N:Int,T>=function(value:T):Function():Tag<N,T>{function():Tag<N,T>{Tag<N,T>{value:value}}};"
 decl+="".join(f"let f{i}:Function(Int):Function():Int=function(value:Int):Function():Int{{function():Int{{loop{{break value+{i};}}}}}};" for i in range(64))
 body="var total:Int=v30;"
 for i in range(64):body+=f"let a{i}:Function():Tag<{i},Int>=make<{i},Int>({i});let b{i}:Function():Int=f{i}(1);total=total+a{i}()->value+b{i}();"
 body+='discard writeStdout(text);total%251'
 files["src/app.mgn"]=program(body,decl)
 save("combined-32-64-64-16384",files,(30+sum(range(64))+sum(range(1,65)))%251,stdout=text.encode(),axis="combined")
 parse=r'''let number:Function(List<String>):Int=function(args:List<String>):Int{let text:String=branch on args->at(0){Result<String,IndexError>::Ok(value:String)=>value,Result<String,IndexError>::Err(error:IndexError)=>panic{"argument"}};var n:Int=0;loop over(text->scalars() as scalar:String){let digit:Int=branch when{scalar=="0"=>0,scalar=="1"=>1,scalar=="2"=>2,scalar=="3"=>3,scalar=="4"=>4,scalar=="5"=>5,scalar=="6"=>6,scalar=="7"=>7,scalar=="8"=>8,scalar=="9"=>9,else=>panic{"digit"}};n=n*10+digit;};n};'''
 for retaining in (False,True):
  body="let limit:Int=number(args);var kept:List<Function():String>=List<Function():String>[];var n:Int=0;loop while(n<limit){let text:String=\"kept\"+\" value\";let fn:Function():String=function():String{text};"
  body+=("kept=kept->append(fn);" if retaining else "kept=List<Function():String>[fn];")
  body+='n=n+1;};loop over(kept as fn:Function():String){branch when{fn()!="kept value"=>{return 1;},else=>unit};};0'
  source=program(body,parse).replace("discard args;","")
  save("lifetime-"+("retained" if retaining else "bounded"),{"src/app.mgn":source},axis="lifetime")
  rows[-1]["arguments"]=[["10000"],["100000"],["1000000"]]

 decl=r'use Std\Io\{readTextFile,IoError,IoErrorKind};'+parse
 body=r'''let limit:Int=number(args);let path:String=branch on args->at(1){Result<String,IndexError>::Ok(value:String)=>value,Result<String,IndexError>::Err(error:IndexError)=>panic{"path"}};let mode:String=branch on args->at(2){Result<String,IndexError>::Ok(value:String)=>value,Result<String,IndexError>::Err(error:IndexError)=>panic{"mode"}};var n:Int=0;loop while(n<limit){branch on readTextFile(path){Result<String,IoError>::Ok(text:String)=>{branch when{mode!="success"||text!="四😀\u{0}"=>{return 1;},else=>unit};},Result<String,IoError>::Err(error:IoError)=>{let matched:Bool=branch on error->kind{IoErrorKind::InvalidEncoding=>mode=="decode",IoErrorKind::Other=>mode=="read",IoErrorKind::InvalidPath=>false,IoErrorKind::NotFound=>false,IoErrorKind::PermissionDenied=>false,IoErrorKind::UnsupportedTarget=>false,IoErrorKind::BrokenPipe=>false,IoErrorKind::ResourceExhausted=>false};branch when{!matched=>{return 2;},else=>unit};}};n=n+1;};0'''
 save("io-resource",{"src/app.mgn":program(body,decl).replace("discard args;","")},axis="io-resource")
 rows[-1]["arguments"]=[[str(n),mode] for n in (100,1000,10000) for mode in ("success","decode","read")]
 (a.output/"manifest.json").write_text(json.dumps(rows,indent=2)+"\n")
 print("SCALE_FIXTURES",len(rows),hashlib.sha256((a.output/"manifest.json").read_bytes()).hexdigest())
if __name__=="__main__":main()
