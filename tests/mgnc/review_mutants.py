#!/usr/bin/env python3
"""Prove review regressions detect five isolated implementation mutations."""
import argparse,hashlib,io,json,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ENTRY='let main:Function(List<String>):Int=function(args:List<String>):Int{'
MUTATIONS=[
 ('reserved-namespace','NativeBridge/bridge.mgn','word=="Std"','false','build','namespace Std;'+ENTRY+'0};',1,'semantic'),
 ('unknown-type','NativeTypes/types.mgn','return Result<Int,Diagnostic>::Err(try failure(tree,id,"semantic","unknown type"));','return Result<Int,Diagnostic>::Ok(1);','build','namespace A;'+ENTRY+'let n:int=0;n};',1,'semantic'),
 ('residual-equals','Cursor/scan.mgn','text=combined;','text=first;','parse','namespace A;let x:Bool=f<T>==true;',0,None),
 ('residual-gap','Cursor/scan.mgn','following->kind==3 && following->start+next%2==end','following->kind==3','parse','namespace A;let x:Bool=f<T>= =true;',1,'parse'),
 ('ordinary-ge','Cursor/scan.mgn','cursor:Int,genericClose:Bool):Result<Terminal,Diagnostic>{','cursor:Int,requestedClose:Bool):Result<Terminal,Diagnostic>{let genericClose:Bool=true;','parse','namespace A;let x:Bool=a>=b;',0,None),
]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);a=ap.parse_args();a.evidence.mkdir(parents=True,exist_ok=True)
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();archive=subprocess.check_output(['git','archive',head,'compiler/mgnc'],cwd=ROOT);rows=[]
 def observe(compiler,mode,source,output,want,phase):
  cmd=[str(compiler),mode,str(source)]+(['-o',str(output)] if mode=='build' else [])
  p=subprocess.run(cmd,capture_output=True,timeout=120)
  passes=p.returncode==want and not p.stdout and (not p.stderr if phase is None else ('mgnc: '+phase+':').encode() in p.stderr)
  return dict(command=cmd,exit=p.returncode,stdout_hex=p.stdout.hex(),stderr_hex=p.stderr.hex(),passes=passes,published=output.exists())
 with tempfile.TemporaryDirectory(prefix='mgnc-review-mutants-') as work:
  root=Path(work)
  for name,relative,old,new,mode,text,want,phase in MUTATIONS:
   folder=root/name;folder.mkdir();source=folder/'input.mgn';source.write_text(text)
   baseline=observe(a.compiler.resolve(),mode,source,folder/'baseline-output',want,phase);assert baseline['passes'],(name,baseline)
   with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(folder,filter='data')
   project=folder/'compiler/mgnc';path=project/'src'/relative;original=path.read_text();assert original.count(old)==1,(name,'mutation site drift');path.write_text(original.replace(old,new))
   compiler=folder/'mutant';build=subprocess.run([a.seed,'build',project/'mognitio.toml','-o',compiler],capture_output=True,timeout=600)
   assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),(name,build.stderr)
   mutant=observe(compiler,mode,source,folder/'mutant-output',want,phase);assert not mutant['passes'],(name,'regression did not detect mutation',mutant)
   rows.append(dict(name=name,head=head,source_sha256=hashlib.sha256(text.encode()).hexdigest(),mutated_file=relative,old=old,new=new,baseline=baseline,mutant=mutant,mutant_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest()))
   (a.evidence/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print('REVIEW_MUTANT_DETECTED',name,flush=True)
 print('REVIEW_MUTANTS_OK',len(rows),flush=True)
if __name__=='__main__':main()
