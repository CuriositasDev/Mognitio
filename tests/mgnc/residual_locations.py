#!/usr/bin/env python3
"""Residual punctuation at Unicode/CRLF and 1024-scalar chunk boundaries."""
import argparse
from frontend import literal
from shared_lexer import run_entry
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);args=ap.parse_args();checks=[];count=0
 for prefix in ['//é日😀\r\n\t','//é日😀'+'x'*1017+'\n']:
  for suffix,steps in [('>==>',[(True,'>',0,1),(False,'==',1,3),(False,'>',3,4)]),('>===',[(True,'>',0,1),(False,'==',1,3),(False,'=',3,4)]),('>>=',[(True,'>',0,1),(True,'>',1,2),(False,'=',2,3)])]:
   source=prefix+suffix;offset=len(prefix.encode());column=len(prefix.rsplit('\n',1)[-1])+1
   checks.append('{let snap:Snapshot=try scanSource('+literal(source)+');var cursor:Int=0;')
   for close,text,start,end in steps:
    checks.append('{let value:Terminal=try scanAt(snap,cursor,'+str(close).lower()+');assert value->token->text=='+literal(text)+f';assert value->token->start=={offset+start}&&value->token->end=={offset+end};assert value->token->line==2&&value->token->column=={column+start};cursor=value->next;}};')
   checks.append('let final:Terminal=try scanAt(snap,cursor,false);assert final->token->kind==0;};');count+=1
 source=r"""namespace Mgnc;
use Mgnc\Data\{Diagnostic};
use Mgnc\Source\{Snapshot};
use Mgnc\Lexical\{scanSource};
use Mgnc\Cursor\{Terminal,scanAt};
use Std\Io\{writeStderr};
let check:Function():Result<Unit,Diagnostic>=function():Result<Unit,Diagnostic>{
"""+ '\n'.join(checks)+r"""
Result<Unit,Diagnostic>::Ok(unit)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{
branch on check(){Result<Unit,Diagnostic>::Ok(value:Unit)=>0,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>{discard writeStderr(error->message+"\n");1}}
};
"""
 run_entry(args.seed,source);print('RESIDUAL_LOCATIONS_OK',count)
if __name__=='__main__':main()
