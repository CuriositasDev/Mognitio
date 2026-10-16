#!/usr/bin/env python3
"""Freeze closed-profile identity cases before native selection is connected."""
import argparse,hashlib,json,subprocess
from pathlib import Path
def program(prefix="",body="0"):
    return "namespace App;\n"+prefix+"\nlet main:Function(List<String>):Int=function(args:List<String>):Int{"+body+"};\n"
CASES={}
def case(name,source,accepted):CASES[name]={"source":source,"native":accepted}
for name in ["readTextFile","writeTextFile","readStdin","writeStdout","writeStderr","IoError","IoOperation","IoErrorKind","IoErrorPhase"]:
    case("io-allowed-"+name,program("use Std\\Io\\{"+name+"};"),True)
for name in ["joinPath","readDirectory","createDirectory","DirectoryEntry","DirectoryEntryKind","inspectPath","FileIdentity","PathInfo","PathInfoError"]:
    case("io-excluded-"+name,program("use Std\\Io\\{"+name+" as renamed};"),False)
for namespace,name in [("Numeric","Bits"),("Numeric","Signed"),("Numeric","Unsigned"),("Binary","Bytes"),("Binary","bytesFromBits")]:
    case("excluded-"+namespace+"-"+name,program("use Std\\"+namespace+"\\{"+name+"};"),False)
case("user-same-name",program('type PathInfoError=product{subject:String;};let value:PathInfoError=PathInfoError{subject:"kept"};','value->subject->length()-4'),True)
case("string-name",program(body='let text:String="Std\\\\Io\\\\joinPath Bytes Bits FileIdentity";branch when{text->length()>0=>0,else=>1}'),True)
case("unused-symbolic-identity",program("template keep<T>=function(value:T):T{value};"),True)
case("unused-symbolic-bits",program("use Std\\Numeric\\{Bits};template make<N:Int>=function():Bits<N>{Bits<N>{0}};"),False)
case("unused-signature",program("use Std\\Io\\{PathInfoError};let unused:Function(List<PathInfoError>):Unit=function(values:List<PathInfoError>):Unit{unit};"),False)
case("unselected-operation",program("use Std\\Io\\{joinPath};",'branch when{false=>{discard joinPath("a","b");0},else=>0}'),False)
case("io-operation-all-variants",program("use Std\\Io\\{IoOperation};",'''let operation:IoOperation=IoOperation::JoinPath;
branch on operation{IoOperation::ReadTextFile=>1,IoOperation::WriteTextFile=>2,IoOperation::ReadStdin=>3,IoOperation::WriteStdout=>4,IoOperation::WriteStderr=>5,IoOperation::JoinPath=>0,IoOperation::ReadDirectory=>6,IoOperation::CreateDirectory=>7}'''),True)
case("alias-result",program("alias Wrapped<T>=Result<List<T>,String>;template keep<T>=function(value:Wrapped<T>):Wrapped<T>{value};","discard keep<Int>(Result<List<Int>,String>::Ok(List<Int>[1]));0"),True)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--compiler",type=Path)
    parser.add_argument("--mode",choices=["check","profile","build"],default="build")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    identity=hashlib.sha256(json.dumps(CASES,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    (args.output/"fixtures.json").write_text(json.dumps({"sha256":identity,"cases":CASES},ensure_ascii=False,indent=2)+"\n")
    print("FIXTURES sha256="+identity,flush=True)
    observations=[]
    for name,fixture in CASES.items():
        path=args.output/(name+".mgn");path.write_text(fixture["source"])
        if args.compiler:
            output=args.output/(name+".elf");cmd=[str(args.compiler),"check" if args.mode=="profile" else args.mode,str(path)]
            if args.mode=="build":cmd+=["-o",str(output)]
            result=subprocess.run(cmd,capture_output=True,timeout=120)
            expected=0 if args.mode=="check" or fixture["native"] else 1
            assert result.returncode==expected,(name,result.returncode,result.stdout,result.stderr)
            assert result.stdout==b"",(name,result.stdout)
            if expected==0:assert result.stderr==b"",(name,result.stderr)
            else:assert b"unsupported" in result.stderr and not output.exists(),(name,result.stderr)
            if args.mode=="build" and fixture["native"]:
                run=subprocess.run([output],capture_output=True,timeout=30)
                assert (run.returncode,run.stdout,run.stderr)==(0,b"",b""),(name,run)
            observations.append({"case":name,"expected_native":fixture["native"],"mode":args.mode,"status":result.returncode})
    (args.output/"observations.json").write_text(json.dumps(observations,indent=2)+"\n")
    print("V160_PROFILE_"+args.mode.upper()+"_OK cases="+str(len(observations)))
if __name__=="__main__":main()
