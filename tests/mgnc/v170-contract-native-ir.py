#!/usr/bin/env python3
"""Check source-coherent interner permutations, serialized images and mutations."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project);shutil.copy2(HERE/'harnesses/v170-contract-ir.mgn',project/'src/mgnc.mgn')
for module,name in [('TestTypePermutation','runtime-type-permutation.mgn'),('TestNativePermutation','native-type-permutation.mgn')]:
    target=project/'src'/module;target.mkdir();shutil.copy2(HERE/'harnesses'/name,target/'code.mgn')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inventory=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inventory,indent=2)+'\n');probe=out/'probe';build=subprocess.run([str(args.seed.resolve()),'build',str(project/'mognitio.toml'),'-o',str(probe)],capture_output=True,timeout=900);(out/'build.stdout').write_bytes(build.stdout);(out/'build.stderr').write_bytes(build.stderr);assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),(build.returncode,build.stderr)
images=out/'images';images.mkdir();run=subprocess.run([str(probe),str(images)],capture_output=True,timeout=240);(out/'run.stdout').write_bytes(run.stdout);(out/'run.stderr').write_bytes(run.stderr);print(run.stdout.decode(),end='');assert run.returncode==0 and run.stderr==b'' and run.stdout.endswith(b'V170_CONTRACT_IR_OK valid_images=6\n') and b'V170_CONTRACT_MACHINE_MUTANTS_OK rejected=' in run.stdout,(run.returncode,run.stdout,run.stderr)
assert len({sha(images/name) for name in ['baseline','permuted','reordered','combined']})==1;assert sha(images/'request-forward')==sha(images/'request-reverse')
observations=[]
for name in ['baseline','permuted','reordered','combined','request-forward','request-reverse']:
    artifact=images/name
    for mode,command in [('native',[artifact]),('stress',[sys.executable,HERE/'v160-native-observe.py','--stress','--report',out/(name+'-stress.json'),'--',artifact])]:
        result=subprocess.run(list(map(str,command)),capture_output=True,timeout=180);observations.append(dict(image=name,mode=mode,sha256=sha(artifact),exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=(result.returncode,result.stdout,result.stderr)==(0,b'',b'')));(out/'results.json').write_text(json.dumps(observations,indent=2)+'\n');assert observations[-1]['passed'],observations[-1]
        if mode=='stress':
            stress=json.loads((out/(name+'-stress.json')).read_text());assert stress['stress'] and stress['heap']['collections']>0
assert all(sha(project/r['path'])==r['sha256'] for r in inventory)
print('V170_CONTRACT_IMAGE_RUNTIME_OK images=6 observations=12')
