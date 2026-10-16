#!/usr/bin/env python3
"""Fixed generic and lexical-environment fixtures for concrete native planning."""
import argparse,hashlib,json,subprocess
from pathlib import Path
CASES={
"capture-alternation":r"""template make<T>=function(value:T):Function():T{function():T{value}};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let a:Function():Int=make<Int>(7);let b:Function():String=make<String>("kept"+" text");let c:Function():Int=make<Int>(9);
 branch when{!(a()==7&&b()=="kept text"&&c()==9)=>{return 1;},else=>unit};0
};""",
"nested-body-only-type":r"""template make<T>=function():Function():Int{function():Int{let values:List<T>=List<T>[];values->length()}};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let a:Function():Int=make<Int>();let b:Function():Int=make<String>();let c:Function():Int=make<Int>();
 branch when{!(a()==0&&b()==0&&c()==0)=>{return 1;},else=>unit};0
};""",
"nested-body-only-value":r"""type Tag<N:Int>=product{};
template make<N:Int>=function():Function():Int{function():Int{let tag:Tag<N>=Tag<N>{};discard tag;7}};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let a:Function():Int=make<-1>();let b:Function():Int=make<2>();let c:Function():Int=make<-1>();
 branch when{!(a()+b()+c()==21)=>{return 1;},else=>unit};0
};""",
"callee-only-outer-type":r"""template size<T>=function():Int{let values:List<T>=List<T>[];values->length()};
template make<T>=function():Function():Int{function():Int{size<T>()}};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let a:Function():Int=make<Int>();let b:Function():Int=make<String>();branch when{!(a()==0&&b()==0)=>{return 1;},else=>unit};0
};""",
"result-owner-substitution":r"""template propagate<T>=function(input:Result<T,String>):Result<Int,String>{
 let value:T=try input;Result<Int,String>::Ok(7)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let first:Result<Int,String>=propagate<String>(Result<String,String>::Err("kept"+" error"));
 let second:Result<Int,String>=propagate<Bool>(Result<Bool,String>::Ok(true));
 branch when{!(branch on first{Result<Int,String>::Ok(value:Int)=>false,Result<Int,String>::Err(error:String)=>error=="kept error"})=>{return 1;},else=>unit};
 branch when{!(branch on second{Result<Int,String>::Ok(value:Int)=>value==7,Result<Int,String>::Err(error:String)=>false})=>{return 1;},else=>unit};0
};""",
"mixed-kind-capture":r"""type Tag<N:Int,T>=product{value:T;};
template make<N:Int,T>=function(value:T):Function():Tag<N,T>{function():Tag<N,T>{Tag<N,T>{value:value}}};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let a:Function():Tag<-1,Int>=make<-1,Int>(7);let b:Function():Tag<2,String>=make<2,String>("kept"+" field");
 let c:Function():Tag<-1,Int>=make<-1,Int>(9);
 branch when{!(a()->value==7&&b()->value=="kept field"&&c()->value==9)=>{return 1;},else=>unit};0
};""",
}
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--output",type=Path,required=True)
 parser.add_argument("--seed",type=Path)
 args=parser.parse_args();args.output.mkdir(exist_ok=False)
 rows=[]
 for name,body in CASES.items():
  project=args.output/name;(project/"src").mkdir(parents=True)
  (project/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="App"\n')
  text="namespace App;\n"+body+"\n";(project/"src/app.mgn").write_text(text)
  rows.append({"name":name,"source_sha256":hashlib.sha256(text.encode()).hexdigest(),"exit":0,"stdout":"","stderr":""})
 manifest=args.output/"manifest.json";manifest.write_text(json.dumps(rows,indent=2)+"\n")
 print("GENERIC_FIXTURES sha256="+hashlib.sha256(manifest.read_bytes()).hexdigest(),flush=True)
 if args.seed:
  for row in rows:
   run=subprocess.run([args.seed,"run",args.output/row["name"]/"mognitio.toml"],capture_output=True,timeout=120)
   assert (run.returncode,run.stdout,run.stderr)==(0,b"",b""),(row["name"],run.returncode,run.stdout,run.stderr)
  print("GENERIC_REFERENCE_OK cases="+str(len(rows)))
if __name__=="__main__":main()
