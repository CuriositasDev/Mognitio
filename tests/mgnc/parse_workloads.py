#!/usr/bin/env python3
"""Freeze exact corpus inventories and independently constructed parse scale inputs."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C0='d14764bb2d9561eba99b584d31efa5a11aef0262'
def sha(data):return hashlib.sha256(data).hexdigest()
def sources():
 result=[]
 def add(name,text,**metadata):result.append((name,text.encode('utf-8'),metadata))
 for count in [10,100,1000]:
  add(f'flat-types-{count}','namespace A;'+''.join(f'type T{i}=product{{value:Int;}};' for i in range(count)),declarations=count)
  add(f'flat-functions-{count}','namespace A;'+''.join(f'let f{i}:Function():Int=function():Int{{0}};' for i in range(count)),declarations=count)
 for depth in [1,8,32,128]:
  add(f'blocks-{depth}','namespace A;let x:Int='+'{'*depth+'0'+'}'*depth+';',syntax_depth=depth)
  add(f'branches-{depth}','namespace A;let x:Int='+'branch when{true=>0,else=>'*depth+'0'+'}'*depth+';',syntax_depth=depth)
  add(f'types-{depth}','namespace A;let x:'+'List<'*depth+'Int'+'>'*depth+'=value;',type_depth=depth)
 deep='List<'*128+'Int'+'>'*128
 add('combined','namespace A;'+''.join(f'type T{i}=product{{value:Int;}};' for i in range(999))+'let f:Function():Int=function():Int{let x:'+deep+'=value;'+'{'*127+'0'+'}'*127+'};',declarations=1000,syntax_depth=128,type_depth=128)
 for kind in ['string','comment']:
  for encoding in ['ascii','unicode']:
   for size in [1024,65536,1048576]:
    prefix=(('//é日😀\r\n' if encoding=='unicode' else '')+'namespace A;let text:String="') if kind=='string' else 'namespace A;//'
    suffix='";' if kind=='string' else '\r\n'
    pattern='x' if encoding=='ascii' else r'aé日😀\n\u{1f600}'
    room=size-len((prefix+suffix).encode());unit=len(pattern.encode());body=pattern*(room//unit)+'x'*(room%unit)
    text=prefix+body+suffix;assert len(text.encode())==size
    add(f'{kind}-{encoding}-{size}',text,target_bytes=size,scalars=len(text),content=kind,encoding=encoding)
    if size==1048576 and encoding=='unicode':
     add(f'{kind}-bad-start',')'+text,expected=1,phase='parse',span=[0,1,1,1])
     add(f'{kind}-bad-end',text+')',expected=1,phase='parse',span=[size,size+1,len(text.splitlines())+(1 if text.endswith(('\r','\n')) else 0),len(text.rsplit('\n',1)[-1])+1])
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--revision',default='HEAD');args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 revision=subprocess.check_output(['git','rev-parse',args.revision],cwd=ROOT,text=True).strip();records=[];identities={}
 for label,commit in [('C0',C0),('C1',revision)]:
  paths=subprocess.check_output(['git','ls-tree','-r','--name-only',commit,'compiler/mgnc/src'],cwd=ROOT,text=True).splitlines();paths=[p for p in paths if p.endswith('.mgn')]
  identities[label]=dict(commit=commit,files=len(paths),manifest_sha256=sha(subprocess.check_output(['git','show',commit+':compiler/mgnc/mognitio.toml'],cwd=ROOT)))
  for path in paths:
   data=subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT);dest=args.output/label/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
   records.append(dict(group=label,name=path,path=str(dest.relative_to(args.output)),bytes=len(data),sha256=sha(data),expected=0))
 for name,data,meta in sources():
  dest=args.output/'scale'/(name+'.mgn');dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
  records.append(dict(group='scale',name=name,path=str(dest.relative_to(args.output)),bytes=len(data),sha256=sha(data),expected=0)|meta)
 manifest=dict(identities=identities,cases=records);(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('PARSE_WORKLOADS',len(records),'scale',sum(x['group']=='scale' for x in records),identities)
if __name__=='__main__':main()
