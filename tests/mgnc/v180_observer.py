"""Per-sample observer isolation; frozen process/reaping behavior plus RSS evidence."""
from pathlib import Path
import hashlib,json,os,resource,sys
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests/mgnc'))
import v160_measurelib
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bindings():return {name:sha(R/'tests/mgnc'/name) for name in ['v150_measurelib.py','v160_measurelib.py']}
def derived_observe():
 source=(R/'tests/mgnc/v150_measurelib.py').read_text()
 edits=[
  ('samples=[];reason=None;', 'samples=[];missing_samples=0;observed_children=set();child_samples_missing=0;reason=None;'),
  ('now=time.monotonic()\n                try:', '''now=time.monotonic()
                try:
                    observed_children.update(int(x) for x in Path(f"/proc/{child.pid}/task/{child.pid}/children").read_text().split())
                except FileNotFoundError:child_samples_missing+=1
                try:'''),
  ('else:\n                    # Linux releases', 'else:\n                    missing_samples+=1\n                    # Linux releases'),
  ('streams={}', '''sample_file=directory/"rss-samples.json"
    sample_file.write_text(__import__('json').dumps(samples,separators=(',',':'))+'\\n')
    streams={}'''),
  ('"streams":streams}', '''"streams":streams,"sampled_peak_rss_bytes":max((x['rss_bytes'] for x in samples),default=None),
            "rss_missing_samples":missing_samples,"observed_child_pids":sorted(observed_children),
            "child_samples_missing":child_samples_missing,"child_observation_scope":"sampled direct-child list; final subreaper residue checked separately",
            "rss_samples_sha256":hashlib.sha256(sample_file.read_bytes()).hexdigest()}'''),
 ]
 for old,new in edits:
  assert source.count(old)==1,old
  source=source.replace(old,new)
 ns={};exec(compile(source,'<frozen-observer-with-sample-evidence>','exec'),ns)
 return ns['observe'],hashlib.sha256(source.encode()).hexdigest()
def worker(request):
 data=json.loads(request.read_text());assert bindings()==data['sources'] and sha(__file__)==data['worker_sha256']
 fn,derived_hash=derived_observe();v160_measurelib.observe_process=fn
 os.chdir(data['cwd']);os.umask(data['umask'])
 before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
 result=v160_measurelib.observe(data['command'],data['directory'],timeout=data['timeout'],rss_limit=data['rss_limit'],interval=data['interval'])
 result.update(observer_policy='fresh-process-v1',observer_request_sha256=sha(request),observer_worker_sha256=sha(__file__),observer_sources=data['sources'],instrumented_observer_sha256=derived_hash,observer_peak_before_child_bytes=before,kernel_peak_scope='wait4 measured command, including fixed observer pre-exec floor; instrumented commands include their observer process')
 Path(data['directory'],'observation.json').write_text(json.dumps(result,indent=2)+'\n')
def observe(command,directory,*,timeout=900.0,rss_limit=4096*1024**2,interval=.01):
 directory=Path(directory).absolute();assert not directory.exists();directory.parent.mkdir(parents=True,exist_ok=True)
 request=directory.with_name(directory.name+'-request.json');outer=directory.with_name(directory.name+'-observer')
 assert not request.exists() and not outer.exists()
 mask=os.umask(0o022);os.umask(mask)
 request.write_text(json.dumps(dict(command=list(map(str,command)),directory=str(directory),cwd=str(Path.cwd()),umask=mask,timeout=timeout,rss_limit=rss_limit,interval=interval,sources=bindings(),worker_sha256=sha(__file__)),indent=2)+'\n')
 supervisor=v160_measurelib.observe([sys.executable,str(Path(__file__).resolve()),'--worker',str(request)],outer,timeout=timeout+30,rss_limit=8192*1024**2,interval=.01)
 (outer/'supervision.json').write_text(json.dumps(supervisor,indent=2)+'\n')
 assert supervisor['exit']==0 and supervisor['signal'] is None and supervisor['cutoff'] is None and supervisor['harness_failure'] is None and supervisor['descendant_residue']==supervisor['unreaped_descendants']==0,supervisor
 assert (outer/'stdout').read_bytes()==(outer/'stderr').read_bytes()==b''
 result=json.loads((directory/'observation.json').read_text())
 assert result['observer_request_sha256']==sha(request) and result['observer_worker_sha256']==sha(__file__) and result['observer_sources']==bindings()
 result['observer_supervision_sha256']=sha(outer/'supervision.json')
 return result
if __name__=='__main__':
 assert len(sys.argv)==3 and sys.argv[1]=='--worker';worker(Path(sys.argv[2]))
