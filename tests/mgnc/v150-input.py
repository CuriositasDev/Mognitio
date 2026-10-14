#!/usr/bin/env python3
"""Test Mognitio input collection through a seed-built native executable."""
import argparse, json, os, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);args=p.parse_args()
def run(argv,**kw):return subprocess.run(list(map(str,argv)),capture_output=True,**kw)
def require(ok,detail):
 if not ok:raise AssertionError(detail)
with tempfile.TemporaryDirectory(prefix="mgnc-v150-input-") as temp:
 work=Path(temp);harness=work/"harness";(harness/"src").mkdir(parents=True)
 for module in ("Data","Width","TextUtil","Manifest","InputData","Project"):
  shutil.copytree(ROOT/"compiler/mgnc/src"/module,harness/"src"/module)
 (harness/"mognitio.toml").write_text('[project]\nname="probe"\nroot_namespace="Mgnc"\n')
 (harness/"src/probe.mgn").write_text(r'''namespace Mgnc;
use Mgnc\Manifest\{Manifest,parse};
use Mgnc\Project\{single,project};
use Mgnc\InputData\{ProjectInput,InputError,SourceUnit};
use Mgnc\TextUtil\{at};
use Mgnc\Data\{Diagnostic,describe};
use Std\Io\{readStdin,IoError,writeStdout,writeStderr};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 branch when{at(args,0)=="manifest"=>{
  let text:String=branch on readStdin(){Result<String,IoError>::Ok(value:String)=>value,Result<String,IoError>::Err(error:IoError)=>{return 2;}};
  return branch on parse(text){Result<Manifest,Diagnostic>::Ok(value:Manifest)=>{discard writeStdout(value->name+"\n"+value->root+"\n");0},Result<Manifest,Diagnostic>::Err(error:Diagnostic)=>2};
 },else=>unit};
 let loaded:Result<ProjectInput,InputError>=branch when{at(args,0)=="single"=>single(at(args,1)),else=>project(at(args,1))};
 branch on loaded{
 Result<ProjectInput,InputError>::Ok(value:ProjectInput)=>{
  loop over(value->sources as source:SourceUnit){discard writeStdout(source->relativePath+"|"+source->expectedNamespace+"\n");};0
 },
 Result<ProjectInput,InputError>::Err(error:InputError)=>{discard writeStderr(describe(error->path,error->diagnostic));error->status}
 }
};
''')
 binary=work/"probe";build=run([args.seed,"build",harness/"mognitio.toml","-o",binary]);require(build.returncode==0,build.stderr.decode())
 cases=0
 valid=[
 '[project]\nname="app"\nroot_namespace="App"',
 "project.name='app'\nproject.root_namespace='App'",
 'project={name="app",root_namespace="App"}',
 '"project"."name"="app"\n\'project\'.\'root_namespace\'="App"',
 '[ "project" ] # hello\n"name" = "app"\n"root_namespace"="App"',
 '[project]\r\nname="app"\r\nroot_namespace="App"\r\n',
 '[project]\nname="""\napp"""\nroot_namespace="""App"""',
 "[project]\nname='''\napp'''\nroot_namespace='''App'''",
 '[project]\nname="\\u0061pp"\nroot_namespace="\\U00000041pp"',
 '[project]\nname="""a\\\n  pp"""\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="App" # 日本語',
 '[project]\nname="app"\nroot_namespace="App\\\\Module"',
 ]
 invalid=[
 '', '[project]\nname="app"', '[project]\nname=1\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="App"\nextra=1',
 '[project]\nname="app"\nname="app"\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="App"\n[project]',
 'project.name="app"\n[project]\nroot_namespace="App"',
 'project={name="app",root_namespace="App",}',
 'project={name="app",\nroot_namespace="App"}',
 '[project]\rname="app"\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="Std\\\\Io"',
 '[project]\nname="App"\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="App\\\\let"',
 '[project]\nname="app"\nroot_namespace="App-Other"',
 '[project]\nname="a\\q"\nroot_namespace="App"',
 '[project]\nname="app"\nroot_namespace="\\uD800"',
 '[project]\nname="app"\nroot_namespace="App"\0',
 '[project]\nname="app"\nroot_namespace="App"\nother=[1,2]',
 '[[project]]\nname="app"\nroot_namespace="App"',
 'project={name="app",root_namespace="App"}\nproject.name="app"',
 ]
 for text,expected in [(x,0) for x in valid]+[(x,2) for x in invalid]:
  result=run([binary,"manifest"],input=text.encode());require(result.returncode==expected,(text,result.returncode,result.stderr))
  if expected==0:
   expected_root="App\\Module" if 'App\\\\Module' in text else "App"
   require(result.stdout==f"app\n{expected_root}\n".encode(),result.stdout)
  cases+=1
 project=work/"input";(project/"src").mkdir(parents=True);manifest=project/"mognitio.toml"
 manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n')
 entry=project/"src/app.mgn";entry.write_text("not parsed by the loader\n")
 def probe(expected=0,mode="project",path=None,contains=None):
  global cases
  result=run([binary,mode,path or manifest]);require(result.returncode==expected,(expected,result.returncode,result.stderr))
  if contains:require(contains in result.stderr,(contains,result.stderr))
  cases+=1;return result
 probe()
 (project/"src/a").mkdir()
 for name in ("a/z.mgn","a.mgn","a!x.mgn","未使用.mgn"):(project/"src"/name).write_text("")
 result=probe();require(result.stdout.decode().splitlines()==["a!x.mgn|App","a.mgn|App","a/z.mgn|App\\a","app.mgn|App","未使用.mgn|App"],result.stdout)
 extra=project/"src/unused"
 extra.symlink_to("missing");probe(2,contains=b"symlink");extra.unlink()
 extra.symlink_to("app.mgn");probe(2);extra.unlink()
 os.link(entry,extra.with_suffix(".mgn"));probe(2,contains=b"duplicate");extra.with_suffix(".mgn").unlink()
 os.link(manifest,extra.with_suffix(".mgn"));probe(2,contains=b"duplicate");extra.with_suffix(".mgn").unlink()
 extra.with_suffix(".mgn").write_text(entry.read_text());probe();extra.with_suffix(".mgn").unlink()
 os.mkfifo(extra.with_suffix(".mgn"));probe(2,contains=b"regular");extra.with_suffix(".mgn").unlink()
 os.mkfifo(extra);probe();extra.unlink()
 extra.with_suffix(".mgn").write_bytes(b"\xff");probe(1,contains=b"source");extra.with_suffix(".mgn").unlink()
 extra.write_bytes(b"\xff");probe();extra.unlink()
 raw=os.fsencode(extra)+b"\xff";fd=os.open(raw,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd);probe(2,contains=b"io");os.unlink(raw)
 extra.with_suffix(".mgn").mkdir();probe();(extra.with_suffix(".mgn")/"x.mgn").write_text("");probe(2,contains=b"namespace");shutil.rmtree(extra.with_suffix(".mgn"))
 entry.unlink();probe(2,contains=b"entry");entry.write_text("")
 original=manifest.read_bytes();manifest.write_bytes(b"\xff");probe(2,contains=b"manifest");manifest.write_bytes(original)
 alias=work/"alias.mgn";alias.symlink_to(entry);probe(mode="single",path=alias)
 alias.unlink();alias.symlink_to(manifest);probe(2,path=alias);alias.unlink()
 probe(2,mode="single",path=project/"src")
 print(json.dumps({"result":"V150_INPUT_OK","cases":cases},sort_keys=True))
