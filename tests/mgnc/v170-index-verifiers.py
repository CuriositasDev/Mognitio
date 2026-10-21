#!/usr/bin/env python3
"""Check instance grouping and emitted-pointer indexing without weakening oracles."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project);shutil.copyfile(ROOT/'tests/mgnc/harnesses/v170-index-verifiers.mgn',project/'src/mgnc.mgn');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inputs=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 built=subprocess.run([args.seed.resolve(),'build',project/'mognitio.toml','-o',out/'probe'],capture_output=True,timeout=1200);(out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr);assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(built.returncode,built.stderr)
 result=subprocess.run([out/'probe'],capture_output=True,timeout=180);(out/'run.stdout').write_bytes(result.stdout);(out/'run.stderr').write_bytes(result.stderr);assert result.returncode==0 and not result.stderr and result.stdout.count(b'MUTANT ')==25 and result.stdout.endswith(b'V170_INDEX_VERIFIERS_OK valid=2 rejected=25\n'),(result.returncode,result.stdout,result.stderr);assert all(sha(project/r['path'])==r['sha256'] for r in inputs);print(result.stdout.decode(),end='')
if __name__=='__main__':main()
