#!/usr/bin/env python3
"""Exercise byte-work observations with independent raw ELF and failure controls."""
from pathlib import Path
import argparse,struct,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
root=ROOT;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def positives(out):
 expected=[]
 for n,unequal,repeats in [(0,False,1),(1,False,1),(17,False,1),(17,True,1),(257,False,1),(257,True,1),(257,False,257)]:
  name=str(n)+('-quadratic' if repeats>1 else '-unequal' if unequal else '-equal');code=bytearray();labels={};fixups=[]
  def raw(b):code.extend(b)
  def label(s):labels[s]=len(code)
  def lea(s):raw(b'\x48\x8d\x35');fixups.append((len(code),s));raw(b'\0'*4)
  def write(s,b):raw(b'\xb8\x01\0\0\0\xbf\x01\0\0\0');lea(s);raw(b'\xba'+struct.pack('<I',len(b))+b'\x0f\x05')
  begin=b'COST_BEGIN\n';end=b'COST_END\n';write('begin',begin);raw(b'\x48\x81\xec'+struct.pack('<I',((n+31)//16)*16));raw(b'\x41\xbc'+struct.pack('<I',repeats));label('repeat');raw(b'\x48\x89\xe7');lea('input');raw(b'\xb9'+struct.pack('<I',n)+b'\xf3\xa4');raw(b'\x49\xff\xcc\x0f\x85');fixups.append((len(code),'repeat'));raw(b'\0'*4);raw(b'\x48\x89\xe7');lea('comparison');raw(b'\xb9'+struct.pack('<I',n)+b'\x48\x39\xc9\xf3\xa6');raw(b'\x0f\x84' if unequal else b'\x0f\x85');fixups.append((len(code),'bad-compare'));raw(b'\0'*4);write('end',end);raw(b'\xb8\x3c\0\0\0\x31\xff\x0f\x05')
  label('bad-compare');raw(b'\xb8\x3c\0\0\0\xbf\x02\0\0\0\x0f\x05');label('begin');raw(begin);label('end');raw(end);data=bytes(i%256 for i in range(n));data=(b'\xf3\xa4\xf3\xa6'+data[4:]) if n>=4 else data;label('input');raw(data);label('comparison');raw((bytes([data[0]^255])+data[1:]) if unequal else data)
  for offset,s in fixups:struct.pack_into('<i',code,offset,labels[s]-(offset+4))
  size=120+len(code);header=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,2,62,1,4194424,64,0,0,64,56,1,0,0,0)+struct.pack('<IIQQQQQQ',1,5,0,4194304,4194304,size,size,4096);path=out/name;path.write_bytes(header+code);path.chmod(0o755);expected.append(dict(name=name,n=n,path=str(path),copied=n*repeats,compared=1 if unequal else n,quadratic=repeats>1,sha256=sha(path)))
 (out/'expected.json').write_text(json.dumps(expected,indent=2)+'\n');rows=[]
 for row in expected:
  report=out/(row['name']+'.json');r=subprocess.run(['python3',str(HERE/'v170-bytes-cost-observe.py'),'--repository',root,'--report',report,'--',row['path']],capture_output=True,timeout=240);(out/(row['name']+'-observer.stdout')).write_bytes(r.stdout);(out/(row['name']+'-observer.stderr')).write_bytes(r.stderr);assert r.returncode==0,(row['name'],r.returncode,r.stdout,r.stderr);data=json.loads(report.read_text());assert data['harness_failure'] is None and data['region_complete'] and data['copied_bytes']==row['copied'] and data['compared_bytes']==row['compared'] and data['target_sha256']==row['sha256'];assert not row['quadratic'] or (data['copied_bytes']>row['n'] and data['instruction_steps']>2048+16*(2*row['n']+1));rows.append(data);print('BYTES_STEP_CONTROL_OK',row['name'],data['copied_bytes'],data['compared_bytes'],flush=True)
 (out/'results.json').write_text(json.dumps(dict(kind='independent-raw-ELF-observer-controls',observations=rows,expected_sha256=sha(out/'expected.json')),indent=2)+'\n')

def negatives(out,positive):
 original=(positive/'17-equal').read_bytes();prefix=b'\xb8\x01\0\0\0\xbf\x01\0\0\0';first=original.find(prefix,120);second=original.find(prefix,first+len(prefix));syscall=original.find(b'\x0f\x05',first);finish=original.find(b'\xb8\x3c\0\0\0\x31\xff\x0f\x05');assert first==120 and second>first and syscall>first and finish>second
 cases=[]
 for name in ['missing-end','target-signal','outside-phase-timeout','nonzero-exit']:
  data=bytearray(original)
  if name=='missing-end':data[second+1]=39
  elif name=='target-signal':data[syscall+2:syscall+4]=b'\x0f\x0b'
  elif name=='outside-phase-timeout':data[120:122]=b'\xeb\xfe'
  else:data[finish+5:finish+7]=b'\x90\x90'
  image=out/name;image.write_bytes(data);image.chmod(0o755);cases.append(dict(name=name,image=str(image),sha256=hashlib.sha256(data).hexdigest()))
 (out/'expected.json').write_text(json.dumps(cases,indent=2)+'\n');rows=[]
 for case in cases:
  report=out/(case['name']+'.json');command=['python3',str(HERE/'v170-bytes-cost-observe.py'),'--timeout','.05' if case['name']=='outside-phase-timeout' else '5','--repository',root,'--report',report,'--',case['image']];r=subprocess.run(command,capture_output=True,timeout=15);(out/(case['name']+'-observer.stderr')).write_bytes(r.stderr);assert r.returncode!=0 and report.exists(),(case['name'],r.returncode,r.stderr);record=json.loads(report.read_text());assert record['harness_failure'] and record['target_reaped'] and not Path('/proc/'+str(record['child_pid'])).exists(),record
  if case['name']=='target-signal':assert record['signal'] is None and record['harness_failure']=="AssertionError: ('single-step stop', 4)"
  elif case['name']=='outside-phase-timeout':assert 'TimeoutError: observer wall guard'==record['harness_failure']
  elif case['name']=='missing-end':assert record['exit']==0 and not record['region_complete'] and 'incomplete region' in record['harness_failure']
  else:assert record['exit']==1 and record['region_complete'] and 'incomplete region' in record['harness_failure']
  rows.append(dict(case=case['name'],rejected=True,record=record));print('BYTES_STEP_NEGATIVE_OK',case['name'],flush=True)
 (out/'results.json').write_text(json.dumps(dict(kind='observer-rejects-incomplete-region-signal-timeout-and-wrong-exit',observations=rows),indent=2)+'\n')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);positive=out/'positive';positive.mkdir();negative=out/'negative';negative.mkdir();positives(positive);negatives(negative,positive);print('BYTES_COST_CONTROLS_OK positive=6 quadratic=1 negative=4')
if __name__=='__main__':main()
