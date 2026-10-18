#!/usr/bin/env python3
"""Carry historical build fixtures through the expanded native profile."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
from parse_cases import fixtures,position
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);a=p.parse_args()
changes={}
for i in range(4):changes[("C140-B07",f"deferred-{i}")]=("semantic","The referenced nominal type is not explicitly imported or declared.")
for i in range(5):changes[("C140-N05",f"top-{i}")]=("semantic","The complete single-file program lacks main, or has an unresolved import.")
for i in [2,3,4,8,9,10,11]:changes[("C140-N05",f"body-{i}")]=("semantic","An unresolved name must be rejected by shared semantic analysis.")
changes[("C140-N05","body-5")]=("semantic","Discard requires a normally completing non-Unit operand.")
changes[("C140-N06","short-circuit")]=("type","Both logical operands require Bool even when the left operand is false.")
for i in [0,4,5]:changes[("DR140-T04",f"annotation-{i}")]=("type","An Int initializer does not match the declared type.")
for i in [1,2,3]:changes[("DR140-T04",f"annotation-{i}")]=("semantic","Signed, Bits, or Bytes requires an explicit standard import.")
# These six unchanged sources are now in the accepted native profile.
# Expected runtime values follow their source bodies, not compiler output.
native_changes={
 ("C140-N05","body-0"):"String values and discard are native.",
 ("C140-N05","body-1"):"Empty Lists and discard are native.",
 ("C140-N05","body-6"):"Function values and discard are native.",
 ("C140-N05","body-7"):"Value loops and break are native.",
 ("C140-N06","helper"):"Unused native helper bodies remain valid.",
 ("C140-N06","arm"):"All native branch arms are checked and supported.",
}
for key,reason in native_changes.items():changes[key]=("ok",reason)
records=[]
with tempfile.TemporaryDirectory(prefix="v150-inherited-") as temp:
 root=Path(temp)
 for row in fixtures():
  if not row["build"]:continue
  key=(row["case"],row["name"]);expected,reason=changes.get(key,(row["build"],"Inherited behavior is unchanged."))
  path=root/"case.mgn";path.write_text(row["source"]);output=root/"program"
  result=subprocess.run([a.compiler,"build",path,"-o",output],capture_output=True,timeout=120)
  success=expected=="ok";good=result.returncode==(0 if success else 1) and not result.stdout and output.exists()==success and (not result.stderr if success else ("mgnc: "+expected+":").encode() in result.stderr)
  if row["build_marker"] is not None:
   start,end,line,column=position(row["source"].encode(),row["build_marker"])
   good=good and f"[{start},{end})".encode() in result.stderr and f":{line}:{column}".encode() in result.stderr
  record={"case":row["case"],"name":row["name"],"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"previous_phase":row["build"],"expected_phase":expected,"reason":reason,"exit":result.returncode,"stderr":result.stderr.decode(),"passed":good}
  if success and key in native_changes:
   run=subprocess.run([output],capture_output=True,timeout=30)
   good=good and (run.returncode,run.stdout,run.stderr)==(0,b"",b"")
   record.update(passed=good,runtime_exit=run.returncode,runtime_stdout_hex=run.stdout.hex(),runtime_stderr_hex=run.stderr.hex())
  records.append(record)
  if output.exists():output.unlink()
data={"compiler_sha256":hashlib.sha256(a.compiler.read_bytes()).hexdigest(),"records":records,"passed":all(r["passed"] for r in records)}
a.evidence.write_text(json.dumps(data,indent=2)+"\n")
assert data["passed"],[r for r in records if not r["passed"]]
print("V160_INHERITED_BUILD_OK checks="+str(len(records))+" migrations="+str(len(changes)))
