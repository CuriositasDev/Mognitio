#!/usr/bin/env python3
"""Validate the review correction against current source and all fresh public-path runs."""
import collections,hashlib,json,statistics
from pathlib import Path
from parse_workloads import sources
from parse_workload_shapes import verify
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify_review(base=ROOT/'verification/v1.4.0-review'):
 def read(name):return json.loads((base/name).read_text())
 identity=read('identity.json');bootstrap=read('bootstrap.json');candidate=next(x for x in bootstrap if x['label']=='candidate');compiler=candidate['compiler_sha256']
 current={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'compiler/mgnc/src').rglob('*.mgn')}
 assert current==candidate['source_files']==identity['source_files']
 assert candidate['revision']==identity['source_revision'] and compiler==identity['compiler_sha256']
 assert sha(ROOT/'compiler/mgnc/mognitio.toml')==candidate['manifest_sha256']
 assert all(x['exit']==0 and x['stdout_hex']=='' and x['stderr']=='' for x in bootstrap)
 assert all(sha(ROOT/p)==h for p,h in identity['harness_files'].items())
 # The old structural/native-core evidence is reused only for byte-identical implementation inputs.
 assert identity['reused_unchanged_files'] and all(sha(ROOT/p)==h for p,h in identity['reused_unchanged_files'].items())
 suite=read('functional.json');assert suite['complete'] and suite['passed'] and suite['compiler_sha256']==compiler
 required={'generate-width.py','generate_grammar.py','generate_storage.py','parse_workload_shapes.py','classification.py','source_profile.py','parse_cases.py','review.py','parse_driver.py','parse_faults.py','parse_mutations.py','parse_compatibility.py','native.py','workloads.py','driver.py','faults.py','isolated.py','parse_isolated.py'}
 assert len(suite['records'])==len(required) and {r['command'][0] for r in suite['records']}==required and all(r['exit']==0 for r in suite['records'])
 for name in ['classification','source_profile','parse_cases','review','parse_driver','parse_faults','parse_mutations','parse_compatibility','native','workloads','isolated','parse_isolated']:
  assert read(name+'.json')['compiler_sha256']==compiler,name
 cases=read('classification.json');assert cases['complete'] and cases['passed'] and len(cases['records'])==20
 for row in cases['records']:
  assert row['passed'] and row['parse_exit']==0 and hashlib.sha256(bytes.fromhex(row['source_hex'])).hexdigest()==row['source_sha256']
  assert set(row['results'])=={'candidate','baseline'}
  for result in row['results'].values():
   assert result['stdout_hex']==''
   if row['phase']:assert result['build_exit']==1 and not result['artifact'] and 'mgnc: '+row['phase']+':' in result['stderr']
   else:assert result['build_exit']==0 and result['artifact'] and result['stderr']=='' and (result['run_exit'],result['run_stdout_hex'],result['run_stderr_hex'])==(row['expected'],'','')
 order=read('order.json');assert order['reverse_prediction'] and order['exit']==0 and order['observations']['passed'] and order['observations']['complete'] and len(order['observations']['records'])==20
 assert {r['source_sha256'] for r in order['observations']['records']}=={r['source_sha256'] for r in cases['records']}
 syntax=read('parse_cases.json');assert syntax['passed']==syntax['total']==169 and all(r['pass'] for r in syntax['cases'])
 manifest=read('corpus-and-scale.json');cells={(c['group'],c['name']):c for c in manifest['cases']};counts=collections.Counter(c['group'] for c in manifest['cases'])
 assert len(cells)==len(manifest['cases']) and counts=={'C0':25,'C1':len(current),'scale':35}
 assert {c['name']:c['sha256'] for c in manifest['cases'] if c['group']=='C1'}==current
 for name,data,meta in sources():
  cell=cells[('scale',name)];assert cell['sha256']==hashlib.sha256(data).hexdigest() and cell['bytes']==len(data)
  if name=='combined':assert verify(data,cell)==dict(declarations=1000,syntax_depth=128,type_depth=128)
 parse=read('parse-measurement.json');assert parse['compiler_sha256']==compiler and parse['passed'] and not parse['preflight'] and len(parse['records'])==len(cells)*6
 for key,cell in cells.items():
  rows=[r for r in parse['records'] if (r['group'],r['name'])==key];assert len(rows)==6 and {r['iteration'] for r in rows}==set(range(6))
  for row in rows:
   assert row['passed'] and not row['timeout'] and row['exit']==cell['expected'] and row['warmup']==(row['iteration']==0) and row['stdout_hex']==''
   if cell['expected']==0:assert row['stderr']==''
   else:assert 'mgnc: '+cell['phase']+':' in row['stderr']
   if 'span' in cell:
    a,b,line,col=cell['span'];assert f'[{a},{b})' in row['stderr'] and f':{line}:{col}' in row['stderr']
  measured=[r for r in rows if not r['warmup']];assert statistics.median(r['seconds'] for r in measured)<=30 and max(r['rss_mib'] for r in measured)<=512
 for group in ['C0','C1']:
  totals=[sum(r['seconds'] for r in parse['records'] if r['group']==group and r['iteration']==i) for i in range(6)]
  assert totals==parse['round_totals'][group] and statistics.median(totals[1:])<=120
 native=read('native-measurement.json');assert native['compiler_sha256']==compiler and len(native['cells'])==21 and native['warmups']==1 and native['repeats']==5
 for cell in native['cells']:
  assert cell['pass'] and len(cell['samples'])==6 and sum(s['warmup'] for s in cell['samples'])==1
  assert all(s['correct'] and not s['timeout'] and s['exit']==0 and s['stdout_hex']==s['stderr_hex']=='' for s in cell['samples'])
  assert statistics.median(s['wall_seconds'] for s in cell['samples'] if not s['warmup'])<=30 and max(s['peak_rss_bytes'] for s in cell['samples'] if not s['warmup'])<=256*2**20
  assert len({s['artifact_sha256'] for s in cell['samples']})==1
  for sample in cell['samples']:
   assert len(sample['runtime'])==3
   for result,want,count in zip(sample['runtime'],cell['fixture']['expected'],cell['fixture']['argv_counts']):assert (result['exit'],result['argv_count'],result['stdout_hex'],result['stderr_hex'])==(want,count,'','')
 isolated=read('parse_isolated.json');assert isolated['nonroot'] and len(isolated['environments'])==2 and len(isolated['records'])==2*(25+len(current))
 for env in {r['environment'] for r in isolated['records']}:
  rows=[r for r in isolated['records'] if r['environment']==env];assert len(rows)==25+len(current) and {(r['group'],r['path']) for r in rows}=={k for k in cells if k[0] in ['C0','C1']}
  for row in rows:assert (row['exit'],row['stdout_hex'],row['stderr_hex'])==(0,'','') and row['source_sha256']==cells[(row['group'],row['path'])]['sha256']
 normal=read('normal-suite.json');assert normal['exit']==0 and normal['final_marker']=='ACCEPTANCE_EDGES_OK checks=19'
 assert normal['tests']==214 and normal['assertions']==9261 and normal['processes']==1266 and all(sha(ROOT/p)==h for p,h in normal['input_files'].items())
 print(f'V140_REVIEW_ACCEPTANCE_OK classification=20 orders=2 corpus={25+len(current)} parse_samples={len(parse["records"])} native_samples=126 normal_exit=0')
if __name__=='__main__':verify_review()
