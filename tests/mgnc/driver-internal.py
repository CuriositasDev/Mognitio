#!/usr/bin/env python3
"""Exercise the shared analysis boundary and internal/CLI diagnostic contracts."""
import argparse,hashlib,os,shutil,subprocess,tempfile
from pathlib import Path
from native import ENTRY
ROOT=Path(__file__).resolve().parents[2]
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seed",required=True,type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mgnc-driver-internal-") as temporary:
        work=Path(temporary);project=work/"project";shutil.copytree(ROOT/"compiler/mgnc",project)
        (project/"src/Pipeline/compile.mgn").write_text(r"""namespace Mgnc\Pipeline;
use Std\Binary\{Bytes};
use Mgnc\Data\{Diagnostic,Span,problem};
use Mgnc\Semantic\{SemanticProject};
use Mgnc\Checked\{CheckedProgram};
use Mgnc\SemanticSnapshot\{snapshot};
public let prepare:Function(SemanticProject):Result<CheckedProgram,Diagnostic>=function(semantic:SemanticProject):Result<CheckedProgram,Diagnostic>{
 discard snapshot(semantic->state);
 Result<CheckedProgram,Diagnostic>::Err(problem("internal",Span{start:0,end:0,line:1,column:1},"injected phase invariant"))
};
public let compile:Function(CheckedProgram):Result<Bytes,Diagnostic>=function(program:CheckedProgram):Result<Bytes,Diagnostic>{
 panic{"backend entered after failed projection"}
};
""")
        probe=project/"src/SemanticSnapshot";probe.mkdir()
        (probe/"snapshot.mgn").write_text((ROOT/"tests/mgnc/harnesses/v150-semantic-snapshot.mgn").read_text())
        analysis=project/"src/Semantic/analyze.mgn";text=analysis.read_text()
        text=text.replace("namespace Mgnc\\Semantic;","namespace Mgnc\\Semantic;\nuse Std\\Io\\{writeStderr};\nuse Mgnc\\SemanticSnapshot\\{snapshot};")
        marker="public let analyze:Function(ProjectInput):Result<SemanticProject,InputError>=function(input:ProjectInput):Result<SemanticProject,InputError>{"
        assert text.count(marker)==1
        text=text.replace(" Result<SemanticProject,InputError>::Ok(SemanticProject{state:state,entry:selected})"," discard snapshot(state);\n Result<SemanticProject,InputError>::Ok(SemanticProject{state:state,entry:selected})")
        analysis.write_text(text.replace(marker,marker+'\n discard writeStderr("SEMANTIC_ENTER\\n");'))
        (project/"src/mgnc.mgn").write_text(r"""namespace Mgnc;
use Mgnc\Driver\{run};
use Mgnc\TextUtil\{at};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 branch when{at(args,0)=="nul-input"=>run(List<String>["check","input\0.mgn"]),
 at(args,0)=="nul-output"=>run(List<String>["build","input.mgn","-o","output\0"]),
 else=>run(args)}
};
""")
        image=work/"compiler";source=work/"input.mgn";source.write_text(ENTRY+"7};")
        build=subprocess.run([args.seed.resolve(),"build",project/"mognitio.toml","-o",image],capture_output=True,timeout=600)
        assert (build.returncode,build.stdout,build.stderr)==(0,b"",b""),build.stderr.decode()
        checks=0;snapshots=[]
        for command,want,phase,count in [
            (["check",source],0,None,1),
            (["parse",source],0,None,0),
            (["build",source,"-o",work/"output"],3,b"internal",1),
            (["nul-input"],2,b"cli",0),(["nul-output"],2,b"cli",0)]:
            result=subprocess.run([image,*map(str,command)],capture_output=True,timeout=30)
            assert result.returncode==want and not result.stdout,(command,result)
            assert result.stderr.count(b"SEMANTIC_ENTER\n")==count,result
            lines=result.stderr.splitlines(keepends=True)
            snapshot=b"".join(line for line in lines if line.startswith(b"SNAP|"))
            if command[0]=="check":snapshots.append(snapshot)
            elif command[0]=="build":
                midpoint=len(snapshot)//2
                assert snapshot[:midpoint]==snapshot[midpoint:]==snapshots[0] and snapshots[0]
            remaining=b"".join(line for line in lines if not line.startswith(b"SNAP|"))
            if phase:assert b"mgnc: "+phase+b":" in result.stderr,result
            else:assert remaining==b"SEMANTIC_ENTER\n"*count,result
            assert not (work/"output").exists()
            checks+=1
        result=subprocess.run([image,"build",source,"-o",work/"output"],capture_output=True,timeout=30,preexec_fn=lambda:os.close(2))
        assert result.returncode==2 and not result.stdout and not (work/"output").exists(),result
        checks+=1
        source.write_text(ENTRY+"true};")
        for command in [["check",source],["build",source,"-o",work/"output"]]:
            result=subprocess.run([image,*map(str,command)],capture_output=True,timeout=30)
            assert result.returncode==1 and not result.stdout and result.stderr.count(b"SEMANTIC_ENTER\n")==1 and b"mgnc: type:" in result.stderr,result
            assert b"injected phase invariant" not in result.stderr and not (work/"output").exists(),result
            checks+=1
    print("MGNC_INTERNAL_DRIVER_OK checks="+str(checks)+" semantic_snapshot_sha256="+hashlib.sha256(snapshots[0]).hexdigest())
if __name__=="__main__":main()
