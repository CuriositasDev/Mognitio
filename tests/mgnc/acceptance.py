#!/usr/bin/env python3
"""Check v1.4 evidence completeness, identities and every retained formal sample."""
import argparse,collections,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,default=ROOT/'verification/v1.4.0');args=ap.parse_args();base=args.evidence
 def load(name):return json.loads((base/name).read_text())
 identity=load('identity.json');compiler=identity['compiler_sha256'];bootstrap=load('bootstrap.json');manifest=load('corpus-and-scale.json');conformance=load('conformance.json')
 expected={f'C140-{group}{i:02}' for group,n in [('L',8),('P',12),('B',8),('N',8),('S',4),('I',5),('R',5),('X',4)] for i in range(1,n+1)}
 assert len(conformance['cases'])==54 and {c['id'] for c in conformance['cases']}==expected
 assert (conformance['required'],conformance['pass_count'],conformance['fail_count'],conformance['unrun_count'])==(54,54,0,0)
 for case in conformance['cases']:
  assert case['required'] and case['result']=='pass' and not case['fail'] and not case['unrun']
  assert case['evidence'] and all((base/p).is_file() for p in case['evidence'])
 inherited=load('inherited-conformance.json');old=json.loads((ROOT/'verification/v1.3.0-review-conformance.json').read_text())
 assert len(inherited['cases'])==55 and {x['id'] for x in inherited['cases']}=={x['id'] for x in old['cases']}
 assert all(c['result']=='pass' and not c['unrun'] and not c['fail'] for c in inherited['cases'])
 current={str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'compiler/mgnc').rglob('*.mgn')}
 assert len(current)==56 and current==identity['executable_source_files']=={r['path']:r['sha256'] for r in bootstrap['inventory']}
 assert digest(ROOT/'compiler/mgnc/mognitio.toml')==identity['manifest_sha256']==bootstrap['manifest_sha256']
 assert bootstrap['exit']==0 and bootstrap['stdout_hex']==bootstrap['stderr_hex']=='' and bootstrap['compiler_sha256']==compiler
 for filename in ['functional.json','parse-cases.json','source-profile.json','review.json','native.json','workloads.json','isolated.json','parse-isolated.json','parse-driver.json','parse-faults.json','parse-mutations.json','parse-compatibility.json','parse-measurement.json','native-measurement.json','ambiguity.json','ambiguity-measurement.json']:
  assert load(filename)['compiler_sha256']==compiler,filename
 suite=load('functional.json');assert suite['complete'] and suite['passed'] and len(suite['records'])==26 and all(r['exit']==0 for r in suite['records'])
 syntax=load('parse-cases.json');assert not syntax['prototype'] and not syntax['parse_only'] and syntax['passed']==syntax['total']==169 and all(r['pass'] for r in syntax['cases'])
 for row in syntax['cases']:
  assert hashlib.sha256(bytes.fromhex(row['source_hex'])).hexdigest()==row['sha256']
  assert row['exit']==(1 if row['phase'] else 0)
  if 'build_result' in row:assert row['build_result']['passed']
 structural=load('structural.json');assert len(structural)==2 and {x['reverse'] for x in structural}=={True,False} and all(x['exit']==0 for x in structural)
 assert all('goldens=4' in x['stdout'] and 'equivalence_pairs=3' in x['stdout'] and 'positive=18 negative=3' in x['stdout'] for x in structural)
 design=load('design-review.json');assert len(design['cases'])==11 and {c['id'] for c in design['cases']}=={f'DR140-T{i:02}' for i in range(1,12)} and all(c['result']=='pass' for c in design['cases'])
 mutations=load('review-mutants.json');assert len(mutations)==5 and all(r['baseline']['passes'] and not r['mutant']['passes'] for r in mutations)
 assert len(load('parse-mutations.json')['records'])==6 and all(r['passed'] for r in load('parse-mutations.json')['records'])
 assert len(load('parse-compatibility.json')['records'])==4 and all(r['normal_exit']==0 and r['parse_exit']==1 for r in load('parse-compatibility.json')['records'])
 cells={(c['group'],c['name']):c for c in manifest['cases']};assert len(cells)==116
 assert collections.Counter(c['group'] for c in manifest['cases'])=={'C0':25,'C1':56,'scale':35}
 assert {c['name']:c['sha256'] for c in manifest['cases'] if c['group']=='C1'}==current
 parse=load('parse-measurement.json');assert parse['passed'] and not parse['preflight'] and len(parse['records'])==696
 for key,cell in cells.items():
  rows=[r for r in parse['records'] if (r['group'],r['name'])==key];assert len(rows)==6 and {r['iteration'] for r in rows}==set(range(6))
  for r in rows:
   assert r['passed'] and not r['timeout'] and r['exit']==cell['expected'] and r['warmup']==(r['iteration']==0) and r['stdout_hex']==''
   if cell['expected']==0:assert r['stderr']==''
   else:assert 'mgnc: '+cell['phase']+':' in r['stderr']
   if 'span' in cell:
    start,end,line,col=cell['span'];assert f'[{start},{end})' in r['stderr'] and f':{line}:{col}' in r['stderr']
  measured=rows[1:];assert statistics.median(r['seconds'] for r in measured)<=30 and max(r['rss_mib'] for r in measured)<=512
 for group in ['C0','C1']:
  totals=[sum(r['seconds'] for r in parse['records'] if r['group']==group and r['iteration']==i) for i in range(6)]
  assert totals==parse['round_totals'][group] and statistics.median(totals[1:])<=120
 native=load('native-measurement.json');assert len(native['cells'])==21 and native['warmups']==1 and native['repeats']==5
 for cell in native['cells']:
  assert cell['pass'] and len(cell['samples'])==6 and all(s['correct'] and not s['timeout'] and s['exit']==0 and s['stdout_hex']==s['stderr_hex']=='' for s in cell['samples'])
  assert sum(not s['warmup'] for s in cell['samples'])==5
  assert statistics.median(s['wall_seconds'] for s in cell['samples'] if not s['warmup'])<=30
  assert max(s['peak_rss_bytes'] for s in cell['samples'] if not s['warmup'])<=256*2**20
  assert len({s['artifact_sha256'] for s in cell['samples']})==1
  for s in cell['samples']:
   assert len(s['runtime'])==3
   for result,want,count in zip(s['runtime'],cell['fixture']['expected'],cell['fixture']['argv_counts']):assert (result['exit'],result['argv_count'],result['stdout_hex'],result['stderr_hex'])==(want,count,'','')
 isolated=load('parse-isolated.json');assert isolated['nonroot'] and len(isolated['environments'])==2 and len(isolated['records'])==162
 for env in {r['environment'] for r in isolated['records']}:
  rows=[r for r in isolated['records'] if r['environment']==env]
  assert len(rows)==81 and {(r['group'],r['path']) for r in rows}=={k for k in cells if k[0] in ['C0','C1']}
  for r in rows:assert (r['exit'],r['stdout_hex'],r['stderr_hex'])==(0,'','') and r['source_sha256']==cells[(r['group'],r['path'])]['sha256']
 ambiguous=load('ambiguity.json');assert ambiguous['complete'] and ambiguous['passed'] and len(ambiguous['records'])==26
 assert all(r['passed'] and not r['timeout'] for r in ambiguous['records'])
 supplemental=load('ambiguity-measurement.json');assert supplemental['passed'] and len(supplemental['records'])==156 and all(r['passed'] for r in supplemental['records'])
 normal=load('normal-equivalence.json');assert normal['unchanged'] and all(digest(ROOT/p)==h for p,h in normal['normal_input_files'].items())
 assert len(load('consumer.json')['records'])==182 and load('consumer-controls.json')['passed']==11
 print('V140_ACCEPTANCE_OK cases=54 inherited=55 corpus=81 parse_samples=696 native_samples=126 auxiliary_samples=156')
if __name__=='__main__':main()
