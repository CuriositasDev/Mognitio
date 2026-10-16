#!/usr/bin/env python3
"""Build one native probe for source/IR correspondence and dataflow controls."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument("--seed",type=Path,required=True)
args=parser.parse_args()
names={"Whole":"v160-whole-ir.mgn","Flow":"v160-dataflow.mgn"}
identity={name:hashlib.sha256((ROOT/"tests/mgnc/harnesses"/file).read_bytes()).hexdigest() for name,file in names.items()}
print(json.dumps({"harness_sha256":identity,"valid":6,"rejected":21}),flush=True)
with tempfile.TemporaryDirectory(prefix="mgnc-v160-internals-") as temporary:
    work=Path(temporary);project=work/"compiler"
    shutil.copytree(ROOT/"compiler/mgnc",project)
    for name,file in names.items():
        source=(ROOT/"tests/mgnc/harnesses"/file).read_text()
        source=source.replace("namespace Mgnc;","namespace Mgnc\\Probe"+name+";",1)
        source=source.replace("\nlet main:Function(","\npublic let main:Function(",1)
        module=project/"src"/("Probe"+name);module.mkdir()
        (module/"probe.mgn").write_text(source)
    (project/"src/mgnc.mgn").write_text('''namespace Mgnc;
use Mgnc\\ProbeWhole\\{main as whole};
use Mgnc\\ProbeFlow\\{main as flow};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let status:Int=flow(args);branch when{status!=0=>status,else=>whole(args)}
};
''')
    binary=work/"probe"
    built=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
    assert built.returncode==0,(built.returncode,built.stdout,built.stderr)
    result=subprocess.run([binary],capture_output=True,timeout=120)
    assert (result.returncode,result.stderr)==(0,b""),(result.returncode,result.stdout,result.stderr)
    assert result.stdout.startswith(b"V160_DATAFLOW_OK valid=3 rejected=8\n"),result.stdout
    assert result.stdout.endswith(b"V160_WHOLE_IR_OK valid=3 rejected=13\n"),result.stdout
    assert result.stdout.count(b"V160_MUTANT ")==13,result.stdout
    print(result.stdout.decode(),end="")
