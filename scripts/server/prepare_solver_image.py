"""Explicit shared-image PDF dependency repair; no models or existing tag changes."""

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-image',required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
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
    write_json(args.output/'environment.json',dict(image_tag=args.image,image_id=image['Id'],
        base_image_id=base['Id'],dockerfile_sha256=hashlib.sha256(dockerfile.encode()).hexdigest(),
        packages_sha256=hashlib.sha256(packages.encode()).hexdigest(),pdf_smoke=rendered.strip(),
        paid_calls=0,existing_image_modified=False))
    print(json.dumps(dict(image_id=image['Id'],pdf_smoke=rendered.strip(),paid_calls=0)))


if __name__=='__main__':main()
