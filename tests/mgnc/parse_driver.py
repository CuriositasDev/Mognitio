#!/usr/bin/env python3
"""Parse CLI, single-source I/O, no filesystem writes and diagnostic failure."""
import argparse,hashlib,json,os,re,stat,subprocess,tempfile
from pathlib import Path
def snapshot(root):
 result={}
 for p in sorted(root.iterdir()):
  info=p.lstat();result[p.name]=dict(mode=stat.S_IMODE(info.st_mode),mtime=info.st_mtime_ns,kind=stat.S_IFMT(info.st_mode))
  if p.is_symlink():result[p.name]['link']=os.readlink(p)
  elif p.is_file() and info.st_mode&0o400:result[p.name]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);args=ap.parse_args();compiler=args.compiler.resolve();records=[]
 with tempfile.TemporaryDirectory(prefix='mgnc-parse-driver-') as work:
  root=Path(work);trace=root/'traces';trace.mkdir();source=root/'source.mgn';source.write_text('namespace App;use Missing\\{Unknown};')
  keep=root/'existing';keep.write_bytes(b'unchanged');keep.chmod(0o640);bad=root/'bad.mgn';bad.write_text('namespace App;let x:Int=;')
  def invoke(name,argv,expected,fragment=b'',**kwargs):
   before=snapshot(root);p=subprocess.run([compiler,*map(str,argv)],cwd=root,capture_output=True,timeout=120,**kwargs)
   good=p.returncode==expected and p.stdout==b'' and (fragment in p.stderr if fragment else p.stderr==b'') and before==snapshot(root)
   row=dict(name=name,argv=list(map(str,argv)),exit=p.returncode,stdout_hex=p.stdout.hex(),stderr=p.stderr.decode(errors='replace'),unchanged=before==snapshot(root),passed=good);records.append(row)
   assert good,row;return p
  for i,argv in enumerate([[],['parse'],['parse','source.mgn','extra'],['parse','source.mgn','-o','new'],['parse','mognitio.toml'],['parse',''],['unknown','source.mgn']]):invoke('C140-I01-'+str(i),argv,2,b'cli:')
  for i,name in enumerate(['relative.mgn','space input.mgn','-leading.mgn']):
   p=root/name;p.write_bytes(source.read_bytes());invoke('C140-I02-'+str(i),['parse',name],0)
  invoke('C140-I02-absolute',['parse',source],0)
  linked=root/'link.mgn';linked.symlink_to(source);invoke('C140-I02-symlink',['parse',linked],0)
  directory=root/'dir.mgn';directory.mkdir();denied=root/'denied.mgn';denied.write_bytes(source.read_bytes());denied.chmod(0)
  try:
   for name,p,fragment in [('missing',root/'missing.mgn',b'NotFound'),('directory',directory,b'UnsupportedTarget'),('denied',denied,b'PermissionDenied')]:invoke('C140-I03-'+name,['parse',p],2,fragment)
  finally:denied.chmod(0o600)
  invoke('C140-I04-success',['parse',source],0);invoke('C140-I04-invalid',['parse',bad],1,b'parse:')
  for fault in ['closed','pipe']:
   writer=None;before=snapshot(root)
   if fault=='closed':kwargs=dict(preexec_fn=lambda:os.close(2),stderr=subprocess.PIPE)
   else:
    reader,writer=os.pipe();os.close(reader);kwargs=dict(stderr=writer)
   try:p=subprocess.run([compiler,'parse',bad],cwd=root,stdout=subprocess.PIPE,timeout=120,**kwargs)
   finally:
    if writer is not None:os.close(writer)
   good=p.returncode==2 and p.stdout==b'' and snapshot(root)==before;records.append(dict(name='C140-I04-'+fault,exit=p.returncode,unchanged=snapshot(root)==before,passed=good));assert good
  for name,argv,expected in [('source',['parse',source],0),('cli',['parse',source,'extra'],2)]:
   log=trace/(name+'.log');before=snapshot(root)
   # Trace files are written only by the harness and are inside the existing trace directory.
   p=subprocess.run(['strace','-qq','-f','-e','trace=%file,execve,execveat','-o',log,compiler,*map(str,argv)],capture_output=True,timeout=120)
   text=log.read_text();opens=[line for line in text.splitlines() if re.search(r'\bopen(?:at|at2)?\(',line)]
   source_opens=[line for line in opens if str(source) in line];expected_opens=1 if name=='source' else 0
   assert p.returncode==expected and len(source_opens)==expected_opens,(p,text)
   assert not any(re.search(r'O_(?:WRONLY|RDWR|CREAT)',line) for line in opens),text
   assert sum('execve(' in line or 'execveat(' in line for line in text.splitlines())==1,text
   assert not any('Missing' in line for line in opens),text
   records.append(dict(name='C140-I01-single-read-'+name,source_opens=len(source_opens),trace=text,passed=True))
 data=dict(compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),records=records,passed=all(x['passed'] for x in records));args.evidence.write_text(json.dumps(data,indent=2)+'\n');print('PARSE_DRIVER_OK',len(records))
if __name__=='__main__':main()
