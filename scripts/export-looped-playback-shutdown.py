"""Compare the pinned looped-playback shutdown records without opening Serato."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path


SOURCES = {
    'host': '785677607f6dfb79264b86adf445e0f0334bbf98e784a5078e4f34b7b1b1a6e5',
    'broker': '97f834bb0db49184b2c9aa19b0442be798ed1b1d3bc07dec797d31e7a268642d',
    'interaction': 'f09f35e28ab53c16aaa88a8ab06b4c32763f00b7ed31bb8eb505251c85f89ce2',
    'controller-journal': '5106ccac00f49aec22697550d498955085b3552d0c2e2d50c2bb0b7a2296b366',
    'worker-journal': '9d96505cf3318a27320ecfe78c9407ca81221372b8fe73b29cfd4055f08dbbcb',
}
FILETIME_EPOCH = datetime(1601,1,1,tzinfo=timezone.utc)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned(path, label):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==SOURCES[label],label+' hash differs')
    return raw


def filetime(stamp):
    delta = datetime.fromisoformat(stamp)-FILETIME_EPOCH
    return ((delta.days*86400+delta.seconds)*1000000+delta.microseconds)*10


def journal(raw, labels):
    rows = [line.split('\t') for line in raw.decode('utf-8').splitlines()]
    selected = [(int(tick),label) for tick,_,label in rows if label in labels]
    require(tuple(label for _,label in selected)==labels and selected==sorted(selected,key=lambda item:item[0]),
            'Journal boundary or ordering differs')
    return {label:tick for tick,label in selected}


def inspect(inputs):
    host = json.loads(inputs['host'],parse_float=Decimal)
    broker = json.loads(inputs['broker'])
    interaction = json.loads(inputs['interaction'])
    process = host['process']
    require(host['schema']=='sl3.startup-supervisor-result.v1' and host['asioStartObserved'] is True and
            host['tracerDetached'] is True and host['endReason']=='viewing_limit' and
            process['closeRequested'] is True and process['observerForcedTermination'] is True and
            process['processExited'] is True and process['exitCode']==1,'Expected the forced-exit session')
    detached, = (event['hostMonotonicSeconds'] for event in host['events'] if event['event']=='diagnostic_tracer_detached')
    ended, = (event['hostMonotonicSeconds'] for event in host['events'] if event['event']=='viewing_window_ended')
    require(ended>detached,'Viewing interval differs')
    require(interaction['schema']=='sl3.owner-close-interaction.v1','Expected the timing-only interaction receipt')
    sent = interaction['closeInstructionSentUtc']['utc']
    received = interaction['closeConfirmationReceivedUtc']['utc']
    created, exited = (int(process['processFileTimes'][key]) for key in ('first','last'))
    require(created<filetime(sent)<exited<filetime(received),'Application and interaction times differ')

    require(broker['schema']=='sl3.broker-controller-result.v1' and broker['reason']=='owner_failure' and
            broker['ownerFailureCode']=='client_control_abandoned' and broker['ownerFailurePhase']==3 and
            broker['connectionDiagnostic']=='Complete broker pipe operation: 109','Expected the running client failure')
    retirement = ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty','controllerExited')
    require(all(broker[key] is True for key in retirement),'Broker retirement is incomplete')
    controller = journal(inputs['controller-journal'],('owner_close_begin','owner_close_returned'))
    worker = journal(inputs['worker-journal'],('redirect_close.enter','redirect_close.return','helper_unload.return'))
    require(controller['owner_close_begin']<=worker['redirect_close.enter']<=
            worker['helper_unload.return']<=controller['owner_close_returned'],'Worker cleanup lies outside controller shutdown')
    return {'schema':'sl3.looped-playback-shutdown-timeline.v1','sourcesSha256':SOURCES,
            'viewingSecondsFromHostClock':str(ended-detached),
            'closeInstructionSentUtc':sent,'applicationExitFileTimeUtc':str(exited),
            'closeConfirmationReceivedUtc':received,
            'instructionToForcedExit100ns':exited-filetime(sent),
            'forcedExitToConfirmation100ns':filetime(received)-exited,
            'brokerFailure':'client_control_abandoned','brokerFailurePhase':'running',
            'brokerRetirementVerified':True,'workerReleaseWithinControllerClose':True,
            'nativeStreamFaultInFinalReport':broker['lastStreamFault'],
            'actualManualWindowCloseTimeKnown':False,'asioShutdownCallsObserved':False,'rootCauseEstablished':False}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for label in SOURCES:
        parser.add_argument('--'+label,type=Path,required=True)
    args = vars(parser.parse_args())
    try:
        report = inspect({label:pinned(args[label.replace('-','_')],label) for label in SOURCES})
    except (OSError,ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report,indent=2))
