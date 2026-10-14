#!/usr/bin/env python3
"""Cross-boundary fixtures for classification, control and project definitions."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
def program(body="0",prefix=""):return "namespace App;"+prefix+"let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};"
cases=[
 ("C150-A02-type",program("true"),"type"),
 ("C150-A02-name",program("missing"),"semantic"),
 ("C150-A03-product",program("let x:Box=Box{value:1};x->value","type Box=product{value:Int;};"),None),
 ("C150-B02-parameter",program("let args:Int=0;args"),"semantic"),
 ("C150-B05-parameter",program("args=List<String>[];0"),"semantic"),
 ("C150-B06-standard",program("0",'use Std\\Io\\{readStdin};template bad<T>=function():Unit{discard readStdin();};'),"semantic"),
 ("C150-B09-simple",program("let a:Int=1;let b:Int=2;branch when{a<b=>0,else=>1}"),None),
 ("C150-B10-case",program("let VALUE:Alias=Box{VALUE:1};VALUE->VALUE","alias Alias=Box;type Box=product{VALUE:Int;};"),None),
 ("C150-C06-other-sum",program("let x:A=A::V;branch on x{B::V=>0}","type A=sum{V;};type B=sum{V;};"),"type"),
 ("C150-C06-binder",program("let x:A=A::V(1);branch on x{A::V(v:Bool)=>0}","type A=sum{V(Int);};"),"type"),
 ("C150-C07-arity",program("f()","let f:Function(Int):Int=function(x:Int):Int{x};"),"type"),
 ("C150-C07-return",program("return true;"),"type"),
 ("C150-C11-outer",program("loop {loop while({break 0;}){};}"),None),
 ("C150-C13-continue",program("loop {let f:Function():Unit=function():Unit{continue;};discard f;break 0;}"),"semantic"),
 ("C150-D02-below",program("0","type Tag<N:Int>=product{};alias Bad=Tag<-9223372036854775809>;"),"type"),
 ("C150-D02-above",program("0","type Tag<N:Int>=product{};alias Bad=Tag<9223372036854775808>;"),"type"),
 ("C150-D04-runtime",program("let n:Int=8;discard make<n>();0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{0}};"),"type"),
 ("C150-D05-arithmetic",program("0","template bad<T>=function(x:T):T{x+x};"),"type"),
 ("C150-D06-uninstantiated",program("0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{255}};"),None),
 ("C150-D09-owner",program("second<Int>(first<Int>(1))","template first<T>=function(x:T):T{x};template second<T>=function(x:T):T{x};"),None),
 ("C150-D14-64",program("discard make<64>();0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{18446744073709551615}};"),None),
 ("C150-D14-63",program("discard make<63>();0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{18446744073709551615}};"),"type"),
 ("C150-E13-value","namespace App;alias Args=List<String>;alias Code=Int;let f:Function(Args):Code=function(args:Args):Code{0};let main:Function(Args):Code=f;",None),
 ("SC150-A03-storage",program("0","use Std\\Io\\{FileIdentity};type Hold=product{id:FileIdentity;};type Choice=sum{Has(FileIdentity);};let probe:Function(FileIdentity):Bool=function(id:FileIdentity):Bool{let b:Hold=Hold{id:id};let xs:List<FileIdentity>=List<FileIdentity>[id];let s:Choice=Choice::Has(id);let r:Result<FileIdentity,String>=Result<FileIdentity,String>::Ok(id);let f:Function():Bool=function():Bool{b->id==id};discard xs;discard s;discard r;f()};"),None),
 ("SC150-A08-call",program("discard FileIdentity();0","use Std\\Io\\{FileIdentity};"),"semantic"),
 ("SC150-A08-convert",program("discard 1->convertTo<FileIdentity>();0","use Std\\Io\\{FileIdentity};"),"type"),
]
records=[]
def run(name,command,expected,phase=None):
 r=subprocess.run([a.compiler,*map(str,command)],capture_output=True,timeout=120)
 good=r.returncode==expected and not r.stdout and (not r.stderr if expected==0 else bool(r.stderr) and (phase is None or ("mgnc: "+phase+":").encode() in r.stderr))
 row={"case":name,"command":str(command[0]),"exit":r.returncode,"stderr":r.stderr.decode(),"passed":good};records.append(row)
 return r
with tempfile.TemporaryDirectory(prefix="v150-boundaries-") as temp:
 root=Path(temp);source=root/"case.mgn"
 for name,text,phase in cases:
  source.write_text(text);run(name,["check",source],0 if phase is None else 1,phase)
  if name.startswith("C150-A02") or name=="C150-A03-product":run(name+"-parse",["parse",source],0)
 for i,argv in enumerate([["check"],["check",""],["check","src"],["check",source,"-o","out"],["check",source,"extra"],["check","other.toml"]]):
  run("C150-A04-"+str(i),argv,2,"cli")
 source.write_text(program());(root/"mognitio.toml").write_text("invalid");(root/"neighbor.mgn").write_text("invalid")
 run("C150-A07",["check",source],0)
 projects=[
  ("C150-E10-definition-site",{
   "app.mgn":program("let x:Actual<Int>=make<Int>(1);x->value","use App\\Lib\\{Box as Actual,make};type Box<T>=product{different:Bool;};"),
   "Lib/lib.mgn":"namespace App\\Lib;public type Box<T>=product{value:T;};public template make<T>=function(value:T):Box<T>{Box<T>{value:value}};"},None),
  ("C150-D08-import-obligation",{
   "app.mgn":program("discard go<7>();0","use App\\Lib\\{forward as go};"),
   "Lib/lib.mgn":'namespace App\\Lib;use Std\\Numeric\\{Bits};alias B<N:Int>=Bits<N>;template make<N:Int>=function():B<N>{B<N>{255}};public template forward<N:Int>=function():Bits<N>{branch when{true=>Bits<N>{0},else=>make<N>()}};'},"type"),
  ("C150-E09-diamond",{
   "app.mgn":program("left()+right()","use App\\Left\\{left};use App\\Right\\{right};"),
   "Left/a.mgn":"namespace App\\Left;use App\\Base\\{base};public let left:Function():Int=function():Int{base()};",
   "Right/a.mgn":"namespace App\\Right;use App\\Base\\{base};public let right:Function():Int=function():Int{base()};",
   "Base/a.mgn":"namespace App\\Base;public let base:Function():Int=function():Int{1};"},None)]
 for name,files,phase in projects:
  project=root/name;(project/"src").mkdir(parents=True);manifest=project/"mognitio.toml";manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
  for path,text in files.items():
   dest=project/"src"/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
  run(name,["check",manifest],0 if phase is None else 1,phase)
 # The diagnostic's own writes must fail explicitly.
 source.write_text(program("missing"))
 import os
 for closed in [True,False]:
  reader=writer=None
  if closed:kw={"preexec_fn":lambda:os.close(2),"stderr":subprocess.PIPE}
  else:reader,writer=os.pipe();os.close(reader);kw={"stderr":writer}
  try:r=subprocess.run([a.compiler,"check",source],stdout=subprocess.PIPE,timeout=120,**kw)
  finally:
   if writer is not None:os.close(writer)
  records.append({"case":"C150-F05-"+str(closed),"exit":r.returncode,"passed":r.returncode==2 and not r.stdout})
result={"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":records,"passed":all(r["passed"] for r in records)}
a.evidence.write_text(json.dumps(result,indent=2)+"\n")
assert result["passed"],[r for r in records if not r["passed"]]
print("V150_BOUNDARIES_OK checks="+str(len(records)))
