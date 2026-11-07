import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from common.file_digest import DigestCache


def test_stable_file_avoids_rehash_but_replaced_content_does_not(tmp_path,monkeypatch):
    p=tmp_path/'input';p.write_bytes(b'aaaa');cache=DigestCache(tmp_path/'hashes.sqlite')
    time.sleep(2.05)
    first=cache.digest(p)
    original=hashlib.sha256
    monkeypatch.setattr(hashlib,'sha256',lambda:pytest.fail('Stable file rehashed'))
    assert cache.digest(p)==first
    monkeypatch.setattr(hashlib,'sha256',original)
    stamp=p.stat();p.write_bytes(b'bbbb');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert cache.digest(p)!=first
    link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(ValueError):cache.digest(link)


def test_recent_timestamp_is_not_enough_to_reuse_a_digest(tmp_path,monkeypatch):
    p=tmp_path/'input';p.write_bytes(b'aaaa');cache=DigestCache(tmp_path/'hashes.sqlite')
    cache.digest(p)
    monkeypatch.setattr(hashlib,'sha256',lambda:(_ for _ in ()).throw(RuntimeError('rehash required')))
    with pytest.raises(RuntimeError,match='rehash required'):cache.digest(p)


def test_concurrent_readers_share_the_same_digest(tmp_path):
    p=tmp_path/'input';p.write_bytes(b'012345'*10000)
    cache=DigestCache(tmp_path/'hashes.sqlite')
    with ThreadPoolExecutor(4) as pool:values=list(pool.map(lambda _:cache.digest(p),range(8)))
    assert len(set(values))==1


def test_pinned_blob_cache_binds_expected_git_oid_and_content(tmp_path,monkeypatch):
    p=tmp_path/'input';p.write_bytes(b'aaaa');cache=DigestCache(tmp_path/'cache.sqlite')
    oid=hashlib.sha1(b'blob 4\0aaaa').hexdigest()
    time.sleep(2.05)
    expected=cache.digest(p,git_blob=oid)
    original=hashlib.sha256
    monkeypatch.setattr(hashlib,'sha256',lambda:pytest.fail('Verified stable blob rehashed'))
    assert cache.digest(p,git_blob=oid)==expected
    monkeypatch.setattr(hashlib,'sha256',original)
    with pytest.raises(ValueError,match='pinned'):cache.digest(p,git_blob='0'*40)
    before=p.stat();p.write_bytes(b'bbbb');os.utime(p,ns=(before.st_atime_ns,before.st_mtime_ns))
    with pytest.raises(ValueError,match='pinned'):cache.digest(p,git_blob=oid)
