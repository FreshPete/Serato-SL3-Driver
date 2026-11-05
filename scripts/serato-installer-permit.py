"""Exclusive, expiring permission for an attended ASIO installer transaction."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import time


def read_permit(stage, handle, path, expected_bundle):
    file = stage.information(handle, False)
    stage.require(stage.local(path) == Path(file['path']) and file['links'] == 1,
                  'Installer permit path or link count differs')
    value = json.loads(stage.read_handle(handle, 1024))
    stage.require(isinstance(value, dict) and set(value) == {'bundleSha256', 'expiresUnix'} and
                  re.fullmatch('[0-9a-f]{64}', expected_bundle) is not None and
                  value['bundleSha256'] == expected_bundle and type(value['expiresUnix']) is int,
                  'Installer permit identity differs')
    return value


@contextmanager
def claim(stage, path, expected_bundle):
    """Hold this handle through both registration and the flushed receipt."""
    with stage.open_file(path, share=0) as handle:
        value = read_permit(stage, handle, path, expected_bundle)
        remaining = value['expiresUnix'] - time.time()
        stage.require(0 < remaining <= 300, 'Installer permit expired or outside the attended window')
        yield


def revoke(stage, path, expected_bundle):
    """Delete on the same handle that verified the permit. A live claim blocks this."""
    with stage.open_file(path, access=0x80010000, share=0) as handle:
        read_permit(stage, handle, path, expected_bundle)
        stage.mark_delete(handle)
