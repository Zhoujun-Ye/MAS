"""Explicit shared-image dependency repair; no models or existing tag changes."""

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import stat
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json

SQLITE_VERSION = '3.54.1'
SQLITE_ARCHIVE_SHA3 = '877c6f4996ce7adb368686bce21638de9e3d91534832ad3d9d119037d1bc22ad'
SQLITE_URL = 'https://www.sqlite.org/2026/sqlite-src-3540100.zip'


def sqlite_sources(archive):
    if hashlib.sha3_256(archive.read_bytes()).hexdigest() != SQLITE_ARCHIVE_SHA3:
        raise ValueError('SQLite archive differs from the official release hash')
    result = {}
    with zipfile.ZipFile(archive) as bundle:
        if sum(m.file_size for m in bundle.infolist()) > 200 * 1024 * 1024:
            raise ValueError('Oversized SQLite source archive')
        for member in bundle.infolist():
            path = Path(member.filename)
            if (path.is_absolute() or '..' in path.parts or path.parts[0] != 'sqlite-src-3540100'
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError('Invalid SQLite source member')
            if not member.is_dir():
                result[str(Path(*path.parts[1:]))] = (bundle.read(member),
                    0o755 if member.external_attr >> 16 & 0o111 else 0o644)
    return result


def sqlite_flags(options):
    flags = []
    for option in options:
        if option.startswith('COMPILER=') or option in {'MUTEX_PTHREADS', 'SYSTEM_MALLOC'}:
            continue
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*(=-?(?:[0-9]+|0x[0-9a-fA-F]+))?', option):
            raise ValueError('Unsupported SQLite compile option: ' + option)
        flags.append('-DSQLITE_' + option)
    return flags


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-image',required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--sqlite-archive', type=Path,
                        help='Explicitly authorized, hash-pinned SQLite source archive; no automatic download')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:@-]*',args.base_image):
        raise ValueError('Invalid base image reference')
    if not args.execute:
        print(json.dumps(dict(status='planned',paid_calls=0,environment_changed=False)))
        return
    if subprocess.run(['docker','image','inspect',args.image],capture_output=True).returncode==0:
        raise ValueError('Refusing to replace an existing image tag')
    base=json.loads(subprocess.check_output(['docker','image','inspect',args.base_image]))[0]
    args.output.mkdir(parents=True,exist_ok=False)
    context=args.output/'build';context.mkdir()
    sqlite_options = None
    if args.sqlite_archive:
        for name, (data, mode) in sqlite_sources(args.sqlite_archive).items():
            path = context / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        sqlite_options = json.loads(subprocess.check_output(['docker', 'run', '--rm', '--network', 'none',
            base['Id'], 'python3', '-c', 'import json,sqlite3; print(json.dumps([r[0] for r in sqlite3.connect(":memory:").execute("pragma compile_options")]))']))
        flags = ' '.join(sqlite_flags(sqlite_options))
        dockerfile = (f"FROM {args.base_image} AS sqlite_build\n"
            "USER root\nRUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev make tcl-dev\n"
            "COPY source/ /src/\nWORKDIR /build\n"
            "RUN /src/configure --enable-update-limit && make -j4 sqlite3.c\n"
            f"RUN gcc -O2 -fPIC -shared -pthread {flags} -Wl,-soname,libsqlite3.so.0 "
            "/build/sqlite3.c -o /build/libsqlite3.so.0 -ldl -lm\n"
            f"RUN make -j4 testfixture OPTIONS='{flags}' && "
            "./testfixture /src/test/select1.test && ./testfixture /src/test/subquery.test && "
            "./testfixture /src/test/limit.test && ./testfixture /src/test/where.test\n"
            f"FROM {args.base_image}\nUSER root\n"
            "COPY --from=sqlite_build /build/libsqlite3.so.0 /usr/local/lib/libsqlite3.so.0\n"
            "RUN ldconfig\n")
    else:
        dockerfile=(f"FROM {args.base_image}\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*\n")
    (context/'Dockerfile').write_text(dockerfile)
    with (args.output/'build.log').open('x') as log:
        subprocess.run(['docker','build','--pull=false','--tag',args.image,str(context)],
            stdout=log,stderr=subprocess.STDOUT,check=True)
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]
    current=json.loads(subprocess.check_output(['docker','image','inspect',args.base_image]))[0]
    if current['Id']!=base['Id'] or image['RootFS']['Layers'][:len(base['RootFS']['Layers'])]!=base['RootFS']['Layers']:
        raise ValueError('Base image changed during build')
    packages=subprocess.check_output(['docker','run','--rm','--network','none',args.image,
        'dpkg-query','-W'],text=True)
    (args.output/'packages.txt').write_text(packages)
    smoke="from pypdf import PdfWriter; import subprocess; from pathlib import Path; w=PdfWriter(); w.add_blank_page(width=300,height=300); w.write('/tmp/probe.pdf'); subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','512','-png','/tmp/probe.pdf','/tmp/probe'],check=True); assert Path('/tmp/probe.png').stat().st_size>100; print('PDF rendering OK')"
    rendered=subprocess.check_output(['docker','run','--rm','--network','none','--cpus','8',
        '--memory','4g',args.image,'python3','-c',smoke],text=True)
    observed_sqlite=json.loads(subprocess.check_output(['docker','run','--rm','--network','none',args.image,
        'python3','-c','import json,sqlite3; c=sqlite3.connect(":memory:"); c.execute("create virtual table f using fts5(body)"); print(json.dumps(dict(version=sqlite3.sqlite_version,source_id=c.execute("select sqlite_source_id()").fetchone()[0],compile_options=[r[0] for r in c.execute("pragma compile_options")],fts5=True)))']))
    if args.sqlite_archive and observed_sqlite['version'] != SQLITE_VERSION:
        raise ValueError('Python did not load the pinned SQLite runtime')
    write_json(args.output/'environment.json',dict(image_tag=args.image,image_id=image['Id'],
        base_image_id=base['Id'],dockerfile_sha256=hashlib.sha256(dockerfile.encode()).hexdigest(),
        packages_sha256=hashlib.sha256(packages.encode()).hexdigest(),pdf_smoke=rendered.strip(),
        sqlite=observed_sqlite, original_sqlite_compile_options=sqlite_options,
        sqlite_source_url=SQLITE_URL if args.sqlite_archive else None,
        sqlite_archive_sha3=SQLITE_ARCHIVE_SHA3 if args.sqlite_archive else None,
        paid_calls=0,existing_image_modified=False))
    print(json.dumps(dict(image_id=image['Id'],pdf_smoke=rendered.strip(),paid_calls=0)))


if __name__=='__main__':main()
