"""Bounded Linux observations shared by the v1.5 corpus and scale runners."""
import hashlib,os,signal,subprocess,time
from pathlib import Path

def observe(command, directory, *, timeout=600.0, rss_limit=4096*1024**2, interval=.05):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    stdout=directory/"stdout";stderr=directory/"stderr"
    samples=[];reason=None;failure=None;status=None;usage=None
    started=time.monotonic()
    with stdout.open("wb") as out,stderr.open("wb") as err:
        child=subprocess.Popen(list(map(str,command)),stdout=out,stderr=err,start_new_session=True)
        try:
            while status is None:
                pid,current,observed=os.wait4(child.pid,os.WNOHANG)
                if pid:
                    status,usage=current,observed
                    break
                now=time.monotonic()
                try:
                    contents=Path(f"/proc/{child.pid}/status").read_text()
                    entries=[line.split() for line in contents.splitlines() if line.startswith("VmRSS:")]
                    if entries:
                        assert len(entries)==1 and entries[0][2]=="kB"
                        current_rss=int(entries[0][1])*1024
                        samples.append({"seconds":now-started,"rss_bytes":current_rss})
                    else:
                        # A zombie can lose VmRSS before wait4 observes its exit.
                        pid,current,observed=os.wait4(child.pid,os.WNOHANG)
                        if pid:
                            status,usage=current,observed
                            break
                        if "State:\tZ" not in contents:
                            raise RuntimeError("live process has no VmRSS")
                        continue
                except FileNotFoundError:
                    pid,current,observed=os.wait4(child.pid,os.WNOHANG)
                    if pid:
                        status,usage=current,observed
                        break
                    raise RuntimeError("live process status is unavailable")
                if samples and samples[-1]["rss_bytes"]>rss_limit:reason="rss"
                elif now-started>=timeout:reason="wall"
                if reason:
                    os.killpg(child.pid,signal.SIGKILL)
                    _,status,usage=os.wait4(child.pid,0)
                    break
                time.sleep(min(interval,max(0,timeout-(time.monotonic()-started))))
        except BaseException as error:
            failure=type(error).__name__+": "+str(error)
            if status is None:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,status,usage=os.wait4(child.pid,0)
        finally:
            child.returncode=os.waitstatus_to_exitcode(status) if status is not None else -signal.SIGKILL
    elapsed=time.monotonic()-started
    streams={}
    for name,path in [("stdout",stdout),("stderr",stderr)]:
        data=path.read_bytes()
        streams[name]={"file":name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
    return {"seconds":elapsed,"peak_rss_raw":usage.ru_maxrss if usage else None,
            "peak_rss_unit":"KiB","peak_rss_bytes":usage.ru_maxrss*1024 if usage else None,
            "exit":child.returncode if child.returncode>=0 else None,
            "signal":-child.returncode if child.returncode<0 else None,
            "cutoff":reason,"harness_failure":failure,"sample_interval_seconds":interval,
            "last_sample":samples[-1] if samples else None,"sample_count":len(samples),
            "streams":streams}
