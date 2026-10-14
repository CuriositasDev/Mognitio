#!/usr/bin/env python3
"""Generate a compact persistent radix map with an exact large-key fallback."""
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/"compiler/mgnc/src/IntMap/map.mgn"
def generate():
 lines=["namespace Mgnc\\IntMap;","// Generated compact low-ID radix tree. Large Int64 keys remain exact.",
 "use Mgnc\\Data\\{Diagnostic,Span,problem};",
 "template replaceSlot<T>=function(values:List<T>,index:Int,value:T,blank:T):List<T>{",
 " var result:List<T>=List<T>[];var cursor:Int=0;let count:Int=branch when{values->length()>index=>values->length(),else=>index+1};",
 " loop while(cursor<count){result=result->append(branch when{cursor==index=>value,else=>branch on values->at(cursor){Result<T,IndexError>::Ok(found:T)=>found,Result<T,IndexError>::Err(error:IndexError)=>blank}});cursor=cursor+1;};result","};"]
 for level in range(9,-1,-1):
  child="Int" if level==9 else f"Level{level+1}"
  lines.append(f"public type Level{level}=product{{children:List<{child}>;}};")
 lines+=["public type Entry=product{key:Int;value:Int;};","public type Map=product{small:Level0;large:List<Entry>;};","public let create:Function():Map=function():Map{Map{small:Level0{children:List<Level1>[]},large:List<Entry>[]}};"]
 for op in ["get","put"]:
  out="Int" if op=="get" else "Map"
  lines.append(f"public let {op}:Function(Map,Int"+(",Int" if op=="put" else "")+f"):Result<{out},Diagnostic>=function(table:Map,key:Int"+(",value:Int" if op=="put" else "")+f"):Result<{out},Diagnostic>{{")
  lines.append(f' branch when{{key<0=>{{return Result<{out},Diagnostic>::Err(problem("internal",Span{{start:0,end:0,line:1,column:1}},"negative radix key"));}},key>=1048576=>{{')
  if op=="get":lines+=["  loop over(table->large as entry:Entry){branch when{entry->key==key=>{return Result<Int,Diagnostic>::Ok(entry->value);},else=>unit};};return Result<Int,Diagnostic>::Ok(-2);"]
  else:lines+=["  var large:List<Entry>=List<Entry>[];var found:Bool=false;",
  "  loop over(table->large as entry:Entry){branch when{entry->key==key=>{large=large->append(Entry{key:key,value:value});found=true;},else=>{large=large->append(entry);}};};",
  "  branch when{!found=>{large=large->append(Entry{key:key,value:value});},else=>unit};return Result<Map,Diagnostic>::Ok(Map{small:table->small,large:large});"]
  lines+=[" },else=>unit};"," let node0:Level0=table->small;"]
  for level in range(1,10):
   child="Int" if level==9 else f"Level{level+1}"
   missing="{return Result<Int,Diagnostic>::Ok(-2);}" if op=="get" else f"Level{level}{{children:List<{child}>[]}}"
   lines.append(f" let node{level}:Level{level}=branch on node{level-1}->children->at(key/{4**(10-level)}%4){{Result<Level{level},IndexError>::Ok(found:Level{level})=>found,Result<Level{level},IndexError>::Err(error:IndexError)=>{missing}}};")
  if op=="get":lines.append(" branch on node9->children->at(key%4){Result<Int,IndexError>::Ok(found:Int)=>Result<Int,Diagnostic>::Ok(found),Result<Int,IndexError>::Err(error:IndexError)=>Result<Int,Diagnostic>::Ok(-2)}")
  else:
   lines.append(" let updated9:Level9=Level9{children:replaceSlot<Int>(node9->children,key%4,value,-2)};")
   for level in range(8,-1,-1):
    child=f"Level{level+1}";grand="Int" if level==8 else f"Level{level+2}"
    lines.append(f" let updated{level}:Level{level}=Level{level}{{children:replaceSlot<{child}>(node{level}->children,key/{4**(9-level)}%4,updated{level+1},{child}{{children:List<{grand}>[]}})}};")
   lines.append(" Result<Map,Diagnostic>::Ok(Map{small:updated0,large:table->large})")
  lines.append("};")
 return "\n".join(lines)+"\n"
def main():
 p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args();text=generate()
 if a.check:assert TARGET.read_text()==text
 else:TARGET.write_text(text)
 print("V150_INT_MAP_REPRODUCIBLE")
if __name__=="__main__":main()
