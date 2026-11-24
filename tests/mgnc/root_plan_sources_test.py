"""The staging graph includes every namespace part and preserves source bytes."""
from pathlib import Path
import runpy
import tempfile
import unittest

prepare = runpy.run_path(str(Path(__file__).resolve().with_name("root_plan_sources.py")))["prepare"]


class SplitNamespaceTests(unittest.TestCase):
    def test_both_parts_supply_imports_and_keep_their_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            sources = {
                "Split/first.mgn": b"namespace Mgnc\\Split;\r\nuse Mgnc\\Left\\{x};\r\n",
                "Split/second.mgn": b"namespace Mgnc\\Split;\nuse Mgnc\\Right\\{y};\n",
                "Left/left.mgn": b"namespace Mgnc\\Left;\n",
                "Right/right.mgn": b"namespace Mgnc\\Right;\n",
                "WholeRoots/roots.mgn": b"namespace Mgnc\\WholeRoots;\n",
                "WholeRootCheck/check.mgn": b"namespace Mgnc\\WholeRootCheck;\n",
                "WholeLayoutCheck/check.mgn": b"namespace Mgnc\\WholeLayoutCheck;\n",
                "Unrelated/unrelated.mgn": b"namespace Mgnc\\Unrelated;\n",
            }
            compiler = root / "compiler/mgnc"
            for name, content in sources.items():
                target = compiler / "src" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            (compiler / "mognitio.toml").write_bytes(b'[project]\r\nname = "mgnc"\r\nroot_namespace = "Mgnc"\r\n')
            fixtures = root / "tests/mgnc/harnesses"
            fixtures.mkdir(parents=True)
            harness = b"namespace Mgnc;\r\nuse Mgnc\\Split\\{a};\r\nuse Mgnc\\WholeRoots\\{a};\nuse Mgnc\\WholeRootCheck\\{a};\nuse Mgnc\\WholeLayoutCheck\\{a};\nuse Mgnc\\RootReference\\{a};\n"
            (fixtures / "probe.mgn").write_bytes(harness)
            reference = b"namespace Mgnc\\RootReference;\r\n"
            (fixtures / "v160-root-reference.mgn").write_bytes(reference)
            project = Path(temporary) / "project"
            selected = prepare(root, "probe.mgn", project)
            self.assertEqual(len(selected["Mgnc\\Split"]), 2)
            self.assertIn("Mgnc\\Left", selected)
            self.assertIn("Mgnc\\Right", selected)
            self.assertNotIn("Mgnc\\Unrelated", selected)
            for name, content in sources.items():
                if name.startswith("Unrelated/"):
                    self.assertFalse((project / "src" / name).exists())
                else:
                    self.assertEqual((project / "src" / name).read_bytes(), content)
            self.assertEqual((project / "src/mgnc.mgn").read_bytes(), harness)
            self.assertEqual((project / "src/RootReference/verify.mgn").read_bytes(), reference)
            self.assertEqual((project / "mognitio.toml").read_bytes(), (compiler / "mognitio.toml").read_bytes())


if __name__ == "__main__":
    unittest.main()
