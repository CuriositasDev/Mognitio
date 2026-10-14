#!/usr/bin/env python3
"""Check complete small programs without evaluating their initializers or bodies."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path);p.add_argument("--compiler",type=Path);p.add_argument("--interpret",action="store_true");args=p.parse_args()
def program(body,prefix=""):return "namespace App;"+prefix+"let main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};"
cases=[
 (program("0"),True),
 (program("let x:Int=1;var y:Int=x+2;y=y+1;y"),True),
 (program("branch when{true=>1,else=>2}"),True),
 (program("var i:Int=0;loop while(i<3){i=i+1;};i"),True),
 (program("loop {break 7;}"),True),
 (program("let xs:List<Int>=List<Int>[1,2];var total:Int=0;loop over(xs as x:Int){total=total+x;};total"),True),
 (program("let p:P=P{value:1};p->value","type P=product{value:Int;};"),True),
 (program("let s:S=S::Value(2);branch on s{S::None=>0,S::Value(v:Int)=>v}","type S=sum{None;Value(Int);};"),True),
 (program("let x:Int=1;let f:Function():Int=function():Int{x};f()"),True),
 (program("let f:Function(Int):Int=function(x:Int):Int{return x;};f(1)"),True),
 (program('let f:Function():Result<Int,String>=function():Result<Int,String>{Result<Int,String>::Ok(try Result<Int,String>::Ok(1))};discard f();0'),True),
 (program('discard readTextFile("/does-not-exist");0',"use Std\\Io\\{readTextFile};"),True),
 (program('1+panic{"stop"}'),True),
 (program('loop over(panic{"stop"} as item:Int){unit;};'),True),
 (program('let f:Function():Int=branch when{true=>function():Int{1},else=>function():Int{2}};f()'),True),
 (program("id<Int>(1)","template id<T>=function(value:T):T{value};"),True),
 (program("let b:Bits<8>=make<8>();discard b;0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{255}};"),True),
 (program('let x:Int=panic{"stop"};0'),False),
 (program('discard unit;0'),False),
 (program('discard panic{"stop"};'),False),
 (program('let x:Int="bad";0'),False),
 (program('let x:Int=1;x=2;0'),False),
 (program('var x:Int=1;let f:Function():Int=function():Int{x=2;x};f()'),False),
 (program('let x:Int={let x:Int=1;x};x'),False),
 (program('let x:Int=x;x'),False),
 (program('let f:Function():Int=function():Int{later};let later:Int=1;f()'),False),
 (program('break;0'),False),
 (program('loop {break;}'),False),
 (program('loop while(true){break 1;};0'),False),
 (program('let x:Int=loop {break 1;};x'),True),
 (program('loop {let f:Function():Unit=function():Unit{break;};discard f;break 0;}'),False),
 (program('branch when{true=>1,else=>"bad"}'),False),
 (program('let s:S=S::A;branch on s{S::A=>0}',"type S=sum{A;B;};"),False),
 (program('let s:S=S::A;branch on s{S::A=>0,S::A=>1}',"type S=sum{A;B;};"),False),
 (program('let s:S=S::A;branch on s{S::A(x:Int)=>0}',"type S=sum{A;};"),False),
 (program('let p:P=P{value:1,value:2};0',"type P=product{value:Int;};"),False),
 (program('let p:P=P{};0',"type P=product{value:Int;};"),False),
 (program('let p:P=P{value:"bad"};0',"type P=product{value:Int;};"),False),
 (program('(panic{"no"})(1)'),False),
 (program('panic{"a"}==panic{"b"}'),False),
 (program('let f:Function(Int,String):Int=function(a:Int,b:String):Int{0};f(panic{"no"},loop {break 1;})'),False),
 (program("let x:Bits<8>=make<7>();0","use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{255}};"),False),
 (program("0","template bad<T>=function(value:T):Unit{discard value;};"),False),
 (program("0","let x:Int=1;template bad<T>=function(value:T):Int{x};"),False),
 (program("0","template a<T>=function(value:T):T{b<T>(value)};template b<T>=function(value:T):T{a<T>(value)};"),False),
 (program("0","type Hidden=product{};public alias Exposed=List<Hidden>;"),False),
 (program("0","type Hidden=product{};public let f:Function():Hidden=function():Hidden{Hidden{}};"),False),
 (program('let x:Int= -9223372036854775808;x'),True),
 (program('let x:Int=9223372036854775808;x'),False),
 (program('let x:Int= -(9223372036854775808);x'),True),
 (program('let x:Bits<64>=Bits<64>{18446744073709551615};discard x;0',"use Std\\Numeric\\{Bits};"),True),
 (program('let x:Bits<64>=Bits<64>{18446744073709551616};discard x;0',"use Std\\Numeric\\{Bits};"),False),
 (program('let x:Int<64,Unsigned>=Int<64,Unsigned>{18446744073709551615};discard x->convertTo<Int>();0',"use Std\\Numeric\\{Unsigned};"),True),
 (program('let x:Bytes=bytesFromInts(List<Int>[256]);0',"use Std\\Binary\\{Bytes,bytesFromInts};"),False),
 (program('discard bytesFromInts(List<Int>[256]);0',"use Std\\Binary\\{bytesFromInts};"),True),
 (program('let x:FileIdentity=FileIdentity{};0',"use Std\\Io\\{FileIdentity};"),False),
 (program('let f:Function(FileIdentity,FileIdentity):Bool=function(a:FileIdentity,b:FileIdentity):Bool{a==b};discard f;0',"use Std\\Io\\{FileIdentity};"),True),
 ("namespace App;let main:Function():Int=function():Int{0};",False),
 ("namespace App;let helper:Function(List<String>):Int=function(args:List<String>):Int{0};",False),
]
if args.compiler:
 with tempfile.TemporaryDirectory(prefix="v150-semantics-cli-") as temp:
  source=Path(temp)/"case.mgn";failures=[]
  for index,(text,expected) in enumerate(cases):
   source.write_text(text)
   result=subprocess.run([str(args.compiler),"check",str(source)],capture_output=True,timeout=60)
   if (result.returncode==0)!=expected or result.stdout or (expected and result.stderr) or result.returncode not in (0,1):
    failures.append((index,result.returncode,result.stderr.decode()))
  assert not failures,failures
 print(json.dumps({"result":"V150_SEMANTICS_OK","cases":len(cases),"compiler":str(args.compiler)},sort_keys=True))
 raise SystemExit(0)
assert args.seed,"--seed or --compiler is required"
driver=r'''namespace Mgnc;
use Mgnc\Data\{Diagnostic,describe,number};
use Mgnc\InputData\{SourceUnit,ProjectInput,InputError};
use Mgnc\Semantic\{SemanticProject,analyze};
use Std\Io\{writeStderr,writeStdout};
type Case=product{text:String;success:Bool;};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 var index:Int=0;var failures:Int=0;
 loop over(CASES as test:Case){
  let source:SourceUnit=SourceUnit{path:"case.mgn",displayPath:"case.mgn",relativePath:"case.mgn",expectedNamespace:"",text:test->text};
  let input:ProjectInput=ProjectInput{manifestPath:"",manifestText:"",rootNamespace:"",entry:0,sources:List<SourceUnit>[source]};
  let result:Result<SemanticProject,InputError>=analyze(input);
  let success:Bool=branch on result{Result<SemanticProject,InputError>::Ok(value:SemanticProject)=>true,Result<SemanticProject,InputError>::Err(error:InputError)=>{
   branch when{test->success=>{discard writeStderr("case "+number(index)+": "+describe(error->path,error->diagnostic));},else=>unit};false}};
  branch when{success!=test->success=>{discard writeStderr("semantic case "+number(index)+" failed\n");failures=failures+1;},else=>unit};index=index+1;
 };
 branch when{failures>0=>1,else=>{discard writeStdout("V150_SEMANTICS_OK\n");0}}
};
'''
driver=driver.replace("CASES","List<Case>["+",".join("Case{text:"+json.dumps(text)+",success:"+str(ok).lower()+"}" for text,ok in cases)+"]")
with tempfile.TemporaryDirectory(prefix="mgnc-v150-semantics-") as temp:
 work=Path(temp);harness=work/"harness";shutil.copytree(ROOT/"compiler/mgnc",harness);(harness/"src/mgnc.mgn").write_text(driver)
 if args.interpret:command=[args.seed,"run",harness/"mognitio.toml"]
 else:
  binary=work/"probe";build=subprocess.run(list(map(str,[args.seed,"build",harness/"mognitio.toml","-o",binary])),capture_output=True)
  if build.returncode:raise AssertionError(build.stderr.decode())
  command=[binary]
 result=subprocess.run(list(map(str,command)),capture_output=True)
 if result.returncode:raise AssertionError(result.stderr.decode())
 assert result.stdout==b"V150_SEMANTICS_OK\n",result.stdout
 print(json.dumps({"result":"V150_SEMANTICS_OK","cases":len(cases)},sort_keys=True))
