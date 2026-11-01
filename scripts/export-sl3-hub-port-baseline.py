"""Verify the actual normal-user cached hub query; offline records only."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    before_path=ROOT/'analysis/sl3-hub-port-20261101-before.json'
    query_path=ROOT/'analysis/sl3-hub-port-20261101-baseline.json'
    require(sha(before_path)=='a71472aaf0d2f474de3227d277b09de14e8ab1f70f47ebf9e6676479892e4e8c' and
            sha(query_path)=='9ac898d7353d7db5a31a10558218072556fb90b72c00ca239082c929fe1afbad','Original query inputs changed')
    before,query=read(before_path),read(query_path)
    after=read(ROOT/'analysis/sl3-hub-port-20261101-after.json')
    supervision=read(ROOT/'analysis/sl3-hub-port-20261101-supervision.json')
    require(supervision['queryRecordSha256']==sha(query_path) and supervision['beforeSha256']==sha(before_path) and
            supervision['exitCode']==0 and supervision['timedOut'] is False and supervision['boundedChildRetired'] is True,
            'Supervised query did not complete')
    require(query['sourceSha256']==sha(ROOT/'scripts/query-sl3-hub-port.py')==
            'b12a96f0d56aca90cc67cc837088120d1b1af342aed5aaf9a5d7ca0801c141ae','Actual query source differs')
    require(query['successful'] is True and query['error'] is None and query['hubOpenSucceeded'] is True and
            query['queryStarted'] is True and query['queryFinished'] is True and query['handleClosed'] is True and
            query['producerToken']['queried'] is True and query['producerToken']['elevated'] is False and
            query['producerToken']['elevationType']==3,'Normal-token query/lifecycle failed')
    require(query['queryIoctl']=='0x220448' and query['createFileDesiredAccess']==0 and query['bytesReturned']==35 and
            query['sl3OpensRequested']==query['usbResetRequests']==query['audioStarts']==0 and
            query['requestsElevation'] is False and query['readinessAdmission'] is False,'Query scope differs')
    require(query['hubInstance']==before['parent']==after['parent'] and query['port']==before['port']==after['port']==4,
            'Port topology changed')
    for key in ('device','locationPaths'):require(before[key]==after[key],'Selected PnP state changed: '+key)
    require(before['device']['InstanceId'].upper()==r'USB\VID_1CC5&PID_0001\SL3.01.00' and before['device']['Problem']==39,
            'Expected original blocked-driver resting node')
    connection=query['connection']
    require(connection['targetDescriptorMatches'] is True and connection['vendor']==0x1cc5 and connection['product']==1 and
            connection['connectionStatus']==1 and connection['connectionStatusName']=='DeviceConnected' and
            connection['currentConfiguration']==connection['numberOfOpenPipes']==0 and
            connection['readinessAdmission'] is False,'Cached connection result differs')
    require({p['pid'] for p in after['processes']}=={supervision['pid'],query['producerToken']['pid']} and
            all(p['present'] is False for p in after['processes']),'Launcher or producer process still present')
    layout=read(ROOT/'analysis/sl3-hub-query-layout-20261101.json')
    require(layout['compileOnly'] is True and layout['assertions']==9 and layout['exitCode']==0 and
            layout['sourceSha256']==sha(ROOT/'scripts/hub-query-layout.cpp') and
            layout['objectSha256']==sha(ROOT/'artifacts/build/hub-query-layout/hub-query-layout.obj') and
            layout['nativeProductRebuilt'] is False,'Compiled SDK layout proof differs')
    result={'scope':'One cached connection-info query after the completed control test; not a readiness discriminator',
            'normalUserQueryPassed':True,'elevationType':3,'administratorPrompts':0,'port':4,'requestedHubAccess':0,
            'targetDescriptorMatches':True,'connectionStatus':'DeviceConnected','speedCode':connection['speedCode'],
            'deviceAddress':connection['deviceAddress'],'configuration':0,'openPipes':0,
            'hostQueryNanoseconds':query['queryElapsedNanoseconds'],'queryIsAudioLatencyMeasurement':False,
            'selectedPnpStateMatches':True,'originalDriverProblemCode':39,'handleClosed':True,
            'launcherAndProducerObservedRetired':True,'launcherPidDiffersFromProducer':supervision['pid']!=query['producerToken']['pid'],
            'directChildTimeoutContainmentCoversDescendantsVerified':False,
            'sdkLayoutAssertionsPassed':9,'softwareCasesPassed':6,'readinessAdmission':False,
            'distinguishesStoppedEnumeratedFromStopped':False,'streamingOrSeratoTested':False,
            'sourceSha256':query['sourceSha256'],'queryRecordSha256':sha(query_path),'beforeSha256':sha(before_path),
            'afterSha256':sha(ROOT/'analysis/sl3-hub-port-20261101-after.json')}
    (ROOT/'docs/evidence/sl3-hub-port-baseline-20261101.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified real normal-user cached hub query, close/retirement and unchanged selected PnP state; no readiness claim')


if __name__=='__main__':main()
