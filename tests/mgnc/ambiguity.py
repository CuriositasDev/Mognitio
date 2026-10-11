#!/usr/bin/env python3
"""Measure ambiguity growth and instrument an archive without changing the public CLI."""
import argparse,hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path
from forest_oracle import Tokens,decode,reachable,saturated
from generate_grammar import load
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def instrument(project):
 path=project/'src/Chart/column.mgn';text=path.read_text()
 text=text.replace('namespace Mgnc\\Chart;','namespace Mgnc\\Chart;\nuse Std\\Io\\{writeStdout};\nuse Mgnc\\Data\\{number};',1)
 text=text.replace('public let column:','let reportKeys:Function(Int,Int):Unit=function(keys:Int,duplicates:Int):Unit{discard writeStdout("K "+number(keys)+" "+number(duplicates)+"\\n");};\npublic let column:',1)
 text=text.replace(' let shape:Slot=try lookup<Slot>(slots,slot);',' var checked:Int=0;\n let shape:Slot=try lookup<Slot>(slots,slot);',1)
 text=text.replace(' let bin:Int=branch when{symbol<0',' var checked:Int=0;\n let bin:Int=branch when{symbol<0',1)
 for token in ['let previous:ChartItem','let previous:ForestNode','let existing:ForestNode','let old:ForestNode']:
  text=text.replace(token,'checked=checked+1;'+token)
 # Exact family duplicates are counted separately from item/terminal deduplication.
 target='return Result<Column,Diagnostic>::Ok(state);';assert text.count(target)==3
 text=text.replace(target,'reportKeys(checked,0);'+target,1)
 # The first occurrence is already instrumented; the remaining two are family matches.
 text=text.replace('=>{return Result<Column,Diagnostic>::Ok(state);','=>{reportKeys(checked,1);return Result<Column,Diagnostic>::Ok(state);')
 state_return='return Result<Column,Diagnostic>::Ok(Column{cursor:state->cursor,base:state->base,items:state->items,nodes:state->nodes,'
 assert text.count(state_return)==2
 text=text.replace(state_return,'reportKeys(checked,branch when{symbol<0=>0,else=>1});'+state_return)
 alternate='return Result<Column,Diagnostic>::Ok(Column{cursor:state->cursor,base:state->base,items:state->items,nodes:nodes,'
 assert text.count(alternate)==2;text=text.replace(alternate,'reportKeys(checked,0);'+alternate)
 final='\n Result<Column,Diagnostic>::Ok(Column{';assert text.count(final)==2
 text=text.replace(final,'\n reportKeys(checked,0);'+final);path.write_text(text)
 path=project/'src/Structural/parse.mgn';text=path.read_text()
 text=text.replace('namespace Mgnc\\Structural;','namespace Mgnc\\Structural;\nuse Std\\Io\\{writeStdout};\nuse Mgnc\\Data\\{number};',1)
 target='  itemCount=itemCount+active->items->count;';assert text.count(target)==1
 text=text.replace(target,'  discard writeStdout("C "+number(active->items->count)+" "+number(active->nodes->count)+"\\n");\n'+target)
 path.write_text(text)
 return {str(p.relative_to(project)):sha(p) for p in [project/'src/Chart/column.mgn',path]}
def fixtures():
 cells=[]
 for n in [1,8,32,128]:
  prefix='namespace A;'+''.join(f'let x{i}:Int=a{i}<b{i}>(c{i});' for i in range(n))
  arguments='namespace A;let x:Int=f<'+','.join('T'+str(i) for i in range(n))+'>(x);'
  nested='namespace A;let x:'+('List<'*n)+'Int'+('>'*n)+'=y;'
  for series,text in [('prefix',prefix),('arguments',arguments),('nested',nested)]:cells.append((series,n,text))
 mixed='namespace A;'+''.join('let x'+str(i)+':Int=f<'+','.join('T'+str(j) for j in range(32))+'>(x);' for i in range(32))
 cells.append(('mixed',32,mixed))
 for series,n,text in list(cells):
  offset=text.rindex('>' if series=='nested' else ')')
  cells.append((series+'-broken',n,text[:offset]+text[offset+1:]))
 return cells

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args()
 out=args.evidence;out.mkdir();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();archive=subprocess.check_output(['git','archive',head,'compiler/mgnc'],cwd=ROOT)
 with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(out,filter='data')
 project=out/'compiler/mgnc';entry=(ROOT/'tests/mgnc/harnesses/forest.mgn').read_text();entry=entry.replace('=>{var index:Int=0;', '=>{discard writeStdout("Q "+number(forest->comparisons->length())+"\\n");var index:Int=0;');(project/'src/mgnc.mgn').write_text(entry);patch=instrument(project)
 probe=out/'probe';p=subprocess.run([args.seed,'build',project/'mognitio.toml','-o',probe],capture_output=True,timeout=600)
 assert (p.returncode,p.stdout,p.stderr)==(0,b'',b''),p.stderr.decode()
 data=load(ROOT/'tests/mgnc/grammar.txt');rows=[];folder=out/'fixtures';folder.mkdir();manifest=[]
 for series,n,text in fixtures():
  name=f'{series}-{n}';path=folder/(name+'.mgn');path.write_text(text);broken=series.endswith('-broken');tokens=Tokens(text)
  with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
   start=time.monotonic();child=subprocess.Popen([probe,path],stdout=stdout,stderr=stderr);timed=False
   while True:
    pid,status,usage=os.wait4(child.pid,os.WNOHANG)
    if pid:break
    if time.monotonic()-start>120:child.kill();pid,status,usage=os.wait4(child.pid,0);timed=True;break
    time.sleep(.001)
   seconds=time.monotonic()-start;child.returncode=os.waitstatus_to_exitcode(status)
  stdout=(out/(name+'.stdout')).read_text();stderr=(out/(name+'.stderr')).read_text();lines=stdout.splitlines();columns=[list(map(int,l.split()[1:])) for l in lines if l.startswith('C ')];keys=[list(map(int,l.split()[1:])) for l in lines if l.startswith('K ')]
  assert not timed and child.returncode==(1 if broken else 0),(name,child.returncode,stderr)
  assert (not stderr) if not broken else 'mgnc: parse:' in stderr,(name,stderr)
  row=dict(series=series,n=n,name=name,bytes=path.stat().st_size,scalars=len(text),tokens=len(tokens.tokens)-1,sha256=sha(path),exit=child.returncode,stderr=stderr,timeout=timed,instrumented_seconds=seconds,instrumented_rss_mib=usage.ru_maxrss/1024,items=sum(c[0] for c in columns),forest_records=sum(c[1] for c in columns),max_column=max(c[0] for c in columns),key_comparisons=sum(k[0] for k in keys),duplicate_family_attempts=sum(k[1] for k in keys),passed=True)
  manifest.append(dict(group='ambiguity',name=name,path=path.name,bytes=path.stat().st_size,sha256=sha(path),expected=1 if broken else 0,**({'phase':'parse'} if broken else {})))
  if not broken:
   raw='\n'.join(l for l in lines if l.startswith(('N ','R ')));root,actual=decode(raw);observed=reachable(root,actual)
   # decode retains shared child symbols, never enumerating type/value tree products.
   row['reachable_symbols']=len(observed);row['reachable_families']=sum(map(len,observed.values()))
   node_rows=[list(map(int,l.split()[1:])) for l in lines if l.startswith('N ')]
   row['stored_families']=sum(x[1]>=1001 or x[1]==1 for x in node_rows)
   indexed={x[0]:x for x in node_rows}
   for node in node_rows:
    if node[1]<1001:continue
    seen=set();current=node
    while True:
     family=tuple(current[5:9]);assert family not in seen,(name,'duplicate stored family',node[0]);seen.add(family)
     if current[9]==0:break
     current=indexed[current[9]-1]
   row['comparison_frontiers']=sum(int(l.split()[1]) for l in lines if l.startswith('Q '))
   if series=='prefix':
    applications=[key for key,choices in observed.items() if any(data['rules'][rid]['name']=='generic_apply' for rid,_ in choices)]
    assert len(applications)==n and row['comparison_frontiers']>=n,(name,len(applications),row['comparison_frontiers'])
   if series in ['arguments','mixed']:
    arguments=[choices for key,choices in observed.items() if key[0]==data['nonterminals']['Argument']]
    assert len(arguments)==(n if series=='arguments' else n*n),(name,len(arguments))
    for choices in arguments:assert {data['rules'][rid]['name'] for rid,_ in choices}=={'argument_type','argument_value'},name
    row['independent_ambiguous_arguments']=len(arguments)
   if n==1:
    expected_root,expected=saturated(data,text);assert root==expected_root and observed==reachable(expected_root,expected),name;row['all_families_oracle']=True
  if broken and n==1:
   root,expected=saturated(data,text);assert root not in expected;row['rejection_oracle']=True
  previous=next((r for r in reversed(rows) if r['series']==series),None)
  if previous:row['growth_ratios']={k:row[k]/previous[k] for k in ['bytes','tokens','items','forest_records','key_comparisons','instrumented_seconds','instrumented_rss_mib']}
  rows.append(row);result=dict(source_revision=head,compiler_sha256=sha(args.compiler),probe_sha256=sha(probe),instrumented_files=patch,records=rows)
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('AMBIGUITY_CELL_OK',name,row['items'],row['forest_records'],flush=True)
 (folder/'manifest.json').write_text(json.dumps(dict(cases=manifest),indent=2)+'\n')
 # The public executable receives the identical fixtures; supplementary budgets are descriptive.
 p=subprocess.run(['python3',str(ROOT/'tests/mgnc/parse_measure.py'),'--compiler',args.compiler,'--fixtures',folder,'--evidence',out/'measurement.json'],stdout=(out/'measurement.log').open('w'),stderr=subprocess.STDOUT)
 assert p.returncode==0
 result['complete']=True;result['passed']=all(r['passed'] for r in rows);(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print('AMBIGUITY_GROWTH_OK',len(rows),flush=True)
if __name__=='__main__':main()
