#!/usr/bin/env python3
"""Replay independent label, contract, and filesystem oracles in one seed build."""
from pathlib import Path
import argparse,shutil,subprocess,json,hashlib,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

VERIFIER_MODULES={
 "WholeMachineCheck":"verify.mgn",
 "WholeHelperCheck":"verify.mgn",
 "WholeContractMachine":"verify.mgn",
 "WholePubMachine":"code.mgn",
 "WholeInspectionMachine":"code.mgn",
 "WholePathMachine":"code.mgn",
 "WholeDirectoryMachine":"code.mgn",
}
def add_verifier_reference(project,reference):
 """Keep the previous verifier bodies separate from all changed modules."""
 template=(HERE/'harnesses/machine-check-equivalence.mgn').read_text()
 # A mismatch must abort the probe, never masquerade as an expected rejection.
 for message in ['indexed machine accepted old rejection','indexed machine rejected old acceptance']:
  before='try require(false,span,"'+message+'");'
  assert template.count(before)==1
  template=template.replace(before,'panic{"'+message+'"};')
 before='try require(error->phase==previous->phase'
 after='span,"indexed machine diagnostic order");'
 assert template.count(before)==template.count(after)==1
 template=template.replace(before,'assert error->phase==previous->phase').replace(','+after,';')
 template=template.replace('use Mgnc\\WholeChecks\\{require};','')
 for module,filename in VERIFIER_MODULES.items():
  text=(reference/'src'/module/filename).read_text()
  assert text.count('namespace Mgnc\\'+module+';')==1,module
  text=text.replace('namespace Mgnc\\'+module+';','namespace Mgnc\\TestOld'+module+';',1)
  for dependency in VERIFIER_MODULES:text=text.replace('use Mgnc\\'+dependency+'\\','use Mgnc\\TestOld'+dependency+'\\')
  folder=project/'src'/('TestOld'+module);folder.mkdir()
  (folder/filename).write_text(text)
  wrapper=template.replace('TestMachineEquivalence','TestCompare'+module)
  wrapper=wrapper.replace('use Mgnc\\WholeMachineCheck\\','use Mgnc\\'+module+'\\').replace('use Mgnc\\TestOldMachine\\','use Mgnc\\TestOld'+module+'\\')
  wrapper=wrapper.replace('MACHINE_INDEX_EQ_OK','VERIFIER_EQ '+module)
  wrapper=wrapper.replace('indexed machine','machine verifier')
  if module=='WholeHelperCheck':
   wrapper=wrapper.replace('use Mgnc\\WholeNativeData\\{Native};','use Mgnc\\WholeHelpers\\{Helper};')
   wrapper=wrapper.replace('Function(Native,Code)','Function(List<Helper>,Code)').replace('plan:Native','plan:List<Helper>')
  folder=project/'src'/('TestCompare'+module);folder.mkdir()
  (folder/'verify.mgn').write_text(wrapper)
 # Route nested verifier calls through comparators too, including contracts.
 # The copied reference closure always calls only its unchanged reference peers.
 for module,filename in VERIFIER_MODULES.items():
  current=project/'src'/module/filename
  if current.exists():
   text=current.read_text()
   for dependency in VERIFIER_MODULES:
    if dependency!=module:text=text.replace('use Mgnc\\'+dependency+'\\','use Mgnc\\TestCompare'+dependency+'\\')
   current.write_text(text)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--compare-machine-reference',action='store_true');parser.add_argument('--compare-verifier-reference',type=Path,help='Previous compiler source root containing src/; compare every changed machine verifier and exact diagnostics');args=parser.parse_args();assert not (args.compare_machine_reference and args.compare_verifier_reference),'choose one reference mode';out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if args.compare_machine_reference:
  for module,file in [('TestOldMachine','legacy-machine-check.mgn'),('TestMachineEquivalence','machine-check-equivalence.mgn')]:
   folder=project/'src'/module;folder.mkdir();shutil.copyfile(HERE/'harnesses'/file,folder/'verify.mgn')
 if args.compare_verifier_reference:add_verifier_reference(project,args.compare_verifier_reference.resolve())
 modules=[('Index','v170-index-verifiers.mgn'),('Contracts','v170-contract-ir.mgn'),('Publication','v170-publication.mgn'),('Inspection','v170-inspection.mgn'),('Path','v170-path-operations.mgn'),('Directory','v170-directory.mgn')]
 for name,file in modules:
  text=(HERE/'harnesses'/file).read_text();assert text.count('namespace Mgnc;')==1 and text.count('\nlet main:Function(')==1;text=text.replace('namespace Mgnc;','namespace Mgnc\\Probe'+name+';',1).replace('\nlet main:Function(','\npublic let main:Function(',1);text=text.replace('Mgnc\\WholeMachineCheck\\','Mgnc\\TestMachineEquivalence\\') if args.compare_machine_reference else text;
  if args.compare_verifier_reference:
   for module in VERIFIER_MODULES:text=text.replace('Mgnc\\'+module+'\\','Mgnc\\TestCompare'+module+'\\')
  folder=project/'src'/('Probe'+name);folder.mkdir();(folder/'probe.mgn').write_text(text)
 for module,file in [('TestTypePermutation','runtime-type-permutation.mgn'),('TestNativePermutation','native-type-permutation.mgn')]:
  folder=project/'src'/module;folder.mkdir();shutil.copyfile(HERE/'harnesses'/file,folder/'code.mgn')
 shutil.copyfile(HERE/'harnesses/v170-runtime-label-oracles.mgn',project/'src/mgnc.mgn');inputs=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');built=subprocess.run([args.seed.resolve(),'build',project/'mognitio.toml','-o',out/'probe'],capture_output=True,timeout=1200);(out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr);assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(built.returncode,built.stderr)
 images=out/'images';images.mkdir();run=subprocess.run([out/'probe',images],capture_output=True,timeout=600);(out/'run.stdout').write_bytes(run.stdout);(out/'run.stderr').write_bytes(run.stderr);assert run.returncode==0 and not run.stderr and run.stdout.endswith(b'RUNTIME_LABEL_ORACLES_OK cells=6\n'),(run.returncode,run.stdout[-2200:],run.stderr)
 requirements=[(b'V170_INDEX_VERIFIERS_OK valid=2 rejected=25',b'MUTANT ',462),(b'V170_CONTRACT_IR_OK valid_images=6',b'V170_CONTRACT_MUTANT ',227),(b'V170_PUBLICATION_IR_OK valid=1',b'V170_PUBLICATION_MUTANT ',86),(b'V170_INSPECTION_IR_OK valid=1',b'V170_INSPECTION_MUTANT ',26),(b'V170_PATH_IR_OK valid=1',b'V170_PATH_MUTANT ',41),(b'V170_DIRECTORY_IR_OK valid=1',b'V170_DIRECTORY_MUTANT ',57)]
 for marker,prefix,count in requirements:assert marker in run.stdout and run.stdout.count(prefix)>=count,marker
 verifier_comparisons={module:run.stdout.count(('VERIFIER_EQ '+module+'\n').encode()) for module in VERIFIER_MODULES}
 if args.compare_verifier_reference:assert all(verifier_comparisons.values()),verifier_comparisons
 equivalence_calls=run.stdout.count(b'MACHINE_INDEX_EQ_OK\n');assert not args.compare_machine_reference or equivalence_calls==266,equivalence_calls
 assert len({sha(images/name) for name in ['baseline','permuted','reordered','combined']})==1 and sha(images/'request-forward')==sha(images/'request-reverse');observations=[]
 for name in ['baseline','permuted','reordered','combined','request-forward','request-reverse']:
  for stress in [False,True]:
   artifact=images/name;command=([sys.executable,HERE/'v160-native-observe.py','--stress','--report',out/(name+'-stress.json'),'--'] if stress else [])+[artifact];result=subprocess.run(command,capture_output=True,timeout=180);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(name,stress,result.returncode,result.stderr)
   if stress:assert json.loads((out/(name+'-stress.json')).read_text())['heap']['collections']>0
   observations.append(dict(image=name,stress=stress,exit=result.returncode,sha256=sha(artifact)))
 assert all(sha(project/r['path'])==r['sha256'] for r in inputs);(out/'results.json').write_text(json.dumps(dict(cells=6,observations=observations,machine_reference_comparisons=equivalence_calls,verifier_reference_comparisons=verifier_comparisons),indent=2)+'\n');print('RUNTIME_LABEL_ORACLES_OK cells=6 rejected='+str(run.stdout.count(b'MUTANT ')));print('RUNTIME_LABEL_IMAGE_RUNTIME_OK images=6 observations=12')
if __name__=='__main__':main()
