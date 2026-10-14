#!/usr/bin/env python3
"""Independently exercise the complete ASCII and keyword lookup domains."""
import argparse,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument("--seed",required=True,type=Path);a=p.parse_args()
 with tempfile.TemporaryDirectory(prefix="mgnc-text-lookup-") as temp:
  work=Path(temp);(work/"src").mkdir()
  for module in ["Data","Width","TextUtil"]:shutil.copytree(ROOT/"compiler/mgnc/src"/module,work/"src"/module)
  (work/"mognitio.toml").write_text('[project]\nname="app"\nroot_namespace="Mgnc"\n')
  shutil.copyfile(ROOT/"tests/mgnc/harnesses/v150-text.mgn",work/"src/app.mgn")
  binary=work/"probe";build=subprocess.run([a.seed.resolve(),"build",work/"mognitio.toml","-o",binary],capture_output=True,timeout=120)
  assert (build.returncode,build.stdout,build.stderr)==(0,b"",b""),build.stderr.decode()
  run=subprocess.run([binary],capture_output=True,timeout=120)
  assert (run.returncode,run.stderr)==(0,b""),run
  print(run.stdout.decode().strip())
if __name__=="__main__":main()
