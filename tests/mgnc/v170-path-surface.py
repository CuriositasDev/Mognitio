#!/usr/bin/env python3
"""Exercise ordinary path Functions, evaluation order and isolated execution."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);options=parser.parse_args();options.output.mkdir(parents=True,exist_ok=False);rows=[];fixtures=0
prefix=r'namespace App;use Std\Io\{joinPath,createDirectory,IoError,IoErrorKind,writeStdout};';join='Function(String,String):Result<String,IoError>';create='Function(String):Result<Unit,IoError>'
def program(body,extra=''):return prefix+extra+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};'
def call(name,command,status=0,out=b'',err=b''):
 result=subprocess.run(list(map(str,command)),capture_output=True,timeout=180);rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=(result.returncode,result.stdout,result.stderr)==(status,out,err)));(options.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert rows[-1]['passed'],rows[-1]
with tempfile.TemporaryDirectory(prefix='mgn-path-surface-') as temporary:
 work=Path(temporary);image=options.output/'program';source=options.output/'input.mgn'
 def fixture(name,body,extra='',status=0,out=b'',err=b''):
  global fixtures
  text=program(body,extra);fixtures+=1;source.write_text(text);(options.output/(name+'.mgn')).write_text(text);image.unlink(missing_ok=True)
  for verb in ('check','lower'):call(name+'-'+verb,[options.compiler,verb,source])
  call(name+'-build',[options.compiler,'build',source,'-o',image]);digest=hashlib.sha256(image.read_bytes()).hexdigest();call(name+'-native',[image],status,out,err);call(name+'-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',options.output/(name+'-stress.json'),'--',image],status,out,err);assert hashlib.sha256(image.read_bytes()).hexdigest()==digest
 fixture('join-arguments-before-validation','var calls:Int=0;branch on joinPath({calls=calls+1;discard writeStdout("b");""},{calls=calls+1;discard writeStdout("r");"/bad"}){Result<String,IoError>::Ok=>{assert false;},Result<String,IoError>::Err(error:IoError)=>{assert error->subject=="";}};assert calls==2;0',out=b'br')
 fixture('create-argument-once','var calls:Int=0;discard createDirectory({calls=calls+1;discard writeStdout("p");""});assert calls==1;0',out=b'p')
 fixture('join-argument-panic','discard joinPath("",stop());0','let stop:Function():String=function():String{panic{"stop"}};',4,err=b'panic: stop\n')
 fixture('create-argument-panic','discard createDirectory(stop());0','let stop:Function():String=function():String{panic{"stop"}};',4,err=b'panic: stop\n')
 fixture('create-argument-return','createDirectory({return 9;})',status=9)
 extra='let attempt:'+join+'=function(base:String,relative:String):Result<String,IoError>{let api:'+join+'=joinPath;Result<String,IoError>::Ok(try api(base,relative))};'
 fixture('ordinary-try','branch on attempt("x",""){Result<String,IoError>::Ok=>1,Result<String,IoError>::Err(error:IoError)=>{assert error->subject=="";0}}',extra)
 body='let api:'+join+'=joinPath;let saved:'+join+'=function(base:String,relative:String):Result<String,IoError>{api(base,relative)};let functions:List<'+join+'>=List<'+join+'>[api,saved];var kept:List<String>=List<String>[];loop over(functions as query:'+join+'){branch on query("a//","../b"){Result<String,IoError>::Ok(value:String)=>{kept=kept->append(value);},Result<String,IoError>::Err=>{assert false;}};};let bad:Result<Unit,IoError>=createDirectory("");let retained:Function():Result<Unit,IoError>=function():Result<Unit,IoError>{bad};let make:'+create+'=createDirectory;var count:Int=0;loop while(count<32){discard make("");discard api("x","y");count=count+1;};loop over(kept as value:String){assert value=="a//../b";};branch on retained(){Result<Unit,IoError>::Ok=>1,Result<Unit,IoError>::Err(error:IoError)=>{assert error->subject=="";0}}'
 fixture('indirect-retained-values',body)
 project=options.output/'project';(project/'src/Bridge').mkdir(parents=True);(project/'src/Fake').mkdir();manifest=project/'mognitio.toml';manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n');(project/'src/Bridge/value.mgn').write_text(r'namespace App\Bridge;use Std\Io\{IoError,joinPath as joinImpl,createDirectory as createImpl};public let join:'+join+'=joinImpl;public let create:'+create+'=createImpl;');(project/'src/Fake/value.mgn').write_text(r'namespace App\Fake;use Std\Io\{IoError};public let joinPath:'+join+'=function(base:String,relative:String):Result<String,IoError>{Result<String,IoError>::Ok("synthetic")};')
 body='branch on fake("a","b"){Result<String,IoError>::Ok(value:String)=>{assert value=="synthetic";},Result<String,IoError>::Err=>{assert false;}};branch on join("a","b"){Result<String,IoError>::Ok(value:String)=>{assert value=="a/b";},Result<String,IoError>::Err=>{assert false;}};branch on create(""){Result<Unit,IoError>::Ok=>1,Result<Unit,IoError>::Err(error:IoError)=>{assert error->subject=="";0}}'
 (project/'src/app.mgn').write_text(program(body).replace('namespace App;',r'namespace App;use App\Bridge\{join,create};use App\Fake\{joinPath as fake};'));image.unlink();call('reexport-build',[options.compiler,'build',manifest,'-o',image]);call('reexport-native',[image]);call('reexport-stress',[sys.executable,Path(__file__).with_name('v160-native-observe.py'),'--stress','--report',options.output/'reexport-stress.json','--',image]);fixtures+=1
 body='let path:String=branch on joinPath("/tmp","directory"){Result<String,IoError>::Ok(value:String)=>value,Result<String,IoError>::Err=>panic{"join failed"}};try make(path);try make(path);Result<Unit,IoError>::Ok(unit)'
 extra='let make:'+create+'=createDirectory;let run:Function():Result<Unit,IoError>=function():Result<Unit,IoError>{'+body+'};'
 source.write_text(program('branch on run(){Result<Unit,IoError>::Ok=>0,Result<Unit,IoError>::Err=>1}',extra));image.unlink();call('isolated-build',[options.compiler,'build',source,'-o',image]);fixtures+=1
 for proc in (True,False):
  command=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','1000','--gid','1000','--clearenv','--ro-bind',image,'/program','--dev','/dev','--tmpfs','/tmp','--chdir','/']
  if proc:command+=['--proc','/proc']
  call('isolated-'+str(proc),command+['--','/program'])
(options.output/'summary.json').write_text(json.dumps(dict(fixtures=fixtures,observations=len(rows),compiler_sha256=hashlib.sha256(options.compiler.read_bytes()).hexdigest(),passed=True),indent=2)+'\n');print('V170_PATH_SURFACE_OK',fixtures,len(rows))
