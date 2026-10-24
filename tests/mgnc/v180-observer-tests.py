#!/usr/bin/env python3
"""Adversarial controls for fresh observer accounting and process recovery."""
from pathlib import Path
import argparse,json,os,sys
import v180_observer as f
parser=argparse.ArgumentParser()
parser.add_argument("--output",type=Path,required=True)
options=parser.parse_args()
O=options.output;O.mkdir(parents=True,exist_ok=False)
rows=[]
def run(name,command,**kwargs):
 r=f.observe(command,O/name,**kwargs);samples=json.loads((O/name/'rss-samples.json').read_text());assert r['sample_count']==len(samples) and r['sampled_peak_rss_bytes']==max((s['rss_bytes'] for s in samples),default=None);assert r['rss_samples_sha256']==f.sha(O/name/'rss-samples.json');assert r['unreaped_descendants']==0
 rows.append(dict(name=name,observation=r));return r
a=run('short',['/bin/true']);assert a['exit']==0 and a['cutoff'] is None and a['harness_failure'] is None
b=run('failure',[sys.executable,'-c','import sys;print("out");print("err",file=sys.stderr);sys.exit(7)']);assert b['exit']==7 and (O/'failure/stdout').read_bytes()==b'out\n' and (O/'failure/stderr').read_bytes()==b'err\n'
c=run('sampled',[sys.executable,'-c','import time;x=bytearray(48*1024**2);time.sleep(.12)']);assert c['sampled_peak_rss_bytes']>48*1024**2 and c['sample_count']>=3
d=run('wall',[sys.executable,'-c','import time;time.sleep(30)'],timeout=.1);assert d['cutoff']=='wall' and d['signal']==9
g=run('rss',[sys.executable,'-c','import time;x=bytearray(64*1024**2);time.sleep(30)'],rss_limit=32*1024**2);assert g['cutoff']=='rss' and g['signal']==9
h=run('descendant',[sys.executable,'-c','import os,time;p=os.fork();time.sleep(30) if p==0 else None']);assert h['descendant_residue']>=1 and h['harness_failure']
i=run('observed-child',[sys.executable,'-c','import subprocess;subprocess.run(["/bin/sleep",".12"],check=True)']);assert i['observed_child_pids'] and i['descendant_residue']==0 and i['exit']==0
j=run('short-rss-guard',['/bin/true'],rss_limit=1);assert j['cutoff']=='rss'
padding=bytearray(128*1024**2)
k=run('parent-padded',['/bin/true']);assert k['exit']==0 and k['peak_rss_bytes']<48*1024**2 and abs(k['peak_rss_bytes']-a['peak_rss_bytes'])<16*1024**2
del padding
l=run('parent-freed',['/bin/true']);assert l['exit']==0 and l['peak_rss_bytes']<48*1024**2
data=dict(status='Passed',observer_sha256=f.sha(f.__file__),sources=f.bindings(),instrumented_sha256=f.derived_observe()[1],cases=rows,checks=['exit and stream preservation','sampler peak and full raw samples','wall kill','RSS kill','descendant reaping and rejection','direct child presence','kernel guard on short process','128 MiB retained and freed controller invariance'],observation_scope='Kernel peak includes a fixed fresh-worker floor; zero samples is explicitly null sampler peak, never zero RSS.')
(O/'results.json').write_text(json.dumps(data,indent=2)+'\n');print('FRESH_OBSERVER_CONTROLS_PASSED',len(rows),[(r['name'],r['observation']['peak_rss_bytes'],r['observation']['sampled_peak_rss_bytes']) for r in rows])
