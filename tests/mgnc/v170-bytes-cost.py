#!/usr/bin/env python3
"""Check Bytes snapshots and structural work with independent fixed formulas.

Instruction bounds are fixture-specific structural guards, separate from wall/RSS
budgets. The source implementation uses bounded setup and one REP pass per copy
or comparison; the observer counts executed work without modifying the target.
"""
from pathlib import Path
import subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
root=ROOT;out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);compiler=args.compiler.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();digest=sha(compiler)
prefix=r'''namespace App;
use Std\Numeric\{Bits,Unsigned,IntegerConversionError};
use Std\Binary\{Bytes,ByteValueError,bytesFromInts};
use Std\Io\{writeStdout};
let make:Function(Int,Int):Bytes=function(size:Int,offset:Int):Bytes{
 var values:List<Int>=List<Int>[];var i:Int=0;loop while(i<size){values=values->append((i+offset)%256);i=i+1;};
 branch on bytesFromInts(values){Result<Bytes,ByteValueError>::Ok(value:Bytes)=>value,Result<Bytes,ByteValueError>::Err(error:ByteValueError)=>panic{"fixture range"}}
};
let octet:Function(Bytes,Int):Int=function(value:Bytes,index:Int):Int{
 let byte:Bits<8>=branch on value->at(index){Result<Bits<8>,IndexError>::Ok(v:Bits<8>)=>v,Result<Bits<8>,IndexError>::Err(error:IndexError)=>panic{"fixture index"}};
 branch on byte->asInteger<Unsigned>()->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(v:Int)=>v,Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>panic{"fixture conversion"}}
};
let check:Function(Bytes,Int,Int,Int):Unit=function(value:Bytes,first:Int,count:Int,offset:Int):Unit{
 var i:Int=0;loop while(i<count){assert octet(value,first+i)==(i+offset)%256;i=i+1;};unit
};
'''
cases=[]
def save(name,n,setup,operation,post,copied,compared):
 source=prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{let original:Bytes=make('+str(n)+',0);'+setup+'discard writeStdout("COST_BEGIN\\n");'+operation+'discard writeStdout("COST_END\\n");'+post+'assert original->length()=='+str(n)+';check(original,0,'+str(n)+',0);0};\n';folder=out/name;folder.mkdir();(folder/'input.mgn').write_text(source);cases.append(dict(name=name,length=n,source_sha256=sha(folder/'input.mgn'),copied_bytes=copied,compared_bytes=compared,step_bound=2048 if name.startswith('length-') else 2048+16*(n+copied+compared+1)))
for n in [0,1,16,64,256,1024]:
 save('length-'+str(n),n,'','let result:Int=original->length();','assert result=='+str(n)+';',0,0)
 if n:save('at-valid-'+str(n),n,'','let result:Result<Bits<8>,IndexError>=original->at('+str(n-1)+');','branch on result{Result<Bits<8>,IndexError>::Ok(value:Bits<8>)=>{assert value==Bits<8>{'+str((n-1)%256)+'};},Result<Bits<8>,IndexError>::Err(error:IndexError)=>panic{"expected index"}};',0,0)
 save('at-invalid-'+str(n),n,'','let result:Result<Bits<8>,IndexError>=original->at('+str(n)+');','branch on result{Result<Bits<8>,IndexError>::Ok(value:Bits<8>)=>panic{"unexpected index"},Result<Bits<8>,IndexError>::Err(error:IndexError)=>{assert error->index=='+str(n)+';assert error->length=='+str(n)+';}};',0,0)
 save('append-'+str(n),n,'','let result:Bytes=original->append(Bits<8>{255});','assert result->length()=='+str(n+1)+';check(result,0,'+str(n)+',0);assert octet(result,'+str(n)+')==255;',n,0)
 for m,suffix in [(n//2+3,'mixed'),(0,'empty')]:
  save('concat-'+suffix+'-'+str(n),n,'let other:Bytes=make('+str(m)+',17);','let result:Bytes=original->concat(other);','assert result->length()=='+str(n+m)+';check(result,0,'+str(n)+',0);check(result,'+str(n)+','+str(m)+',17);assert other->length()=='+str(m)+';check(other,0,'+str(m)+',17);',n+m,0)
 for start,end,suffix in [(n//3,2*n//3,'middle'),(n//2,n//2,'empty')]:
  save('slice-'+suffix+'-'+str(n),n,'','let result:Result<Bytes,SliceError>=original->slice('+str(start)+','+str(end)+');','branch on result{Result<Bytes,SliceError>::Ok(value:Bytes)=>{assert value->length()=='+str(end-start)+';check(value,0,'+str(end-start)+','+str(start)+');},Result<Bytes,SliceError>::Err(error:SliceError)=>panic{"expected slice"}};',end-start,0)
 save('slice-invalid-'+str(n),n,'','let result:Result<Bytes,SliceError>=original->slice(-1,'+str(n+1)+');','branch on result{Result<Bytes,SliceError>::Ok(value:Bytes)=>panic{"unexpected slice"},Result<Bytes,SliceError>::Err(error:SliceError)=>{assert error->start== -1;assert error->end=='+str(n+1)+';assert error->length=='+str(n)+';}};',0,0)
 for op,name,answer in [('==','equal',True),('!=','not-equal',False)]:
  save(name+'-'+str(n),n,'let other:Bytes=make('+str(n)+',0);','let result:Bool=original'+op+'other;','assert result=='+str(answer).lower()+';',0,n)
 save('different-length-'+str(n),n,'let other:Bytes=make('+str(n+1)+',0);','let result:Bool=original==other;','assert !result;',0,0)
 if n:
  save('different-first-'+str(n),n,'let other:Bytes=make('+str(n)+',1);','let result:Bool=original==other;','assert !result;',0,1)
  setup='let prefix:Bytes=branch on original->slice(0,'+str(n-1)+'){Result<Bytes,SliceError>::Ok(value:Bytes)=>value,Result<Bytes,SliceError>::Err(error:SliceError)=>panic{"prefix"}};let other:Bytes=prefix->append(Bits<8>{'+str(n%256)+'});'
  save('different-last-'+str(n),n,setup,'let result:Bool=original==other;','assert !result;',0,n)
assert len(cases)==81;(out/'expected.json').write_text(json.dumps(dict(kind='independent-byte-copy-and-comparison-formulas',cases=cases),indent=2)+'\n');rows=[]
for case in cases:
 folder=out/case['name'];source=folder/'input.mgn';image=folder/'program';r=subprocess.run([compiler,'build',source,'-o',image],capture_output=True,timeout=180,umask=0o022);(folder/'build.stdout').write_bytes(r.stdout);(folder/'build.stderr').write_bytes(r.stderr);assert (r.returncode,r.stdout,r.stderr)==(0,b'',b''),(case['name'],r.returncode,r.stderr[-2000:])
 report=folder/'observed.json';r=subprocess.run(['python3',str(HERE/'v170-bytes-cost-observe.py'),'--repository',root,'--report',report,'--',image],capture_output=True,timeout=240);(folder/'observer.stdout').write_bytes(r.stdout);(folder/'observer.stderr').write_bytes(r.stderr);assert r.returncode==0,(case['name'],r.returncode,r.stdout,r.stderr[-2000:]);data=json.loads(report.read_text());assert data['harness_failure'] is None and data['region_complete'] and data['target_reaped'] and data['copied_bytes']==case['copied_bytes'] and data['compared_bytes']==case['compared_bytes'],(case,data);assert data['instruction_steps']<=case['step_bound'] and data['heap_samples']['begin']['collections']==data['heap_samples']['end']['collections'];assert sha(source)==case['source_sha256'] and sha(compiler)==digest
 rows.append(dict(case=case['name'],copied=data['copied_bytes'],compared=data['compared_bytes'],steps=data['instruction_steps'],heap_samples=data['heap_samples'],artifact_sha256=sha(image)));(out/'results.json').write_text(json.dumps(dict(kind='structural-functional-cost-not-wall-or-RSS-acceptance',compiler_sha256=digest,expected_sha256=sha(out/'expected.json'),observations=rows,complete=len(rows)==len(cases)),indent=2)+'\n');print('BYTES_STRUCTURAL_COST_CASE_OK',case['name'],data['copied_bytes'],data['compared_bytes'],flush=True)
length_steps=[r['steps'] for r in rows if r['case'].startswith('length-')];assert max(length_steps)-min(length_steps)<=128
print('BYTES_STRUCTURAL_COST_OK cases='+str(len(rows)),flush=True)
