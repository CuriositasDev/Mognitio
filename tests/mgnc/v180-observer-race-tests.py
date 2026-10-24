#!/usr/bin/env python3
"""Deterministic controls for process exit races and checkout-independent workers."""
from pathlib import Path
import concurrent.futures
import importlib.util
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import v180_observer as observer

class RaceTests(unittest.TestCase):
    def test_disappearing_descendant_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            real_read=Path.read_text
            root_pid=None
            injected=False
            def read(path,*args,**kwargs):
                nonlocal root_pid,injected
                value=str(path)
                if value.startswith('/proc/') and value.endswith('/status'):
                    pid=value.split('/')[2]
                    if root_pid is None:root_pid=pid
                    elif pid!=root_pid and not injected:
                        injected=True
                        raise ProcessLookupError(3,'injected process exit race')
                return real_read(path,*args,**kwargs)
            fn,_=observer.derived_observe()
            command=[sys.executable,'-c','import subprocess,sys;subprocess.run([sys.executable,"-c","import time;time.sleep(.15)"],check=True)']
            with patch.object(Path,'read_text',read):
                result=fn(command,Path(temporary)/'raw',timeout=5,interval=.005)
            self.assertTrue(injected)
            self.assertEqual(result['exit'],0)
            self.assertIsNone(result['harness_failure'])
            samples=json.loads((Path(temporary)/'raw/rss-samples.json').read_text())
            self.assertTrue(any(row['unavailable_pids'] for row in samples))

    def test_worker_survives_source_checkout_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);module_root=root/'checkout/tests/mgnc';module_root.mkdir(parents=True)
            for name in ['v180_observer.py','v150_measurelib.py','v160_measurelib.py']:
                (module_root/name).write_bytes((observer.R/'tests/mgnc'/name).read_bytes())
            path=module_root/'v180_observer.py'
            spec=importlib.util.spec_from_file_location('checkout_observer_control',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(module.observe,[sys.executable,'-c','import time;time.sleep(.25)'],root/'run',timeout=5)
                request=root/'run-request.json'
                deadline=time.monotonic()+5
                while not request.exists() and time.monotonic()<deadline:time.sleep(.001)
                self.assertTrue(request.exists())
                # This is a disposable observer checkout, never the repository.
                path.write_text('checkout replaced while a worker is running\n')
                result=future.result(timeout=10)
            data=json.loads(request.read_text())
            self.assertEqual(result['exit'],0)
            self.assertIsNone(result['harness_failure'])
            self.assertEqual(result['observer_worker_sha256'],data['worker_sha256'])
            self.assertNotEqual(observer.sha(path),data['worker_sha256'])
            self.assertEqual(observer.sha(Path(data['observer_source_bundle'])/'tests/mgnc/v180_observer.py'),data['worker_sha256'])

if __name__=='__main__':unittest.main()
