#!/usr/bin/env python3
"""Replay independent label, contract, and filesystem oracles in one seed build."""
from pathlib import Path
import argparse,shutil,subprocess,json,hashlib,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--compare-machine-reference',action='store_true');args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if args.compare_machine_reference:
  for module,file in [('TestOldMachine','legacy-machine-check.mgn'),('TestMachineEquivalence','machine-check-equivalence.mgn')]:
   folder=project/'src'/module;folder.mkdir();shutil.copyfile(HERE/'harnesses'/file,folder/'verify.mgn')
 modules=[('Index','v170-index-verifiers.mgn'),('Contracts','v170-contract-ir.mgn'),('Publication','v170-publication.mgn'),('Inspection','v170-inspection.mgn'),('Path','v170-path-operations.mgn'),('Directory','v170-directory.mgn')]
 for name,file in modules:
  text=(HERE/'harnesses'/file).read_text();assert text.count('namespace Mgnc;')==1 and text.count('\nlet main:Function(')==1;text=text.replace('namespace Mgnc;','namespace Mgnc\\Probe'+name+';',1).replace('\nlet main:Function(','\npublic let main:Function(',1);text=text.replace('Mgnc\\WholeMachineCheck\\','Mgnc\\TestMachineEquivalence\\') if args.compare_machine_reference else text;folder=project/'src'/('Probe'+name);folder.mkdir();(folder/'probe.mgn').write_text(text)
 for module,file in [('TestTypePermutation','runtime-type-permutation.mgn'),('TestNativePermutation','native-type-permutation.mgn')]:
  folder=project/'src'/module;folder.mkdir();shutil.copyfile(HERE/'harnesses'/file,folder/'code.mgn')
 shutil.copyfile(HERE/'harnesses/v170-runtime-label-oracles.mgn',project/'src/mgnc.mgn');inputs=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');built=subprocess.run([args.seed.resolve(),'build',project/'mognitio.toml','-o',out/'probe'],capture_output=True,timeout=1200);(out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr);assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(built.returncode,built.stderr)
 images=out/'images';images.mkdir();run=subprocess.run([out/'probe',images],capture_output=True,timeout=600);(out/'run.stdout').write_bytes(run.stdout);(out/'run.stderr').write_bytes(run.stderr);assert run.returncode==0 and not run.stderr and run.stdout.endswith(b'RUNTIME_LABEL_ORACLES_OK cells=6\n'),(run.returncode,run.stdout[-2200:],run.stderr)
 requirements=[(b'V170_INDEX_VERIFIERS_OK valid=2 rejected=25',b'MUTANT ',462),(b'V170_CONTRACT_IR_OK valid_images=6',b'V170_CONTRACT_MUTANT ',227),(b'V170_PUBLICATION_IR_OK valid=1',b'V170_PUBLICATION_MUTANT ',86),(b'V170_INSPECTION_IR_OK valid=1',b'V170_INSPECTION_MUTANT ',26),(b'V170_PATH_IR_OK valid=1',b'V170_PATH_MUTANT ',41),(b'V170_DIRECTORY_IR_OK valid=1',b'V170_DIRECTORY_MUTANT ',57)]
 for marker,prefix,count in requirements:assert marker in run.stdout and run.stdout.count(prefix)>=count,marker
 equivalence_calls=run.stdout.count(b'MACHINE_INDEX_EQ_OK\n');assert not args.compare_machine_reference or equivalence_calls==266,equivalence_calls
 assert len({sha(images/name) for name in ['baseline','permuted','reordered','combined']})==1 and sha(images/'request-forward')==sha(images/'request-reverse');observations=[]
 for name in ['baseline','permuted','reordered','combined','request-forward','request-reverse']:
  for stress in [False,True]:
   artifact=images/name;command=([sys.executable,HERE/'v160-native-observe.py','--stress','--report',out/(name+'-stress.json'),'--'] if stress else [])+[artifact];result=subprocess.run(command,capture_output=True,timeout=180);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(name,stress,result.returncode,result.stderr)
   if stress:assert json.loads((out/(name+'-stress.json')).read_text())['heap']['collections']>0
   observations.append(dict(image=name,stress=stress,exit=result.returncode,sha256=sha(artifact)))
 assert all(sha(project/r['path'])==r['sha256'] for r in inputs);(out/'results.json').write_text(json.dumps(dict(cells=6,observations=observations,machine_reference_comparisons=equivalence_calls),indent=2)+'\n');print('RUNTIME_LABEL_ORACLES_OK cells=6 rejected='+str(run.stdout.count(b'MUTANT ')));print('RUNTIME_LABEL_IMAGE_RUNTIME_OK images=6 observations=12')
if __name__=='__main__':main()
