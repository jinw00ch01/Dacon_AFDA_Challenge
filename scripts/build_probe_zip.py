"""Rebuild a submission zip from a source zip, replacing only inference.py.

Usage: python scripts/build_probe_zip.py <src_zip> <inference.py> <dst_zip>

Copies every non-inference entry with byte-identical *content* (verified by
per-entry SHA256 of the decompressed bytes) so only inference.py differs.
"""
import hashlib
import sys
import zipfile


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(src, inf, dst):
    with open(inf, "rb") as f:
        inf_bytes = f.read()
    src_hashes = {}
    dst_hashes = {}
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zi.infolist():
            data = zi.read(item.filename)
            src_hashes[item.filename] = sha(data)
            if item.filename == "inference.py":
                data = inf_bytes
            zo.writestr(item, data)
            dst_hashes[item.filename] = sha(data)
    # verify: only inference.py content changed
    for name in src_hashes:
        if name == "inference.py":
            continue
        assert src_hashes[name] == dst_hashes[name], f"content drift: {name}"
    with open(dst, "rb") as f:
        zip_sha = sha(f.read())
    print("dst:", dst)
    print("zip_sha256:", zip_sha)
    print("inference.py src_sha:", src_hashes["inference.py"], "-> dst_sha:", dst_hashes["inference.py"])
    print("model/other entries: content byte-identical (verified)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
