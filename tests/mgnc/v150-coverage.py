#!/usr/bin/env python3
"""Compare source membership/body completion with an independent top-level scanner."""
import argparse,hashlib,json,re,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C0="4908a1a91be61d64695b9e048b833637aee0aefc"
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);p.add_argument("--corpus",choices=["C0","C1"],required=True);p.add_argument("--evidence",required=True,type=Path);args=p.parse_args()
def declarations(text):
 tokens=re.findall(r'"(?:\\.|[^"\\])*"|//[^\n]*|[A-Za-z_][A-Za-z_0-9]*|[^\s]',text,re.S)
 result=[];statement=[];depth=0
 for token in tokens:
  if token.startswith("//"):continue
  if token in ("{","(","["):depth+=1
  elif token in ("}",")","]"):depth-=1
  if token==";" and depth==0:
   words=statement[1:] if statement and statement[0]=="public" else statement
   if words and words[0] in ("let","var","template","alias","type"):
    kind={"let":4,"var":5,"template":3,"alias":2}.get(words[0],0 if "product" in words else 1)
    result.append((words[1],kind))
   elif not words or words[0] not in ("namespace","use"):raise AssertionError(words[:10])
   statement=[]
  else:statement.append(token)
 assert depth==0 and not statement
 return result
driver=r'''namespace Mgnc;
use Mgnc\Data\{Diagnostic,lookup,number};
use Mgnc\Project\{project};
use Mgnc\InputData\{ProjectInput,InputError};
use Mgnc\Semantic\{SemanticProject,analyze};
use Mgnc\SemanticData\{Module,Declaration};
use Mgnc\SemanticValues\{BodyState};
use Mgnc\TextUtil\{at};
use Mgnc\InputDiagnostics\{message};
use Std\Io\{writeStdout,writeStderr};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let input:ProjectInput=branch on project(at(args,0)){Result<ProjectInput,InputError>::Ok(v:ProjectInput)=>v,Result<ProjectInput,InputError>::Err(e:InputError)=>{discard writeStderr(message(e));return e->status;}};
 let semantic:SemanticProject=branch on analyze(input){Result<SemanticProject,InputError>::Ok(v:SemanticProject)=>v,Result<SemanticProject,InputError>::Err(e:InputError)=>{discard writeStderr(message(e));return e->status;}};
 var file:Int=0;loop while(file<semantic->state->types->headers->modules->count){
  let module:Module=branch on lookup<Module>(semantic->state->types->headers->modules,file){Result<Module,Diagnostic>::Ok(v:Module)=>v,Result<Module,Diagnostic>::Err(e:Diagnostic)=>{return 3;}};
  branch when{!module->standard=>{
   discard writeStdout("M\t"+module->source->relativePath+"\n");
   loop over(module->declarations as id:Int){
    let declared:Declaration=branch on lookup<Declaration>(semantic->state->types->headers->declarations,id){Result<Declaration,Diagnostic>::Ok(v:Declaration)=>v,Result<Declaration,Diagnostic>::Err(e:Diagnostic)=>{return 3;}};
    let body:BodyState=branch on lookup<BodyState>(semantic->state->bodies,id){Result<BodyState,Diagnostic>::Ok(v:BodyState)=>v,Result<BodyState,Diagnostic>::Err(e:Diagnostic)=>{return 3;}};
    let completed:Int=branch on body{BodyState::Complete(root:Int)=>1,BodyState::NotRequired=>0,BodyState::Pending=> -1,BodyState::Checking=> -2};
    discard writeStdout("D\t"+module->source->relativePath+"\t"+declared->name+"\t"+number(declared->kind)+"\t"+number(completed)+"\n");
   };
  },else=>unit};file=file+1;
 };0
};
'''
with tempfile.TemporaryDirectory(prefix="v150-coverage-") as temp:
 work=Path(temp);corpus=work/"corpus";corpus.mkdir()
 if args.corpus=="C1":shutil.copytree(ROOT/"compiler/mgnc",corpus,dirs_exist_ok=True)
 else:
  paths=subprocess.check_output(["git","ls-tree","-r","--name-only",C0,"compiler/mgnc/src","compiler/mgnc/mognitio.toml"],cwd=ROOT,text=True).splitlines()
  for name in paths:
   if name.endswith((".mgn",".toml")):
    destination=corpus/Path(name).relative_to("compiler/mgnc");destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(subprocess.check_output(["git","show",C0+":"+name],cwd=ROOT))
 files=sorted((corpus/"src").rglob("*.mgn"),key=lambda x:x.relative_to(corpus/"src").as_posix().encode())
 expected={f.relative_to(corpus/"src").as_posix():declarations(f.read_text()) for f in files}
 harness=work/"harness";shutil.copytree(ROOT/"compiler/mgnc",harness);(harness/"src/mgnc.mgn").write_text(driver)
 binary=work/"probe"
 built=subprocess.run([args.seed,"build",harness/"mognitio.toml","-o",binary],capture_output=True,timeout=600)
 assert built.returncode==0,built.stderr.decode()
 result=subprocess.run([binary,corpus/"mognitio.toml"],capture_output=True,timeout=1800)
 args.evidence.with_suffix(".stdout").write_bytes(result.stdout);args.evidence.with_suffix(".stderr").write_bytes(result.stderr)
 actual={};complete=0
 for line in result.stdout.decode().splitlines():
  fields=line.split("\t")
  if fields[0]=="M":assert fields[1] not in actual;actual[fields[1]]=[]
  elif fields[0]=="D":
   _,file,name,kind,body=fields;kind=int(kind);body=int(body)
   assert body==(1 if kind>=3 else 0),fields
   complete+=body;actual[file].append((name,kind))
  else:raise AssertionError(fields)
 record={"corpus":args.corpus,"harness_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),"source_files":len(expected),"declarations":sum(map(len,expected.values())),"completed_bodies":complete,"exit":result.returncode,"membership_matches":actual==expected,"passed":result.returncode==0 and not result.stderr and actual==expected}
 args.evidence.write_text(json.dumps(record,indent=2)+"\n")
 assert record["passed"],record
 print("V150_COVERAGE_OK "+json.dumps(record,sort_keys=True))
