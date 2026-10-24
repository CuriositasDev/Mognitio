#!/usr/bin/env python3
"""Reject mismatched execution context, weak negative oracles and old-role substitution."""
import base64
import copy
import tempfile
import unittest
from pathlib import Path
from v180_evidence import Store, digest, identity
from v180_acceptance import (evaluate_execution, evaluate_matrix,
                              validate_inherited_mapping, validate_observer_binding)

class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.source = self.put("SourceSet", role="T1", files=[])
        self.environment = self.put("Environment", userland="26")
        seed=self.put("Seed",archive="d"*64)
        self.candidate=self.put("Candidate",sources={"T1":self.source},seed=seed)
        def edge(role,parent=None):
            builder=seed if parent is None else self.store.get(parent)["artifact"]
            artifact=self.put("Artifact",candidate=self.candidate,role=role,
                              file=dict(sha256="b"*64,bytes=8,mode=0o700 if role=="A" else 0o755))
            raw=self.put("Raw",files=[])
            observation=self.put("Observation",candidate=self.candidate,status="Passed",raw=raw,
                environment=self.environment,exit=0,signal=None,cutoff=None,harness_failure=None,
                inputs_unchanged=True,residue=0,builder=builder,source=self.source,output=artifact)
            return self.put("BuildEdge",candidate=self.candidate,status="Passed",role=role,
                builder_role="S" if role=="A" else "A",source_role="T1",source=self.source,
                producer=parent,builder=builder,artifact=artifact,observation=observation)
        first=edge("A");self.producer=edge("B",first);self.graph=[first,self.producer]
        expected = self.put("Expected", exit=1, stdout_hex="",
            stderr={"contains_all_hex":[b"type:".hex(), b"[4,5)".hex()]},
            observables={"input_unchanged":True, "output":[]})
        self.contract = dict(candidate=self.candidate, cell="B/26/type", generation="B",
            producer=self.producer, source=self.source, environment=self.environment,
            target={"sha256":"b"*64}, expected=expected,generation_graph=self.graph)
        contents = {"stdout":b"", "stderr":b"mgnc: type: source [4,5)\n"}
        paths = {name:base64.b64encode(name.encode()).decode() for name in contents}
        raw = self.put("Raw", files=[dict(path_b64=paths[name],type="file",
            sha256=digest(data),bytes=len(data)) for name,data in contents.items()])
        self.execution = dict(**self.contract,status="Passed",raw=raw,stream_paths=paths,
            stdout_hex="",stderr_hex=contents["stderr"].hex(),exit=1,signal=None,cutoff=None,
            harness_failure=None,descendant_residue=0,unreaped_descendants=0,
            observables={"input_unchanged":True,"output":[]})
    def put(self, kind, **fields):
        return self.store.put(dict(schema=1,kind=kind,**fields))
    def evaluate(self, changes=None):
        return evaluate_execution(self.store,self.contract,self.put("Execution",**dict(self.execution,**(changes or {}))))
    def test_exact_failure_and_required_observables(self):
        self.assertEqual(self.evaluate(),"Passed")
        for change in [dict(exit=2),dict(signal=9),dict(cutoff="wall"),
                       dict(harness_failure="lost"),dict(descendant_residue=1),
                       dict(unreaped_descendants=1),
                       dict(observables={"input_unchanged":False,"output":[]} )]:
            with self.subTest(change=change):self.assertEqual(self.evaluate(change),"Failed")
    def test_wrong_cell_environment_producer_target_and_expected(self):
        for key,value in [("candidate","c"*64),("cell","B/24/type"),("generation","A"),
                          ("producer","d"*64),("source","e"*64),("environment","f"*64),
                          ("target",{"sha256":"0"*64}),("expected","1"*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.evaluate({key:value})
    def test_missing_generation_ancestor_rejected(self):
        self.contract["generation_graph"]=[self.producer]
        with self.assertRaises(ValueError):self.evaluate()
    def test_raw_stream_must_bind_and_failed_cannot_be_promoted(self):
        for change in [dict(stderr_hex=b"type: [0,1)".hex()),dict(status="Failed"),
                       dict(stream_paths={"stdout":"absent","stderr":"absent"})]:
            with self.subTest(change=change),self.assertRaises(ValueError):self.evaluate(change)
        old=self.put("Execution",**dict(self.execution,status="Failed"))
        self.assertEqual(self.store.get(old)["status"],"Failed")
    def test_expected_position_is_independent_of_observation(self):
        content=b"mgnc: type: source [0,1)\n";row=copy.deepcopy(self.execution)
        raw=self.store.get(row["raw"]);raw["files"][1].update(sha256=digest(content),bytes=len(content))
        row.update(stderr_hex=content.hex(),raw=self.store.put(raw))
        self.assertEqual(evaluate_execution(self.store,self.contract,self.put("Execution",**row)),"Failed")
    def test_missing_environment_remains_not_run(self):
        other=dict(self.contract,cell="B/24/type",environment=self.put("Environment",userland="24"))
        result=evaluate_matrix(self.store,{self.contract["cell"]:self.contract,other["cell"]:other},
                               [self.put("Execution",**self.execution)])
        self.assertEqual(result,{self.contract["cell"]:"Passed",other["cell"]:"NotRun"})
    def test_runtime_exit_four_cannot_be_relabelled_as_two(self):
        expected=self.put("Expected",exit=4,stdout_hex="",stderr={"exact_hex":""},observables={})
        self.contract["expected"]=expected;self.execution["expected"]=expected
        raw=self.store.get(self.execution["raw"]);raw["files"][1].update(sha256=digest(b""),bytes=0)
        self.execution.update(raw=self.store.put(raw),stderr_hex="",exit=4,observables={})
        self.assertEqual(self.evaluate(),"Passed");self.assertEqual(self.evaluate(dict(exit=2)),"Failed")


class ObserverBindingTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(worker_sha256="a"*64, sources={
            "v150_measurelib.py":"b"*64, "v160_measurelib.py":"c"*64})
        self.request_hash = identity(self.request)
        self.result = dict(observer_policy="fresh-process-v2-tree",
            observer_request_sha256=self.request_hash, observer_worker_sha256="a"*64,
            observer_sources=copy.deepcopy(self.request["sources"]), exit=0)
    def test_saved_worker_identity_survives_different_current_checkout(self):
        self.assertTrue(validate_observer_binding(self.request, self.result, self.request_hash))
        self.result.update(exit=None, signal=9, cutoff="wall")
        before=copy.deepcopy(self.result)
        self.assertTrue(validate_observer_binding(self.request, self.result, self.request_hash))
        self.assertEqual(self.result,before)
    def test_success_cannot_relabel_worker_or_dependency_bytes(self):
        for field,value in [("observer_worker_sha256","d"*64),
                ("observer_request_sha256","e"*64),
                ("observer_sources",dict(self.request["sources"], **{"v150_measurelib.py":"f"*64})),
                ("observer_policy","old")]:
            changed=copy.deepcopy(self.result);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_observer_binding(self.request,changed,self.request_hash)
    def test_missing_malformed_or_extra_source_bindings_rejected(self):
        for field,value in [("worker_sha256",None),("worker_sha256","not-a-hash"),
                ("sources",{}),("sources",{"v150_measurelib.py":"b"*64}),
                ("sources",dict(self.request["sources"], extra="d"*64))]:
            changed=copy.deepcopy(self.request);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_observer_binding(changed,self.result,self.request_hash)
        for field in ["observer_request_sha256","observer_worker_sha256","observer_sources"]:
            changed=copy.deepcopy(self.result);del changed[field]
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_observer_binding(self.request,changed,self.request_hash)

class InheritedTests(unittest.TestCase):
    def setUp(self):
        def cell(name,command,source,build=None,dependency=None,group="native"):
            return dict(name=name,command=command,source=source,build_key=build,
                        artifact_dependency=dependency,group=group,expected={"exit":0})
        self.manifest=dict(compiler="old-A",cells=[
            cell("S-build-A",["S17","build","O1"],"C1","A",group="bootstrap"),
            cell("C1-build",["old-A","build","O1"],"C1","B1"),
            cell("B1-build",["$ARTIFACT:B1","build","P"],"P","B1-program","B1"),
            cell("B1-native",["$ARTIFACT:B1-program"],None,dependency="B1-program")])
        self.budget={"cells":{c["name"]:{"wall":12,"rss":4096} for c in self.manifest["cells"]}}
        self.bindings=dict(candidate="a"*64,measurement={"observer":"fixed","warmups":1,"runs":3},
                           roles={"S17":"seed-fixed","A":"new-A","D1":"new-D1","program:D1":"new-P"})
        roles=["S17","A","D1","program:D1"]
        self.mapping=dict(candidate=self.bindings["candidate"],manifest_sha256=identity(self.manifest),
            budget_sha256=identity(self.budget),cells={
                c["name"]:dict(role=role,producer=self.bindings["roles"][role],source=c["source"],
                    old_cell_sha256=identity(c),limit=self.budget["cells"][c["name"]],
                    measurement=self.bindings["measurement"],includes_dependency_build=False)
                for c,role in zip(self.manifest["cells"],roles)})
    def test_original_producer_relationships(self):
        self.assertTrue(validate_inherited_mapping(self.manifest,self.budget,self.mapping,self.bindings))
    def test_substitutions_scope_and_thresholds_rejected(self):
        changes=[("role","B"),("producer","saved-old-B1"),("producer","new-B"),
                 ("source","T1"),("old_cell_sha256","0"*64),("limit",{"wall":3600,"rss":8192}),
                 ("measurement",{"observer":"new"}),("includes_dependency_build",True)]
        for key,value in changes:
            mapping=copy.deepcopy(self.mapping);mapping["cells"]["B1-build"][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_inherited_mapping(self.manifest,self.budget,mapping,self.bindings)
        mapping=copy.deepcopy(self.mapping);del mapping["cells"]["B1-native"]
        with self.assertRaises(ValueError):validate_inherited_mapping(self.manifest,self.budget,mapping,self.bindings)
        mapping=copy.deepcopy(self.mapping);mapping["cells"]["S-build-A"]["producer"]="new-seed"
        with self.assertRaises(ValueError):validate_inherited_mapping(self.manifest,self.budget,mapping,self.bindings)
    def test_original_manifest_and_budget_immutable(self):
        for which in ["manifest","budget"]:
            manifest=copy.deepcopy(self.manifest);budget=copy.deepcopy(self.budget)
            if which=="manifest":manifest["cells"][1]["source"]="T1"
            else:budget["cells"]["B1-build"]["wall"]=3600
            with self.subTest(which=which),self.assertRaises(ValueError):
                validate_inherited_mapping(manifest,budget,self.mapping,self.bindings)

if __name__=="__main__":unittest.main()
