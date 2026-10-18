#!/usr/bin/env python3
"""v1.6 expectations for unchanged v1.5 conformance fixtures."""
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--evidence",type=Path);p.add_argument("--command",choices=("check","lower"),default="check");args=p.parse_args()
compiler=args.compiler.resolve();records=[];failures=[]
def program(body="0",prefix=""):return "namespace App;"+prefix+"let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};"
cases=[]
def add(case,body="0",prefix="",phase=None,native=False,token=None):cases.append((case,program(body,prefix),phase,native,token))
add("C150-B03","{let x:Int=1;discard x;};{let x:Int=2;discard x;};0",native=True)
add("C150-B04-forward","let p:P=P{value:1};p->value","alias P=Later;type Later=product{value:Int;};")
add("C150-B07","let f:Function():Int=keep<Int>(2);f()","template keep<T>=function(value:T):Function():T{function():T{value}};")
add("C150-B09-chain","let a:Int=1;let b:Int=2;let c:Int=3;a<b>(c)",phase="parse")
add("C150-C01-nominal","let a:A=B{};0","type A=product{};type B=product{};",phase="type")
add("C150-C01-alias","let a:A=B{};discard a;0","type A=product{};alias B=A;")
add("C150-C02-empty","discard Empty{};0","type Empty=product{};")
add("C150-C02-empty-sum","0","type Empty=sum{};",phase="semantic")
add("C150-C03-unknown","discard P{other:1};0","type P=product{value:Int;};",phase="semantic")
add("C150-C04","let p:P=P{b:2,a:function():Int{3}};p->a()+p->b","type P=product{a:Function():Int;b:Int;};")
add("C150-C05-unknown","discard S::Missing;0","type S=sum{A;};",phase="semantic")
add("C150-C05-missing","discard S::A;0","type S=sum{A(Int);};",phase="type")
add("C150-C05-extra","discard S::A(1);0","type S=sum{A;};",phase="type")
add("C150-C06-ignored-payload","let s:S=S::A(1);branch on s{S::A=>0}","type S=sum{A(Int);};")
add("C150-C06-alias-duplicate","let s:S=S::A;branch on s{S::A=>0,A::A=>1}","type S=sum{A;};alias A=S;",phase="semantic")
for shape in ["List<A>","Result<Int,A>","Function():A"]:
 add("C150-C08-"+shape,"0","alias A="+shape+";",phase="semantic")
add("C150-C10-ambiguous",'panic{"a"}+panic{"b"}',phase="type")
add("C150-C11-while",'loop while({break;}){};0',phase="semantic")
add("C150-C11-over",'loop over({continue;} as x:Int){};0',phase="semantic")
add("C150-C12-reference","loop over(x as x:Int){};0",phase="semantic")
add("C150-C12-reserved","loop over({let x:List<Int>=List<Int>[];x} as x:Int){};0",phase="semantic")
add("C150-C14-try","try Result<Int,String>::Ok(0)",phase="type")
add("C150-C14-panic","panic{1}",phase="type")
add("C150-C16-overflow","9223372036854775807+1",native=True)
add("C150-C16-divzero","1/0",native=True)
add("C150-D01-kind","discard id<1>(0);0","template id<T>=function(value:T):T{value};",phase="type")
add("C150-D01-bare","discard id;0","template id<T>=function(value:T):T{value};",phase="semantic")
add("C150-D01-arity","discard id<Int,Int>(0);0","template id<T>=function(value:T):T{value};",phase="type")
for a,b in [("-1","(-1)"),("-0","0"),("-9223372036854775808","(-9223372036854775808)")]:
 add("C150-D02-"+a,"let x:Tag<"+a+">=Tag<"+b+">{};discard x;0","type Tag<N:Int>=product{};")
for width in [1,7,8,63,64,0,65,-1]:
 add("C150-D03-"+str(width),"let x:Bits<"+str(width)+">=Bits<"+str(width)+">{0};discard x;0","use Std\\Numeric\\{Bits};",phase=None if 1<=width<=64 else "type")
for arg in ["1+7","-N"]:
 add("C150-D04-"+arg,"0","use Std\\Numeric\\{Bits};template bad<N:Int>=function():Bits<"+arg+">{panic{\"x\"}};",phase="parse")
prefix="use Std\\Numeric\\{Bits};alias Pattern<W:Int>=Bits<W>;template make<N:Int>=function():Pattern<N>{Pattern<N>{255}};template forward<N:Int>=function():Pattern<N>{make<N>()};"
for width in [7,8]:
 add("C150-D07-"+str(width),"let x:Bits<"+str(width)+">=forward<"+str(width)+">();discard x;0",prefix,phase="type" if width==7 else None,token=str(width)+">()" if width==7 else None)
add("C150-D09-shadow","0","type T=product{};template bad<T>=function(value:T):T{value};",phase="semantic")
add("C150-D10-changing","0","template bad<T>=function(value:T):Unit{bad<List<T>>(List<T>[value])};",phase="semantic")
add("C150-D11-method","discard 1->convertTo<Bool>();0",phase="type")
add("C150-D11-unknown","discard 1->missing();0",phase="semantic")
add("C150-D12-impossible","0","use Std\\Numeric\\{Bits};template bad<N:Int>=function():Bits<N>{Bits<N>{18446744073709551616}};",phase="type",token="18446744073709551616")
add("C150-D13-alias","0","use Std\\Numeric\\{Bits};alias B<N:Int>=Bits<N>;template bad<N:Int>=function():B<N>{B<N>{18446744073709551616}};",phase="type")
add("C150-D14-declaration","0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{18446744073709551615}};")
add("C150-E11-unknown","0","use Std\\Io\\{unknown};",phase="semantic")
add("C150-E11-implicit",'discard inspectPath("x");0',phase="semantic")
add("C150-E11-wrong",'discard inspectPath(1);0',"use Std\\Io\\{inspectPath};",phase="type")
add("C150-E13-alias","0","alias Args=List<String>;alias Code=Int;")
add("SC150-A01","let f:Function(String):Result<PathInfo,PathInfoError>=inspectPath;let box:Box=Box{f:f};let fs:List<Function(String):Result<PathInfo,PathInfoError>>=List<Function(String):Result<PathInfo,PathInfoError>>[box->f];discard fs;0","use Std\\Io\\{inspectPath,PathInfo,PathInfoError};type Box=product{f:Function(String):Result<PathInfo,PathInfoError>;};")
for op in ["<","+"]:
 add("SC150-A07-"+op,"let f:Function(FileIdentity,FileIdentity):Bool=function(a:FileIdentity,b:FileIdentity):Bool{a"+op+"b};discard f;0","use Std\\Io\\{FileIdentity};",phase="type")
add("SC150-B12-error-construct",'discard PathInfoError{kind:IoErrorKind::NotFound,subject:"x"};0',"use Std\\Io\\{PathInfoError,IoErrorKind};")
add("SC150-B12-error-try",'let f:Function():Result<Unit,IoError>=function():Result<Unit,IoError>{discard try inspectPath("x");Result<Unit,IoError>::Ok(unit)};discard f;0',"use Std\\Io\\{IoError,inspectPath};",phase="type")
# These closed-profile forms are supported by N160. Fixed-width numeric and
# path-inspection cases retain their unsupported build expectations.
MIGRATED={"C150-B04-forward":1,"C150-B07":2,"C150-C01-alias":0,
          "C150-C02-empty":0,"C150-C04":5,"C150-C06-ignored-payload":0,
          "C150-D02--1":0,"C150-D02--0":0,"C150-D02--9223372036854775808":0,
          "C150-E13-alias":0}
cases=[(case,source,phase,True if case in MIGRATED else native,token)
       for case,source,phase,native,token in cases]
assert MIGRATED.keys() <= {row[0] for row in cases}

def run(case,command,path,expected,phase=None):
 before=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
 started=time.monotonic();result=subprocess.run([str(compiler),command,str(path)],capture_output=True,timeout=600)
 passed=result.returncode==expected and not result.stdout and (not result.stderr if expected==0 else (("mgnc: "+phase+":").encode() in result.stderr if phase else bool(result.stderr)))
 if before is not None:passed=passed and before==hashlib.sha256(path.read_bytes()).hexdigest()
 row=dict(case=case,command=command,exit=result.returncode,stderr=result.stderr.decode(errors="replace"),seconds=time.monotonic()-started,passed=passed)
 records.append(row)
 if not passed:failures.append(row)
 return result
with tempfile.TemporaryDirectory(prefix="mgnc-v150-conformance-") as temporary:
 root=Path(temporary);path=root/"case.mgn"
 for case,source,phase,native,token in cases:
  path.write_text(source);result=run(case,args.command,path,0 if phase is None else 1,phase)
  if token and phase and result.returncode==1:
   start=source.index(token);end=start+len(token.split(">")[0])
   if f"[{start},{end})" not in result.stderr.decode():
    row={"case":case+"-primary","stderr":result.stderr.decode(),"expected_span":[start,end],"passed":False};records.append(row);failures.append(row)
  artifact=root/"artifact"
  built=subprocess.run([compiler,"build",path,"-o",artifact],capture_output=True,timeout=60)
  expected=0 if native and phase is None else 1
  wanted=phase or "unsupported"
  valid=built.returncode==expected and not built.stdout and (not built.stderr if expected==0 else ("mgnc: "+wanted+":").encode() in built.stderr)
  row=dict(case=case,command="build",exit=built.returncode,stderr=built.stderr.decode(),passed=valid);records.append(row)
  if not valid:failures.append(row)
  if expected:
   assert not artifact.exists(),case
  elif artifact.exists():
   if case in MIGRATED:
    executed=subprocess.run([artifact],capture_output=True,timeout=60)
    valid=(executed.returncode,executed.stdout,executed.stderr)==(MIGRATED[case],b"",b"")
    row=dict(case=case,command="execute",exit=executed.returncode,passed=valid);records.append(row)
    if not valid:failures.append(row)
   artifact.unlink()
 projects=[
 ("C150-E02-unused-invalid",{"app.mgn":program(),"Other/bad.mgn":"namespace App\\Other;let unused:Int=false;"},"type"),
 ("C150-E05-explicit",{"app.mgn":program("f()","use App\\Lib\\{f};"),"Lib/one.mgn":"namespace App\\Lib;public let f:Function():Int=function():Int{0};"},None),
 ("C150-E05-no-use",{"app.mgn":program("f()"),"Lib/one.mgn":"namespace App\\Lib;public let f:Function():Int=function():Int{0};"},"semantic"),
 ("C150-E06-alias-duplicate",{"app.mgn":program("0","use App\\Lib\\{T as A,T as B};"),"Lib/one.mgn":"namespace App\\Lib;public type T=product{};"},"semantic"),
 ("C150-E07-alias",{"app.mgn":program("let x:A=T{};discard x;0","use App\\Lib\\{T,A};"),"Lib/one.mgn":"namespace App\\Lib;public type T=product{};public alias A=T;"},None),
 ("C150-E08-private",{"app.mgn":program(),"Lib/one.mgn":"namespace App\\Lib;type Hidden=product{};public alias Leak=Hidden;"},"semantic"),
 ("C150-E09-cycle",{"app.mgn":program("0","use App\\A\\{A};"),"A/a.mgn":"namespace App\\A;use App\\B\\{B};public type A=product{};","B/b.mgn":"namespace App\\B;use App\\A\\{A};public type B=product{};"},"semantic"),
 ("C150-B08-import-template",{"app.mgn":program("identity<Int>(1)","use App\\Lib\\{id as identity};"),"Lib/lib.mgn":"namespace App\\Lib;public template id<T>=function(value:T):T{value};"},None),
 ]
 for case,files,phase in projects:
  project=root/case;(project/"src").mkdir(parents=True);manifest=project/"mognitio.toml";manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
  for name,text in files.items():
   source=project/"src"/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_text(text)
  run(case,args.command,manifest,0 if phase is None else 1,phase)
 # Check must not evaluate any user expression.
 output=root/"must-not-exist"
 path.write_text(program("0",f'use Std\\Io\\{{writeTextFile}};let attempted:Result<Unit,IoError>=writeTextFile({json.dumps(str(output))},"bad");'.replace("{writeTextFile}","{writeTextFile,IoError}")))
 run("C150-A06",args.command,path,0);assert not output.exists()
 # Invalid UTF-8 is reported without a fabricated span.
 path.write_bytes(b"\xff");run("C150-F03-utf8",args.command,path,1,"source")
 path.write_bytes(b"\xef\xbb\xbf"+program().encode());run("C150-F03-bom",args.command,path,1,"source")
 for case,raw,phase in [("C150-F03-escape",program('discard "\\q";0'),"lexical"),("C150-F03-eof","namespace App;","semantic")]:
  path.write_text(raw);run(case,args.command,path,1,phase)
 for filename in ["with space.mgn","-entry.mgn"]:
  target=root/filename;target.write_text(program());run("C150-A05-"+filename,args.command,target,0)
 for spelling in ["directory.mgn","mognitio.toml"]:
  target=root/spelling;target.mkdir();run("C150-A09-"+spelling,args.command,target,2,"io")
evidence={"compiler_sha256":hashlib.sha256(compiler.read_bytes()).hexdigest(),"records":records,"failures":len(failures)}
if args.evidence:args.evidence.write_text(json.dumps(evidence,indent=2)+"\n")
assert not failures,json.dumps(failures,indent=2)
print("V160_CONFORMANCE_OK checks="+str(len(records)))
