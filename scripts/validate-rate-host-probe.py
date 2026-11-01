"""Offline held-rate intent/result/ownership consistency; no hardware attestation or traced-test pass."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
base=load('rate_probe_controls','validate-controls-host-probe.py')
rate=load('rate_probe_observations','validate-usbdk-rate.py')
require,read,digest=base.require,base.read,base.digest


def decode_wire(text,expected):
    require(type(expected) is int and expected in (44100,48000),'Invalid expected rate target')
    require(type(text) is str and re.fullmatch('[0-9a-f]{128}',text) is not None,'Invalid rate wire hex/size')
    w=struct.unpack('<16I',bytes.fromhex(text))
    require(w[:3]==(0x52334c53,1,expected) and not w[14] and not w[15] and not w[12]&~3,'Wrong rate version/target/reserved fields')
    observation={'schema':'sl3.rate-diagnostic.v2','phase':'finished','utc':'2000-01-01T00:00:00Z',
        'target_rate_hz':w[2],'diagnostic_error':w[3],'transaction_error':w[4],'exchange_error':w[5],
        'initial_rate_hz':w[6],'verified_rate_hz':w[7],'readback_rate_hz':w[8],
        'write_attempts':w[9],'read_attempts':w[10],'setter_attempts':w[11],
        'control_transfer_attempts':w[9]+w[10],'device_may_have_changed':bool(w[12]&1),
        'acknowledgement_received':bool(w[12]&2),'last_io_retired':True,'redirect_closed':False,
        'audio_submissions':0,'alternate_changes':0,'automatic_rollback':False,'error':''}
    # These synthetic envelope fields validate wire consistency only. They never
    # become native retirement, timestamp or cleanup evidence.
    rate.observation_fields(observation,expected)
    envelope={'schema','phase','utc','last_io_retired','redirect_closed','audio_submissions','alternate_changes','automatic_rollback','error'}
    return {'observation':{k:v for k,v in observation.items() if k not in envelope},'nativeError':w[13]}


def journal(path,target):
    require(0<path.stat().st_size<=65536,'Empty/oversized rate journal')
    raw=path.read_bytes();require(raw.endswith(b'\n'),'Incomplete rate journal')
    rows=[]
    for line in raw.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9]+)\t([0-9]+)\t([a-z0-9_]+\.(?:enter|return))',line)
        require(match is not None,'Malformed rate journal')
        tick,pid=int(match[1]),int(match[2]);require(base.uint(tick) and 0<pid<2**32 and (not rows or tick>=rows[-1][0]),'Invalid journal clock/PID')
        rows.append((tick,pid,match[3]))
    require(len({r[1] for r in rows})==1,'Multiple rate workers')
    stages=[r[2] for r in rows];require(stages[:3]==['worker.enter','helper_load.enter','helper_load.return'],'Wrong rate journal prefix')
    at=3
    while stages[at:at+2]==['enumerate.enter','enumerate.return']:at+=2
    require(at>3,'Missing rate enumeration')
    expected=['configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return',
        'redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return',
        f'rate_target_{target}.enter','rate_selection.enter','rate_selection.return','redirect_close.enter','redirect_close.return',
        'helper_unload.enter','helper_unload.return']
    require(stages[at:]==expected,'Expected exactly one held acquire/rate transaction/release without audio')
    return {'sha256':digest(path),'workerPid':rows[0][1],'records':len(rows),'redirects':1,'redirectCloses':1,
        'individualRateTransfersJournalled':False}


def probe(folder,worker_sha,simulated=False):
    folder=Path(folder)
    require(type(simulated) is bool and type(worker_sha) is str and re.fullmatch('[0-9a-fA-F]{64}',worker_sha) is not None,'Invalid expected kind/hash')
    data,request=read(folder/'probe.json'),read(folder/'request.json')
    target=data['target_rate_hz'];require(type(target) is int and target in (44100,48000),'Unsupported rate target')
    expected=data['expected_initial_rate_hz'];require(expected is None or (type(expected) is int and expected in (44100,48000)),'Invalid initial rate guard')
    require(simulated or expected is not None,'Native rate probe requires a reviewed initial rate')
    for r in (request,data):
        require(r['schema']=='sl3.rate-host-probe.v1' and r['simulated'] is simulated and type(r['worker_sha256']) is str and
            r['worker_sha256'].lower()==worker_sha.lower(),'Wrong probe schema/kind/worker')
        require(type(r['target_rate_hz']) is int and r['target_rate_hz']==target and r['expected_initial_rate_hz']==expected and
            (r['expected_initial_rate_hz'] is None or type(r['expected_initial_rate_hz']) is int),'Request target/initial rate changed')
        for key,value in {'device_protocol_version':3,'audio_start_attempts':0,'alternate_changes_requested':0,'control_setters':0,'firmware_requests':0}.items():
            require(type(r[key]) is int and r[key]==value,'Unexpected rate probe count: '+key)
        base.flags(r,no=('audio_buffers_created','automatic_rollback','calibration_verified','analogue_signal_verified','asio_com_registered'))
    require(request['phase']=='preparing' and request['error']=='' and request['outcome_wire_hex'] is None,'Initial request already contains outcome')
    for key in ('acquisition_attempts','selection_attempts'):require(type(request[key]) is int and request[key]==0,'Initial request already attempted operation')
    base.flags(request,no=('successful','finished','acquisition_verified','publication_pending','command_attempted','outcome_unknown',
        'device_may_have_changed','rejected_before_operation','operation_verified'))
    for name in ('acquisition','after_selection','final'):
        require(type(request[name]) is dict and type(data[name]) is dict and request[name].keys()==data[name].keys(),'Initial owner shape differs')
        for key,value in request[name].items():
            if type(data[name][key]) is bool:require(type(value) is bool and value is (key in ('io_retired','device_released','audio_thread_retired')),'Initial request claims owner activity')
            else:require(type(value) is int and value==0,'Initial request claims owner observation')
    require(data['phase']=='finished' and data['error']=='','Unfinished or failed rate probe')
    base.flags(data,yes=('successful','finished','acquisition_verified','command_attempted','operation_verified'),
        no=('publication_pending','outcome_unknown','rejected_before_operation'))
    for key in ('acquisition_attempts','selection_attempts'):require(type(data[key]) is int and data[key]==1,'Expected exactly one acquisition/rate operation')
    outcome=decode_wire(data['outcome_wire_hex'],target);o=outcome['observation']
    require(o['diagnostic_error']==0 and data['device_may_have_changed'] is o['device_may_have_changed'],'Rate operation did not verify or effect flag differs')
    for name,released in (('acquisition',False),('after_selection',False),('final',True)):base.owner(data[name],released)
    require(data['acquisition']['rate_hz']==o['initial_rate_hz'] and (expected is None or expected==o['initial_rate_hz']),'Acquired/reviewed/transaction initial rates differ')
    require(data['after_selection']['rate_hz']==data['final']['rate_hz']==target and data['after_selection']['native_error']==outcome['nativeError'],'Selected/final rate or native status differs')
    journals=list(folder.glob('worker-*.tsv'));native=None
    if simulated:require(not journals and not list(folder.glob('worker-*.tsv.rate')),'Simulated probe contains native evidence')
    else:
        require(len(journals)==1 and journals[0].name=='worker-1.tsv','Expected one rate worker journal')
        native=journal(journals[0],target)
        record_path=folder/'worker-1.tsv.rate/rate.json';record=rate.observation_result(record_path,target)
        require(record['last_io_retired'] is True and record['redirect_closed'] is False,'Held native record must retire I/O without claiming final release')
        for key in o:require(record[key]==o[key] and type(record[key]) is type(o[key]),'Native/wire rate observation differs: '+key)
        native['observationSha256']=digest(record_path)
    return {'valid':True,'scope':'Recorded intent/rate result/owner consistency only; not a traced experiment, security/recovery, physical audio or ASIO/Serato pass',
        'simulated':simulated,'workerSha256':worker_sha.lower(),'targetRateHz':target,'outcome':outcome,
        'requestRecordSha256':digest(folder/'request.json'),'probeRecordSha256':digest(folder/'probe.json'),'nativeJournal':native,
        'rateRestorationVerified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--probe',type=Path,required=True)
    parser.add_argument('--worker-sha256',required=True);parser.add_argument('--expect-simulated',action='store_true');args=parser.parse_args()
    print(json.dumps(probe(args.probe,args.worker_sha256,args.expect_simulated),indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
