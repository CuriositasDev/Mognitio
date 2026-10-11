#!/usr/bin/env python3
# Closed structural grammar: P140-01..10; generated tables are compiler source.
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(path):
 rows=[tuple(x.strip() for x in line.split('|',2)) for line in path.read_text().splitlines() if line.strip()]
 names=list(dict.fromkeys(x[0] for x in rows));ns={x:i+1 for i,x in enumerate(names)}
 terms=list(dict.fromkeys(y for _,_,rhs in rows for y in rhs.split() if y not in ns));ts={x:-i-1 for i,x in enumerate(terms)}
 rules=[dict(lhs=ns[lhs],name=tag,rhs=[ns[x] if x in ns else ts[x] for x in rhs.split()]) for lhs,tag,rhs in rows]
 assert all(not t[0].isupper() for t in terms),('undefined nonterminal',terms)
 assert all(t in {'#id','#typeid','#function','#number','#string','#close'} or not t.startswith('#') for t in terms),'undefined terminal kind'
 assert len({(x['lhs'],tuple(x['rhs'])) for x in rules})==len(rules),'duplicate production'
 assert len({x['name'] for x in rules})==len(rules),'duplicate tag'
 nullable=set();first={n:set() for n in ns.values()}
 while True:
  before=(len(nullable),sum(map(len,first.values())))
  for r in rules:
   for x in r['rhs']:
    first[r['lhs']].update({x} if x<0 else first[x])
    if x not in nullable:break
   else:nullable.add(r['lhs'])
  if before==(len(nullable),sum(map(len,first.values()))):break
 graph={n:set() for n in ns.values()}
 for r in rules:
  for i,x in enumerate(r['rhs']):
   if x>0 and all(y in nullable for j,y in enumerate(r['rhs']) if i!=j):graph[r['lhs']].add(x)
 for n in graph:
  todo=list(graph[n]);seen=set()
  while todo:
   x=todo.pop();assert x!=n,('zero-consumption cycle',n)
   if x not in seen:seen.add(x);todo.extend(graph[x])
 reached={1}
 while True:
  more={x for r in rules if r['lhs'] in reached for x in r['rhs'] if x>0}
  if more<=reached:break
  reached.update(more)
 assert reached==set(ns.values()),('unreachable',set(ns.values())-reached)
 slots=[];starts=[];predict=[]
 for i,r in enumerate(rules):
  starts.append(len(slots))
  for d in range(len(r['rhs'])+1):
   slots.append(dict(lhs=r['lhs'],rule=i,dot=d,next=r['rhs'][d] if d<len(r['rhs']) else 0))
  look=set()
  for x in r['rhs']:
   look.update({x} if x<0 else first[x])
   if x not in nullable:break
  else:look.add(0)
  predict.append(sorted(look))
 return dict(nonterminals=ns,terminals=ts,rules=rules,slots=slots,starts=starts,first=predict,nullable=sorted(nullable))
def mgn(data,reverse_predictions=False):
 lines=[r'namespace Mgnc\Grammar;',r'use Mgnc\Data\{Paged,empty,push,lookup,Diagnostic};',r'use Mgnc\Source\{Lexeme};',r'use Mgnc\GrammarData\{Slot as StoredSlot,Prediction as StoredPrediction};']
 count=(len(data['slots'])+63)//64
 lines += ['use Mgnc\\GrammarPart'+str(i)+'\\{extend as extend'+str(i)+'};' for i in range(count)]
 lines += ['// Generated structural table. Production IDs are independent of source partitioning.',
 'public alias Slot=StoredSlot;','public alias Prediction=StoredPrediction;',
 'let makeSlots:Function():Paged<Slot>=function():Paged<Slot>{',' var result:Paged<Slot>=empty<Slot>();']
 lines += [' result=extend'+str(i)+'(result);' for i in range(count)]
 lines += [' result','};','public let slots:Paged<Slot>=makeSlots();']
 lines+=['let makePredictions:Function():Paged<List<Prediction>>=function():Paged<List<Prediction>>{',' var result:Paged<List<Prediction>>=empty<List<Prediction>>();',' result=push<List<Prediction>>(result,List<Prediction>[]);']
 for nt in data['nonterminals'].values():
  values=[]
  for i,r in enumerate(data['rules']):
   if r['lhs']==nt:values.append('Prediction{slot:'+str(data['starts'][i])+',first:'+str(sum(1<<(-x-1) for x in data['first'][i] if x<0))+',nullable:'+str(0 in data['first'][i]).lower()+'}')
  if reverse_predictions:values.reverse()
  lines.append(' result=push<List<Prediction>>(result,List<Prediction>['+','.join(values)+']);')
 lines+=[' result','};','public let predictions:Paged<List<Prediction>>=makePredictions();']
 for name,ident in data['nonterminals'].items():lines.append('public let nt'+name+':Int='+str(ident)+';')
 for i,r in enumerate(data['rules']):lines.append('public let rule'+''.join(x.title() for x in r['name'].split('_'))+':Int='+str(i)+';')
 lines+=['public let closeTerminal:Int='+str(data['terminals']['#close'])+';']
 assert len(data['terminals'])<=62,'extend the fixed grammar lookahead word before adding terminals'
 def power(name):return str(1<<(-data['terminals'][name]-1))
 lines+=['public type Lookahead=product{ordinary:Int;extra:Int;};','public let lookahead:Function(Lexeme,Lexeme):Lookahead=function(token:Lexeme,close:Lexeme):Lookahead{',' let ordinary:Int=branch when{',' token->kind==1=>'+power('#id')+',',' token->kind==2=>'+power('#number')+',',' token->kind==5=>'+power('#string')+',']
 for term,ident in data['terminals'].items():
  if not term.startswith('#'):lines.append(' token->text=='+json.dumps(term)+'=>'+power(term)+',')
 lines+=[' else=>0,',' };',' let extra:Int=branch when{token->kind==1=>branch when{token->text=="Function"=>'+power('#function')+',else=>'+power('#typeid')+'},close->text==">"=>'+power('#close')+',else=>0};',' Lookahead{ordinary:ordinary,extra:extra}','};','public let possible:Function(Prediction,Lookahead):Bool=function(prediction:Prediction,ahead:Lookahead):Bool{',' prediction->nullable||(ahead->ordinary>0&&(prediction->first/ahead->ordinary)%2==1)||(ahead->extra>0&&(prediction->first/ahead->extra)%2==1)','};']

 lines+=['public let matches:Function(Int,Lexeme):Bool=function(symbol:Int,token:Lexeme):Bool{',' branch when{']
 for term,ident in data['terminals'].items():
  if term=='#id':cond='token->kind==1'
  elif term=='#typeid':cond='token->kind==1&&token->text!="Function"'
  elif term=='#function':cond='token->kind==1&&token->text=="Function"'
  elif term=='#number':cond='token->kind==2'
  elif term=='#string':cond='token->kind==5'
  else:cond='token->text=='+json.dumps('>' if term=='#close' else term)
  lines.append('  symbol=='+str(ident)+'=>'+cond+',')
 lines+=['  else=>false,',' }','};']
 return '\n'.join(lines)+'\n'
def sources(data):
 result={'Grammar/table.mgn':mgn(data)}
 result['GrammarData/types.mgn']=r"""namespace Mgnc\GrammarData;
public type Slot=product{lhs:Int;rule:Int;dot:Int;next:Int;};
public type Prediction=product{slot:Int;first:Int;nullable:Bool;};
"""
 for page,start in enumerate(range(0,len(data['slots']),64)):
  lines=['namespace Mgnc\\GrammarPart'+str(page)+';',r'use Mgnc\Data\{Paged,push};',r'use Mgnc\GrammarData\{Slot};',
         '// Generated fixed grammar slots; every part is included in the C1 inventory.',
         'public let extend:Function(Paged<Slot>):Paged<Slot>=function(initial:Paged<Slot>):Paged<Slot>{',
         ' var result:Paged<Slot>=initial;',' loop over(List<Slot>[']
  lines += [' Slot{'+','.join(f'{k}:{v}' for k,v in slot.items())+'},' for slot in data['slots'][start:start+64]]
  lines += [' ] as value:Slot){result=push<Slot>(result,value);};',' result','};']
  result[f'GrammarPart{page}/slots.mgn']='\n'.join(lines)+'\n'
 return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 data=load(ROOT/'tests/mgnc/grammar.txt')
 for name,text in sources(data).items():
  target=ROOT/'compiler/mgnc/src'/name
  if args.check:assert target.read_text()==text,('generated grammar differs',name)
  else:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
 print(f"GRAMMAR_OK productions={len(data['rules'])} slots={len(data['slots'])} nonterminals={len(data['nonterminals'])} zero_cycles=0")
if __name__=='__main__':main()
