#!/usr/bin/env python3
"""Check bounded mixed-value lifetimes against a retained-value growth control.

These structural functional bounds are separate from wall/RSS acceptance budgets.
"""
from pathlib import Path
import argparse,subprocess,json,hashlib,sys,shutil
HERE=Path(__file__).resolve().parent
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);compiler=args.compiler.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();digest=sha(compiler)
 shutil.copyfile(HERE/'fixtures/v170-lifetimes.mgn',out/'input.mgn');(out/'identity.input').write_bytes(b'identity fixture\n')
 source_digest=sha(out/'input.mgn');run=subprocess.run([compiler,'build',out/'input.mgn','-o',out/'program'],capture_output=True,timeout=180);(out/'build.stdout').write_bytes(run.stdout);(out/'build.stderr').write_bytes(run.stderr);assert (run.returncode,run.stdout,run.stderr)==(0,b'',b''),(run.returncode,run.stderr)
 rows=[];expected=b'checkpoint\n'*4+b'done\n'
 for mode in ['bounded','retained','resources']:
  for count in [64,256,1024]:
   command=[str(out/'program'),mode,str(count),str(out/'identity.input')];run=subprocess.run(command,capture_output=True,timeout=180);assert (run.returncode,run.stdout,run.stderr)==(0,expected,b''),(mode,count,run.returncode,run.stdout,run.stderr)
   for stress in [False,True]:
    report=out/(mode+'-'+str(count)+('-stress' if stress else '-normal')+'.json');run=subprocess.run([sys.executable,str(HERE/'v170-lifetime-observe.py'),'--report',str(report),*(['--stress'] if stress else []),'--',*command],capture_output=True,timeout=300);(report.with_suffix('.stdout')).write_bytes(run.stdout);(report.with_suffix('.stderr')).write_bytes(run.stderr);assert (run.returncode,run.stdout,run.stderr)==(0,expected,b''),(mode,count,stress,run.returncode,run.stderr[-1800:]);data=json.loads(report.read_text());assert not data['error'];samples=data['snapshots'];assert data['allocation_observations']>0 and 0<data['maximum_requested_allocation']<=65536;assert all(s['frame_depth']<=8 and s['fd_count']<=3 and s['resource_depth']<=2 and s['scratch_bytes']<=65536 for s in samples)
    sizes=[s['reachable_bytes'] for s in samples]
    if mode!='retained':assert max(sizes)<=262144,(mode,count,stress,sizes)
    else:assert sizes[-1]>=count*256 and sizes[-1]>sizes[0],(mode,count,stress,sizes)
    assert not stress or samples[-1]['collections']>samples[0]['collections']>0
    rows.append(dict(mode=mode,count=count,stress=stress,reachable_bytes=sizes,collections=[s['collections'] for s in samples],descriptor_counts=[s['descriptor_count'] for s in samples],allocation_observations=data['allocation_observations'],maximum_requested_allocation=data['maximum_requested_allocation']));(out/'results.json').write_text(json.dumps(dict(kind='lifetime-functional-not-formal-performance',compiler_sha256=digest,source_sha256=source_digest,program_sha256=sha(out/'program'),observations=rows),indent=2)+'\n');print(mode,count,stress,sizes,data['maximum_requested_allocation'],flush=True)
 assert len(rows)==18 and len({n for r in rows for n in r['descriptor_counts']})==1 and sha(compiler)==digest and sha(out/'input.mgn')==source_digest;print('V170_LIFETIME_OK observations=18 unobserved=9')
if __name__=='__main__':main()
