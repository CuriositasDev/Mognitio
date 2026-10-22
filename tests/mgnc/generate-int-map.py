#!/usr/bin/env python3
"""Generate a persistent four-way radix map with shared immutable empty nodes."""
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/"compiler/mgnc/src/IntMap/map.mgn"
LEVELS=12
LAST=LEVELS-1
LIMIT=4**LEVELS
FIELDS=["zero","one","two","three"]
def generate():
 lines=["namespace Mgnc\\IntMap;",
 "// Generated fixed-field radix tree. Empty subtrees are shared immutable values.",
 "// No child lookup or path update creates an intermediate List or Result.",
 "use Mgnc\\Data\\{Diagnostic,Span,problem};"]
 for level in range(LAST,-1,-1):
  child="Int" if level==LAST else f"Level{level+1}"
  lines.append(f"public type Level{level}=product{{"+"".join(f"{field}:{child};" for field in FIELDS)+"};")
 for level in range(LAST,-1,-1):
  child="-2" if level==LAST else f"blank{level+1}"
  lines.append(f"let blank{level}:Level{level}=Level{level}{{"+",".join(f"{field}:{child}" for field in FIELDS)+"};")
 lines+=["public type Entry=product{key:Int;value:Int;};","public type Map=product{small:Level0;large:List<Entry>;};",
 "public let create:Function():Map=function():Map{Map{small:blank0,large:List<Entry>[]}};"]
 for op in ["get","put"]:
  out="Int" if op=="get" else "Map"
  lines.append(f"public let {op}:Function(Map,Int"+(",Int" if op=="put" else "")+f"):Result<{out},Diagnostic>=function(table:Map,key:Int"+(",value:Int" if op=="put" else "")+f"):Result<{out},Diagnostic>{{")
  lines.append(f' branch when{{key<0=>{{return Result<{out},Diagnostic>::Err(problem("internal",Span{{start:0,end:0,line:1,column:1}},"negative radix key"));}},key>={LIMIT}=>{{')
  if op=="get":
   lines+=["  loop over(table->large as entry:Entry){branch when{entry->key==key=>{return Result<Int,Diagnostic>::Ok(entry->value);},else=>unit};};return Result<Int,Diagnostic>::Ok(-2);"]
  else:
   lines+=["  var large:List<Entry>=List<Entry>[];var found:Bool=false;",
   "  loop over(table->large as entry:Entry){branch when{entry->key==key=>{large=large->append(Entry{key:key,value:value});found=true;},else=>{large=large->append(entry);}};};",
   "  branch when{!found=>{large=large->append(Entry{key:key,value:value});},else=>unit};return Result<Map,Diagnostic>::Ok(Map{small:table->small,large:large});"]
  lines+=[" },else=>unit};"," let node0:Level0=table->small;"]
  for level in range(LEVELS):
   divisor=4**(LAST-level)
   lines.append(f" let digit{level}:Int=key/{divisor}%4;")
   expr="branch when{"+",".join(f"digit{level}=={i}=>node{level}->{field}" for i,field in enumerate(FIELDS[:3]))+f",else=>node{level}->three"+"}"
   if level<LAST:lines.append(f" let node{level+1}:Level{level+1}={expr};")
   elif op=="get":lines.append(f" Result<Int,Diagnostic>::Ok({expr})")
  if op=="put":
   for level in range(LAST,-1,-1):
    updated="value" if level==LAST else f"updated{level+1}"
    fields=",".join(f"{field}:branch when{{digit{level}=={i}=>{updated},else=>node{level}->{field}}}" for i,field in enumerate(FIELDS))
    lines.append(f" let updated{level}:Level{level}=Level{level}{{{fields}}};")
   lines.append(" Result<Map,Diagnostic>::Ok(Map{small:updated0,large:table->large})")
  lines.append("};")
 return "\n".join(lines)+"\n"
def main():
 p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args();text=generate()
 if a.check:assert TARGET.read_text()==text
 else:TARGET.write_text(text)
 print("V150_INT_MAP_REPRODUCIBLE")
if __name__=="__main__":main()
