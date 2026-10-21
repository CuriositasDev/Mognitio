#!/usr/bin/env python3
"""Check actual frame-point indexing against scan and independent site values."""
from pathlib import Path
import subprocess,json,hashlib,shutil,random
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'project';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for module in ['Data','IntMap','WholeFrameData']:shutil.copytree(root/'compiler/mgnc/src'/module,project/'src'/module)
(project/'mognitio.toml').write_text('[project]\nname="mgnc"\nroot_namespace="Mgnc"\n')
text=(root/'compiler/mgnc/src/WholeMachineCheck/verify.mgn').read_text();helpers=text[text.index('// This index is local'):text.index('public let verify:Function(Native,Code)')];(out/'tested-helpers.mgn').write_text(helpers)
prefix=r'''namespace Mgnc;
use Mgnc\Data\{Paged,Diagnostic,empty,push,lookup,number};
use Mgnc\WholeFrameData\{Point};
use Mgnc\IntMap\{Map,create,get,put};
use Std\Numeric\{Bits};
use Std\Io\{writeStdout};
'''
functions=r'''
type Query=product{operation:Int;value:Int;};
let scan:Function(Paged<Point>,Paged<Int>,Int):Result<Map,Diagnostic>=function(points:Paged<Point>,labels:Paged<Int>,block:Int):Result<Map,Diagnostic>{
 var roots:Map=create();var ordinal:Int=0;
 loop over(points->pages->append(points->tail) as page:List<Point>){loop over(page as point:Point){branch when{point->block==block&&point->operation>=0=>{roots=try put(roots,point->operation,try lookup<Int>(labels,ordinal));},else=>unit};ordinal=ordinal+1;};};
 Result<Map,Diagnostic>::Ok(roots)
};
let exercise:Function(List<Point>,List<Int>,Int,List<Query>,Bool):Unit=function(items:List<Point>,values:List<Int>,block:Int,expected:List<Query>,bad:Bool):Unit{
 var points:Paged<Point>=empty<Point>();loop over(items as point:Point){points=push<Point>(points,point);};var labels:Paged<Int>=empty<Int>();loop over(values as label:Int){labels=push<Int>(labels,label);};
 let index:PointIndex=branch on indexPoints(points){Result<PointIndex,Diagnostic>::Ok(value:PointIndex)=>value,Result<PointIndex,Diagnostic>::Err(error:Diagnostic)=>panic{"index preparation"}};
 let actual:Result<Map,Diagnostic>=rootsAt(index,labels,block);let reference:Result<Map,Diagnostic>=scan(points,labels,block);
 branch on actual{
  Result<Map,Diagnostic>::Ok(roots:Map)=>{assert !bad;branch on reference{Result<Map,Diagnostic>::Ok(old:Map)=>{loop over(expected as query:Query){let observed:Int=branch on get(roots,query->operation){Result<Int,Diagnostic>::Ok(value:Int)=>value,Result<Int,Diagnostic>::Err(error:Diagnostic)=>panic{"query"}};branch when{observed!=query->value=>{discard writeStdout("MISMATCH block="+number(block)+" op="+number(query->operation)+" actual="+number(observed)+" expected="+number(query->value)+" points="+number(items->length())+" labels="+number(values->length())+"\n");},else=>unit};assert observed==query->value;assert (branch on get(old,query->operation){Result<Int,Diagnostic>::Ok(value:Int)=>value,Result<Int,Diagnostic>::Err(error:Diagnostic)=>panic{"old query"}})==query->value;};},Result<Map,Diagnostic>::Err(error:Diagnostic)=>panic{"old unexpectedly rejected"}};},
  Result<Map,Diagnostic>::Err(error:Diagnostic)=>{assert bad;branch on reference{Result<Map,Diagnostic>::Err(old:Diagnostic)=>{assert error->phase==old->phase;assert error->message==old->message;assert error->span->start==old->span->start;assert error->span->end==old->span->end;},Result<Map,Diagnostic>::Ok(roots:Map)=>panic{"old unexpectedly accepted"}};}
 };
};
'''
blocks=[0,1,2,31,64,257,1048577];operations=[0,1,7,65,999];definitions=[];calls=[];cases=[];r=random.Random(170172)
for size in [0,1,3,7,63,64,65,127,257]:
 points=[(r.choice([-1,*blocks]),r.choice([-2,-1,0,1,7,65])) for _ in range(size)]
 # Force repeated sites and both ignored negative categories at page boundaries.
 if size>=3:points[-3:]=[(0,7),(0,7),(-1,1)]
 pl='List<Point>['+','.join('Point{block:'+str(b)+',operation:'+str(o)+';roots:List<Bits<64>>[];handoff:List<Bits<64>>[];}'.replace(';',',').replace(',}', '}') for b,o in points)+']'
 definitions.append('let points'+str(size)+':List<Point>='+pl+';')
 for limit in sorted({0,max(0,size-1),size}):
  labels=[100+i*17 for i in range(limit)];vl='List<Int>['+','.join(map(str,labels))+']';definitions.append('let labels'+str(size)+'x'+str(limit)+':List<Int>='+vl+';')
  for block in blocks:
   chosen=[i for i,(b,o) in enumerate(points) if b==block and o>=0];bad=any(i>=limit for i in chosen);expected={}
   if not bad:
    for i in chosen:expected[points[i][1]]=labels[i]
   queries=[dict(operation=o,value=expected.get(o,-2)) for o in operations];q='List<Query>['+','.join('Query{operation:'+str(x['operation'])+',value:'+str(x['value'])+'}' for x in queries)+']';calls.append('exercise(points'+str(size)+',labels'+str(size)+'x'+str(limit)+','+str(block)+','+q+','+str(bad).lower()+');');cases.append(dict(points=size,label_count=limit,block=block,error=bad,queries=queries))
expected=dict(cases=cases,seed=170172,independent_rule='original-order selection by equal nonnegative block and operation; labels read only for selected points; last duplicate site wins');(out/'expected.json').write_text(json.dumps(expected,indent=2)+'\n')
entry=prefix+helpers+functions+'\n'+'\n'.join(definitions)+'\nlet main:Function(List<String>):Int=function(args:List<String>):Int{'+''.join(calls)+'discard writeStdout("POINT_INDEX_ORACLE_OK cases='+str(len(cases))+'\\n");0};\n';(project/'src/mgnc.mgn').write_text(entry)
inputs=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');seed=args.seed.resolve();r=subprocess.run([seed,'build',project/'mognitio.toml','-o',out/'probe'],capture_output=True,timeout=180);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr);assert (r.returncode,r.stdout,r.stderr)==(0,b'',b''),(r.returncode,r.stderr[-2500:])
r=subprocess.run([out/'probe'],capture_output=True,timeout=180);(out/'run.stdout').write_bytes(r.stdout);(out/'run.stderr').write_bytes(r.stderr);assert (r.returncode,r.stdout,r.stderr)==(0,('POINT_INDEX_ORACLE_OK cases='+str(len(cases))+'\n').encode(),b''),(r.returncode,r.stdout,r.stderr);assert all(sha(project/p['path'])==p['sha256'] for p in inputs);(out/'results.json').write_text(json.dumps(dict(kind='actual-helper-vs-original-scan-and-independent-expected-values',cases=len(cases),expected_sha256=sha(out/'expected.json'),helper_sha256=sha(out/'tested-helpers.mgn'),probe_sha256=sha(out/'probe')),indent=2)+'\n');print(r.stdout.decode(),end='')

mutant=out/'wrong-order';shutil.copytree(project,mutant);p=mutant/'src/mgnc.mgn';text=p.read_text();assert text.count('lookup<Int>(selected,position)')==1;p.write_text(text.replace('lookup<Int>(selected,position)','lookup<Int>(selected,selected->count-1-position)'))
r=subprocess.run([seed,'build',mutant/'mognitio.toml','-o',out/'wrong-order-probe'],capture_output=True,timeout=180);(out/'negative-build.stdout').write_bytes(r.stdout);(out/'negative-build.stderr').write_bytes(r.stderr);assert (r.returncode,r.stdout,r.stderr)==(0,b'',b''),(r.returncode,r.stderr)
r=subprocess.run([out/'wrong-order-probe'],capture_output=True,timeout=180);(out/'negative-run.stdout').write_bytes(r.stdout);(out/'negative-run.stderr').write_bytes(r.stderr);assert r.returncode==5 and r.stdout==b'MISMATCH block=0 op=7 actual=100 expected=117 points=3 labels=2\n' and b'assertion: assertion failed (outside test)' in r.stderr,(r.returncode,r.stdout,r.stderr)
(out/'negative-results.json').write_text(json.dumps(dict(wrong_duplicate_order_detected=True,exit=r.returncode,mutant_source_sha256=sha(p),probe_sha256=sha(out/'wrong-order-probe')),indent=2)+'\n');print('POINT_INDEX_ORACLE_NEGATIVE_OK wrong_duplicate_order_detected=True')
