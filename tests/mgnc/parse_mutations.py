#!/usr/bin/env python3
"""Four independent single-byte corruptions of the complete frozen C0 files."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from parse_workloads import C0,ROOT
HASHES={'Data/data.mgn':'7c8bc81e369e11a176690581b6c3dc6f9d23f3d0667dfda2f073b6f3f0f7f1b7','Fields/fields.mgn':'8e3bffd507c1870e2e484ecbb03d6c7bd3af4ae92fd1422dda49e5a17440cebc','Parser/expression.mgn':'77952a3621e8942a392e4a0026036a38430776f6e4cc612c42b80dd5de6a2dda','Width/width.mgn':'8091746b104b9088204f72ee89d51df21f7031971f36b7789a7fc17bacb7c340'}
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);a=ap.parse_args();rows=[]
 with tempfile.TemporaryDirectory(prefix='mgnc-corpus-mutations-') as work:
  for name,digest in HASHES.items():
   path='compiler/mgnc/src/'+name;before=subprocess.check_output(['git','show',C0+':'+path],cwd=ROOT);assert sha(before)==digest
   phase='parse';replacement=b')'
   if name.startswith('Data/'):
    at=before.rindex(b';');replacement=b'';after=before[:at]+before[at+1:];start=len(after);end=start
   else:
    if name.startswith('Fields/'):at=before.index(b'Result<Bytes,Diagnostic>')+len(b'Result<Bytes,Diagnostic')
    elif name.startswith('Parser/'):at=before.index(b'loop while(true){')+len(b'loop while(true)')
    else:at=before.index(b'";',before.index(b'let width3:'));replacement=b'\n';phase='lexical'
    after=before[:at]+replacement+before[at+1:];start=at;end=at+1
   prefix=after[:start].decode();line=prefix.count('\n')+1;column=len(prefix.rsplit('\n',1)[-1])+1
   source=Path(work)/Path(name).name;source.write_bytes(after);p=subprocess.run([a.compiler.resolve(),'parse',source],capture_output=True,timeout=120)
   expected=f':{line}:{column} [{start},{end})'.encode();good=p.returncode==1 and not p.stdout and b'mgnc: '+phase.encode()+b':' in p.stderr and expected in p.stderr and source.read_bytes()==after
   row=dict(id='C140-S03',source=path,commit=C0,original_sha256=digest,mutated_sha256=sha(after),edit=dict(start=at,removed_hex=before[at:at+1].hex(),inserted_hex=replacement.hex()),expected_phase=phase,expected_span=[start,end,line,column],exit=p.returncode,stderr=p.stderr.decode(),passed=good);rows.append(row)
   a.evidence.write_text(json.dumps(dict(compiler_sha256=sha(a.compiler.read_bytes()),records=rows),indent=2)+'\n');assert good,row
  # Preserve every C0 byte and add a legal multibyte trailing comment as a
  # positive control, then introduce one final unmatched delimiter after it.
  original=subprocess.check_output(['git','show',C0+':compiler/mgnc/src/Width/width.mgn'],cwd=ROOT)
  augmented=original+'//é日😀\r\n'.encode()
  source=Path(work)/'width-multibyte.mgn'
  for label,data,want in [('valid-comment',augmented,0),('broken-tail',augmented+b')',1)]:
   source.write_bytes(data);p=subprocess.run([a.compiler.resolve(),'parse',source],capture_output=True,timeout=120)
   line=augmented.count(b'\n')+1;span=[len(augmented),len(augmented)+1,line,1]
   good=p.returncode==want and not p.stdout and source.read_bytes()==data
   if want:good=good and b'mgnc: parse:' in p.stderr and f':{line}:1 [{span[0]},{span[1]})'.encode() in p.stderr
   else:good=good and not p.stderr
   row=dict(id='C140-S03',variant=label,source='compiler/mgnc/src/Width/width.mgn',commit=C0,original_sha256=sha(original),valid_source_sha256=sha(augmented),source_sha256=sha(data),expected_span=span if want else None,exit=p.returncode,stderr=p.stderr.decode(),passed=good);rows.append(row)
   a.evidence.write_text(json.dumps(dict(compiler_sha256=sha(a.compiler.read_bytes()),records=rows),indent=2)+'\n');assert good,row
 print('PARSE_MUTATIONS_OK',len(rows))
if __name__=='__main__':main()
