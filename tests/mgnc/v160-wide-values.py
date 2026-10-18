#!/usr/bin/env python3
"""Wide List ordering and non-completing operand regressions."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
rows=[]
for width in [65,257]:
    for position in [0,width//2,width-1]:
        values=[str(i%97) for i in range(width)]
        values[position]="{return 7;}"
        for bad in [False,True]:
            operands=values+(['true'] if bad else [])
            name=f"width-{width}-stop-{position}-bad-{int(bad)}"
            source="namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{List<Int>["+','.join(operands)+"]->length()};"
            rows.append((name,source,"type" if bad else None,7))
    values=','.join(str(i%97) for i in range(width))
    source="namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{var index:Int=0;loop over(List<Int>["+values+"] as value:Int){branch when{value!=index%97=>{return 2;},else=>unit};index=index+1;};branch when{index=="+str(width)+"=>0,else=>3}};"
    rows.append((f"width-{width}-order",source,None,0))
records=[]
for name,source,phase,exit_code in rows:
    path=a.output/(name+".mgn");path.write_text(source)
    commands=["check","lower"]+([] if phase else ["build"])
    for command in commands:
        binary=a.output/(name+".elf")
        argv=[str(a.compiler),command,str(path)]+(["-o",str(binary)] if command=="build" else [])
        result=subprocess.run(argv,capture_output=True,timeout=900)
        if phase:assert result.returncode==1 and b"mgnc: type:" in result.stderr,(name,command,result)
        else:assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(name,command,result)
        if command=="build":
            run=subprocess.run([binary],capture_output=True,timeout=120)
            assert (run.returncode,run.stdout,run.stderr)==(exit_code,b"",b""),(name,run)
    records.append({"case":name,"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"commands":commands,"expected_phase":phase,"exit":None if phase else exit_code})
(a.output/"results.json").write_text(json.dumps(records,indent=2)+"\n")
print("V160_WIDE_VALUES_OK cases="+str(len(records)))
