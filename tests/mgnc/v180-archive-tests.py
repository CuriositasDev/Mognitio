#!/usr/bin/env python3
"""Round-trip and negative controls for raw evidence restoration."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from v180_archive import freeze, restore, decode_name
from v180_evidence import ledger


class ArchiveTests(unittest.TestCase):
    def test_binary_names_modes_and_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            work=Path(temporary);root=work/"source";root.mkdir()
            (root/"dir").mkdir();(root/"dir/data").write_bytes(bytes([0,255,1]))
            (root/"dir/data").chmod(0o664)
            os.link(root/"dir/data",root/"hard")
            (root/"link").symlink_to("dir/data")
            fd=os.open(os.fsencode(root)+b"/invalid-"+bytes([255]),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o640)
            os.write(fd,b"payload");os.close(fd)
            archive=work/"evidence.tar.gz"
            receipt=freeze(root,archive)
            result=restore(archive,work/"restored",receipt)
            self.assertEqual(result["status"],"Passed")
            self.assertEqual(ledger(root),ledger(work/"restored"))
            self.assertEqual(receipt["unique_blobs"],2)
            with self.assertRaises(ValueError):freeze(root,archive)
            with self.assertRaises(ValueError):restore(archive,work/"restored",receipt)
            with self.assertRaises(ValueError):restore(archive,work/"invalid",dict(receipt,sha256="0"*64))
            with self.assertRaises(ValueError):restore(archive,work/"invalid",dict(receipt,ledger_sha256="0"*64))
            with self.assertRaises(ValueError):freeze(root,root/"archive")
            archive.write_bytes(archive.read_bytes()+b"changed")
            with self.assertRaises(ValueError):restore(archive,work/"invalid",receipt)

    @unittest.skipIf(os.geteuid() == 0, "permission controls require non-root")
    def test_unreadable_subtree_cannot_be_archived_as_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            work=Path(temporary);root=work/"source";root.mkdir()
            (root/"visible").write_bytes(b"visible")
            restricted=root/"restricted";restricted.mkdir()
            (restricted/"hidden").write_bytes(b"must not disappear")
            archive=work/"evidence.tar.gz"
            restricted.chmod(0)
            try:
                with self.assertRaises(PermissionError):freeze(root,archive)
                self.assertFalse(archive.exists())
                self.assertEqual(restricted.stat().st_mode&0o777,0)
            finally:
                restricted.chmod(0o700)
            receipt=freeze(root,archive)
            self.assertEqual(receipt["unique_blobs"],2)
            self.assertEqual(restore(archive,work/"restored",receipt)["status"],"Passed")
            self.assertEqual((work/"restored/restricted/hidden").read_bytes(),b"must not disappear")

    def test_unsafe_names(self):
        for name in ("../escape","/absolute","a/../b","a//b","", "."):
            with self.subTest(name=name),self.assertRaises(ValueError):
                decode_name(base64.b64encode(name.encode()).decode())


if __name__=="__main__":unittest.main()
