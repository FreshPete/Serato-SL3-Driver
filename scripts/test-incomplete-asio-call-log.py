"""Exercise the marker-free reader on saved ETLs only; no logger/application/device start."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('incomplete_log',ROOT/'scripts/inspect-incomplete-asio-call-log.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def exercise(completed, marker, incomplete, incomplete_pid, output):
    output = Path(output).absolute()
    p.v.require(output.parent.resolve() == (ROOT/'analysis').resolve() and
                output.name.startswith('asio-incomplete-tests-') and not output.exists(), 'Fresh analysis fixture required')
    saved = p.v.parse(p.v.bounded(marker,65536))
    original = {str(path):p.a.sha(path) for path in (completed,marker,incomplete)}
    output.mkdir(); cases=[]
    full_rows = [p.v.parse(line) for line in (Path(completed).parent/'events.jsonl').read_bytes().splitlines()]
    full = p.a.analyze(full_rows,saved)
    partial = p.inspect(completed,saved['pid'],output/'completed-as-partial')
    assert partial['pairedCalls'] == full['pairedCalls'] == 8
    assert partial['sessionMetadataComplete'] is False and partial['shutdownVerified'] is False
    assert partial['reportedEventsLost'] is None and full['reportedEventsLost'] == 0
    assert partial['methods'] == full['methods'] and partial['pairs'] == full['pairs']
    cases.append({'name':'real-completed-etl-records-preserved-with-unknown-session-state','passed':True})
    old = p.inspect(incomplete,incomplete_pid,output/'markerless')
    assert old['sessionMetadataComplete'] is False and old['shutdownVerified'] is False
    cases.append({'name':'real-markerless-etl-inspected-without-invented-marker','passed':True,
                  'decodedRecords':old['recordCount'],'matchingEventsObserved':old['matchingEventsObserved']})
    try: p.inspect(completed,saved['pid']+1,output/'wrong-pid')
    except ValueError as error:
        assert 'Decoder did not finish successfully' in str(error)
    else: raise AssertionError('Wrong PID accepted')
    assert not (output/'wrong-pid/analysis.json').exists()
    cases.append({'name':'wrong-pid-refused-without-analysis-report','passed':True})
    k=c.WinDLL('kernel32',use_last_error=True)
    k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    k.CreateFileW.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    # Hold write access without writing. The decoder's read-only share must
    # refuse this input rather than inspect or flush an active writer's file.
    handle=k.CreateFileW(str(Path(completed).absolute()),0xC0000000,3,None,3,0,None)
    assert handle not in (None,c.c_void_p(-1).value)
    try:
        try: p.inspect(completed,saved['pid'],output/'writer-held')
        except ValueError as error: assert 'Decoder did not finish successfully' in str(error)
        else: raise AssertionError('Writer-held input accepted')
    finally: k.CloseHandle(handle)
    assert not (output/'writer-held/analysis.json').exists()
    cases.append({'name':'writer-held-input-refused-without-flush-or-analysis','passed':True})
    sentinel=output/'occupied'; sentinel.mkdir(); (sentinel/'keep.txt').write_bytes(b'preserve')
    try: p.inspect(completed,saved['pid'],sentinel)
    except ValueError as error: assert 'Fresh output' in str(error)
    else: raise AssertionError('Existing output accepted')
    assert (sentinel/'keep.txt').read_bytes() == b'preserve' and len(list(sentinel.iterdir())) == 1
    cases.append({'name':'existing-output-preserved','passed':True})
    corrupt=output/'corrupt.etl'; corrupt.write_bytes(b'not an ETL')
    try: p.inspect(corrupt,saved['pid'],output/'corrupt-result')
    except ValueError as error: assert 'Decoder did not finish successfully' in str(error)
    else: raise AssertionError('Corrupt ETL accepted')
    assert not (output/'corrupt-result/analysis.json').exists()
    cases.append({'name':'corrupt-etl-refused-without-analysis-report','passed':True})
    assert all(p.a.sha(Path(path)) == identity for path,identity in original.items())
    report={'schema':'sl3.incomplete-asio-call-log-tests.v1','cases':cases,
        'inputSha256':list(original.values()),'nativeReadOnlyDecoderUsed':True,'completionMarkersWritten':False,
        'completedFixturePairsUnchanged':True,'traceControllerStarted':False,'applicationStarted':False,
        'deviceAccess':False,'seratoShutdownValidated':False}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--completed-etl',type=Path,required=True)
    parser.add_argument('--completed-session',type=Path,required=True)
    parser.add_argument('--incomplete-etl',type=Path,required=True)
    parser.add_argument('--expected-incomplete-pid',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(exercise(args.completed_etl,args.completed_session,args.incomplete_etl,
                             args.expected_incomplete_pid,args.output),indent=2))
