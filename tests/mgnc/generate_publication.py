#!/usr/bin/env python3
"""Regenerate source publication instruction rows from the checked legacy adapter.

The source emitter adapts object/frame ABI explicitly; it never embeds a linked
image or calls the legacy compiler when a generated compiler runs.
"""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EXPORT_LISP='(require :asdf)\n(asdf:load-asd (truename @ASD@))\n(asdf:load-system "mognitio")\n(defun publication-json-form (value)\n  (cond ((listp value) (coerce (mapcar #\'publication-json-form value) \'vector))\n        ((symbolp value) (symbol-name value))\n        (t value)))\n(defun publication-unit-forms (unit)\n  (loop for instruction in (mognitio.object:code-unit-instructions unit)\n        collect (cons (mognitio.machine:instruction-opcode instruction)\n                      (mognitio.machine:instruction-operands instruction))))\n(let ((mognitio.native.runtime::*test-options* nil))\n (with-open-file (out @OUTPUT@ :direction :output :if-exists :error :external-format :utf-8)\n  (write-string\n   (mognitio.json:encode\n    (mognitio.json:object\n     "path" (publication-json-form (mognitio.native.runtime::publication-path-forms))\n     "temp" (publication-json-form (mognitio.native.runtime::publication-temp-forms))\n     "write" (publication-json-form (mognitio.native.runtime::publication-write-commit-forms))\n     "profile" (publication-json-form (publication-unit-forms (mognitio.native.runtime::publication-profile-unit)))\n     "cleanup" (publication-json-form (publication-unit-forms (mognitio.native.runtime::publication-cleanup-unit)))\n     "errno" (publication-json-form (publication-unit-forms (mognitio.native.runtime::publication-errno-unit))))) out)\n  (terpri out)))'

def lisp_string(value):
    return '"'+str(value).replace(chr(92),chr(92)*2).replace('"',chr(92)+'"')+'"'

def legacy_forms():
    with tempfile.TemporaryDirectory(prefix='mognitio-publication-') as scratch:
        scratch=Path(scratch);output=scratch/'forms.json';script=scratch/'export.lisp'
        script.write_text(EXPORT_LISP.replace('@ASD@',lisp_string(ROOT/'mognitio.asd')).replace('@OUTPUT@',lisp_string(output))+'\n')
        run=subprocess.run(['sbcl','--noinform','--script',str(script)],cwd=ROOT,capture_output=True,timeout=180)
        if run.returncode:raise RuntimeError(run.stderr.decode(errors='replace'))
        return json.loads(output.read_text())

def adapted(original):
    data=copy.deepcopy(original)
    def reg(name):return ['RAX','RCX','RDX','RBX','RSP','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15'].index(name)
    # Replace the legacy private Bytes header with the current allocator's header.
    a=data['path'];start=a.index(['CALL',['RUNTIME','ALLOCATE-BLOCK']]);end=next(i for i in range(start+1,len(a)) if a[i]==['LOAD-FRAME','RAX',-160]);assert end-start-1==18;a[start+1:end]=[]
    for old,new,count in [(['LOAD-WORD','RCX','RSI',16],['LOAD-WORD','RCX','RSI',24],2),(['ADD-IMM','RSI',32],['ADD-IMM','RSI',40],2),(['STORE-WORD','RDX',32,'RAX'],['STORE-WORD','RDX',24,'RAX'],1),(['LEA-BASE','RDI','RDX',40],['LEA-BASE','RDI','RDX',32],1),(['ADD-IMM','RAX',40],['ADD-IMM','RAX',32],1)]:
     assert a.count(old)==count,(old,a.count(old));a[:]=[new if row==old else row for row in a]
    # Publish a fully copied leaf into its root slot. No allocation occurs in fill.
    store=a.index(['STORE-FRAME',-24,'RDX']);a.pop(store);at=a.index(['LOAD-FRAME','RAX',-24]);a.insert(at,['STORE-FRAME',-24,'RDX'])
    a=data['write'];assert a.count(['LOAD-WORD','RDX','RSI',32])==1 and a.count(['ADD-IMM','RSI',40])==1;a[:]=[['LOAD-WORD','RDX','RSI',24] if row==['LOAD-WORD','RDX','RSI',32] else ['ADD-IMM','RSI',32] if row==['ADD-IMM','RSI',40] else row for row in a]
    init=[['LOAD-WORD','RAX','R15',168],['STORE-FRAME',-256,'RAX'],['IMM-RAX',-2],['STORE-FRAME',-248,'RAX'],['IMM-RAX',-1]]+[['STORE-FRAME',n,'RAX'] for n in [-240,-232,-176,-72]]+[['LEA-BASE','RAX','RBP',-256],['STORE-WORD','R15',168,'RAX'],['LOAD-FRAME','RDX',32],['LOAD-WORD','RAX','RDX',24],['CMP-IMM','RAX',0],['JZ','DATA-MODE'],['CMP-IMM','RAX',1],['JNZ','INTERNAL'],['IMM-RAX',511],['JMP','MODE-SET'],['LABEL','DATA-MODE'],['IMM-RAX',438],['LABEL','MODE-SET'],['STORE-FRAME',-120,'RAX']]
    footer=[]
    for label,kind in [('INVALID-PATH',0),('ALREADY-EXISTS',1),('EXHAUSTED',5),('ZERO-WRITE',6)]:footer +=[['LABEL',label],['IMM-RAX',kind],['STORE-FRAME',-72,'RAX'],['JMP','CLEANUP']]
    footer +=[['LABEL','INTERNAL'],['IMM-RAX',1],['STORE-FRAME',-104,'RAX'],['JMP','CLEANUP'],['LABEL','OS-ERROR'],['CMP-IMM','RAX',-9],['JZ','INTERNAL'],['CMP-IMM','RAX',-14],['JZ','INTERNAL'],['CMP-IMM','RAX',-4095],['JL','INTERNAL'],['TEST'],['JS','ERRNO-VALID'],['JMP','INTERNAL'],['LABEL','ERRNO-VALID'],['STORE-FRAME',-96,'RAX'],['LABEL','CLEANUP'],['LEA-BASE','RAX','RBP',-256],['STORE-OUT',0,'RAX'],['CALL',['RUNTIME','PUBLICATION.CLEANUP']],['STORE-FRAME',-160,'RAX'],['CMP-IMM','RDX',0],['JZ','CLEANUP-STATE'],['STORE-FRAME',-104,'RDX'],['LABEL','CLEANUP-STATE'],['LOAD-FRAME','RCX',-96],['TEST-RCX'],['JNZ','CLEANED'],['LOAD-FRAME','RCX',-72],['CMP-IMM','RCX',-1],['JNZ','CLEANED'],['LOAD-FRAME','RAX',-160],['TEST'],['JZ','CLEANED'],['STORE-FRAME',-96,'RAX'],['IMM-RAX',4],['STORE-FRAME',-80,'RAX'],['LABEL','CLEANED'],['LOAD-FRAME','RAX',-256],['STORE-WORD','R15',168,'RAX'],['LOAD-FRAME','RAX',-104],['TEST'],['JNZ',['RUNTIME','DIRECTORY.INTERNAL']],['LOAD-FRAME','RAX',-72],['CMP-IMM','RAX',-1],['JNZ','ERROR'],['LOAD-FRAME','RAX',-96],['TEST'],['JZ','OK'],['CALL',['RUNTIME','PUBLICATION.ERRNO']],['STORE-FRAME',-72,'RAX'],['LABEL','ERROR'],['ENUM',1,-72,-24,7],['ENUM',2,-80,-32,5],['ENUM',3,-88,-40,3],['ERROR'],['JMP','RESULT'],['LABEL','OK'],['OK'],['LABEL','RESULT'],['RESULT'],['RET']]
    data['publish']=init+data.pop('path')+data.pop('temp')+data.pop('write')+footer
    for key,words in [('profile',640),('cleanup',64)]:
     a=data[key];assert a[0][0]=='LABEL' and a[1:3]==[['PUSH-RBP'],['MOV-REG','RBP','RSP']] and all(row==['PUSH-ZERO'] for row in a[3:3+words]);assert a[-3:]==[['MOV-REG','RSP','RBP'],['POP-RBP'],['RET']];data[key]=a[3+words:-3]+[['RET']]
    assert data['errno'][0][0]=='LABEL';data['errno']=data['errno'][1:]
    # Every cleanup syscall has a zero-or-errno result domain. Invalid replies
    # set the invariant flag while the remaining owned resources are released.
    forms=data['cleanup'];checked=[];site=0;close=0
    for index,row in enumerate(forms):
     if row==['LABEL','RUNTIME/PUBLICATION.CLEANUP/IDENTITY-FAILED']:
      checked +=[['JMP','RUNTIME/PUBLICATION.CLEANUP/IDENTITY-FAILED'],['LABEL','RUNTIME/PUBLICATION.CLEANUP/BAD-IDENTITY'],['IMM-RCX',1],['STORE-FRAME',-24,'RCX']]
     checked.append(row)
     if row!=['SYSCALL']:continue
     previous=forms[index-1];assert previous[0]=='MOV-EAX';number=previous[1]
     if number==3:
      close+=1;bad=['FILE-BAD','PROBE-BAD','BAD-PARENT'][close-1]
     else:bad={5:'BAD-IDENTITY',262:'BAD-NAME',263:'BAD-NAME',11:'BAD-MAP'}[number]
     bad='RUNTIME/PUBLICATION.CLEANUP/'+bad;negative='STRICT-NEGATIVE-'+str(site);done='STRICT-CHECKED-'+str(site);site+=1
     checked +=[['TEST'],['JZ',done],['JS',negative],['JMP',bad],['LABEL',negative],['CMP-IMM','RAX',-4095],['JL',bad]]
     for error in [9,14,22]:checked +=[['CMP-IMM','RAX',-error],['JZ',bad]]
     checked +=[['LABEL',done]]
    assert site==7 and close==3;data['cleanup']=checked
    helpers={'ALLOCATE-BLOCK':10,'IO.MAP':60,'PUBLICATION.CLEANUP':80,'PUBLICATION.PROFILE':81,'PUBLICATION.ERRNO':82,'DIRECTORY.INTERNAL':2}
    jumps={'JMP':233,'JZ':132,'JNZ':133,'JO':128,'JS':136,'JB':130,'JBE':134,'JA':135,'JAE':131,'JL':140}
    def token(value):return json.dumps(value,separators=(',',':'))
    def location(offset,role):return offset-64 if offset<0 else offset+8 if role=='publish' else offset
    compiled={};sites={}
    for role,forms in data.items():
     labels={token(row[1]):i for i,row in enumerate(row for row in forms if row[0]=='LABEL')};assert len(labels)==sum(row[0]=='LABEL' for row in forms);steps=[];i=0
     while i<len(forms):
      row=forms[i];op,*args=row;i+=1
      def add(opcode,*values):steps.append([opcode,*values,*([0]*(4-len(values)))])
      if op=='LABEL':add(0,labels[token(args[0])])
      elif op in jumps:
       target=args[0]
       if token(target) in labels:destination=labels[token(target)]
       else:
        helper=1 if target=='ALLOCATION-FAILED' else helpers[target[1]] if isinstance(target,list) and target[0]=='RUNTIME' else None
        assert helper in [1,2],(role,target);destination=-helper
       add(1,jumps[op],destination)
      elif op=='MOV-REG':assert args[0]!='RSP';add(2,reg(args[0]),reg(args[1]))
      elif op in ['LOAD-WORD','STORE-WORD','LEA-BASE']:
       if op=='LOAD-WORD':dest,source,off=args;add(3,reg(dest),reg(source),off)
       elif op=='STORE-WORD':dest,off,source=args;add(4,reg(dest),off,reg(source))
       else:dest,source,off=args;add(5,reg(dest),reg(source),location(off,role) if source=='RBP' else off)
      elif op=='LOAD-FRAME':
       dest,off=args
       if off>=0 and role!='publish':assert off==16;add(2,reg(dest),12)
       else:add(3,reg(dest),5,location(off,role))
      elif op=='STORE-FRAME':off,source=args;add(4,5,location(off,role),reg(source))
      elif op=='STORE-OUT':off,source=args;assert off in [0,8,16];add(4,4,off,reg(source))
      elif op in ['IMM-RAX','IMM-RCX','IMM-RDX']:add(6,{'IMM-RAX':0,'IMM-RCX':1,'IMM-RDX':2}[op],args[0])
      elif op=='IMM-REG':add(6,reg(args[0]),args[1])
      elif op in ['MOV-EAX','MOV-EDX','MOV-R10D']:
       if op=='MOV-EAX' and i<len(forms) and forms[i]==['SYSCALL']:
        i+=1;nr=args[0];add(12,nr,0,1 if role!='cleanup' and nr in [138,332,63,3,5,91,11,262] else 0)
       else:add(6,{'MOV-EAX':0,'MOV-EDX':2,'MOV-R10D':10}[op],args[0])
      elif op in ['ADD-IMM','AND-IMM','CMP-IMM']:add(8,{'ADD-IMM':0,'AND-IMM':4,'CMP-IMM':7}[op],reg(args[0]),args[1])
      elif op in ['ADD-REG','SUB-REG','CMP-REG']:add(7,{'ADD-REG':1,'SUB-REG':41,'CMP-REG':57}[op],reg(args[0]),reg(args[1]))
      elif op=='CMP':add(7,57,0,1)
      elif op in ['TEST','TEST-RCX']:add(7,133,0 if op=='TEST' else 1,0 if op=='TEST' else 1)
      elif op=='CMP-EINTR':add(8,7,0,-4)
      elif op=='DEC-RCX':add(8,5,1,1)
      elif op=='SHR-IMM':add(11,5,reg(args[0]),args[1])
      elif op=='LOAD-BYTE':add(9,reg(args[0]),reg(args[1]),location(args[2],role) if args[1]=='RBP' else args[2])
      elif op=='STORE-BYTE':add(10,reg(args[0]),location(args[1],role) if args[0]=='RBP' else args[1],reg(args[2]))
      elif op=='PUBLICATION-SYSCALL':
       site,nr=args;sites.setdefault(site,len(sites)+1);add(12,nr,sites[site],1 if nr in [5,11,91,262,316,3] else 0)
      elif op=='CALL':assert args[0][0]=='RUNTIME';add(13,helpers[args[0][1]])
      elif op=='UMUL':add(14,1)
      elif op=='RET':add(15)
      elif op=='ENUM':descriptor,source,target,count=args;add(16,descriptor,location(source,role),location(target,role),count)
      elif op in ['ERROR','OK','RESULT']:add({'ERROR':17,'OK':18,'RESULT':19}[op])
      else:raise AssertionError((role,row))
     compiled[role]={'labels':len(labels),'steps':steps}
    return compiled

def rendered(data):
    result={}
    def put(namespace,text):
        path=Path('compiler/mgnc/src')/namespace/'code.mgn'
        result[path]=(text.strip()+'\n').encode()
    parts={}
    for role in ["profile","cleanup","errno","publish"]:
     program=data[role]
     parts[role]=[]
     for i,start in enumerate(range(0,len(program['steps']),48)):
      component=role.capitalize()+str(i);alias='rows'+component;parts[role].append((component,alias));text='namespace Mgnc\\PubData\\'+component+';\nuse Mgnc\\WholePubStep\\{Step};\n// Adapted publication instructions; regenerate from the checked legacy adapter.\npublic let rows:Function():List<Step>=function():List<Step>{List<Step>[\n'
      text+=',\n'.join(' Step{op:'+str(a)+',a:'+str(b)+',b:'+str(c)+',c:'+str(d)+',d:'+str(e)+'}' for a,b,c,d,e in program['steps'][start:start+48]);text+='\n]};\n';put('PubData/'+component,text)
    imports='\n'.join('use Mgnc\\PubData\\'+component+'\\{rows as '+alias+'};' for names in parts.values() for component,alias in names)
    program='\nnamespace Mgnc\\WholePubPrograms;\nuse Mgnc\\Data\\{Diagnostic};\nuse Mgnc\\WholeChecks\\{require};\nuse Mgnc\\WholePubStep\\{emit as emitRows};\nuse Mgnc\\Machine\\{Code,fresh};\n'+imports+'\n'+'\npublic let emit:Function(Code,Int,List<Int>):Result<Code,Diagnostic>=function(initial:Code,owner:Int,descriptors:List<Int>):Result<Code,Diagnostic>{\n var code:Code=initial;let base:Int=code->nextLabel;\n'
    for role,id in [('publish',75),('cleanup',80),('profile',81),('errno',82)]:
     program+=' branch when{owner=='+str(id)+'=>{code=fresh(code,'+str(data[role]['labels'])+');\n';scratch=512 if id==80 else 5120 if id==81 else 0
     for component,alias in parts[role]:program+='  code=try emitRows(code,'+alias+'(),base,owner,descriptors,'+str(scratch)+');\n'
     program+=' },else=>unit};\n'
    program+=' Result<Code,Diagnostic>::Ok(code)\n};\n';put('WholePubPrograms',program)
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    files=rendered(adapted(legacy_forms()))
    for relative,content in files.items():
        path=ROOT/relative
        if args.check:
            if not path.exists() or path.read_bytes()!=content:raise RuntimeError('Publication source drift: '+relative.as_posix())
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    print('PUBLICATION_SOURCE_GENERATION_OK files='+str(len(files)))
if __name__=='__main__':main()
