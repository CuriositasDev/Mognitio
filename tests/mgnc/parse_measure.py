#!/usr/bin/env python3
"""Sequential per-process parse wall time/RSS; retain every failure and timeout."""
import argparse,hashlib,json,os,signal,statistics,subprocess,time
from pathlib import Path
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--fixtures',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);ap.add_argument('--preflight',action='store_true');ap.add_argument('--group',action='append');args=ap.parse_args()
 manifest=json.loads((args.fixtures/'manifest.json').read_text());cases=[x for x in manifest['cases'] if not args.group or x['group'] in args.group];records=[]
 evidence=dict(compiler_sha256=hashlib.sha256(args.compiler.read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((args.fixtures/'manifest.json').read_bytes()).hexdigest(),preflight=args.preflight,records=records)
 for group in dict.fromkeys(x['group'] for x in cases):
  for iteration in range(1 if args.preflight else 6):
   for case in [x for x in cases if x['group']==group]:
    path=args.fixtures/case['path'];before=path.read_bytes();assert hashlib.sha256(before).hexdigest()==case['sha256']
    start=time.monotonic();p=subprocess.Popen([args.compiler.resolve(),'parse',path.resolve()],stdout=subprocess.PIPE,stderr=subprocess.PIPE);timed=False
    while True:
     pid,status,usage=os.wait4(p.pid,os.WNOHANG)
     if pid:break
     if time.monotonic()-start>120:p.kill();pid,status,usage=os.wait4(p.pid,0);timed=True;break
     time.sleep(.001)
    elapsed=time.monotonic()-start;p.returncode=os.waitstatus_to_exitcode(status);out=p.stdout.read();err=p.stderr.read()
    okay=p.returncode==case['expected'] and out==b'' and not timed and path.read_bytes()==before
    if case['expected']==0:okay=okay and not err
    else:okay=okay and ('mgnc: '+case['phase']+':').encode() in err
    if 'span' in case:
     a,b,line,col=case['span'];okay=okay and f'[{a},{b})'.encode() in err and f':{line}:{col}'.encode() in err
    row=dict(group=group,name=case['name'],iteration=iteration,warmup=iteration==0,seconds=elapsed,rss_mib=usage.ru_maxrss/1024,exit=p.returncode,stdout_hex=out.hex(),stderr=err.decode(errors='replace'),timeout=timed,passed=bool(okay));records.append(row)
    args.evidence.write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(row),flush=True)
 summaries=[]
 for case in cases:
  rows=[r for r in records if r['group']==case['group'] and r['name']==case['name']];measured=rows if args.preflight else [r for r in rows if not r['warmup']]
  summaries.append(dict(group=case['group'],name=case['name'],median_seconds=statistics.median(r['seconds'] for r in measured),max_rss_mib=max(r['rss_mib'] for r in measured),passed=all(r['passed'] for r in rows)))
 totals={group:[sum(r['seconds'] for r in records if r['group']==group and r['iteration']==iteration) for iteration in range(1 if args.preflight else 6)] for group in ['C0','C1'] if any(r['group']==group for r in records)}
 passed=all(x['passed'] and x['median_seconds']<=30 and x['max_rss_mib']<=512 for x in summaries) and all(statistics.median(v if args.preflight else v[1:])<=120 for v in totals.values())
 evidence.update(summaries=summaries,round_totals=totals,passed=passed);args.evidence.write_text(json.dumps(evidence,indent=2)+'\n');print('PARSE_MEASURE',passed,'preflight',args.preflight,flush=True)
 raise SystemExit(not passed)
if __name__=='__main__':main()
