#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
cases=[]
def save(name,body,expected,stdout="",dimensions=None):
 source="namespace App;use Std\\Io\\{writeStdout};let main:Function(List<String>):Int=function(args:List<String>):Int{discard args;"+body+"};\n"
 (a.output/(name+".mgn")).write_text(source)
 cases.append({"name":name,"expected_totals":expected,"stdout_hex":stdout.encode().hex(),"dimensions":dimensions or {},"source_sha256":hashlib.sha256(source.encode()).hexdigest()})
for n in (0,1,16,64,256,1024):
 setup=f"var values:List<Int>=List<Int>[];var i:Int=0;loop while(i<{n}){{values=values->append(i);i=i+1;}};"
 base={"2":n,"3":max(n-1,0)}
 save(f"length-{n}",setup+f"branch when{{values->length()=={n}=>0,else=>1}}",dict(base,**{"1":int(n>0)}))
 save(f"at-{n}",setup+"branch on values->at(0){Result<Int,IndexError>::Ok(value:Int)=>branch when{value==0=>0,else=>1},Result<Int,IndexError>::Err(error:IndexError)=>branch when{values->length()==0=>0,else=>1}}",dict(base,**{"4":max(n-1,0)}))
 save(f"append-{n}",setup+f"branch when{{values->length()=={n}=>0,else=>1}}",dict(base,**{"1":int(n>0)}))
 save(f"branch-{n}",setup+f"var k:Int=0;loop while(k<16){{let fork:List<Int>=values->append(999);branch when{{fork->length()!={n+1}=>{{return 1;}},else=>unit}};k=k+1;}};branch when{{values->length()=={n}=>0,else=>1}}",{"2":n+16,"3":max(n-1,0)+(16 if n else 0),"1":16+int(n>0)})
 save(f"over-{n}",setup+f"var total:Int=0;loop over(values as value:Int){{total=total+value;}};branch when{{total=={n*(n-1)//2}=>0,else=>1}}",dict(base,**{"5":n,"6":n}))
 for width,scalar in enumerate(("x","¢","日","😀"),1):
  text=scalar*n;literal=json.dumps(text,ensure_ascii=False)
  body=f'let source:String={literal};let values:List<String>=source->scalars();let result:String=values->join("");discard writeStdout(result);branch when{{values->length()=={n}&&result==source=>0,else=>1}}'
  save(f"scalars-{width}-{n}",body,{"7":n,"8":n*width,"9":n,"10":n,"11":n,"12":n,"13":n*width,"1":int(n>0)},text,{"n":n,"b":n*width})
 for q in (0,1,4,16):
  sep="s"*q;fragments=["" if i%2==0 else "日😀" for i in range(n)];output=sep.join(fragments);literal=json.dumps(sep)
  body=f'var values:List<String>=List<String>[];var i:Int=0;loop while(i<{n}){{values=values->append(branch when{{i%2==0=>"",else=>"日😀"}});i=i+1;}};let result:String=values->join({literal});discard writeStdout(result);0'
  save(f"join-{q}-{n}",body,dict(base,**{"11":n,"12":n,"13":len(output.encode())}),output,{"k":n,"b":sum(len(x.encode()) for x in fragments),"q":q,"o":len(output.encode())})
(a.output/"cases.json").write_text(json.dumps(cases,indent=2,ensure_ascii=False)+"\n")
print("COST_FIXTURES",len(cases),hashlib.sha256((a.output/"cases.json").read_bytes()).hexdigest())
