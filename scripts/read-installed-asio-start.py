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
RECOVERY = re.compile(r'input_empty_recovery_count([0-9]{1,20})_last_block_f([0-9]{1,20})_p([0-7])_frames([56])')
RECOVERY_CONTEXT = re.compile(r'input_empty_recovery_context_f([0-9]{1,20})_observed_([056](?:,[056]){7})'
                              r'_preceding_([0-9]{2}(?:,[0-9]{2}){8})')
INVALID_INPUT = re.compile(r'invalid_input_f([0-9]{1,20})_expected([0-9]{1,2})_received([0-9]{1,2})'
                           r'_p([0-9]{1,10})_len([0-9]{1,20})_status([0-9]{1,20})')
STREAM_FAILURE = re.compile(r'stream_failed_reason([0-9]{1,10})_fault([0-9]{1,10})_native([0-9]{1,10})'
                            r'_input([0-9]{1,20})')
OUTPUT_DEADLINE = re.compile(r'output_deadline_f([0-9]{1,20})_age_ns([0-9]{1,20})_gap_ns([0-9]{1,20})'
                             r'_expected([0-9]{1,2})_usb_mask([0-9]{1,2})_queued(-1|[0-8])')


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


def worker_journal(path, worker_pid):
    if not path.exists() and not path.is_symlink():
        return {'outcome':'absent'}
    try:
        require(type(worker_pid) is int and 0 < worker_pid <= 0xffffffff, 'Readiness worker PID required')
        raw = read(path)
        require(raw.endswith(b'\n'), 'Worker journal has no complete final row')
        recoveries, invalid_inputs, failures, deadlines = [], [], [], []
        keepalive = []
        keepalive_start = None
        previous_stage = ''
        previous_tick = 0
        for line in raw.decode('ascii').splitlines():
            row = re.fullmatch(r'([0-9]{1,20})\t([0-9]{1,10})\t([a-zA-Z0-9_.,-]+)', line)
            require(row and int(row[2]) == worker_pid and int(row[1]) >= previous_tick,
                    'Worker journal PID, timestamp or row format differs')
            previous_tick, stage = int(row[1]), row[3]
            if stage == 'playback_keepalive.enter':
                require(keepalive_start is None, 'Overlapping playback keepalive markers')
                keepalive_start = previous_tick
            elif stage in ('playback_keepalive.return', 'playback_keepalive.failed'):
                require(keepalive_start is not None, 'Playback keepalive ended without a start marker')
                keepalive.append({'startTickMs':keepalive_start, 'endTickMs':previous_tick,
                                  'elapsedMs':previous_tick-keepalive_start,
                                  'outcome':'failed' if stage.endswith('.failed') else 'returned'})
                keepalive_start = None
            elif stage.startswith('input_empty_recovery_count'):
                match = RECOVERY.fullmatch(stage)
                require(match and int(match[1]) > 0, 'Invalid empty input recovery marker')
                count, frame, index, estimate = map(int, match.groups())
                recoveries.append({'count':count,'lastBlockFirstFrame':frame,'packetIndex':index,
                                   'estimatedFrames':estimate,'context':None})
            elif stage.startswith('input_empty_recovery_context'):
                match = RECOVERY_CONTEXT.fullmatch(stage)
                require(match and RECOVERY.fullmatch(previous_stage), 'Recovery context lacks a paired marker')
                recovery = recoveries[-1]
                observed = list(map(int, match[2].split(',')))
                preceding = list(map(int, match[3].split(',')))
                require(int(match[1]) == recovery['lastBlockFirstFrame'] and observed.count(0) == 1 and
                        observed[recovery['packetIndex']] == 0 and all(40 <= value <= 48 for value in preceding) and
                        sum(observed) + sum(preceding) + recovery['estimatedFrames'] == 441,
                        'Recovery context differs from the estimate or packet position')
                recovery['context'] = {'observedPacketFrames':observed,'precedingBatchFrames':preceding}
            elif stage.startswith('invalid_input_'):
                match = INVALID_INPUT.fullmatch(stage)
                require(match, 'Invalid input fault marker')
                frame, expected, received, index, length, status = map(int, match.groups())
                invalid_inputs.append({'blockFirstFrame':frame,'expectedPackets':expected,'receivedPackets':received,
                                       'packetIndex':index,'lengthBytes':length,'status':status,
                                       'successfulEmptyPacket':expected == received and index < received and
                                       length == 0 and status == 0})
            elif stage.startswith('stream_failed_'):
                match = STREAM_FAILURE.fullmatch(stage)
                require(match, 'Invalid stream failure marker')
                reason, fault, error, blocks = map(int, match.groups())
                failures.append({'reasonCode':reason,'streamFaultCode':fault,'nativeError':error,'inputBlocks':blocks})
            elif stage.startswith('output_deadline_'):
                match = OUTPUT_DEADLINE.fullmatch(stage)
                require(match, 'Invalid output deadline marker')
                frame, age, gap, expected, mask, queued = map(int, match.groups())
                require(age >= max(1_000_000, gap) and 1 <= expected <= 16 and 0 <= mask <= 15,
                        'Output deadline context is out of range')
                deadlines.append({'blockFirstFrame':frame,'ageNs':age,'workerStepGapNs':gap,'expectedBlocks':expected,
                                  'pendingUsbOutputMask':mask,'queuedOutputBlocks':None if queued == -1 else queued})
            previous_stage = stage
        if keepalive_start is not None:
            keepalive.append({'startTickMs':keepalive_start, 'endTickMs':None, 'elapsedMs':None,
                              'outcome':'end_unobserved'})
    except (OSError, ValueError) as error:
        return {'outcome':'unavailable','error':str(error)[:256]}
    return {'outcome':'parsed','workerPid':worker_pid,'sha256':sha(raw),
            'emptyInputRecoveries':recoveries,'invalidInputs':invalid_inputs,'streamFailures':failures,
            'outputDeadlines':deadlines,'playbackKeepaliveWindows':keepalive}


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
    application_lifetime = activation[-1] == '0'
    expected = builder['activation_records'](install, activation[1], worker_sha.decode('ascii'),
        builder['APPLICATION_ACTIVATION_MODE'], playback_keepalive=version==b'2', buffer_frames=int(frames),
        application_lifetime=application_lifetime)
    require(sha(expected['sl3-asio.conf'])==activation_sha and worker==expected['sl3-worker.conf'] and
            timing==expected['sl3-timing.conf'], 'Diagnostic configuration or timing hash chain differs')
    return {'configuredBufferFrames':int(frames),'rateHz':44100,'workerSha256':worker_sha.decode('ascii'),
            'timingSha256':sha(timing),'playbackKeepalive':version==b'2','applicationLifetime':application_lifetime}


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
    result['readinessVerified'] = True
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
        if ready['kind']=='native':
            result['workerJournal'] = worker_journal(folder/'worker-startup.tsv', ready.get('workerPid'))
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
