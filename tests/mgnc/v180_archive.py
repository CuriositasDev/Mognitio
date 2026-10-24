"""Content-addressed evidence archives with byte-preserving path restoration."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
from v180_evidence import canonical, digest, ledger, require


def decode_name(encoded):
    name=base64.b64decode(encoded,validate=True)
    require(name and not name.startswith(b"/") and b"\0" not in name
            and all(p not in (b"",b".",b"..") for p in name.split(b"/")), "unsafe ledger path")
    return os.fsdecode(name)


def freeze(root,archive):
    root=Path(root).resolve();archive=Path(archive).resolve()
    require(not archive.is_relative_to(root),"archive must be outside input")
    require(not archive.exists(),"immutable archive already exists")
    rows=ledger(root);blobs={}
    for row in rows:
        if row["type"]=="file":
            blobs.setdefault(row["sha256"],root/decode_name(row["path_b64"]))
    manifest=dict(schema=1,kind="EvidenceArchive",entries=rows)
    with archive.open("xb") as stream:
        with tarfile.open(fileobj=stream,mode="w:gz",format=tarfile.PAX_FORMAT) as output:
            data=canonical(manifest);info=tarfile.TarInfo("ledger.json");info.size=len(data);info.mode=0o644
            output.addfile(info,io.BytesIO(data))
            for key,path in sorted(blobs.items()):
                data=path.read_bytes();require(digest(data)==key,"source changed during archival")
                info=tarfile.TarInfo("blobs/"+key);info.size=len(data);info.mode=0o644
                output.addfile(info,io.BytesIO(data))
    require(rows==ledger(root),"source tree changed during archival")
    return dict(schema=1,kind="ArchiveReceipt",sha256=digest(archive.read_bytes()),
                bytes=archive.stat().st_size,ledger_sha256=digest(canonical(manifest)),
                entries=len(rows),unique_blobs=len(blobs))


def restore(archive,destination,receipt):
    archive=Path(archive);destination=Path(destination)
    require(not destination.exists(),"restore requires absent destination")
    require(digest(archive.read_bytes())==receipt["sha256"],"archive digest mismatch")
    with tarfile.open(archive) as data:
        members=data.getmembers();names=[m.name for m in members]
        require(len(names)==len(set(names)) and all(m.isfile() for m in members),"invalid archive members")
        manifest_bytes=data.extractfile("ledger.json").read()
        require(digest(manifest_bytes)==receipt["ledger_sha256"],"ledger digest mismatch")
        manifest=json.loads(manifest_bytes)
        require(canonical(manifest)==manifest_bytes and manifest["schema"]==1
                and manifest["kind"]=="EvidenceArchive","invalid archive schema")
        rows=manifest["entries"]
        require(len(rows)==receipt["entries"],"entry count mismatch")
        paths=[decode_name(row["path_b64"]) for row in rows]
        require(len(paths)==len(set(paths)),"duplicate ledger path")
        index=dict(zip(paths,rows))
        for name in paths:
            parent=Path(name).parent
            while parent!=Path("."):
                require(str(parent) in index and index[str(parent)]["type"]=="directory",
                        "non-directory ancestor")
                parent=parent.parent
        blobnames={"blobs/"+row["sha256"] for row in rows if row["type"]=="file"}
        require(set(names)=={"ledger.json"}|blobnames,"extra or missing archive content")
        require(len(blobnames)==receipt["unique_blobs"],"blob count mismatch")
        destination.mkdir()
        groups={}
        for name in sorted(paths,key=lambda p: (len(Path(p).parts),os.fsencode(p))):
            row=index[name];target=destination/name
            require(type(row["mode"]) is int and 0<=row["mode"]<=0o7777,"invalid mode")
            if row["type"]=="directory":target.mkdir()
            elif row["type"]=="symlink":
                target.symlink_to(os.fsdecode(base64.b64decode(row["target_b64"],validate=True)))
            elif row["type"]=="file":
                content=data.extractfile("blobs/"+row["sha256"]).read()
                require(digest(content)==row["sha256"] and len(content)==row["bytes"],"blob mismatch")
                group=row["hardlink_group"]
                if group in groups:
                    require(groups[group][1]==(row["sha256"],row["mode"]),"hardlink content mismatch")
                    os.link(groups[group][0],target)
                else:
                    with target.open("xb") as f:f.write(content)
                    target.chmod(row["mode"])
                    groups[group]=(target,(row["sha256"],row["mode"]))
            else:raise ValueError("unhandled resource kind")
        for name in sorted(paths,key=lambda p: len(Path(p).parts),reverse=True):
            if index[name]["type"]=="directory":(destination/name).chmod(index[name]["mode"])
    require(ledger(destination)==rows,"restored ledger mismatch")
    return dict(schema=1,kind="RestorationReceipt",archive=receipt["sha256"],
                ledger=receipt["ledger_sha256"],status="Passed",entries=len(rows))
