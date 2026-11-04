"""Download an exact official npm platform package and verify registry integrity."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import inspect
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    meta = json.load(urllib.request.urlopen("https://registry.npmjs.org/" + args.package.replace("/", "%2f") + "/" + args.version, timeout=30))
    data = urllib.request.urlopen(meta["dist"]["tarball"], timeout=180).read()
    assert "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode() == meta["dist"]["integrity"]
    args.output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        if "filter" in inspect.signature(archive.extractall).parameters:
            archive.extractall(args.output, filter="data")
        else:
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()) or member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise ValueError("Unsafe archive member")
            archive.extractall(args.output)
    (args.output / "package-receipt.json").write_text(json.dumps(dict(package=args.package, version=args.version,
        dist=meta["dist"], sha256=hashlib.sha256(data).hexdigest()), indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
