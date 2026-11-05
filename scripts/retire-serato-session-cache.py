"""Inspect or retire only the exact rebuilt launcher from Serato's cache."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import re
import runpy

LAUNCHER = 'SL3_Rebuild_Development_x64.exe'


def inspect_or_retire(local_app_data, expected, retire=False):
    if not re.fullmatch('[0-9a-f]{64}',expected):
        raise ValueError('Expected lowercase launcher SHA-256')
    stage = runpy.run_path(str(Path(__file__).with_name('asio-install-journal.py')))['stage_module']()
    parent = Path(local_app_data).resolve()
    path = (parent/'Serato'/'Serato DJ Pro'/'Drivers'/LAUNCHER).resolve()
    stage.require(path.is_relative_to(parent) and path.name == LAUNCHER,'Cache path escaped the selected profile')
    stage.local(path)
    if stage.absent(path):
        return {'cachedLauncherPresent':False,'retired':False,'alreadyAbsent':True}
    with stage.pinned_parents(path):
        access = 0x80010100 if retire else 0x80000000
        with stage.open_file(path,access=access,share=0) as handle:
            info = stage.information(handle,False)
            stage.require(Path(info['path']) == path and info['links'] == 1,'Cache identity or link count differs')
            actual = hashlib.sha256(stage.read_handle(handle,1024*1024)).hexdigest()
            stage.require(actual == expected,'Cached launcher differs; preserve it for review')
            if retire:
                flags = w.DWORD(0x1|0x4|0x10)
                stage.check(stage.api('kernel32.dll','SetFileInformationByHandle',w.BOOL,
                                      [w.HANDLE,w.DWORD,c.c_void_p,w.DWORD])(
                    handle,21,c.byref(flags),c.sizeof(flags)))
        if retire:stage.require(stage.absent(path),'Cached launcher still present')
    return {'cachedLauncherPresent':not retire,'retired':retire,'alreadyAbsent':False,'sha256':expected}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-app-data',type=Path,required=True)
    parser.add_argument('--expected-launcher-sha256',required=True)
    parser.add_argument('--retire',action='store_true')
    args=parser.parse_args()
    print(json.dumps(inspect_or_retire(args.local_app_data,args.expected_launcher_sha256,args.retire)))
