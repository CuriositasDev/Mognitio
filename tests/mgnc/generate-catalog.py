#!/usr/bin/env python3
"""Reproduce compiler-owned catalog declarations from the accepted Lisp sources."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/"compiler/mgnc/src/Catalog/catalog.mgn"
def literal(text,start):
 assert text[start]=='"'
 output=[];index=start+1
 while index<len(text):
  char=text[index];index+=1
  if char=='"':return ''.join(output)
  if char=='\\':char=text[index];index+=1
  output.append(char)
 raise AssertionError("unterminated Lisp catalog string")
def generate():
 records=[];values={}
 for key,file,namespace,marker in [
  ("io","src/standard-catalog.lisp","Std\\Io",'((text "'),
  ("numeric","src/numeric-catalog.lisp","Std\\Numeric",'(utf8 "'),
  ("binary","src/binary-catalog.lisp","Std\\Binary",'((text "'),
 ]:
  path=ROOT/file;text=path.read_text();at=text.index(marker)+len(marker)-1;body=literal(text,at)
  prefix="namespace "+namespace+";\n"
  if key=="binary":prefix+="use Std\\Numeric\\{Bits};\n"
  values[key]=prefix+body
  records.append({"path":file,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"catalog_sha256":hashlib.sha256(values[key].encode()).hexdigest()})
 old=TARGET.read_text()
 for key,value in values.items():
  old=re.sub(r'let '+key+r':String="(?:\\.|[^"\\])*";',lambda _: "let "+key+":String="+json.dumps(value,ensure_ascii=False)+";",old,count=1)
 return old,records
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");args=parser.parse_args()
 generated,records=generate()
 evidence=ROOT/"compiler/mgnc/catalog-inputs.json"
 payload=json.dumps({"command":"python3 tests/mgnc/generate-catalog.py","inputs":records,"generated_sha256":hashlib.sha256(generated.encode()).hexdigest()},indent=2)+"\n"
 if args.check:
  assert TARGET.read_text()==generated,"catalog source drift"
  assert evidence.read_text()==payload,"catalog provenance drift"
 else:TARGET.write_text(generated);evidence.write_text(payload)
 print("V150_CATALOG_REPRODUCIBLE")
if __name__=="__main__":main()
