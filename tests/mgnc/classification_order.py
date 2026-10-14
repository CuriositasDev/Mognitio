#!/usr/bin/env python3
"""Run the native guard regression in the opposite grammar prediction order."""
import argparse,hashlib,io,json,subprocess,tarfile,tempfile
from pathlib import Path
from generate_grammar import load,mgn
ROOT=Path(__file__).resolve().parents[2]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seed',required=True);ap.add_argument('--force-full-classification',action='store_true');ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args()
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 archive=subprocess.check_output(['git','archive',head,'compiler/mgnc'],cwd=ROOT)
 with tempfile.TemporaryDirectory(prefix='mgnc-classification-order-') as work:
  root=Path(work)
  with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(root,filter='data')
  project=root/'compiler/mgnc';(project/'src/Grammar/table.mgn').write_text(mgn(load(ROOT/'tests/mgnc/grammar.txt'),True))
  if args.force_full_classification:
   classification=project/'src/SemanticClassification/classify.mgn';source=classification.read_text()
   assert source.count('var required:Bool=false;')==1
   classification.write_text(source.replace('var required:Bool=false;','var required:Bool=true;'))
  binary=root/'mgnc';build=subprocess.run([args.seed,'build',project/'mognitio.toml','-o',binary],capture_output=True,timeout=600)
  assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),build.stderr.decode()
  evidence=root/'classification.json';run=subprocess.run(['python3',str(ROOT/'tests/mgnc/classification.py'),'--compiler',binary,'--evidence',evidence],capture_output=True,text=True,timeout=120)
  result=dict(head=head,reverse_prediction=True,force_full_classification=args.force_full_classification,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),exit=run.returncode,stdout=run.stdout,stderr=run.stderr,observations=json.loads(evidence.read_text()) if evidence.exists() else None)
  args.evidence.write_text(json.dumps(result,indent=2)+'\n');print(run.stdout,run.stderr);assert run.returncode==0
 print('CLASSIFICATION_ORDER_OK')
if __name__=='__main__':main()
