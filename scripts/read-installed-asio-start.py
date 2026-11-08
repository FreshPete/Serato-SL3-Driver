"""Read one or two completed application-bound starts without opening the driver."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import runpy


ROOT = Path(__file__).resolve().parent
identity = runpy.run_path(str(ROOT/'read-retained-start-result.py'))['identity']
FIELDS = ('controller','controller_sha256','input','input_sha256',
          'startup_timeout_ms','startup_failure_grace_ms','lifetime_ms')


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    require(path.is_file() and not path.is_symlink(),'Regular record required: '+path.name)
    with path.open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw)<=65536,'Oversize record: '+path.name)
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(raw):
    value = json.loads(raw)
    require(isinstance(value,dict),'Expected a JSON report object')
    return value


def configuration(path):
    raw = read(path)
    header, *rows = raw.decode('utf-8').splitlines()
    fields = [row.partition('=') for row in rows]
    require(header=='SL3-ASIO-ACTIVATION-2' and tuple(key for key,_,_ in fields)==FIELDS and
            all(separator and value for _,separator,value in fields),'Application-bound activation configuration required')
    values = [value for _,_,value in fields]
    require(all(re.fullmatch('[0-9a-f]{64}',values[index]) for index in (1,3)) and
            all(re.fullmatch('[0-9]{1,9}',value) for value in values[4:]),'Invalid activation identities or limits')
    return values,sha(raw)


def diagnostic_profile(path, activation, activation_sha):
    """Verify the diagnostic buffer through the activation/worker/timing hash chain."""
    worker = read(path.with_name('sl3-worker.conf'))
    timing = read(path.with_name('sl3-timing.conf'))
    match = re.fullmatch(rb'SL3-ASIO-DIAGNOSTIC-TIMING-([12])\nworker_sha256=([0-9a-f]{64})\n'
                         rb'helper_sha256=[0-9a-f]{64}\nrate_hz=44100\nbuffer_frames=(32|64|128)\n', timing)
    require(match, 'Recognized 44.1 kHz diagnostic timing record required')
    version, worker_sha, frames = match.groups()
    install = PureWindowsPath(activation[2]).parent
    require(install.is_absolute(), 'Absolute protected diagnostic destination required')
    builder = runpy.run_path(str(ROOT/'prepare-asio-deployment.py'))
    expected = builder['activation_records'](install, activation[1], worker_sha.decode('ascii'),
        builder['APPLICATION_ACTIVATION_MODE'], playback_keepalive=version==b'2', buffer_frames=int(frames))
    require(sha(expected['sl3-asio.conf'])==activation_sha and worker==expected['sl3-worker.conf'] and
            timing==expected['sl3-timing.conf'], 'Diagnostic configuration or timing hash chain differs')
    return {'configuredBufferFrames':int(frames),'rateHz':44100,'workerSha256':worker_sha.decode('ascii'),
            'timingSha256':sha(timing),'playbackKeepalive':version==b'2'}


def unpublished_result(folder, activation):
    intent_path, final_path = folder/'intent.json', folder/'result.json'
    if not intent_path.exists() or not final_path.exists():
        return {}
    intent = record(read(intent_path))
    require(intent.get('schema')=='sl3.broker-controller-intent.v1' and intent.get('applicationBound') is True and
            intent.get('brokerSha256')==activation[1] and intent.get('limitMs')==int(activation[-1]) and
            intent.get('kind') in ('native','simulated'),'Startup intent differs from selected configuration')
    raw = read(final_path)
    final = record(raw)
    require(final.get('schema')=='sl3.broker-controller-result.v1' and final.get('kind')==intent['kind'] and
            type(final.get('published')) is bool,'Expected a broker result for this startup intent')
    if final['published']:
        return {}  # The driver never committed the receipt that would bind published readiness.
    native_error = final.get('lastNativeError')
    require(type(native_error) is int and 0<=native_error<=0xffffffff,'Invalid startup error number')
    overlap_refused = (intent['kind']=='native' and final.get('acquireAttempted') is True and
        final.get('acquired') is False and final.get('snapshotValid') is True and final.get('failed') is True and
        type(final.get('lastDeviceFailure')) is int and final['lastDeviceFailure']==1 and
        native_error==170 and final.get('lastDiagnostic')=='Acquire exclusive SL3 redirect owner failed, Win32=170')
    return {'outcome':'redirect_owner_busy' if overlap_refused else 'broker_result_before_readiness',
            'brokerKind':intent['kind'],'lastNativeError':native_error,'resultSha256':sha(raw)}


def summarize(folder, activation, profile=None):
    match = re.fullmatch(r'application-([1-9][0-9]{0,9})-([1-9][0-9]{0,19})',folder.name)
    require(match and not folder.is_symlink() and not folder.is_junction(),'Expected an application-bound session path')
    pid,created = identity({'pid':int(match[1]),'creationFileTimeUtc':match[2]})
    result = {'hostPid':pid,'hostCreationFileTimeUtc':created,'outcome':'activation_receipt_incomplete'}
    prefix = ('\n'.join(['SL3-ASIO-APPLICATION-1',*activation])+'\n').encode('utf-8')
    claim = read(folder.with_name(folder.name+'.claim'))
    if len(claim)<len(prefix)+65 and claim[:len(prefix)]==prefix[:len(claim)]:
        return {**result,**unpublished_result(folder,activation)}
    require(claim.startswith(prefix) and len(claim)==len(prefix)+65,'Activation receipt differs from selected configuration')
    config = read(folder/'sl3-asio.conf')
    config_hash = sha(config)
    require(claim==prefix+config_hash.encode('ascii')+b'\n','Published configuration differs from activation receipt')
    ready = record(read(folder/'ready.json'))
    require(ready.get('schema')=='sl3.broker-controller-ready.v1' and ready.get('readyIsSnapshot') is True and
            ready.get('brokerSha256')==activation[1] and ready.get('configSha256')==config_hash and
            ready.get('limitMs')==int(activation[-1]) and ready.get('kind') in ('native','simulated'),
            'Readiness differs from activation receipt')
    if profile is not None:
        prefix, separator, _ = config.partition(b'\nbroker=')
        header = b'SL3-ASIO-BROKER-CONFIG-1\n'
        require(separator and prefix.startswith(header) and
                sha(b'SL3-ASIO-CONFIG-1\n'+prefix[len(header):]+b'\n')==activation[3],
                'Published worker configuration differs from the diagnostic profile')
        require(ready.get('workerSha256')==profile['workerSha256'] and ready.get('rateHz')==profile['rateHz'],
                'Readiness does not match the diagnostic worker and rate')
        result['diagnosticProfileMatchedReadiness'] = True
    final_path = folder/'result.json'
    if not final_path.exists():
        return dict(result,outcome='completed_result_missing',brokerKind=ready['kind'])
    raw = read(final_path)
    final = record(raw)
    require(final.get('schema')=='sl3.broker-controller-result.v1' and final.get('kind')==ready['kind'] and
            final.get('published') is True,'Expected a completed result for this activation')
    clients = final.get('clientObservations')
    require(isinstance(clients,list) and len(clients)<=16 and type(final.get('clientObservationsTruncated')) is bool,
            'Bounded client observations required')
    starts = 0
    for client in clients:
        key = identity(client,allow_unknown_creation=True)
        count = client.get('streamStartReplies')
        require(type(count) is int and 0<=count<=0xffffffff and
                (not count or (key==(pid,created) and client.get('admissionReplySent') is True)),
                'Stream start differs from the bound host or admission')
        starts += count
    native = final.get('nativeDeviceAcquired')
    require(type(native) is bool and (not native or ready['kind']=='native'),'Invalid native acquisition result')
    retirement = final.get('reason')=='application_exit' and all(final.get(name) is True for name in
        ('successful','applicationExitObserved','ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')) and all(
        final.get(name) is False for name in ('failed','lifetimeExpired','terminationRequested'))
    if profile is not None:
        result['brokerOwnerFailureCode'] = final.get('ownerFailureCode')
        result['workerStreamFault'] = final.get('lastStreamFault') if final.get('snapshotValid') is True else None
    return dict(result,outcome='stream_start_reported' if starts else 'no_stream_start_reported',brokerKind=ready['kind'],
                nativeAcquisitionReported=native,streamStartReplies=starts,applicationExitRetirementReported=retirement,
                observationsTruncated=final['clientObservationsTruncated'],resultSha256=sha(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activation',type=Path,required=True)
    parser.add_argument('--session',type=Path,action='append',required=True)
    parser.add_argument('--diagnostic-timing',action='store_true',
                        help='verify the sibling worker and timing records against activation and readiness')
    args = parser.parse_args()
    try:
        require(1<=len(args.session)<=2,'Supply one or two session paths')
        activation,digest = configuration(args.activation)
        profile = diagnostic_profile(args.activation,activation,digest) if args.diagnostic_timing else None
        rows = [summarize(folder.absolute(),activation,profile) for folder in args.session]
        require(len({(row['hostPid'],row['hostCreationFileTimeUtc']) for row in rows})==len(rows),'Expected distinct host processes')
    except (OSError,ValueError) as error:
        parser.error(str(error))
    report = {'schema':'sl3.installed-asio-start-readout.v1','activationSha256':digest,'sessions':rows,
              'hostImageVerified':False,'callbacksVerified':False}
    if profile is not None:
        report['diagnosticProfile'] = profile
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
