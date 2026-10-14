#!/usr/bin/env python3
"""Validate dependency postorder and real cycle edges independently."""
import argparse,random,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);args=p.parse_args()
rng=random.Random(150)
cases=[("chain",1000,[(i,i+1) for i in range(999)],False),
       ("diamond",4,[(0,1),(0,2),(1,3),(2,3)],False),
       ("cycle",1000,[(i,i+1) for i in range(999)]+[(999,0)],True),
       ("self",1,[(0,0)],True),
       ("dag",100,[(i,j) for i in range(100) for j in range(i+1,100) if rng.random()<.03],False)]
with tempfile.TemporaryDirectory(prefix="v150-graph-") as temp:
 root=Path(temp);(root/"src").mkdir()
 for module in ["Data","Tables","DependencyGraph"]:shutil.copytree(ROOT/"compiler/mgnc/src"/module,root/"src"/module)
 prefix="namespace Mgnc;use Mgnc\\Data\\{Span,Diagnostic,Paged,empty,push,lookup};use Mgnc\\Tables\\{replaceItem};use Mgnc\\DependencyGraph\\{Edge,Graph,Order,sort};"
 functions=[]
 for case,n,edges,cyclic in cases:
  encoded=",".join(f"Edge{{owner:{a},target:{b},file:0,span:span}}" for a,b in edges)
  edge_source="let edges:List<Edge>=List<Edge>["+encoded+"];"
  if case in ("chain","cycle"):
   edge_source="var edges:List<Edge>=List<Edge>[];i=0;loop while(i<999){edges=edges->append(Edge{owner:i,target:i+1,file:0,span:span});i=i+1;};"
   if case=="cycle":edge_source+="edges=edges->append(Edge{owner:999,target:0,file:0,span:span});"
  functions.append("let "+case+":Function():Result<Bool,Diagnostic>=function():Result<Bool,Diagnostic>{let span:Span=Span{start:0,end:0,line:1,column:1};var vertices:List<Int>=List<Int>[];var i:Int=0;loop while(i<"+str(n)+"){vertices=vertices->append(i);i=i+1;};"+edge_source+"let result:Order=try sort(Graph{vertices:vertices,edges:edges,size:"+str(n)+"});"+
   ("branch when{result->cycle->length()!=1=>{return Result<Bool,Diagnostic>::Ok(false);},else=>unit};let actual:Edge=branch on result->cycle->at(0){Result<Edge,IndexError>::Ok(e:Edge)=>e,Result<Edge,IndexError>::Err(e:IndexError)=>panic{\"edge\"}};var found:Bool=false;loop over(edges as e:Edge){branch when{e->owner==actual->owner&&e->target==actual->target=>{found=true;},else=>unit};};Result<Bool,Diagnostic>::Ok(found)"
   if cyclic else
   "branch when{result->cycle->length()!=0||result->values->length()!="+str(n)+"=>{return Result<Bool,Diagnostic>::Ok(false);},else=>unit};var positions:Paged<Int>=empty<Int>();i=0;loop while(i<"+str(n)+"){positions=push<Int>(positions,-1);i=i+1;};i=0;loop over(result->values as v:Int){branch when{(try lookup<Int>(positions,v))>=0=>{return Result<Bool,Diagnostic>::Ok(false);},else=>unit};positions=try replaceItem<Int>(positions,v,i);i=i+1;};loop over(edges as e:Edge){branch when{(try lookup<Int>(positions,e->target))>=(try lookup<Int>(positions,e->owner))=>{return Result<Bool,Diagnostic>::Ok(false);},else=>unit};};Result<Bool,Diagnostic>::Ok(true)")+"};")
 main="let main:Function(List<String>):Int=function(args:List<String>):Int{"
 for i,(case,_,_,_) in enumerate(cases):
  main+="branch on "+case+"(){Result<Bool,Diagnostic>::Ok(ok:Bool)=>{branch when{!ok=>{return "+str(i+1)+";},else=>unit};},Result<Bool,Diagnostic>::Err(e:Diagnostic)=>{return "+str(i+11)+";}};"
 main+="0};"
 (root/"src/app.mgn").write_text(prefix+"".join(functions)+main)
 (root/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="Mgnc"\n')
 result=subprocess.run([args.seed,"build",root/"mognitio.toml","-o",root/"probe"],capture_output=True,timeout=600)
 assert result.returncode==0,result.stderr.decode()
 result=subprocess.run([root/"probe"],capture_output=True,timeout=60)
 assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
 print("V150_DEPENDENCY_GRAPH_OK cases=5 chain=1000 actual_cycle_edges=true")
