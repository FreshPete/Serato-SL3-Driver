"""Restore MSI File/Component/Directory names after static 7-Zip extraction.

Input JSON comes from read-msi.ps1. No MSI actions are executed.
"""
import argparse
import json
from pathlib import Path
import shutil

def restore(metadata, extracted, output):
    data = json.loads(Path(metadata).read_text(encoding='utf-8-sig'))
    directories = {r['Directory']: r for r in data['Directory']}
    components = {r['Component']: r['Directory_'] for r in data['Component']}
    def directory(key):
        row = directories[key]
        name = row['DefaultDir'].split(':')[0].split('|')[-1]
        parent = row['Directory_Parent']
        if not parent:
            return Path()
        if name == '.':
            return directory(parent)
        return directory(parent) / name
    count = 0
    missing = []
    for row in data['File']:
        source = Path(extracted) / row['File']
        if not source.is_file():
            missing.append(row['File'])
            continue
        destination = Path(output) / directory(components[row['Component_']]) / row['FileName'].split('|')[-1]
        destination.resolve().relative_to(Path(output).resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        count += 1
    print(json.dumps({'restored': count, 'missing': missing, 'output': output}))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('metadata'); p.add_argument('extracted'); p.add_argument('output')
    restore(**vars(p.parse_args()))
