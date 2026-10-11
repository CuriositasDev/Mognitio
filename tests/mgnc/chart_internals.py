#!/usr/bin/env python3
"""Persistent arena boundaries and invalid grammar rejection, independent of parser."""
import argparse,tempfile
from pathlib import Path
from shared_lexer import run_entry
from generate_grammar import load
ROOT=Path(__file__).resolve().parents[2]
def grammar_checks():
 original=(ROOT/'tests/mgnc/grammar.txt').read_text()
 mutations=[original+'Module | duplicate | Namespace Uses Declarations\n',
            original+'Unused | dead | ;\n',
            original.replace('Namespace Uses Declarations','Misspelled Uses Declarations',1),
            original+'Expr | cycle | Expr\n',
            original+'Expr | cycle_a | Temporary\nTemporary | cycle_b | Expr CommaOpt\n',
            original+'Expr | bad_kind | #bogus\n']
 with tempfile.TemporaryDirectory() as work:
  for i,text in enumerate(mutations):
   p=Path(work)/str(i);p.write_text(text)
   try:load(p)
   except AssertionError:pass
   else:raise AssertionError(('invalid grammar accepted',i))
 return len(mutations)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);args=ap.parse_args();mutations=grammar_checks()
 imports=[r'namespace Mgnc;',r'use Mgnc\Data\{Diagnostic};',r'use Mgnc\ForestData\{ForestNode,ChartItem};',r'use Mgnc\SourceData\{Lexeme};',r'use Std\Io\{writeStderr};']
 checks=[]
 for prefix,record,fields in [('Node','ForestNode','symbol slot start end rule left right split alternatives'.split()),('Item','ChartItem','slot origin node'.split()),('Token','Lexeme','kind text start end line column scalarStart scalarEnd endLine endColumn'.split())]:
  store=prefix+'Store';var=prefix.lower();imports.append('use Mgnc\\'+prefix+'Storage\\{'+','.join([store,'empty'+prefix+'s','add'+prefix,'get'+prefix,'set'+prefix])+'};')
  value=record+'{'+','.join(f'{f}:'+('"old"' if f=='text' else f'i*17+{j}-10') for j,f in enumerate(fields))+'}'
  checks.extend(['{var table:'+store+'=empty'+prefix+'s();var i:Int=0;',f'loop while(i<1500){{table=add{prefix}(table,{value});i=i+1;}};',f'let original:{store}=table;i=0;',f'loop while(i<1500){{let value:{record}=try get{prefix}(table,i);'])
  checks += ['assert value->'+f+'=='+('"old"' if f=='text' else f'i*17+{j}-10')+';' for j,f in enumerate(fields)]
  checks+=['i=i+1;};',f'i=0;loop while(i<1500){{let value:{record}='+value.replace('i*17','i*17+10000')+f';table=try set{prefix}(table,i,value);i=i+31;}};',f'i=0;loop while(i<1500){{let value:{record}=try get{prefix}(original,i);assert value->'+fields[0]+'==i*17-10;i=i+1;};']
  checks += [f'i=0;loop while(i<1500){{let value:{record}=try get{prefix}(table,i);let extra:Int=branch when{{i%31==0=>10000,else=>0}};assert value->'+fields[0]+'==i*17-10+extra;i=i+1;};']
  for index in [-1,1500]:checks.append(f'branch on get{prefix}(table,{index}){{Result<{record},Diagnostic>::Ok(value:{record})=>{{assert false;}},Result<{record},Diagnostic>::Err(error:Diagnostic)=>{{assert error->phase=="internal";}}}};')
  checks+=['};']
 source='\n'.join(imports)+r"""
let check:Function():Result<Unit,Diagnostic>=function():Result<Unit,Diagnostic>{
"""+'\n'.join(checks)+r"""
Result<Unit,Diagnostic>::Ok(unit)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{
branch on check(){Result<Unit,Diagnostic>::Ok(value:Unit)=>0,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(error->message+"\n");1}}
};
"""
 run_entry(args.seed,source);print(f'CHART_INTERNALS_OK arenas=3 records_per_arena=1500 invalid_grammars={mutations}')
if __name__=='__main__':main()
