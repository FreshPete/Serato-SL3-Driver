"""Stage a hash-reviewed embedded Python ZIP and reviewed wheel files offline."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parents[1]
MAX_FILE=256*1024*1024
MAX_TOTAL=384*1024*1024


def require(value,message):
    if not value:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def member_name(name):
    path=PurePosixPath(name)
    require(name and '\\' not in name and ':' not in name and not path.is_absolute() and
            all(part not in ('','..','.') for part in name.split('/')) and str(path)==name,
            'Unsafe runtime member path')
    return path


def embedded_files(raw):
    files={}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows=archive.infolist()
        require(1<=len(rows)<=128 and sum(row.file_size for row in rows)<=64*1024*1024,'Embedded ZIP inventory exceeds bounds')
        for row in rows:
            member_name(row.filename)
            require('/' not in row.filename and not row.is_dir() and row.filename not in files and
                    not stat.S_ISLNK(row.external_attr>>16) and not row.flag_bits&1,
                    'Embedded ZIP requires unique regular top-level files')
            require(0<=row.file_size<=32*1024*1024,'Embedded ZIP member exceeds bound')
            files[row.filename]=archive.read(row)
    paths=[name for name in files if re.fullmatch(r'python3[0-9]+\._pth',name)]
    require(len(paths)==1 and all(name in files for name in ('python.exe','python3.dll','LICENSE.txt')),
            'Expected embedded Python distribution')
    name=paths[0];stem=name.removesuffix('._pth')
    require(stem+'.zip' in files and stem+'.dll' in files,'Embedded standard library/runtime missing')
    # Isolated module search; do not enable site, user packages, registry or pip.
    files[name]=(stem+'.zip\n.\npackages\n').encode('ascii')
    return files


def wheel_files(record_path):
    record_path=Path(record_path).absolute()
    require(record_path.name=='RECORD' and record_path.parent.name.endswith('.dist-info'),'Wheel RECORD required')
    base=record_path.parent.parent
    package_name=record_path.parent.name.split('-',1)[0].lower()
    require(package_name in ('pefile','capstone','frida'),'Unexpected runtime dependency')
    raw=record_path.read_bytes();require(len(raw)<=1024*1024,'Wheel inventory exceeds bound')
    files={}
    for row in csv.reader(io.StringIO(raw.decode('utf-8'))):
        require(len(row)==3,'Malformed wheel inventory')
        name,digest,size=row;parts=member_name(name)
        if '__pycache__' in parts.parts or name.endswith('.pyc'):continue
        require(name not in files,'Duplicate wheel member')
        path=base.joinpath(*parts.parts)
        require(path.resolve().is_relative_to(base.resolve()),'Wheel member escapes its root')
        info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400 and
                info.st_size<=MAX_FILE,'Regular bounded wheel member required')
        data=path.read_bytes()
        if name==record_path.relative_to(base).as_posix():
            require(not digest and not size,'Wheel RECORD must be its unhashed self entry')
        else:
            require(digest.startswith('sha256=') and size.isdigit() and len(data)==int(size),'Wheel member hash/size required')
            actual=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            require(digest=='sha256='+actual,'Wheel member changed: '+name)
        files['packages/'+name]=data
    require(any('LICENSE' in name.upper() or name.endswith('/COPYING') for name in files),'Dependency license file missing')
    return package_name,sha(raw),files


def prepare(archive,expected,records,output=None):
    require(re.fullmatch('[0-9a-f]{64}',expected),'Expected lowercase archive SHA-256')
    require(Path(archive).stat().st_size<=32*1024*1024,'Embedded archive exceeds bound')
    raw=Path(archive).read_bytes();require(sha(raw)==expected,'Embedded archive hash differs')
    files=embedded_files(raw);dependencies={}
    require(len(records)==3,'Three reviewed runtime dependency records required')
    for record in records:
        name,identity,added=wheel_files(record)
        require(name not in dependencies and not set(files)&set(added),'Dependency inventory collision')
        dependencies[name]={'recordSha256':identity};files.update(added)
    require(set(dependencies)=={'pefile','capstone','frida'} and sum(map(len,files.values()))<=MAX_TOTAL,'Runtime inventory differs or exceeds bound')
    manifest={'schema':'sl3.embedded-python.v1','archiveSha256':expected,'dependencies':dependencies,
              'moduleSearch':'embedded standard library, runtime directory, packages; site disabled',
              'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in sorted(files.items())},
              'systemPythonModified':False,'liveSeratoValidated':False}
    if output is None:
        return {'planOnly':True,'filesVerified':len(files),'expandedBytes':sum(map(len,files.values())),
                'filesWritten':False,'interpreterExecuted':False}
    output=Path(output).absolute()
    require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('embedded-python-') and
            not output.exists(),'Fresh artifacts/build/embedded-python-* directory required')
    output.mkdir()
    for name,data in sorted(files.items()):
        path=output.joinpath(*member_name(name).parts);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
    with (output/'runtime-manifest.json').open('x',encoding='utf-8') as stream:json.dump(manifest,stream,sort_keys=True,indent=2);stream.write('\n')
    return {'prepared':True,'directory':str(output),'filesVerified':len(files),'expandedBytes':sum(map(len,files.values())),
            'runtimeManifestSha256':sha((output/'runtime-manifest.json').read_bytes()),'interpreterExecuted':False,
            'systemPythonModified':False}


def verify(directory,expected):
    directory=Path(directory).absolute()
    require(re.fullmatch('[0-9a-f]{64}',expected),'Expected runtime manifest SHA-256')
    path=directory/'runtime-manifest.json';raw=path.read_bytes()
    require(len(raw)<=1024*1024 and sha(raw)==expected,'Runtime manifest differs')
    manifest=json.loads(raw)
    require(manifest['schema']=='sl3.embedded-python.v1' and 1<=len(manifest['files'])<=512,
            'Unsupported runtime inventory')
    require(sum(details['bytes'] for details in manifest['files'].values())<=MAX_TOTAL,'Runtime inventory exceeds total bound')
    expected_paths=set()
    for name,details in manifest['files'].items():
        target=directory.joinpath(*member_name(name).parts)
        info=target.lstat()
        require(target.resolve().is_relative_to(directory.resolve()) and stat.S_ISREG(info.st_mode) and
                not getattr(info,'st_file_attributes',0)&0x400 and 0<=info.st_size<=MAX_FILE,
                'Runtime member must be contained, regular and bounded')
        require(info.st_size==details['bytes'] and sha(target.read_bytes())==details['sha256'],
                'Runtime member differs: '+name)
        expected_paths.add(name)
    require(len({name.casefold() for name in expected_paths})==len(expected_paths),'Runtime path aliases refused')
    actual={path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    require(actual==expected_paths|{'runtime-manifest.json'},'Unexpected runtime files')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--expected-archive-sha256')
    parser.add_argument('--package-record',type=Path,action='append')
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--expected-runtime-manifest-sha256')
    args=parser.parse_args()
    if args.verify:
        manifest=verify(args.verify,args.expected_runtime_manifest_sha256 or '')
        print(json.dumps({'runtimeVerified':True,'filesVerified':len(manifest['files']),'interpreterExecuted':False}))
    else:
        require(args.archive is not None and args.expected_archive_sha256 and args.package_record,'Complete preparation inputs required')
        print(json.dumps(prepare(args.archive,args.expected_archive_sha256,args.package_record,args.prepare),indent=2))
