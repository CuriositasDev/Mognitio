#!/usr/bin/env python3
"""Adapt checked directory algorithms into ordinary source instruction rows.

The emitted compiler has no legacy compiler or linked-image dependency.
"""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EXPORT_LISP='(require :asdf)\n(asdf:load-asd (truename @ASD@))\n(asdf:load-system "mognitio")\n(defun directory-json-form (value)\n  (cond ((listp value) (coerce (mapcar #\'directory-json-form value) \'vector))\n        ((symbolp value) (symbol-name value))\n        (t value)))\n(defun directory-unit-forms (unit)\n  (loop for instruction in (mognitio.object:code-unit-instructions unit)\n        collect (cons (mognitio.machine:instruction-opcode instruction)\n                      (mognitio.machine:instruction-operands instruction))))\n(let ((mognitio.native.runtime::*test-options* nil))\n (with-open-file (out @OUTPUT@ :direction :output :if-exists :error :external-format :utf-8)\n  (write-string\n   (mognitio.json:encode\n    (mognitio.json:object\n     "read" (directory-json-form (subseq (mognitio.native.runtime::directory-read-forms) (length (mognitio.native.runtime::directory-path-map-forms))))\n     "compare" (directory-json-form (directory-unit-forms (mognitio.native.runtime::directory-compare-unit)))\n     "names" (directory-json-form (directory-unit-forms (mognitio.native.runtime::directory-compare-unit t)))\n     "sift" (directory-json-form (directory-unit-forms (mognitio.native.runtime::directory-sift-unit)))\n     "sort" (directory-json-form (directory-unit-forms (mognitio.native.runtime::directory-sort-unit))))) out)\n  (terpri out)))'

def lisp_string(value):
    return '"'+str(value).replace(chr(92),chr(92)*2).replace('"',chr(92)+'"')+'"'

def legacy_forms():
    with tempfile.TemporaryDirectory(prefix='mognitio-directory-') as scratch:
        scratch=Path(scratch);output=scratch/'forms.json';script=scratch/'export.lisp'
        script.write_text(EXPORT_LISP.replace('@ASD@',lisp_string(ROOT/'mognitio.asd')).replace('@OUTPUT@',lisp_string(output))+'\n')
        run=subprocess.run(['sbcl','--noinform','--script',str(script)],cwd=ROOT,capture_output=True,timeout=180)
        if run.returncode:raise RuntimeError(run.stderr.decode(errors='replace'))
        return json.loads(output.read_text())

def home(offset,role):
 if role!='read':
  assert offset>=0 or -48<=offset<=-8,offset
  return offset if offset>=0 else offset-64
 if -64<=offset<0 or -176<=offset<=-96:return offset-64
 if -240<=offset<=-184:return offset-272
 if -304<=offset<=-248:return offset-400
 if -736<=offset<=-312:return offset-528
 raise AssertionError(('directory frame displacement',offset))

def adapted(original):
 data=copy.deepcopy(original)
 # Strict helper 84 already validates the raw result; publish immediately.
 rows=data['read'];mapped=[];index=0;count=0
 guard=[['CMP-IMM','RAX',-22],['JZ','INTERNAL'],['CMP-IMM','RAX',-4095],['JAE','ALLOCATION-FAILED'],['TEST'],['JLE','INTERNAL'],['MOV-REG','RDX','RAX'],['AND-IMM','RDX',4095],['CMP-IMM','RDX',0],['JNZ','INTERNAL']]
 while index<len(rows):
  row=rows[index];mapped.append(row);index+=1
  if row==['CALL',['RUNTIME','DIRECTORY.MAP']]:assert rows[index:index+10]==guard;assert rows[index+10][0]=='STORE-FRAME';index+=10;count+=1
 assert count==3;data['read']=mapped

 for role in ('sift','sort'):
  forms=data[role];assert forms[0][0]=='LABEL' and forms[1:3]==[['PUSH-RBP'],['MOV-REG','RBP','RSP']] and forms[3:15]==[['PUSH-ZERO']]*12 and forms[-3:]==[['MOV-REG','RSP','RBP'],['POP-RBP'],['RET']];data[role]=forms[15:-3]+[['RET']]
 for role in ('compare','names'):assert data[role][0][0]=='LABEL';data[role]=data[role][1:]
 # The source wrapper closes the descriptor before managed materialization.
 footer=[]
 for label,kind in [('INVALID-PATH',0),('UNSUPPORTED',4),('INVALID-ENCODING',1)]:footer += [['LABEL',label],['IMM-RAX',kind],['STORE-FRAME',-96,'RAX'],['JMP','BODY-DONE']]
 data['read']+=footer+[['LABEL','OS-ERROR'],['CALL',['RUNTIME','DIRECTORY.ERRNO']],['STORE-FRAME',-96,'RAX'],['LABEL','BODY-DONE']]
 reg=lambda name:['RAX','RCX','RDX','RBX','RSP','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15'].index(name)
 jumps={'JMP':233,'JZ':132,'JNZ':133,'JO':128,'JS':136,'JB':130,'JBE':134,'JA':135,'JAE':131,'JL':140,'JLE':142}
 helpers={'UTF8.COUNT':40,'DIRECTORY.ERRNO':83,'DIRECTORY.MAP':84,'DIRECTORY.COMPARE':85,'DIRECTORY.SIFT':87}
 token=lambda value:json.dumps(value,separators=(',',':'))
 compiled={}
 for role,forms in data.items():
  labels={token(row[1]):i for i,row in enumerate(row for row in forms if row[0]=='LABEL')};assert len(labels)==sum(row[0]=='LABEL' for row in forms);steps=[]
  def add(opcode,*values):steps.append([opcode,*values,*([0]*(4-len(values)))])
  for row in forms:
   op,*args=row
   if op=='LABEL':add(0,labels[token(args[0])])
   elif op in jumps:
    target=args[0]
    if token(target) in labels:destination=labels[token(target)]
    else:
     assert target in ('ALLOCATION-FAILED','INTERNAL'),(role,target);destination=-1 if target=='ALLOCATION-FAILED' else -2
    add(1,jumps[op],destination)
   elif op=='MOV-REG':assert args[0]!='RSP';add(2,reg(args[0]),reg(args[1]))
   elif op=='LOAD-WORD':add(3,reg(args[0]),reg(args[1]),args[2])
   elif op=='STORE-WORD':add(4,reg(args[0]),args[1],reg(args[2]))
   elif op=='LEA-BASE':add(5,reg(args[0]),reg(args[1]),home(args[2],role) if args[1]=='RBP' else args[2])
   elif op=='LOAD-FRAME':add(3,reg(args[0]),5,home(args[1],role))
   elif op=='STORE-FRAME':add(4,5,home(args[0],role),reg(args[1]))
   elif op=='STORE-OUT':assert args[0] in (0,8,16,24);add(4,4,args[0],reg(args[1]))
   elif op in ('IMM-RAX','IMM-RCX','IMM-RDX'):add(6,{'IMM-RAX':0,'IMM-RCX':1,'IMM-RDX':2}[op],args[0])
   elif op=='IMM-REG':add(6,reg(args[0]),args[1])
   elif op in ('MOV-EAX','MOV-EDX','MOV-R10D'):add(6,{'MOV-EAX':0,'MOV-EDX':2,'MOV-R10D':10}[op],args[0])
   elif op=='SYSCALL':add(12)
   elif op in ('ADD-IMM','AND-IMM','CMP-IMM'):add(8,{'ADD-IMM':0,'AND-IMM':4,'CMP-IMM':7}[op],reg(args[0]),args[1])
   elif op in ('ADD-REG','SUB-REG','CMP-REG'):add(7,{'ADD-REG':1,'SUB-REG':41,'CMP-REG':57}[op],reg(args[0]),reg(args[1]))
   elif op in ('CMP','CMP-RAX-RDX'):add(7,57,0,1 if op=='CMP' else 2)
   elif op in ('TEST','TEST-RCX'):add(7,133,0 if op=='TEST' else 1,0 if op=='TEST' else 1)
   elif op=='CMP-EINTR':add(8,7,0,-4)
   elif op=='DEC-RCX':add(8,5,1,1)
   elif op=='SHR-IMM':add(11,5,reg(args[0]),args[1])
   elif op=='LOAD-BYTE':add(9,reg(args[0]),reg(args[1]),args[2])
   elif op=='STORE-BYTE':add(10,reg(args[0]),args[1],reg(args[2]))
   elif op=='CALL':assert args[0][0]=='RUNTIME';add(13,helpers[args[0][1]])
   elif op=='MUL':add(14,1)
   elif op=='RET':add(15)
   else:raise AssertionError((role,row))
  compiled[role]=dict(labels=len(labels),steps=steps)
 return compiled

def rendered(data):
 result={};parts={}
 def put(namespace,text):result[Path('compiler/mgnc/src')/namespace/'code.mgn']=(text.strip()+'\n').encode()
 for role,program in data.items():
  parts[role]=[]
  for i,start in enumerate(range(0,len(program['steps']),48)):
   component=role.capitalize()+str(i);alias='rows'+component;parts[role].append((component,alias));text='namespace Mgnc\\DirectoryData\\'+component+';\nuse Mgnc\\WholeDirectoryStep\\{Step};\n// Adapted raw directory instructions; regenerate from the checked adapter.\npublic let rows:Function():List<Step>=function():List<Step>{List<Step>[\n'
   text+=',\n'.join(' Step{op:'+str(a)+',a:'+str(b)+',b:'+str(c)+',c:'+str(d)+',d:'+str(e)+'}' for a,b,c,d,e in program['steps'][start:start+48]);text+='\n]};\n';put('DirectoryData/'+component,text)
 imports='\n'.join('use Mgnc\\DirectoryData\\'+component+'\\{rows as '+alias+'};' for names in parts.values() for component,alias in names)
 text='namespace Mgnc\\WholeDirectoryPrograms;\nuse Mgnc\\Data\\{Diagnostic};\nuse Mgnc\\WholeDirectoryStep\\{emit as emitRows};\nuse Mgnc\\Machine\\{Code,fresh};\n'+imports+'\npublic let emit:Function(Code,Int):Result<Code,Diagnostic>=function(initial:Code,owner:Int):Result<Code,Diagnostic>{var code:Code=initial;let base:Int=code->nextLabel;\n'
 for role,owner in [('read',79),('compare',85),('names',86),('sift',87),('sort',88)]:
  text+='branch when{owner=='+str(owner)+'=>{code=fresh(code,'+str(data[role]['labels'])+');\n'
  for component,alias in parts[role]:text+='code=try emitRows(code,'+alias+'(),base,owner);\n'
  text+='},else=>unit};\n'
 text+='Result<Code,Diagnostic>::Ok(code)};';put('WholeDirectoryPrograms',text);return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');options=parser.parse_args();files=rendered(adapted(legacy_forms()))
 for relative,content in files.items():
  path=ROOT/relative
  if options.check:
   if not path.exists() or path.read_bytes()!=content:raise RuntimeError('Directory source drift: '+relative.as_posix())
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
 actual={path.relative_to(ROOT) for path in (ROOT/'compiler/mgnc/src/DirectoryData').rglob('*.mgn')}
 if actual-set(files):raise RuntimeError('Obsolete directory source parts: '+str(sorted(map(str,actual-set(files)))))
 print('DIRECTORY_SOURCE_GENERATION_OK files='+str(len(files)))
if __name__=='__main__':main()
