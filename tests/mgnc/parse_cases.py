#!/usr/bin/env python3
"""Observable v1.4 syntax and build boundary fixtures, independent of chart tables."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
ENTRY='namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{'
def main_source(body):return ENTRY+body+'};'
def fixtures():
 rows=[]
 def add(case,name,source,phase=None,build=None,marker=None,build_marker=None):
  rows.append(dict(case=case if case.startswith('DR140-') else 'C140-'+case,name=name,source=source,phase=phase,build=build,marker=marker,build_marker=build_marker))
 def expression(case,name,body,phase=None,build=None):add(case,name,'namespace App;let x:Unknown='+body+';',phase,build)
 add('L01','unicode','//aé日😀\r\n\tnamespace App;let s:String="aé日😀";')
 add('L02','invalid-utf8',b'namespace App;\xff','source')
 add('L02','bom','\ufeffnamespace App;','source',marker='\ufeff')
 add('L03','escapes',r'namespace App;let s:String="\"\\\n\r\t\0\u{0}\u{41}\u{0ff}\u{abcd}\u{10000}\u{10ffff}";')
 for i,value in enumerate([r'\q',r'\u{}',r'\u{d800}',r'\u{dfff}',r'\u{110000}',r'\u{0000000}']):
  add('L04',f'escape-{i}','namespace App;let s:String="'+value+'";','lexical')
 for i,value in enumerate(['"no end','"line\n"','"line\r"']):add('L05',f'string-{i}','namespace App;let s:String='+value+';','lexical')
 add('L06','protected',r'namespace App;// } ] namespace "'+ '\n'+r'let s:String="} ] // namespace \"";')
 for i,value in enumerate(['01','0x1','1_0','9u','日','$']):expression('L07',f'lexical-{i}',value,'lexical')
 for i,value in enumerate(['a','é','日','😀',r'\u{1f600}']):
  source='namespace App;let s:String="'+value+'";\r\n\tlet x:Int=;'
  add('L08',f'span-{i}',source,'parse',marker=(';',source.rindex(';')))
 add('L08','eof','namespace App;let x:Int=1','parse',marker='')
 add('P01','imports','namespace Long\\Path;use Missing\\Path\\{Name as Alias,Other,};let x:T=Alias<Int>(0);')
 for i,s in enumerate(['let x:Int=1;','namespace A;namespace B;','namespace A;let x:Int=1;use B\\{X};','namespace A;use B\\{};','namespace A;use B\\{X\\{Y}};','namespace A;use B\\X;']):add('P02',f'module-{i}',s,'parse')
 for prefix in ['', 'public ']:
  for i,declaration in enumerate(['type P<T>=product{value:T;};','type S<T>=sum{None;Some(T);};','alias A<T>=List<T>;','template f<T>=function(x:T):T{x};','let value:Function(Int):Int=function(x:Int):Int{x};']):
   add('P03',('public-' if prefix else 'private-')+str(i),'namespace A;'+prefix+declaration)
 add('P03','var','namespace A;var value:Int=1;')
 for i,s in enumerate(['let x=1;','let f:Function():Int=function(x){0};','let f:Function():Int=function(){0};','let x:Int=1','public var x:Int=0;','public use A\\{X};']):add('P04',f'annotation-{i}','namespace A;'+s,'parse')
 for i,e in enumerate(['Pair<Int,String>{first:1,second:"x",}','Maybe<Int>::Some(1)','Maybe<Int>::None','List<Int>[1,2,]','value->field->method(1)(2)->field','function(x:Int):Int{let f:Function(Int):Int=function(y:Int):Int{y};f(x)}']):expression('P05',f'construct-{i}',e)
 for i,d in enumerate(['type Packet<N:Int,T>=product{x:Bits<N>;y:T;};','alias A<N:Int>=Bits<N>;','template f<N:Int>=function(x:Bits<N>):Bits<N>{x};','let x:A<(-1),(N)>=value;','let x:A<-(1),T>=value;']):add('P06',f'parameters-{i}','namespace A;'+d)
 for i,e in enumerate(['List<List<Int>>[]','value->convertTo<Int<32,Signed>>()','f<A<B<C>>>(x)']):expression('P07',f'generic-{i}',e)
 add('P07','close-equals','namespace A;let x:List<Int>=List<Int>[];')
 for i,e in enumerate(['Int<64,Unsigned>{18446744073709551615}','Bits<8>{(255)}','A{-((9223372036854775808))}','99999999999999999999999999999999999999']):expression('P08',f'scalar-{i}',e)
 for i,e in enumerate(['Bits<8>{1+7}','Bits<8>{1,}','f<>','f<1+7>','f<-N>','f<--1>','f<g()>']):expression('P09',f'shape-{i}',e,'parse')
 for i,e in enumerate(['branch when{true=>1,else=>2,}','branch on x{M::None=>1,M::Some(value:Int)=>value,}','loop while(true){break;}','loop over(xs as x:T){continue;}','loop{break 1;}','try f()','panic{"message"}','{return 1;}','{discard 1;x=2;unit}']):expression('P10',f'control-{i}',e)
 for i,e in enumerate(['panic("message")','branch when{true=>1 else=>2}','branch when{true=>1}','branch on x{else=>1}','branch on x{M::Some(value)=>1}','branch when{else=>1,true=>2}']):expression('P11',f'control-bad-{i}',e,'parse')
 for i,s in enumerate(['template f<T>=function():T{let x:T=(1; x};','let x:Int=branch when{true=>1,else=>{(2}};','let f:Function():Int=function():Int{let g:Function():Int=function():Int{(1};1};','let x:Int=1; ;']):add('P12',f'nested-bad-{i}','namespace A;'+s,'parse')
 expression('B01','unresolved','f<Int>(0)')
 add('B01','renamed','namespace A;use Missing\\{f as Renamed};let x:Int=Renamed<Int>(0);')
 add('B02','runtime-generic',main_source('let a:Int=1;let b:Int=2;let c:Int=3;a < b > (c)'),build='parse')
 for i,e in enumerate(['a<b','a<b<c','(a<b)==true']):expression('B03',f'comparison-{i}',e,'parse' if i==1 else None)
 add('B04','no-main','namespace App;',build='semantic')
 for name,body,phase in [('type','let x:Int=false;0','type'),('shadow','let x:Int=1;{let x:Int=2;};0','semantic'),('unknown','missing','semantic')]:add('B05',name,main_source(body),build=phase)
 add('B06','overflow',main_source('9223372036854775808'),build='type')
 for i,e in enumerate(['-9223372036854775808','-(9223372036854775808)']):add('B06',f'minimum-{i}',main_source('let x:Int='+e+';0'),build='ok')
 for i,e in enumerate(['Bits<0>{0}','f<true>','Unknown{missing:1}','M::Unknown']):
  # Bool is not a structural generic argument; use a type/value kind mismatch with a valid shape.
  if e=='f<true>':e='Bits<String>{0}'
  add('B07',f'deferred-{i}',main_source('discard '+e+';0'),build='unsupported')
 for i,(body,phase) in enumerate([('break;0','semantic'),('return false;','type'),('1;0','type')]):add('B08',f'flow-{i}',main_source(body),build=phase)
 for i,s in enumerate(['type P=product{x:Int;};','alias A=Int;','template f<T>=function(x:T):T{x};','use Missing\\{X};','public let x:Int=1;']):add('N05',f'top-{i}','namespace App;'+s,build='unsupported')
 for i,e in enumerate(['"x"','List<Int>[]','P{x:1}','M::V(1)','try f()','panic{"x"}','function():Int{1}','loop{break 1;}','loop over(xs as x:T){}','branch on x{M::A=>1}','f<Int>(0)','value->convertTo<Int>()']):add('N05',f'body-{i}',main_source('discard '+e+';0'),build='unsupported')
 for name,s in [('helper','namespace App;let f:Function():Int=function():Int{discard "x";1};'+ENTRY.split('namespace App;')[1]+'0};'),('arm',main_source('branch when{true=>0,else=>{discard "x";1}}')),('short-circuit',main_source('let x:Bool=false&&"x";0'))]:add('N06',name,s,build='unsupported')
 add('N07','malformed-product','namespace App;type P=product{x:Int};','parse',build='parse')

 for name in ['Std',r'Std\X','App','StdX',r'App\Std']:
  reserved=name in ['Std',r'Std\X']
  add('DR140-T01','namespace-'+name,main_source('0').replace('namespace App;','namespace '+name+';'),build='semantic' if reserved else 'ok',build_marker='Std' if reserved else None)
 for annotation,phase in [('Int','ok'),('int','semantic')]:add('DR140-T02',annotation,main_source('let value:'+annotation+'=0;0'),build=phase,build_marker='int' if phase=='semantic' else None)
 helper='namespace App;let f:Function(Int):Int=function(value:Int):Int{value};'+main_source('0').split('namespace App;')[1]
 for i,at in enumerate([helper.index('Int'),helper.index('):Int')+2,helper.index('value:Int')+6,helper.index('):Int',helper.index('function'))+2]):
  add('DR140-T03',f'helper-{i}',helper[:at]+'int'+helper[at+3:],build='semantic',build_marker=('int',at))
 for i,(annotation,phase) in enumerate([('String','unsupported'),('Int<8,Signed>','unsupported'),('Bits<8>','unsupported'),('Bytes','unsupported'),('List<Int>','unsupported'),('List<String>','unsupported'),('int','semantic')]):
  add('DR140-T04',f'annotation-{i}',main_source('let value:'+annotation+'=0;0'),build=phase,build_marker='int' if annotation=='int' else None)
 add('DR140-T05','structure-first',main_source('let value:int=;0'),'parse',build='parse')
 for i,e in enumerate(['f<T> == g','f<T>==g']):expression('DR140-T06',f'equality-{i}',e)
 for i,e in enumerate(['branch when{f<T> =>1,else=>2}','branch when{f<T>=>1,else=>2}']):expression('DR140-T07',f'arrow-{i}',e)
 for i,gap in enumerate([' ','\r\n','//gap\n']):
  expression('DR140-T08',f'equality-gap-{i}','f<T>='+gap+'=g','parse')
  expression('DR140-T08',f'arrow-gap-{i}','branch when{f<T>='+gap+'>1,else=>2}','parse')
 for i,e in enumerate(['a>=b','List<List<Int>>[]','value->convertTo<Int<8,Signed>>()']):expression('DR140-T09',f'control-{i}',e)
 add('DR140-T09','assignment','namespace A;let values:List<Int>=List<Int>[];')
 return rows

def position(source,marker):
 text=source.decode('utf-8');token,start=marker if isinstance(marker,tuple) else (marker,len(text) if marker=='' else text.index(marker))
 before=text[:start];lines=re.split(r'\r\n|\r|\n',before);offset=len(before.encode())
 return offset,offset+len(token.encode()),len(lines),len(lines[-1])+1

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler',required=True,type=Path);ap.add_argument('--evidence',required=True,type=Path);ap.add_argument('--prototype',action='store_true');ap.add_argument('--parse-only',action='store_true');args=ap.parse_args()
 records=[]
 with tempfile.TemporaryDirectory(prefix='mgnc-parse-cases-') as work:
  root=Path(work)
  for i,case in enumerate(fixtures()):
   source=case['source'].encode() if isinstance(case['source'],str) else case['source'];path=root/f'{i}.mgn';path.write_bytes(source)
   before=set(root.iterdir());command=[str(args.compiler.resolve())]+([] if args.prototype else ['parse'])+[str(path)]
   result=subprocess.run(command,capture_output=True,timeout=120);phase=case['phase'];expected=1 if phase else 0
   okay=result.returncode==expected and (args.prototype or result.stdout==b'') and ((not phase and not result.stderr) or (phase and ('mgnc: '+phase+':').encode() in result.stderr))
   okay=bool(okay and set(root.iterdir())==before and path.read_bytes()==source)
   record={k:v for k,v in case.items() if k not in ['source','marker','build_marker']};record.update(source_hex=source.hex(),sha256=hashlib.sha256(source).hexdigest(),exit=result.returncode,stdout_hex=result.stdout.hex(),stderr=result.stderr.decode(errors='replace').replace(str(root),'<fixtures>'))
   if case['marker'] is not None:
    start,end,line,col=position(source,case['marker']);record['expected_span']=[start,end,line,col]
    okay=okay and f'[{start},{end})'.encode() in result.stderr and f':{line}:{col}'.encode() in result.stderr
   if case['build'] and not args.parse_only and not args.prototype:
    output=root/f'{i}.out';built=subprocess.run([args.compiler.resolve(),'build',path,'-o',output],capture_output=True,timeout=120)
    expected_build=0 if case['build']=='ok' else 1
    good=built.returncode==expected_build and not built.stdout and output.exists()==(expected_build==0)
    if expected_build:good=good and ('mgnc: '+case['build']+':').encode() in built.stderr
    else:good=good and not built.stderr
    if case['build_marker'] is not None:
     start,end,line,col=position(source,case['build_marker']);record['expected_build_span']=[start,end,line,col]
     good=good and f'[{start},{end})'.encode() in built.stderr and f':{line}:{col}'.encode() in built.stderr
    record['build_result']=dict(exit=built.returncode,stderr=built.stderr.decode(errors='replace').replace(str(root),'<fixtures>'),passed=bool(good));okay=okay and good
   record['pass']=bool(okay);records.append(record)
   if not okay:print('FAIL',record['case'],record['name'],record,flush=True)
 data=dict(compiler_sha256=hashlib.sha256(args.compiler.read_bytes()).hexdigest(),prototype=args.prototype,parse_only=args.parse_only,passed=sum(r['pass'] for r in records),total=len(records),cases=records)
 args.evidence.write_text(json.dumps(data,indent=2)+'\n');print('PARSE_CASES',data['passed'],'/',data['total'],flush=True)
 raise SystemExit(data['passed']!=data['total'])
if __name__=='__main__':main()
