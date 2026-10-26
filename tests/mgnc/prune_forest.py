"""Bounded recursive forest oracle against compiled iterative prune implementations."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,tempfile
FIELDS=['symbol','slot','start','end','rule','left','right','split','alternatives']
def node(symbol,left=-1,right=-1,alt=-1,rule=7,start=2,end=9,slot=3,split=5):
 return dict(zip(FIELDS,[symbol,slot,start,end,rule,left,right,split,alt]))
def reference(nodes,root,rejected):
 output=[];memo={}
 def visit(i):
  if i<0:return -1
  if i in memo:return memo[i]
  n=nodes[i];left=visit(n['left']);right=visit(n['right']);alt=visit(n['alternatives'])
  alive=i not in rejected and (n['left']<0 or left>=0) and (n['right']<0 or right>=0)
  if alive:
   result=len(output);output.append(dict(n,left=left,right=right,alternatives=alt))
  elif alt<0 or n['symbol']==-1000:result=alt
  else:
   chosen=output[alt];result=len(output)
   output.append(dict(n,**{k:chosen[k] for k in ['rule','left','right','split','alternatives']}))
  memo[i]=result;return result
 result=visit(root);return output,result
def cases():
 rows=[]
 def add(name,nodes,root,rejected=()):rows.append(dict(name=name,nodes=nodes,root=root,rejected=list(rejected)))
 add('leaf',[node(-1)],0)
 diamond=[node(-1),node(-2),node(0,0,1),node(42,2,2),node(99)]
 for name,rejected in [('shared',[]),('dead-leaf',[1]),('dead-branch',[2]),('dead-root',[3]),('unreachable-rejection',[4]),('duplicate-rejection',[1,1])]:
  add(name,diamond,3,rejected)
 alternative=[node(-1),node(-2),node(-1000,1,rule=22,split=8),node(42,0,alt=2,rule=11)]
 for name,rejected in [('all-alternatives',[]),('promote-dead-child',[0]),('promote-rejected-root',[3]),('dead-alternative',[2]),('both-families-dead',[0,1]),('family-record-root',[0])]:
  add(name,alternative,2 if name=='family-record-root' else 3,rejected)
 add('forward-shared',[node(42,2,1,3),node(-1),node(-2),node(-1000,2,1)],0)
 chain=[node(-1)]
 for i in range(1,81):chain.append(node(0,i-1,0))
 add('paged-shared-chain',chain,80)
 # Handwritten checks anchor the recursive model's shared-node and promotion behavior.
 out,root=reference(diamond,3,[]);assert out==diamond[:4] and root==3
 out,root=reference(alternative,3,[0]);assert len(out)==3 and root==2
 assert out[2]==dict(alternative[3],rule=22,left=0,right=-1,split=8,alternatives=-1)
 return rows
HEADER=r"""namespace Mgnc;
use Mgnc\Data\{Diagnostic,Span,number};
use Mgnc\Classification\{prune};
use Mgnc\Forest\{SyntaxForest,ComparisonFailure};
use Mgnc\ForestData\{ForestNode};
use Mgnc\NodeStorage\{NodeStore,emptyNodes,addNode,getNode};
use Mgnc\Source\{Snapshot};
use Mgnc\SourceData\{Site};
use Mgnc\TokenStorage\{emptyTokens};
use Std\Io\{writeStdout};
type Case=product{nodes:List<ForestNode>;root:Int;rejected:List<Int>;};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let source:Snapshot=Snapshot{text:"sentinel",tokens:emptyTokens(),end:Site{span:Span{start:2,end:9,line:1,column:3},scalarStart:2,scalarEnd:9,endLine:1,endColumn:10}};
 let cases:List<Case>=__CASES__;
 var ordinal:Int=0;
 loop over(cases as test:Case){
  var nodes:NodeStore=emptyNodes();loop over(test->nodes as n:ForestNode){nodes=addNode(nodes,n);};
  let input:SyntaxForest=SyntaxForest{source:source,nodes:nodes,root:test->root,itemCount:37,comparisons:List<ComparisonFailure>[ComparisonFailure{start:4,cursor:7}]};
  let result:SyntaxForest=branch on prune(input,test->root,test->rejected){Result<SyntaxForest,Diagnostic>::Ok(value:SyntaxForest)=>value,Result<SyntaxForest,Diagnostic>::Err(error:Diagnostic)=>{return 3;}};
  branch when{result->itemCount!=37||result->source->text!="sentinel"||result->source->end->endColumn!=10||result->comparisons->length()!=1=>{return 4;},else=>unit};
  discard writeStdout("C "+number(ordinal)+" "+number(result->root+1)+" "+number(result->nodes->count)+"\n");
  var index:Int=0;
  loop while(index<result->nodes->count){
   let n:ForestNode=branch on getNode(result->nodes,index){Result<ForestNode,Diagnostic>::Ok(value:ForestNode)=>value,Result<ForestNode,Diagnostic>::Err(error:Diagnostic)=>{return 5;}};
   discard writeStdout("N "+number(n->symbol+1001)+" "+number(n->slot+1)+" "+number(n->start)+" "+number(n->end)+" "+number(n->rule+1)+" "+number(n->left+1)+" "+number(n->right+1)+" "+number(n->split)+" "+number(n->alternatives+1)+"\n");
   index=index+1;
  };
  ordinal=ordinal+1;
 };
 0
};
"""
def generate(rows):
 entries=[]
 for row in rows:
  nodes='List<ForestNode>['+','.join('ForestNode{'+','.join(k+':'+str(n[k]) for k in FIELDS)+'}' for n in row['nodes'])+']'
  entries.append('Case{nodes:'+nodes+',root:'+str(row['root'])+',rejected:List<Int>['+','.join(map(str,row['rejected']))+']}')
 return HEADER.replace('__CASES__','List<Case>['+','.join(entries)+']')
def expected(rows):
 lines=[]
 for i,row in enumerate(rows):
  nodes,root=reference(row['nodes'],row['root'],row['rejected']);lines.append(f'C {i} {root+1} {len(nodes)}')
  for n in nodes:
   values=[n[k]+(1001 if k=='symbol' else 1 if k in ['slot','rule','left','right','alternatives'] else 0) for k in FIELDS]
   lines.append('N '+' '.join(map(str,values)))
 return ('\n'.join(lines)+'\n').encode()
def project(source,destination,entry):
 destination.mkdir();(destination/'src').mkdir()
 (destination/'mognitio.toml').write_text('[project]\nname = "mgnc"\nroot_namespace = "Mgnc"\n')
 (destination/'src/mgnc.mgn').write_text(entry)
 modules={}
 for path in (source/'src').rglob('*.mgn'):
  namespace=re.search(r'namespace\s+([\w\\]+)\s*;',path.read_text()).group(1);modules.setdefault(namespace,[]).append(path)
 visited=set();pending=re.findall(r'use\s+(Mgnc(?:\\\w+)*)\\\{',entry)
 while pending:
  namespace=pending.pop()
  if namespace in visited:continue
  visited.add(namespace);assert namespace in modules
  for src in modules[namespace]:
   dst=destination/'src'/src.relative_to(source/'src');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
   pending+=re.findall(r'use\s+(Mgnc(?:\\\w+)*)\\\{',src.read_text())
 return sorted(visited)
def verify(source, compiler, output):
 output.mkdir();rows=cases();entry=generate(rows);golden=expected(rows);records=[]
 (output/'cases.json').write_text(json.dumps(rows,indent=2)+'\n');(output/'expected.stdout').write_bytes(golden)
 for label in ['candidate']:
  root=output/label;modules=project(source,root,entry);binary=output/(label+'.elf')
  with (output/(label+'.build.stdout')).open('xb') as so,(output/(label+'.build.stderr')).open('xb') as se:build=subprocess.run([str(compiler),'build',str(root/'mognitio.toml'),'-o',str(binary)],stdout=so,stderr=se,timeout=1200)
  assert build.returncode==0,(label,'build')
  run=subprocess.run([str(binary)],capture_output=True,timeout=60)
  (output/(label+'.stdout')).write_bytes(run.stdout);(output/(label+'.stderr')).write_bytes(run.stderr)
  assert (run.returncode,run.stdout,run.stderr)==(0,golden,b''),(label,'forest oracle mismatch')
  records.append(dict(label=label,modules=modules,cases=len(rows),artifact_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),output_sha256=hashlib.sha256(run.stdout).hexdigest()))
 result=dict(status='PassedPruneReachability',cases=len(rows),records=records,scope='Compiled source checked against independent recursive oracle: exact forest nodes/root, shared DAGs, alternatives, rejected ancestors, forward IDs, page boundaries and retained metadata.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
def main():
 root=Path(__file__).resolve().parents[2]
 parser=argparse.ArgumentParser()
 parser.add_argument('--compiler',type=Path,default=root/'bin/mgn')
 parser.add_argument('--source',type=Path,default=root/'compiler/mgnc')
 parser.add_argument('--output',type=Path)
 args=parser.parse_args()
 if args.output:
  verify(args.source.resolve(),args.compiler.resolve(),args.output.resolve())
 else:
  with tempfile.TemporaryDirectory(prefix='prune-forest-') as directory:
   verify(args.source.resolve(),args.compiler.resolve(),Path(directory)/'evidence')
if __name__=='__main__':main()
