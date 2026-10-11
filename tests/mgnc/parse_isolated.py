#!/usr/bin/env python3
"""Parse every exact C0/C1 file in each toolchain-free nonroot userland."""
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
from isolated import prefix
from parse_workloads import sha
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--fixtures',required=True,type=Path);ap.add_argument('--userland',required=True,action='append',type=Path);ap.add_argument('--evidence',required=True,type=Path);a=ap.parse_args();manifest=json.loads((a.fixtures/'manifest.json').read_text());rows=[];envs=[]
 cases=[x for x in manifest['cases'] if x['group'] in ['C0','C1']];assert len({x['path'] for x in cases})==len(cases)
 with tempfile.TemporaryDirectory(prefix='mgnc-parse-isolated-') as work:
  output=Path(work);marker=output/'unchanged';marker.write_bytes(b'unchanged');mounted=output/'input.mgn'
  for env in a.userland:
   release=(env/'etc/os-release').read_text();assert 'VERSION_ID="24.04"' in release or 'VERSION_ID="26.04"' in release
   envs.append(dict(path=str(env),os_release=release))
   for case in cases:
    source=a.fixtures/case['path'];assert sha(source.read_bytes())==case['sha256'];mounted.write_bytes(source.read_bytes());start=time.monotonic()
    p=subprocess.run(prefix(env.resolve(),a.compiler.resolve(),output)+['/emitter','parse','input.mgn'],capture_output=True,timeout=120)
    row=dict(environment=env.name,group=case['group'],path=case['name'],source_sha256=case['sha256'],exit=p.returncode,stdout_hex=p.stdout.hex(),stderr_hex=p.stderr.hex(),wall_seconds=time.monotonic()-start);rows.append(row)
    a.evidence.write_text(json.dumps(dict(compiler_sha256=sha(a.compiler.read_bytes()),kernel=os.uname().release,nonroot=os.getuid()!=0,environments=envs,records=rows),indent=2)+'\n')
    assert (p.returncode,p.stdout,p.stderr)==(0,b'',b''),row
    assert sha(source.read_bytes())==case['sha256'] and set(output.iterdir())=={marker,mounted} and sha(mounted.read_bytes())==case['sha256'] and marker.read_bytes()==b'unchanged'
   print('PARSE_ISOLATED',env.name,len(cases),flush=True)
 print('PARSE_ISOLATED_OK',len(rows),flush=True)
if __name__=='__main__':main()
