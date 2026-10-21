#!/usr/bin/env python3
"""Verify failure before and after boxing, without publishing partial packages."""
import argparse,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False);rows=[]
for name in ['scalar','unit','managed-snapshot','function','returned-method-closure','wide-word']:
    program=(args.fixtures/name/'program').resolve();assert program.is_file()
    for stage in ['box','package']:
        report=args.output/(name+'-'+stage+'.json');run=subprocess.run([sys.executable,str(HERE/'v170-contract-allocation-fault.py'),'--stage',stage,'--report',str(report),str(program)],capture_output=True,timeout=60)
        passed=(run.returncode,run.stdout,run.stderr)==(0,b'',b'runtime error: allocation failure\n');rows.append(dict(case=name,stage=stage,exit=run.returncode,stdout_hex=run.stdout.hex(),stderr_hex=run.stderr.hex(),passed=passed));(args.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1];data=json.loads(report.read_text());assert data['injected'] and data['exit']==4
print('V170_CONTRACT_ALLOCATION_OK cases='+str(len(rows)))
