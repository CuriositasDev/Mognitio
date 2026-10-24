#!/usr/bin/env python3
"""Adversarial checks for candidate, graph, suite and restored raw evidence."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from v180_evidence import *


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "store")
        self.src = self.root / "src"
        self.src.mkdir()
        (self.src / "main.mgn").write_text("0")
        (self.src / "unused.mgn").write_text("discard 1;")
        self.source = source_set(self.src, "T1", "revision")
        self.sid = self.store.put(self.source)
        self.seed = self.store.put(dict(schema=1,kind="Seed",archive="a"*64,manifest="b"*64))
        self.candidate = candidate(self.store,sources={"T1":self.sid},seed=self.seed,
            runtime=self.sid,target="linux-amd64",conditions={"umask":18},
            implementation="tree",authority="accepted")

    def edge(self, role, parent=None, **changes):
        builder_role = {"A":"S","B":"A","C":"B","B-repeat":"A","C-repeat":"B"}[role]
        builder = self.seed if parent is None else self.store.get(parent)["artifact"]
        artifact = self.store.put(dict(schema=1,kind="Artifact",candidate=self.candidate,
            role=role,file=dict(bytes=10,mode=0o755,sha256="c"*64)))
        raw=self.store.put(dict(schema=1,kind="Raw",files=[]))
        env=self.store.put(dict(schema=1,kind="Environment",fixture="unit-test"))
        obs = dict(schema=1,kind="Observation",raw=raw,environment=env,candidate=self.candidate,status="Passed",
            exit=0,signal=None,cutoff=None,harness_failure=None,inputs_unchanged=True,
            residue=0,builder=builder,source=self.sid,output=artifact)
        obs.update(changes.pop("observation",{}))
        edge = dict(schema=1,kind="BuildEdge",candidate=self.candidate,role=role,
            builder_role=builder_role,source_role="T1",source=self.sid,producer=parent,
            builder=builder,artifact=artifact,status="Passed",observation=self.store.put(obs))
        edge.update(changes)
        return self.store.put(edge)

    def test_whole_inventory(self):
        verify_sources(self.src,self.source)
        (self.src/"unused.mgn").unlink()
        with self.assertRaises(ValueError):verify_sources(self.src,self.source)

    def test_inventory_mode_extra_and_source_change(self):
        for operation in ("mode","extra","bytes"):
            with self.subTest(operation=operation):
                p=self.src/"main.mgn"
                old=p.read_bytes();mode=p.stat().st_mode&0o777
                if operation=="mode":p.chmod(mode^0o100)
                if operation=="extra":(self.src/"extra").write_bytes(b"table")
                if operation=="bytes":p.write_bytes(b"1")
                with self.assertRaises(ValueError):verify_sources(self.src,self.source)
                p.write_bytes(old);p.chmod(mode)
                if (self.src/"extra").exists():(self.src/"extra").unlink()

    def test_symlink_and_paths(self):
        (self.src/"link").symlink_to("main.mgn")
        with self.assertRaises(ValueError):source_set(self.src,"T1","r")
        for value in ("../x","/x","a//x","a/./x",".","a\\x"):
            with self.subTest(value=value),self.assertRaises(ValueError):relative(value)

    def test_serialization_corruption(self):
        with self.assertRaises(ValueError):canonical({"x":float("nan")})
        key=self.sid;p=self.store.root/(key+".json");p.write_bytes(p.read_bytes()+b" ")
        with self.assertRaises(ValueError):self.store.get(key)
        with self.assertRaises(ValueError):self.store.put(self.source)

    def test_generation_roles_even_with_identical_bytes(self):
        a=self.edge("A");b=self.edge("B",a);c=self.edge("C",b)
        bp=self.edge("B-repeat",a);cp=self.edge("C-repeat",b)
        roles=validate_graph(self.store,self.candidate,[a,b,c,bp,cp],complete=True)
        self.assertEqual(len(roles),5)
        with self.assertRaises(ValueError):validate_graph(self.store,self.candidate,[a,b,c],complete=True)

    def test_invalid_producer(self):
        a=self.edge("A")
        for kwargs in ({"builder_role":"B"},{"candidate":"f"*64},{"source":"e"*64},
                       {"producer":"d"*64},{"status":"Failed"},{"builder":self.seed}):
            with self.subTest(kwargs=kwargs):
                bad=self.edge("B",a,**kwargs)
                with self.assertRaises((ValueError,FileNotFoundError)):
                    validate_graph(self.store,self.candidate,[a,bad])

    def test_failed_observation_cannot_be_promoted(self):
        for field,value in (("exit",1),("signal",9),("cutoff","wall"),
                            ("harness_failure","missing"),("inputs_unchanged",False),
                            ("residue",1),("status","Failed"),("output","d"*64)):
            with self.subTest(field=field):
                a=self.edge("A",observation={field:value})
                with self.assertRaises(ValueError):validate_graph(self.store,self.candidate,[a])

    def test_raw_comparator(self):
        a=self.root/"a";b=self.root/"b"
        a.write_bytes(b"abcdef");b.write_bytes(a.read_bytes());a.chmod(0o755);b.chmod(0o755)
        self.assertEqual(compare_files(a,b)["status"],"Passed")
        b.write_bytes(b"abcxef")
        self.assertEqual(compare_files(a,b)["first_difference"],3)
        b.write_bytes(b"abcdefx")
        self.assertEqual(compare_files(a,b)["first_difference"],6)
        b.write_bytes(a.read_bytes());b.chmod(0o700)
        self.assertEqual(compare_files(a,b)["status"],"Failed")
        self.assertIsNone(compare_files(a,b)["first_difference"])

    def test_suite_missing_environment_and_expected(self):
        cells=["A/24/check","A/26/check","B/24/check","B/26/check","C/24/check","C/26/check"]
        suite=self.store.put(dict(schema=1,kind="Suite",cells=cells,expected={c:"e"*64 for c in cells}))
        run=dict(schema=1,kind="Run",candidate=self.candidate,suite=suite,cell=cells[0],
                 expected="e"*64,status="Failed",receipts=[])
        key=self.store.put(run)
        statuses=evaluate_suite(self.store,self.candidate,suite,[key])
        self.assertEqual(statuses[cells[0]],"Failed")
        self.assertEqual(list(statuses.values()).count("NotRun"),5)
        for changes in (dict(expected="d"*64),dict(candidate="d"*64),dict(status="Passed")):
            bad=dict(run,**changes)
            with self.assertRaises(ValueError):
                evaluate_suite(self.store,self.candidate,suite,[self.store.put(bad)])
        self.assertEqual(self.store.get(key)["status"],"Failed")

    def test_ledger_content_and_hardlinks(self):
        import shutil
        tree=self.root/"tree";tree.mkdir()
        (tree/"data").write_bytes(b"binary\x00\xff")
        os.link(tree/"data",tree/"hard")
        (tree/"link").symlink_to("data")
        expected=ledger(tree)
        other=self.root/"restored";shutil.copytree(tree,other,symlinks=True)
        self.assertNotEqual(expected,ledger(other))
        (other/"hard").unlink();os.link(other/"data",other/"hard")
        self.assertEqual(expected,ledger(other))
        (other/"data").write_bytes(b"changed")
        self.assertNotEqual(expected,ledger(other))


if __name__=="__main__":
    unittest.main()
