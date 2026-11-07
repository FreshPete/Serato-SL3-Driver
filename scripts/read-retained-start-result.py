"""Join reviewed module and broker reports from one completed retained trial."""
import argparse
import hashlib
import json
from pathlib import Path
import re


CLEAN = {'archive':'original','seratoRunning':False,'native':{'state':'absent'}}


def require(value, message):
    if not value:
        raise ValueError(message)


def read_pinned(path, expected):
    require(path.is_file(),'Regular report file required: '+path.name)
    with path.open('rb') as stream:
        raw = stream.read(65537)
    require(0<len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==expected,
            'Reviewed bounded report required: '+path.name)
    record = json.loads(raw)
    require(isinstance(record,dict),'JSON report object required')
    return record


def identity(row, allow_unknown_creation=False):
    require(isinstance(row,dict),'Process identity object required')
    pid, created = row.get('pid'),row.get('creationFileTimeUtc')
    require(type(pid) is int and 0<pid<=0xffffffff and isinstance(created,str) and
            re.fullmatch(r'0|[1-9][0-9]{0,19}',created) and int(created)<2**64 and
            (allow_unknown_creation or created!='0'),'Bounded PID and decimal creation FILETIME required')
    return pid,created


def summarize(observer, broker, restore=None):
    require(observer.get('schema')=='sl3.asio-module-observation.v1' and
            observer.get('asioCallsObserved') is False and observer.get('moduleAbsenceProved') is False,
            'Expected the passive module observation')
    for name in ('applicationSha256','moduleFileSha256'):
        require(isinstance(observer.get(name),str) and re.fullmatch('[0-9a-f]{64}',observer[name]),
                'Observed file hash required')
    process = observer.get('process')
    selected = identity(process) if process is not None else None
    if process is not None:
        require(process.get('elevated') is False and process.get('tokenQueried') is True and
                isinstance(process.get('imagePath'),str) and process['imagePath'],
                'Expected the ordinary observed process')
    module = observer.get('modulePathObserved')
    require(module is None or (isinstance(module,str) and module and selected is not None and
                               type(observer.get('completedModuleSamples')) is int and observer['completedModuleSamples']>0),
            'Module observation lacks a matching sampled process')
    follow_up = observer.get('followUpModuleSamples')
    disappeared = observer.get('moduleDisappearanceSampled')
    if 'followUpModuleSamples' in observer or 'moduleDisappearanceSampled' in observer:
        total = observer.get('completedModuleSamples')
        require(type(total) is int and type(follow_up) is int and 0<=follow_up<=total and
                type(disappeared) is bool and (not follow_up or (module and follow_up<total)) and
                (not disappeared or follow_up>0),'Inconsistent module follow-up observation')

    require(broker.get('schema')=='sl3.broker-controller-result.v1' and broker.get('kind') in ('native','simulated'),
            'Expected the completed broker result')
    rows = broker.get('clientObservations')
    require(isinstance(rows,list) and len(rows)<=16 and type(broker.get('clientObservationsTruncated')) is bool and
            type(broker.get('published')) is bool and (not rows or broker['published']) and
            (not broker['clientObservationsTruncated'] or len(rows)==16),'Bounded broker observation inventory required')
    acquired = broker.get('nativeDeviceAcquired')
    require(type(acquired) is bool and (not acquired or broker['kind']=='native'),'Broker acquisition kind differs')
    matched = []
    for row in rows:
        key = identity(row,allow_unknown_creation=True)
        admitted, starts, detached = row.get('admissionReplySent'),row.get('streamStartReplies'),row.get('detachAcknowledged')
        require(type(admitted) is bool and type(detached) is bool and type(starts) is int and 0<=starts<=0xffffffff and
                (admitted or (starts==0 and not detached)),'Inconsistent broker observation')
        if key==selected:
            matched.append(row)

    retirement_flags = ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')
    require(all(type(broker.get(name)) is bool for name in ('failed','terminationRequested',*retirement_flags)),
            'Typed worker retirement observations required')
    restored = None
    if restore is not None:
        require(restore.get('schema')=='sl3.on-demand-test-action.v1' and restore.get('action')=='restore' and
                type(restore.get('successful')) is bool,'Expected the restore action receipt')
        restored = restore['successful'] and restore.get('after')==CLEAN
    return {'schema':'sl3.retained-start-readout.v1','brokerKind':broker['kind'],'nativeAcquisitionReported':acquired,
            'applicationFileSha256':observer['applicationSha256'],'moduleFileSha256':observer['moduleFileSha256'],
            'ordinaryProcessObserved':selected is not None,'moduleLoadObserved':bool(module),
            'followUpModuleSamples':follow_up,'moduleDisappearanceSampled':disappeared,
            'matchingChallengedConnections':len(matched),
            'matchingAdmissionReplies':sum(row['admissionReplySent'] for row in matched),
            'matchingStreamStartReplies':sum(row['streamStartReplies'] for row in matched),
            'matchingDetachAcknowledgements':sum(row['detachAcknowledged'] for row in matched),
            'brokerObservationsTruncated':broker['clientObservationsTruncated'],
            'workerRetirementReported':all(broker[name] for name in retirement_flags),
            'brokerFailureReported':broker['failed'],'terminationRequested':broker['terminationRequested'],
            'originalSetupReportedByRestore':restored,'applicationCallbacksVerified':False,
            'audibleOutputVerified':False,'dvsVerified':False,'absenceProved':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-report',type=Path,required=True)
    parser.add_argument('--module-report-sha256',required=True)
    parser.add_argument('--broker-report',type=Path,required=True)
    parser.add_argument('--broker-report-sha256',required=True)
    parser.add_argument('--restore-report',type=Path)
    parser.add_argument('--restore-report-sha256')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    require(bool(args.restore_report)==bool(args.restore_report_sha256),'Restore report and hash must be supplied together')
    observer = read_pinned(args.module_report,args.module_report_sha256)
    broker = read_pinned(args.broker_report,args.broker_report_sha256)
    restore = read_pinned(args.restore_report,args.restore_report_sha256) if args.restore_report else None
    result = summarize(observer,broker,restore)
    result['inputReportSha256'] = {'module':args.module_report_sha256,'broker':args.broker_report_sha256,
                                   'restore':args.restore_report_sha256}
    rendered = json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(rendered)
    print(rendered,end='')


if __name__ == '__main__':
    main()
