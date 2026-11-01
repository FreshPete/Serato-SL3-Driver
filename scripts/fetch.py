"""Download research artifacts without executing them; append provenance records."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request

def fetch(url, destination):
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.partial')
    request = urllib.request.Request(url, headers={'User-Agent': 'SL3-compatibility-research/0.1'})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as output:
        digest = hashlib.sha256()
        size = 0
        while block := response.read(1024 * 1024):
            output.write(block)
            digest.update(block)
            size += len(block)
        record = dict(url=url, resolved_url=response.url.split('?')[0], path=target.as_posix(),
                      retrieved_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                      bytes=size, sha256=digest.hexdigest(), content_type=response.headers.get('Content-Type'))
    partial.replace(target)
    ledger = Path('docs/evidence/downloads.jsonl')
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open('a', encoding='utf-8') as output:
        output.write(json.dumps(record) + '\n')
    print(json.dumps(record))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('destination')
    args = parser.parse_args()
    fetch(args.url, args.destination)
