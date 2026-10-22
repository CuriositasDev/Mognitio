#!/usr/bin/env python3
"""Compare record encoding with a frozen source reference and an independent ELF oracle."""
from pathlib import Path
import argparse,hashlib,json,shutil,stat,struct,subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
COUNTS=[0,1,119,120,3975,3976,3977,4095,4096,4097,8191,8192,8193,65535,65536,65537,1048577]
CARRIES=[0,1,2,3,7,8,31,64,65,257]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def expectations():
    rows=[]
    for count in COUNTS:
        body=bytes(i%256 for i in range(count))+b'\xe9'+struct.pack('<i',34)
        body+=b'\x48\x81\xf8'+struct.pack('<i',-2147483648)+b'\x48\x81\xf8'+struct.pack('<i',2147483647)
        body+=b'\x48\xb8'+struct.pack('<q',-9223372036854775808)+b'\x48\xb8'+struct.pack('<q',9223372036854775807)+b'\x48\xba'+struct.pack('<Q',4194424)
        size=120+len(body)
        header=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,2,62,1,4194424,64,0,0,64,56,1,0,0,0)
        header+=struct.pack('<IIQQQQQQ',1,5,0,4194304,4194304,size,size,4096)
        assert len(header)==120 and size==count+169
        value=header+body;rows.append(dict(path='raw-'+str(count)+'.elf',bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),mode=0o644))
    for count in CARRIES:
        value=b''.join(bytes([i%256])*(i%17+1) for i in range(count))
        rows.append(dict(path='carry-'+str(count)+'.bin',bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),mode=0o644))
    for count in CARRIES:
        widths=[0,1,2,3,4095,4096,4097,17,0,8192]
        value=b''.join(bytes([i%256])*widths[i%10] for i in range(count))
        rows.append(dict(path='buffered-'+str(count)+'.bin',bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),mode=0o644))
    for count in [0,1,255,256,257,4095,4096,4097,16385]:
        body=b''.join(bytes([i%256])*(i%17+1) for i in range(count))
        size=120+len(body)
        header=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,2,62,1,4194424,64,0,0,64,56,1,0,0,0)
        header+=struct.pack('<IIQQQQQQ',1,5,0,4194304,4194304,size,size,4096)
        value=header+body
        rows.append(dict(path='records-'+str(count)+'.elf',bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),mode=0o644))
    for count in [0,1,2,3,7,8,4095,4096,4097]:
        value=bytes(i%256 for i in range(count))
        rows.append(dict(path='batch-'+str(count)+'.bin',bytes=count,sha256=hashlib.sha256(value).hexdigest(),mode=0o644))
    return rows
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project)
    old=project/'src/TestOldEncode';old.mkdir();shutil.copyfile(HERE/'harnesses/legacy-encode.mgn',old/'encode.mgn')
    harness=HERE/'harnesses/v170-encode-chunks.mgn';assert harness.read_text().count('try reject(')==16;shutil.copyfile(harness,project/'src/mgnc.mgn')
    rows=expectations();(out/'expected.json').write_text(json.dumps(rows,indent=2)+'\n')
    inputs=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()]
    (out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');images=out/'images';images.mkdir()
    built=subprocess.run([args.seed.resolve(),'build',project/'mognitio.toml','-o',out/'probe'],capture_output=True,timeout=1200,umask=0o022)
    (out/'build.stdout').write_bytes(built.stdout);(out/'build.stderr').write_bytes(built.stderr);assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(built.returncode,built.stderr)
    result=subprocess.run([out/'probe',images],capture_output=True,timeout=600,umask=0o022)
    (out/'run.stdout').write_bytes(result.stdout);(out/'run.stderr').write_bytes(result.stderr)
    assert (result.returncode,result.stdout,result.stderr)==(0,b'ENCODER_CHUNKS_ORACLE_OK images=26 carry_series=29 negative=17\n',b''),(result.returncode,result.stdout,result.stderr)
    for row in rows:
        path=images/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==row['mode'],row['path']
    assert {p.name for p in images.iterdir()}=={r['path'] for r in rows}
    assert all(sha(project/r['path'])==r['sha256'] for r in inputs)
    (out/'results.json').write_text(json.dumps(dict(kind='encoder-bytes-and-diagnostics-not-performance',images=26,carry_series=29,negative=17,independent_expected_sha256=sha(out/'expected.json'),probe_sha256=sha(out/'probe'),source_inputs_sha256=sha(out/'inputs.json')),indent=2)+'\n')
    print('ENCODER_CHUNKS_ORACLE_OK images=26 carry_series=29 negative=17 expected_files='+str(len(rows)))
if __name__=='__main__':main()
