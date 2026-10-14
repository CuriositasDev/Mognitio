#!/usr/bin/env python3
"""Native declaration collection and import resolution tests, before type analysis."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);args=p.parse_args()
def run(argv,**kw):return subprocess.run(list(map(str,argv)),capture_output=True,**kw)
def require(ok,detail):
 if not ok:raise AssertionError(detail)
with tempfile.TemporaryDirectory(prefix="mgnc-v150-headers-") as temp:
 work=Path(temp);harness=work/"harness";shutil.copytree(ROOT/"compiler/mgnc",harness)
 (harness/"src/mgnc.mgn").write_text(r'''namespace Mgnc;
use Mgnc\Project\{single,project};
use Mgnc\InputData\{ProjectInput,InputError};
use Mgnc\Headers\{collect};
use Mgnc\Catalog\{attach};
use Mgnc\Imports\{resolve};
use Mgnc\SemanticData\{Headers};
use Mgnc\Data\{Diagnostic,describe,number};
use Mgnc\TextUtil\{at};
use Std\Io\{writeStdout,writeStderr};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let input:ProjectInput=branch on branch when{at(args,0)=="single"=>single(at(args,1)),else=>project(at(args,1))}{
 Result<ProjectInput,InputError>::Ok(value:ProjectInput)=>value,
 Result<ProjectInput,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));return error->status;}};
 let collected:Headers=branch on collect(input){Result<Headers,InputError>::Ok(value:Headers)=>value,
 Result<Headers,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));return error->status;}};
 let catalog:Headers=branch on attach(collected){Result<Headers,Diagnostic>::Ok(value:Headers)=>value,
 Result<Headers,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(describe("standard:catalog",error));return 3;}};
 branch on resolve(catalog){
 Result<Headers,InputError>::Ok(value:Headers)=>{discard writeStdout(number(value->modules->count)+" "+number(value->declarations->count)+"\n");0},
 Result<Headers,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));error->status}
 }
};
''')
 binary=work/"probe";build=run([args.seed,"build",harness/"mognitio.toml","-o",binary]);require(build.returncode==0,build.stderr.decode())
 cases=0;single=work/"one.mgn"
 def case(body,expected=0,contains=None):
  global cases
  single.write_text("namespace App;"+body)
  result=run([binary,"single",single])
  require(result.returncode==expected,(body,result.returncode,result.stderr))
  if contains:require(contains in result.stderr,(body,result.stderr))
  cases+=1
 case("let main:Function(List<String>):Int=function(args:List<String>):Int{0};")
 case("type Box<T>=product{value:T;};alias Name=String;type Choice=sum{A;B(Int);};template identity<T>=function(value:T):T{value};")
 case("use Std\\Io\\{FileIdentity,inspectPath as inspect};")
 case("use Std\\Io\\{unknown};",1,b"public import")
 case("use Std\\Io\\{inspectPath,inspectPath as another};",1,b"duplicate")
 case("use Std\\Io\\{inspectPath as Int};",1,b"reserved")
 case("type X=product{};type X=sum{};",1,b"duplicate")
 case("type Int=product{};",1,b"reserved")
 case("type X<T,T>=product{};",1,b"parameter")
 case("type X<Int>=product{};",1,b"parameter")
 case("use Std\\Io\\{FileIdentity};type FileIdentity=product{};",1,b"duplicate")
 case("use App\\{X};public type X=product{};",1,b"same source")
 case("use Absent\\{X};",1,b"public import")
 project=work/"input";(project/"src").mkdir(parents=True)
 manifest=project/"mognitio.toml";manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
 files={"app.mgn":"namespace App;use App\\{Value};","value.mgn":"namespace App;public type Value=product{};"}
 def project_case(expected=0,contains=None):
  global cases
  for name,text in files.items():(project/"src"/name).write_text(text)
  result=run([binary,"project",manifest]);require(result.returncode==expected,(files,result.returncode,result.stderr))
  if contains:require(contains in result.stderr,(files,result.stderr))
  cases+=1
 project_case()
 files["value.mgn"]="namespace Wrong;public type Value=product{};";project_case(1,b"namespace")
 files["value.mgn"]="namespace App;type Value=product{};";project_case(1,b"public import")
 files["value.mgn"]="namespace App;use App\\{Entry};public type Value=product{};"
 files["app.mgn"]="namespace App;use App\\{Value};public type Entry=product{};";project_case(1,b"cyclic")
 files["value.mgn"]="namespace App;public type Value=product{};"
 files["extra.mgn"]="namespace App;public type Value=product{};";project_case(1,b"duplicate public")
 files["app.mgn"]="namespace App;";project_case(1,b"duplicate public")
 print(json.dumps({"result":"V150_HEADERS_OK","cases":cases},sort_keys=True))
