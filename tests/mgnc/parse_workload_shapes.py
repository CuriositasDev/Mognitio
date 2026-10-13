#!/usr/bin/env python3
"""Measure generated syntax independently; mandatory function braces add no depth."""
import hashlib,json
from parse_workloads import sources
from forest_oracle import Tokens

def measure(data):
 tokens=Tokens(data.decode()).tokens;brace=0;angle=0;max_brace=0;max_angle=0;declarations=0
 for word,kind,start,end in tokens:
  if brace==0 and word in ['type','let','var']:declarations+=1
  if word=='{':brace+=1;max_brace=max(max_brace,brace)
  elif word=='}':brace-=1;assert brace>=0
  if word=='<':angle+=1;max_angle=max(max_angle,angle)
  elif word in ['>','>=']:angle-=1;assert angle>=0
 assert brace==angle==0
 return dict(declarations=declarations,syntax_depth=max_brace-1,type_depth=max_angle)

def verify(data,metadata):
 actual=measure(data);assert actual=={k:metadata[k] for k in actual}==dict(declarations=1000,syntax_depth=128,type_depth=128),actual
 return actual

def main():
 name,data,metadata=next(x for x in sources() if x[0]=='combined');actual=verify(data,metadata)
 controls=[data.replace(b'{'*128+b'0'+b'}'*128,b'{'*127+b'0'+b'}'*127),data.replace(b'List<'*128+b'Int'+b'>'*128,b'List<'*127+b'Int'+b'>'*127),data.replace(b'type T0=product{value:Int;};',b'')]
 for changed in controls:
  assert changed!=data
  try:verify(changed,metadata)
  except AssertionError:pass
  else:raise AssertionError('corrupted shape passed')
 print('PARSE_WORKLOAD_SHAPES_OK',json.dumps(actual),'mutation_controls=3','sha256='+hashlib.sha256(data).hexdigest())
if __name__=='__main__':main()
