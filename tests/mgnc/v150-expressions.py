#!/usr/bin/env python3
"""Visit every retained expression in every current compiler source body."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);p.add_argument("--interpret",action="store_true");args=p.parse_args()
driver=r'''namespace Mgnc;
use Mgnc\Data\{Diagnostic,describe,number,lookup,Paged,empty,push};
use Mgnc\InputData\{ProjectInput,InputError};
use Mgnc\Project\{project};
use Mgnc\SemanticData\{Headers,Module,Declaration};
use Mgnc\Headers\{collect};
use Mgnc\Catalog\{attach};
use Mgnc\Imports\{resolve};
use Mgnc\Syntax\{Parent};
use Mgnc\SemanticClassification\{classify};
use Mgnc\Expressions\{Expression,read};
use Mgnc\Forest\{SyntaxForest};
use Std\Io\{writeStderr,writeStdout};
let walk:Function(SyntaxForest):Result<Int,Diagnostic>=function(tree:SyntaxForest):Result<Int,Diagnostic>{
 var nodes:Paged<Int>=push<Int>(empty<Int>(),tree->root);var index:Int=0;
 loop while(index<nodes->count){let id:Int=try lookup<Int>(nodes,index);index=index+1;let expression:Expression=try read(tree,id);
  loop over(expression->children as child:Int){nodes=push<Int>(nodes,child);};
 };Result<Int,Diagnostic>::Ok(index)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let input:ProjectInput=branch on project(INPUT){Result<ProjectInput,InputError>::Ok(value:ProjectInput)=>value,Result<ProjectInput,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));return error->status;}};
 let headers:Headers=branch on collect(input){Result<Headers,InputError>::Ok(value:Headers)=>value,Result<Headers,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));return error->status;}};
 let catalog:Headers=branch on attach(headers){Result<Headers,Diagnostic>::Ok(value:Headers)=>value,Result<Headers,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(describe("catalog",error));return 3;}};
 let resolved:Headers=branch on resolve(catalog){Result<Headers,InputError>::Ok(value:Headers)=>value,Result<Headers,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));return error->status;}};
 var index:Int=0;var expressions:Int=0;var bodies:Int=0;
 loop while(index<resolved->declarations->count){
  let declaration:Declaration=branch on lookup<Declaration>(resolved->declarations,index){Result<Declaration,Diagnostic>::Ok(value:Declaration)=>value,Result<Declaration,Diagnostic>::Err(error:Diagnostic)=>{return 3;}};
  let module:Module=branch on lookup<Module>(resolved->modules,declaration->file){Result<Module,Diagnostic>::Ok(value:Module)=>value,Result<Module,Diagnostic>::Err(error:Diagnostic)=>{return 3;}};
  branch when{!module->standard&&declaration->kind>=3=>{
   let tree:SyntaxForest=branch on classify(resolved,declaration->file,declaration->body,branch when{declaration->kind==3=>Parent::Some(index),else=>Parent::None}){
    Result<SyntaxForest,Diagnostic>::Ok(value:SyntaxForest)=>value,Result<SyntaxForest,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(describe(module->source->displayPath,error));return 1;}};
   branch on walk(tree){Result<Int,Diagnostic>::Ok(count:Int)=>{expressions=expressions+count;},Result<Int,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(describe(module->source->displayPath,error));return 1;}};
   bodies=bodies+1;
  },else=>unit};index=index+1;
 };
 discard writeStdout("V150_EXPRESSIONS_OK sources="+number(input->sources->length())+" bodies="+number(bodies)+" expressions="+number(expressions)+"\n");0
};
'''
with tempfile.TemporaryDirectory(prefix="mgnc-v150-expressions-") as temp:
 work=Path(temp);corpus=work/"corpus";shutil.copytree(ROOT/"compiler/mgnc",corpus)
 harness=work/"harness";shutil.copytree(corpus,harness)
 (harness/"src/mgnc.mgn").write_text(driver.replace("INPUT",json.dumps(str(corpus/"mognitio.toml"))))
 binary=work/"probe"
 if args.interpret:
  command=[args.seed,"run",harness/"mognitio.toml"]
 else:
  build=subprocess.run(list(map(str,[args.seed,"build",harness/"mognitio.toml","-o",binary])),capture_output=True)
  if build.returncode:raise AssertionError(build.stderr.decode())
  command=[binary]
 result=subprocess.run(list(map(str,command)),capture_output=True)
 if result.returncode:raise AssertionError(result.stderr.decode())
 print(result.stdout.decode(),end="")
