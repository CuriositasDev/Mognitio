#!/usr/bin/env python3
"""Allocation failure, OS signal and harness timeout stay distinct in parse."""
import argparse,hashlib,json,os,signal,subprocess,sys,tempfile
from pathlib import Path
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);a=ap.parse_args();rows=[]
 with tempfile.TemporaryDirectory(prefix='mgnc-parse-faults-') as work:
  root=Path(work);source=root/'input.mgn';source.write_text('namespace A;'+''.join(f'let f{i}:Function():Int=function():Int{{0}};' for i in range(1000)));before=source.read_bytes();digest=hashlib.sha256(before).hexdigest()
  p=subprocess.run([sys.executable,Path(__file__).with_name('syscall-fault.py'),'--syscall','9','--ordinal','1','--errno','12','--',a.compiler.resolve(),'parse',source],capture_output=True,timeout=120)
  assert p.returncode==4 and not p.stdout and b'runtime error:' in p.stderr,p
  rows.append(dict(kind='allocation',exit=4,stdout_hex=p.stdout.hex(),stderr_hex=p.stderr.hex()))
  p=subprocess.Popen([a.compiler.resolve(),'parse',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE);os.kill(p.pid,signal.SIGKILL);out,err=p.communicate(timeout=5);assert p.returncode==-signal.SIGKILL
  rows.append(dict(kind='os-kill',signal=signal.SIGKILL,exit=p.returncode,stdout_hex=out.hex(),stderr_hex=err.hex()))
  try:subprocess.run([a.compiler.resolve(),'parse',source],capture_output=True,timeout=.01)
  except subprocess.TimeoutExpired as x:rows.append(dict(kind='harness-timeout',timeout_seconds=.01,exit=None,stdout_hex=(x.stdout or b'').hex(),stderr_hex=(x.stderr or b'').hex()))
  else:raise AssertionError('expected timeout')
  assert source.read_bytes()==before and list(root.iterdir())==[source]
 a.evidence.write_text(json.dumps(dict(compiler_sha256=hashlib.sha256(a.compiler.read_bytes()).hexdigest(),source_sha256=digest,records=rows),indent=2)+'\n');print('PARSE_FAULTS_OK',len(rows))
if __name__=='__main__':main()
