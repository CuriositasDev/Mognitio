#!/usr/bin/env python3
"""Paired native regressions for declaration-guard propagation through the forest."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
HEADER='namespace App;let choose:Function(Bool,Bool):Int=function(left:Bool,right:Bool):Int{branch when{left&&right=>7,else=>9}};'
ENTRY='let main:Function(List<String>):Int=function(args:List<String>):Int{'
def fixtures():
 rows=[]
 def add(name,body,expected=7,prefix='',phase=None):rows.append(dict(name=name,source=HEADER+prefix+ENTRY+body+'};',expected=expected,phase=phase))
 for name,call in [('plain','choose(a < 2, 3 > (1))'),('grouped','choose((a < 2), (3 > (1)))'),('compact','choose(a<2,3>(1))'),('renamed','choose(A<2,3>(1))'),('comments','choose(a /*unused*/ <2,3>(1))'.replace(' /*unused*/',' // name\n')),('negative-value','choose(a < -2, 3 > (1))')]:
  binding='A' if name=='renamed' else 'a';add(name,f'let {binding}:Int=1;'+call,9 if name=='negative-value' else 7)
 add('parameter','probe(1)',prefix='let probe:Function(Int):Int=function(a:Int):Int{choose(a<2,3>(1))};')
 add('mutable','var a:Int=1;choose(a<2,3>(1))')
 add('nested-scope','{let a:Int=1;choose(a<2,3>(1))}')
 add('initializer','let a:Int=1;let b:Int=choose(a<2,3>(1));b')
 add('nested-call','let a:Int=1;choose(choose(a<2,3>(1))==7,true)')
 add('argument-block','choose({let a:Int=1;choose(a<2,3>(1))==7},true)')
 add('sibling-scopes','{let a:Int=1;discard choose(a<2,3>(1));unit};{let a:Int=1;choose(a<2,3>(1))}')
 add('two-ambiguous-pairs','let a:Int=1;let b:Int=1;four(a<2,3>(1),b<2,3>(1))',prefix='let four:Function(Bool,Bool,Bool,Bool):Int=function(w:Bool,x:Bool,y:Bool,z:Bool):Int{branch when{w&&x&&y&&z=>7,else=>9}};')
 add('named-value-arguments','let a:Int=1;let b:Int=2;let c:Int=3;choose(a<b,c>(1))')
 add('ordinary-comparison','let a:Int=1;choose(a<2,3>=1)')
 add('chain-rejected','let a:Int=1;let b:Int=2;let c:Int=3;a<b>(c)',phase='parse')
 add('initializer-not-visible','let a:Int=choose(a<2,3>(1));a',phase='semantic')
 add('later-local-not-visible','let b:Int=choose(a<2,3>(1));let a:Int=1;b',phase='semantic')
 add('sibling-not-visible','{let a:Int=1;unit};choose(a<2,3>(1))',phase='semantic')
 return rows

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--baseline',type=Path);ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args();rows=[]
 with tempfile.TemporaryDirectory(prefix='mgnc-classification-') as work:
  root=Path(work)
  for case in fixtures():
   source=case['source'].encode();path=root/(case['name']+'.mgn');path.write_bytes(source);output=root/(case['name']+'.out')
   parsed=subprocess.run([args.compiler.resolve(),'parse',path],capture_output=True,timeout=120)
   assert (parsed.returncode,parsed.stdout,parsed.stderr)==(0,b'',b''),(case,parsed.stderr)
   results={}
   for label,binary in [('candidate',args.compiler),('baseline',args.baseline)]:
    if binary is None:continue
    target=output.with_suffix('.'+label);built=subprocess.run([binary.resolve(),'build',path,'-o',target],capture_output=True,timeout=120)
    result=dict(build_exit=built.returncode,stdout_hex=built.stdout.hex(),stderr=built.stderr.decode().replace(str(root),'<fixtures>'),artifact=target.exists())
    if case['phase']:
     assert built.returncode==1 and not built.stdout and not target.exists(),(case,result)
     if case['phase']!='reject':assert 'mgnc: '+case['phase']+':' in result['stderr'],(case,result)
    else:
     assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(case,result)
     run=subprocess.run([target],capture_output=True,timeout=30);result.update(run_exit=run.returncode,run_stdout_hex=run.stdout.hex(),run_stderr_hex=run.stderr.hex())
     assert (run.returncode,run.stdout,run.stderr)==(case['expected'],b'',b''),(case,result)
    results[label]=result
   if case['phase'] and args.baseline:
    pattern=r':(\d+):(\d+) \[(\d+),(\d+)\)'
    assert re.search(pattern,results['candidate']['stderr']).groups()==re.search(pattern,results['baseline']['stderr']).groups(),results
   assert path.read_bytes()==source
   rows.append(dict(case=case['name'],source_hex=source.hex(),source_sha256=hashlib.sha256(source).hexdigest(),expected=case['expected'],phase=case['phase'],parse_exit=0,results=results,passed=True))
   args.evidence.write_text(json.dumps(dict(compiler_sha256=hashlib.sha256(args.compiler.read_bytes()).hexdigest(),records=rows,complete=False),indent=2)+'\n')
 args.evidence.write_text(json.dumps(dict(compiler_sha256=hashlib.sha256(args.compiler.read_bytes()).hexdigest(),baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest() if args.baseline else None,records=rows,complete=True,passed=True),indent=2)+'\n');print('CLASSIFICATION_OK',len(rows),'baseline',args.baseline is not None)
if __name__=='__main__':main()
