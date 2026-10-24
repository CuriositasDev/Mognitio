#!/usr/bin/env python3
"""Verify generation preconditions and failed-run retention without a compiler."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from v180_evidence import Store, candidate, identity, ledger, source_set
from v180_runner import namespace, run_edge, validate_generation_candidate


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        old_mask=os.umask(0o022);self.addCleanup(os.umask,old_mask)
        self.store=Store(self.root/"records")
        self.source=self.root/"source";self.source.mkdir()
        (self.source/"mognitio.toml").write_text("fixture")
        (self.source/"src").mkdir()
        (self.source/"src/main.mgn").write_text("fixture")
        (self.source/"src/unused-table.mgn").write_bytes(b"table"*1000)
        self.seed=self.root/"seed";self.seed.mkdir()
        (self.seed/"component").write_bytes(b"fixture")
        self.userland=self.root/"userland";self.userland.mkdir()
        sid=self.store.put(source_set(self.source,"T1","fixture"))
        seed=self.store.put(dict(schema=1,kind="Seed",ledger=identity(ledger(self.seed))))
        runtime=self.store.put(source_set(self.source/"src","runtime","fixture"))
        self.cid=candidate(self.store,sources={"T1":sid},seed=seed,runtime=runtime,
            target={"triple":"linux-amd64","abi":"inherited-1.7"},
            conditions=dict(bootstrap_mode=0o700,native_mode=0o755,umask=0o022,guard_wall=3600,guard_rss=8192*1024**2),
            implementation="fixture",authority="fixture")

    def test_candidate_runtime_target_and_generation_conditions(self):
        original=validate_generation_candidate(self.store,self.cid)
        for field,value in [("target",{"triple":"linux-arm64","abi":"inherited-1.7"}),
                            ("target",{"triple":"linux-amd64","abi":"unknown"}),
                            ("conditions",dict(original["conditions"],guard_wall=7200)),
                            ("conditions",dict(original["conditions"],umask=0)),
                            ("runtime",original["sources"]["T1"])]:
            with self.subTest(field=field,value=value):
                changed=copy.deepcopy(original);changed[field]=value
                with self.assertRaises(ValueError):
                    validate_generation_candidate(self.store,self.store.put(changed))
        runtime=self.store.get(original["runtime"])
        for mutation in ["bytes","mode","missing","extra","revision","aggregate"]:
            changed=copy.deepcopy(runtime)
            if mutation=="bytes":changed["files"][0]["sha256"]="0"*64
            if mutation=="mode":changed["files"][0]["mode"]^=0o100
            if mutation=="missing":changed["files"].pop()
            if mutation=="extra":changed["files"].append(dict(changed["files"][0],path="extra.mgn"))
            if mutation=="revision":changed["revision"]="other"
            if mutation=="aggregate":changed["inventory_sha256"]="0"*64
            candidate_record=dict(original,runtime=self.store.put(changed))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_generation_candidate(self.store,self.store.put(candidate_record))

    def test_candidate_mismatch_rejected_before_observer_or_output_creation(self):
        changed=dict(self.store.get(self.cid),target={"triple":"linux-arm64","abi":"inherited-1.7"})
        key=self.store.put(changed);output=self.root/"mismatched"
        with patch("v180_runner.v180_observer.observe") as observer:
            with self.assertRaises(ValueError):
                run_edge(self.store,key,"A",self.source,self.userland,output,seed_root=self.seed)
            observer.assert_not_called()
        self.assertFalse(output.exists())

    def test_process_umask_must_match_frozen_conditions(self):
        os.umask(0)
        with self.assertRaises(ValueError):
            run_edge(self.store,self.cid,"A",self.source,self.userland,self.root/"bad-mask",seed_root=self.seed)
        self.assertEqual(os.umask(0o022),0)

    def test_namespace_native_has_no_seed(self):
        output=self.root/"output";output.mkdir()
        args=namespace(self.userland,self.source,output,builder=self.root/"compiler")
        self.assertNotIn("/seed",args)
        self.assertIn("--ro-bind",args)
        self.assertIn("--unshare-net",args)
        self.assertIn("--as-pid-1",args)
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
