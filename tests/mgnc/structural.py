#!/usr/bin/env python3
"""Build exact-HEAD forest probes and compare every reachable family in two orders."""
import argparse,hashlib,io,json,subprocess,tarfile,tempfile
from pathlib import Path
from generate_grammar import load,mgn
ROOT=Path(__file__).resolve().parents[2]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args()
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();rows=[]
 archive=subprocess.check_output(['git','archive',head,'compiler/mgnc'],cwd=ROOT)
 entry=subprocess.check_output(['git','show',head+':tests/mgnc/harnesses/forest.mgn'],cwd=ROOT)
 with tempfile.TemporaryDirectory(prefix='mgnc-structural-') as work:
  root=Path(work)
  for reverse in [False,True]:
   location=root/str(reverse);location.mkdir()
   with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(location,filter='data')
   project=location/'compiler/mgnc';(project/'src/mgnc.mgn').write_bytes(entry)
   if reverse:(project/'src/Grammar/table.mgn').write_text(mgn(load(ROOT/'tests/mgnc/grammar.txt'),True))
   binary=location/'probe';build=subprocess.run([args.seed,'build',project/'mognitio.toml','-o',binary],capture_output=True,timeout=600)
   assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),build.stderr.decode()
   run=subprocess.run(['python3',str(ROOT/'tests/mgnc/forest_oracle.py'),'--compiler',binary],capture_output=True,timeout=120)
   row=dict(head=head,reverse=reverse,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),exit=run.returncode,stdout=run.stdout.decode(),stderr=run.stderr.decode());rows.append(row)
   args.evidence.write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
   assert run.returncode==0,row
 print('STRUCTURAL_ORACLE_OK orders=2',flush=True)
if __name__=='__main__':main()
