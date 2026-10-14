#!/usr/bin/env python3
"""Exercise named type formation and mathematical literal range primitives."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);p.add_argument("--interpret",action="store_true");args=p.parse_args()
cases=[
 ("type Pair=product{left:Int;right:String;};",True),
 ("alias Forward=Later;type Later=product{};",True),
 ("type Box<T>=product{value:T;};alias B=Box<Int>;",True),
 ("type Choice<T>=sum{None;Some(T);};alias C=Choice<List<Int>>;",True),
 ("alias Fn=Function(Int,List<String>):Result<Int,String>;",True),
 ("use Std\\Numeric\\{Bits,Signed,Unsigned};alias B=Bits<64>;alias U=Int<64,Unsigned>;alias I=Int<8,Signed>;",True),
 ("use Std\\Numeric\\{Bits};type Box<N:Int>=product{value:Bits<N>;};alias B=Box<8>;",True),
 ("use Std\\Numeric\\{Bits};alias Narrow<N:Int>=Bits<N>;alias Relay<M:Int>=Narrow<M>;alias B=Relay<8>;",True),
 ("alias Counter=Int;type Box<N:Counter>=product{};alias B=Box<-9223372036854775808>;",True),
 ("type Box<N:Int>=product{};alias B=Box<(-0)>;",True),
 ("type X=product{a:Int;a:Bool;};",False),
 ("type X=sum{A;A(Int);};",False),
 ("alias Loop=Loop;",False),
 ("type A=product{b:List<B>;};type B=sum{Next(Function():A);};",False),
 ("type X<T>=product{value:T;};alias B=X;",False),
 ("type X<T>=product{value:T;};alias B=X<1>;",False),
 ("type X<N:Int>=product{};alias B=X<Int>;",False),
 ("type X<N:String>=product{};",False),
 ("use Std\\Numeric\\{Bits};alias X=Bits<0>;",False),
 ("use Std\\Numeric\\{Bits};alias X=Bits<65>;",False),
 ("use Std\\Numeric\\{Bits};type Box<N:Int>=product{value:Bits<N>;};alias B=Box<-1>;",False),
 ("use Std\\Numeric\\{Bits};alias Narrow<N:Int>=Bits<N>;alias Relay<M:Int>=Narrow<M>;alias B=Relay<65>;",False),
 ("use Std\\Numeric\\{Signed};alias X=Int<8,Int>;",False),
 ("alias X=List<Int,Bool>;",False),
 ("alias X=Missing;",False),
 ("let X:Int=1;alias Y=X;",False),
]
driver=r'''namespace Mgnc;
use Mgnc\Data\{Diagnostic,describe,number,lookup};
use Mgnc\InputData\{SourceUnit,ProjectInput,InputError};
use Mgnc\SemanticData\{Headers};
use Mgnc\Headers\{collect};
use Mgnc\Catalog\{attach};
use Mgnc\Imports\{resolve};
use Mgnc\TypeDependencies\{order};
use Mgnc\TypeDeclarations\{define};
use Mgnc\TypeData\{Store};
use Mgnc\TypeOps\{initialize};
use Mgnc\MathValue\{Integer,normalize,fits,ordinary,minimumWidth};
use Mgnc\Data\{Span};
use Std\Io\{writeStderr,writeStdout};
type Case=product{text:String;success:Bool;};
let analyze:Function(String):Result<Store,Diagnostic>=function(text:String):Result<Store,Diagnostic>{
 let source:SourceUnit=SourceUnit{path:"case.mgn",displayPath:"case.mgn",relativePath:"case.mgn",expectedNamespace:"",text:"namespace App;"+text};
 let input:ProjectInput=ProjectInput{manifestPath:"",manifestText:"",rootNamespace:"",entry:0,sources:List<SourceUnit>[source]};
 let headers:Headers=branch on collect(input){Result<Headers,InputError>::Ok(value:Headers)=>value,Result<Headers,InputError>::Err(error:InputError)=>{return Result<Store,Diagnostic>::Err(error->diagnostic);}};
 let catalog:Headers=try attach(headers);
 let resolved:Headers=branch on resolve(catalog){Result<Headers,InputError>::Ok(value:Headers)=>value,Result<Headers,InputError>::Err(error:InputError)=>{return Result<Store,Diagnostic>::Err(error->diagnostic);}};
 let sequence:List<Int>=try order(resolved);var store:Store=initialize(resolved);
 loop over(sequence as id:Int){store=try define(store,id);};Result<Store,Diagnostic>::Ok(store)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 var index:Int=0;
 loop over(CASES as test:Case){
  let result:Result<Store,Diagnostic>=analyze(test->text);
  let success:Bool=branch on result{Result<Store,Diagnostic>::Ok(value:Store)=>true,Result<Store,Diagnostic>::Err(error:Diagnostic)=>{branch when{test->success=>{discard writeStderr(describe("case "+number(index),error));},else=>unit};false}};
  branch when{success!=test->success=>{discard writeStderr("type case "+number(index)+" failed\n");return 1;},else=>unit};index=index+1;
 };
 MATH
 discard writeStdout("V150_TYPES_OK\n");0
};
'''
case_source="List<Case>["+",".join("Case{text:"+json.dumps(text)+",success:"+str(ok).lower()+"}" for text,ok in cases)+"]"
math=[];checks=0
for width in (1,2,7,8,31,32,63,64):
 for signed in (False,True):
  minimum=-(2**(width-1)) if signed else 0
  maximum=2**(width-1)-1 if signed else 2**width-1
  for value in sorted({minimum-1,minimum,0,maximum,maximum+1,2**64}):
   expected=minimum<=value<=maximum;checks+=1
   expression=f'fits(normalize({str(value<0).lower()},"{abs(value)}"),{width},{str(signed).lower()})'
   math.append(f'branch when{{{expression}!={str(expected).lower()}=>{{discard writeStderr("math case {checks} failed\\n");return 1;}},else=>unit}};')
driver=driver.replace("CASES",case_source).replace("MATH","\n".join(math))
with tempfile.TemporaryDirectory(prefix="mgnc-v150-types-") as temp:
 work=Path(temp);harness=work/"harness";shutil.copytree(ROOT/"compiler/mgnc",harness);(harness/"src/mgnc.mgn").write_text(driver)
 if args.interpret:command=[args.seed,"run",harness/"mognitio.toml"]
 else:
  binary=work/"probe"
  result=subprocess.run(list(map(str,[args.seed,"build",harness/"mognitio.toml","-o",binary])),capture_output=True)
  if result.returncode:raise AssertionError(result.stderr.decode())
  command=[binary]
 result=subprocess.run(list(map(str,command)),capture_output=True)
 if result.returncode:raise AssertionError(result.stderr.decode())
 assert result.stdout==b"V150_TYPES_OK\n",result.stdout
 print(json.dumps({"result":"V150_TYPES_OK","type_cases":len(cases),"math_cases":checks},sort_keys=True))
