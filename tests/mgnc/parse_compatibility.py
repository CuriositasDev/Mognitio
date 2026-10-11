#!/usr/bin/env python3
"""Valid normal-toolchain contracts/assertions remain outside experimental parse."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args();records=[]
 examples=[('witness',r'use App\Evidence\{C};witness Evidence=Int implements C{get(self:Self):Int{self}}','0'),('contract','contract C{get(self:Self):Int;}witness Evidence=Int implements C{get(self:Self):Int{self}}', 'C(0)->get()'),('assert','', 'assert true;0'),('attribute','@test let check:Function():Unit=function():Unit{assert true;};','0')]
 with tempfile.TemporaryDirectory(prefix='mgnc-compatibility-') as work:
  root=Path(work)
  for name,declarations,body in examples:
   project=root/name;(project/'src').mkdir(parents=True);manifest=project/'mognitio.toml';manifest.write_text('[project]\nname="app"\nroot_namespace="App"\n');source='namespace App;'+declarations+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};';path=project/'src/app.mgn';path.write_text(source)
   if name=='witness':
    domain=project/'src/Evidence';domain.mkdir();(domain/'contract.mgn').write_text(r'namespace App\Evidence;public contract C{get(self:Self):Int;}')
   normal=subprocess.run([ROOT/'bin/mgn','run',manifest],capture_output=True,timeout=120)
   experimental=subprocess.run([args.compiler.resolve(),'parse',path],capture_output=True,timeout=120)
   assert (normal.returncode,normal.stdout,normal.stderr)==(0,b'',b''),(name,normal)
   assert experimental.returncode==1 and not experimental.stdout and b'mgnc: unsupported:' in experimental.stderr,(name,experimental)
   tests=None
   if name=='attribute':
    tests=subprocess.run([ROOT/'bin/mgn','test',manifest],capture_output=True,timeout=120);assert tests.returncode==0 and b'passed=1' in tests.stdout and not tests.stderr,tests
   records.append(dict(name=name,sha256=hashlib.sha256(source.encode()).hexdigest(),normal_exit=normal.returncode,parse_exit=experimental.returncode,parse_stderr=experimental.stderr.decode().replace(str(root),'<fixtures>'),test_stdout=tests.stdout.decode() if tests else None))
 data=dict(compiler_sha256=hashlib.sha256(args.compiler.read_bytes()).hexdigest(),records=records);args.evidence.write_text(json.dumps(data,indent=2)+'\n');print('PARSE_COMPATIBILITY_OK',len(records))
if __name__=='__main__':main()
