#!/usr/bin/env python3
# Independent bounded CFG saturation oracle. It never executes the chart algorithm.
import argparse,itertools,re,subprocess,tempfile
from pathlib import Path
from generate_grammar import load
ROOT=Path(__file__).resolve().parents[2]
KEYWORDS=set('alias as branch break continue contract discard else function implements let loop on over panic product return sum template try type var when while witness true false unit namespace use public assert'.split())
OPS=['->','=>','==','!=','<=','>=','&&','||','::','{','}','(',')',';',',','\\','*','%','[',']','/','+','-','=','!','<','>',':','@']
PAT=re.compile(r'//[^\r\n]*|[ \t\r\n]+|"(?:[^"\\\r\n]|\\.)*"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|'+'|'.join(re.escape(x) for x in OPS))
class Tokens:
 def __init__(self,text):
  self.text=text;self.tokens=[];end=0
  for m in PAT.finditer(text):
   assert m.start()==end,(text,end);end=m.end();s=m.group()
   if s.isspace() or s.startswith('//'):continue
   kind=5 if s.startswith('"') else 4 if s in KEYWORDS else 1 if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',s) else 2 if s.isdigit() else 3
   self.tokens.append((s,kind,m.start(),m.end()))
  assert end==len(text);self.tokens.append(('',0,end,end));self.end=2*(len(self.tokens)-1)
  self.cursors={t[2]:2*i for i,t in enumerate(self.tokens)}
  for i,t in enumerate(self.tokens):
   if t[1]==3 and len(t[0])==2:self.cursors[t[2]+1]=2*i+1
  self.ends={t[3]:2*(i+1) for i,t in enumerate(self.tokens[:-1])}
 def terminal(self,cursor,symbol):
  i,part=divmod(cursor,2);s,kind,start,end=self.tokens[i]
  if part and (kind!=3 or len(s)!=2):return None
  begin=start+part
  if symbol=='#close':
   if kind!=3 or self.text[begin:begin+1]!='>':return None
   finish=begin+1;return self.ends.get(finish,self.cursors.get(finish))
  if part:
   options=[op for op in OPS if self.text.startswith(op,begin)]
   if not options:return None
   s=max(options,key=len);kind=3;end=begin+len(s)
  matches=(kind==1 if symbol=='#id' else kind==1 and s!='Function' if symbol=='#typeid' else kind==1 and s=='Function' if symbol=='#function' else kind==2 if symbol=='#number' else kind==5 if symbol=='#string' else s==symbol)
  return self.ends.get(end,self.cursors.get(end)) if matches and kind!=0 else None

def saturated(data,text):
 tok=Tokens(text);terms={v:k for k,v in data['terminals'].items()};families={};by_start={};changed=True
 cursors=list(range(tok.end+1))
 while changed:
  changed=False
  for rid,rule in enumerate(data['rules']):
   for start in cursors:
    paths={(start,())}
    for symbol in rule['rhs']:
     following=set()
     for current,children in paths:
      if symbol<0:
       end=tok.terminal(current,terms[symbol])
       if end is not None:following.add((end,children+((symbol,current,end),)))
      else:
       for end in list(by_start.get((symbol,current),())):following.add((end,children+((symbol,current,end),)))
     paths=following
     if not paths:break
    for end,children in paths:
     key=(rule['lhs'],start,end);entry=(rid,children)
     if entry not in families.setdefault(key,set()):
      families[key].add(entry);by_start.setdefault((rule['lhs'],start),set()).add(end);changed=True
 root=(data['nonterminals']['Module'],0,tok.end)
 return root,families

def reachable(root,families):
 todo=[root];seen=set();result={}
 while todo:
  key=todo.pop()
  if key in seen:continue
  seen.add(key)
  if key[0]<0:continue
  result[key]=families[key]
  for _,children in result[key]:todo.extend(children)
 return result

def decode(stdout):
 nodes={};root=None
 for line in stdout.splitlines():
  values=line.split()
  if values[0]=='R':root=int(values[1]);continue
  assert values[0]=='N';i,sym,slot,start,end,rule,left,right,split,alt=map(int,values[1:]);nodes[i]=(sym-1001,slot-1,start,end,rule-1,left-1,right-1,split,alt-1)
 def key(i):
  n=nodes[i];return n[0],n[2],n[3]
 def choices(i):
  n=nodes[i];result=[(n[4],n[5],n[6])];alt=n[8];seen=set()
  while alt>=0:
   assert alt not in seen;seen.add(alt);a=nodes[alt];assert a[0]==-1000;result.append((a[4],a[5],a[6]));alt=a[8]
  return result
 memo={}
 def prefix(i):
  if i<0:return {()}
  if i in memo:return memo[i]
  n=nodes[i]
  if n[0]!=0:return {(key(i),)}
  result=set()
  for _,left,right in choices(i):
   for children in prefix(left):result.add(children+((key(right),) if right>=0 else ()))
  memo[i]=result;return result
 families={}
 for i,n in nodes.items():
  if n[0]<=0:continue
  for rid,left,right in choices(i):
   assert right==-1
   for children in prefix(left):families.setdefault(key(i),set()).add((rid,children))
 assert root is not None;return key(root),families

def expression_core(data,text,families):
 tokens=Tokens(text)
 def visit(key):
  answers=set()
  for rid,children in families[key]:
   name=data['rules'][rid]['name']
   if name in ['integer','name','true','false']:
    label='int' if name=='integer' else 'name' if name=='name' else 'bool'
    answers.add((label,tokens.tokens[key[1]//2][0]))
   elif name.startswith('binary_'):
    for left,right in itertools.product(visit(children[0]),visit(children[2])):answers.add((name[7:],left,right))
   elif name=='group':answers.update(('group',x) for x in visit(children[1]))
   else:
    assert len(children)==1 and children[0][0]>0,(name,children)
    answers.update(visit(children[0]))
  return answers
 expressions=[children[5] for fs in families.values() for rid,children in fs if data['rules'][rid]['name']=='let_binding']
 assert len(expressions)==1
 return visit(expressions[0])
GOLDENS={
 'namespace A;let x:Int=1+2*3;':('add',('int','1'),('mul',('int','2'),('int','3'))),
 'namespace A;let x:Int=(1+2)*3;':('mul',('group',('add',('int','1'),('int','2'))),('int','3')),
 'namespace A;let x:Bool=(a<b)==true;':('eq',('group',('lt',('name','a'),('name','b'))),('bool','true')),
}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True);args=parser.parse_args();data=load(ROOT/'tests/mgnc/grammar.txt')
 positive=['namespace App;', 'namespace A;let x:Int=1+2*3;', 'namespace A;let x:Int=(1+2)*3;', 'namespace A;let x:Int=f<T>(a);', 'namespace A;let x:Int=f<T>==g;', 'namespace A;let x:Int=branch when{f<T>=>1,else=>2};', 'namespace A;let x:List<Int>=List<Int>[];', 'namespace A;let x:Int={let y:Int=1;y};']
 positive += ['namespace A;let x:Int=a->m();','namespace A;let x:Int=(a->f)(b);','namespace A;let x:Int=a->m<T>();','namespace A;let x:Int=loop while(false){}==unit;']
 positive.append('namespace A;let x:Bool=(a<b)==true;')
 golden_count=0;mutation_controls=set()
 negative=['namespace A;let x:Int=a<b<c;','namespace A;type T=product{x:Int};','namespace A;let x:Int=branch when{true=>1};']
 with tempfile.TemporaryDirectory(prefix='mgnc-oracle-') as work:
  for i,text in enumerate(positive+negative):
   expected_root,expected=saturated(data,text);accepted=expected_root in expected;assert accepted==(i<len(positive)),(i,accepted)
   path=Path(work)/f'{i}.mgn';path.write_text(text);p=subprocess.run([args.compiler,str(path)],capture_output=True,text=True,timeout=30)
   if not accepted:assert p.returncode==1,(i,p.stderr);continue
   assert p.returncode==0,(i,p.stderr)
   actual_root,actual=decode(p.stdout);assert actual_root==expected_root
   observed=reachable(actual_root,actual);wanted=reachable(expected_root,expected)
   assert observed==wanted,(i,'forest differs')
   if text in GOLDENS:
    assert expression_core(data,text,observed)=={GOLDENS[text]},(i,'handwritten precedence/grouping golden')
    golden_count+=1
    # Inject group erasure into observed edges; the same complete-family oracle must reject it.
    groups={key:children[1] for key,fs in observed.items() for rid,children in fs if data['rules'][rid]['name']=='group'}
    if groups:
     erased={key:{(rid,tuple(groups.get(child,child) for child in children)) for rid,children in fs} for key,fs in observed.items()}
     assert reachable(actual_root,erased)!=wanted;mutation_controls.add('group-erasure')
   ambiguous=next((key for key,fs in observed.items() if len(fs)>1),None)
   if ambiguous:
    dropped={key:set(fs) for key,fs in observed.items()};dropped[ambiguous].pop()
    assert reachable(actual_root,dropped)!=wanted;mutation_controls.add('family-deletion')
 assert golden_count==3 and len(mutation_controls)==2,(golden_count,mutation_controls)
 print(f'FOREST_ORACLE_OK goldens={golden_count} mutation_controls={len(mutation_controls)} positive={len(positive)} negative={len(negative)} all_reachable_families=True')
if __name__=='__main__':main()
