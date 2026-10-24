#!/usr/bin/env python3
"""Verify generation preconditions and failed-run retention without a compiler."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from v180_evidence import Store, candidate, identity, ledger, source_set
from v180_runner import namespace, run_edge


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/"records")
        self.source=self.root/"source";self.source.mkdir()
        (self.source/"mognitio.toml").write_text("fixture")
        self.seed=self.root/"seed";self.seed.mkdir()
        (self.seed/"component").write_bytes(b"fixture")
        self.userland=self.root/"userland";self.userland.mkdir()
        sid=self.store.put(source_set(self.source,"T1","fixture"))
        seed=self.store.put(dict(schema=1,kind="Seed",ledger=identity(ledger(self.seed))))
        self.cid=candidate(self.store,sources={"T1":sid},seed=seed,runtime=sid,
            target="linux-amd64",conditions={"umask":18},implementation="fixture",authority="fixture")

    def test_namespace_native_has_no_seed(self):
        output=self.root/"output";output.mkdir()
        args=namespace(self.userland,self.source,output,builder=self.root/"compiler")
        self.assertNotIn("/seed",args)
        self.assertIn("--ro-bind",args)
        self.assertIn("--unshare-net",args)
        (output/"old").write_bytes(b"old")
        with self.assertRaises(ValueError):namespace(self.userland,self.source,output,builder=self.root/"compiler")

    def test_wrong_producer_and_seed_mutation(self):
        with self.assertRaises(ValueError):
            run_edge(self.store,self.cid,"B",self.source,self.userland,self.root/"bad-native",seed_root=self.seed)
        (self.seed/"component").write_bytes(b"mutation")
        with self.assertRaises(ValueError):
            run_edge(self.store,self.cid,"A",self.source,self.userland,self.root/"bad-seed",seed_root=self.seed)

    def test_failed_raw_does_not_register_artifact(self):
        run=self.root/"failed"
        def failed(command,directory,**kwargs):
            directory.mkdir()
            (directory/"stdout").write_bytes(b"")
            (directory/"stderr").write_bytes(b"diagnostic\xff")
            (run/"output/compiler").write_bytes(b"partial")
            return dict(exit=None,signal=9,cutoff="wall",harness_failure=None,
                        descendant_residue=0,unreaped_descendants=0)
        with patch("v180_runner.v180_observer.observe",failed):
            edge,passed=run_edge(self.store,self.cid,"A",self.source,self.userland,run,seed_root=self.seed)
        self.assertFalse(passed)
        receipt=self.store.get(edge)
        self.assertEqual(receipt["status"],"Failed")
        self.assertIsNone(receipt["artifact"])
        self.assertEqual((run/"output/compiler").read_bytes(),b"partial")
        self.assertTrue((run/"receipt.json").is_file())
        with self.assertRaises(ValueError):
            run_edge(self.store,self.cid,"A",self.source,self.userland,run,seed_root=self.seed)


if __name__=="__main__":unittest.main()
