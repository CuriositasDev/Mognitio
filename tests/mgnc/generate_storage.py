#!/usr/bin/env python3
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generate(prefix,record,fields,lanes):
 page=prefix+'Page';store=prefix+'Store';lines=['namespace Mgnc\\'+prefix+'Storage;',r'use Mgnc\Data\{Paged,empty,push,lookup,Diagnostic,problem,Span};',r'use Mgnc\Tables\{replaceItem,replaceList,atList};','use Mgnc\\'+('SourceData' if prefix=='Token' else 'ForestData')+'\\{'+record+'};','// Generated scalar pages: no mutable collection, raw pointer, or seed/runtime extension.']
 lines+=['public type '+page+'=product{'+''.join(f'{f}{i}:'+('String' if f=='text' else 'Int')+';' for i in range(lanes) for f in fields)+'};','public type '+store+'=product{pages:Paged<'+page+'>;tail:List<'+record+'>;count:Int;};','let zero:'+page+'='+page+'{'+','.join(f'{f}{i}:'+('""' if f=='text' else '0') for i in range(lanes) for f in fields)+'};',f'public let empty{prefix}s:Function():{store}=function():{store}{{{store}{{pages:empty<{page}>(),tail:List<{record}>[],count:0}}}};']
 lines+=[f'let writePage:Function({page},Int,{record}):{page}=function(page:{page},lane:Int,value:{record}):{page}{{',page+'{'+','.join(f'{f}{i}:branch when{{lane=={i}=>value->{f},else=>page->{f}{i}}}' for i in range(lanes) for f in fields)+'}','};']
 lines+=[f'let readPage:Function({page},Int):{record}=function(page:{page},lane:Int):{record}{{branch when{{']
 for i in range(lanes):lines.append(('else' if i==lanes-1 else 'lane=='+str(i))+'=>'+record+'{'+','.join(f'{f}:page->{f}{i}' for f in fields)+'},')
 lines+=['}};']
 lines += [f'let packPage:Function(List<{record}>):{page}=function(values:List<{record}>):{page}{{']
 for i in range(lanes):lines.append(f' let v{i}:{record}=branch on values->at({i}){{Result<{record},IndexError>::Ok(value:{record})=>value,Result<{record},IndexError>::Err(error:IndexError)=>panic {{"incomplete scalar page"}}}};')
 lines += [page+'{'+','.join(f'{f}{i}:v{i}->{f}' for i in range(lanes) for f in fields)+'}','};']
 lines += [f'public let add{prefix}:Function({store},{record}):{store}=function(table:{store},value:{record}):{store}{{',
  f' var pages:Paged<{page}>=table->pages;var tail:List<{record}>=table->tail;',
  f' branch when{{tail->length()=={lanes}=>{{pages=push<{page}>(pages,packPage(tail));tail=List<{record}>[];}},else=>unit}};',
  f' {store}{{pages:pages,tail:tail->append(value),count:table->count+1}}','};']
 lines+=[f'public let get{prefix}:Function({store},Int):Result<{record},Diagnostic>=function(table:{store},index:Int):Result<{record},Diagnostic>{{',f' branch when{{index<0||index>=table->count=>{{return Result<{record},Diagnostic>::Err(problem("internal",Span{{start:0,end:0,line:1,column:1}},"invalid {prefix.lower()} arena index"));}},else=>unit}};',f' branch when{{index/{lanes}==table->pages->count=>{{return atList<{record}>(table->tail,index%{lanes});}},else=>unit}};',f' let page:{page}=try lookup<{page}>(table->pages,index/{lanes});',f' Result<{record},Diagnostic>::Ok(readPage(page,index%{lanes}))','};']
 lines+=[f'public let set{prefix}:Function({store},Int,{record}):Result<{store},Diagnostic>=function(table:{store},index:Int,value:{record}):Result<{store},Diagnostic>{{',f' let checked:{record}=try get{prefix}(table,index);',f' branch when{{index/{lanes}==table->pages->count=>Result<{store},Diagnostic>::Ok({store}{{pages:table->pages,tail:replaceList<{record}>(table->tail,index%{lanes},value),count:table->count}}),else=>{{',f' let previous:{page}=try lookup<{page}>(table->pages,index/{lanes});',f' let pages:Paged<{page}>=try replaceItem<{page}>(table->pages,index/{lanes},writePage(previous,index%{lanes},value));',f' Result<{store},Diagnostic>::Ok({store}{{pages:pages,tail:table->tail,count:table->count}})',' }}','};']
 return '\n'.join(lines)+'\n'
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
 for prefix,record,fields,lanes in [('Node','ForestNode','symbol slot start end rule left right split alternatives'.split(),16),('Item','ChartItem','slot origin node'.split(),16),('Token','Lexeme','kind text start end line column scalarStart scalarEnd endLine endColumn'.split(),16)]:
  target=ROOT/f'compiler/mgnc/src/{prefix}Storage/data.mgn';text=generate(prefix,record,fields,lanes)
  if args.check:assert target.read_text()==text
  else:target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
 print('STORAGE_GENERATION_OK')
if __name__=='__main__':main()
