"""Same recon schema/path validation on the host and in the read-only native hook."""

import json
from pathlib import Path


def validate_packet(path, data_root):
    path, data_root = Path(path), Path(data_root)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('Write a regular recon.json of at most 32768 bytes')
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {'task_qualifiers','candidate_sources','uncertainties'}:
        raise ValueError('Use exactly task_qualifiers, candidate_sources, uncertainties')
    for key in ('task_qualifiers','uncertainties'):
        if not isinstance(data[key],list) or not all(isinstance(v,str) for v in data[key]):
            raise ValueError('Qualifiers and uncertainties must be lists of strings')
    if not isinstance(data['candidate_sources'],list):
        raise ValueError('candidate_sources must be a list')
    for source in data['candidate_sources']:
        if not isinstance(source,dict) or set(source) != {'path','columns','units','relevance'}:
            raise ValueError('Each source needs path, columns, units, relevance')
        if not isinstance(source['path'],str):
            raise ValueError('Source path must be a string')
        p=Path(source['path'])
        if not p.is_absolute() or '..' in p.parts or not p.is_relative_to('/data'):
            raise ValueError('Source path must be an absolute /data/ input file')
        host=data_root/p.relative_to('/data')
        if not host.is_file() or host.is_symlink() or not host.resolve().is_relative_to(data_root.resolve()):
            raise ValueError('Each source path must be an existing FILE, not a directory: '+str(p))
        if (not isinstance(source['columns'],list) or not all(isinstance(c,str) for c in source['columns'])
                or not isinstance(source['units'],str) or not isinstance(source['relevance'],str)):
            raise ValueError('Source columns must be strings; units/relevance must be strings')
    return data
