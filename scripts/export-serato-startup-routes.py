"""Compare three pinned Serato startup captures without opening Serato or the SL3."""

import argparse
import hashlib
import json
from pathlib import Path


SOURCES = {
    'workspace': 'ee5c0821d96165cc0aee15fb94424338bfb0f00b22c9546c9f5990013fe54cea',
    'two-deck': 'f814c4bb7f124711cd2680a55cbcaededb3cdf9190d77c31a211443eb3c06f6e',
    'selection': '0c19d62c462de4ec1bcad020e6f10be23647805b4729aa1bb32f62e40a90891b',
}
OBSERVERS = {
    'workspace': 'b9683b15c868a9550e6af4659caa8d5cf131d88247575ee3fa28c57a6d258e9a',
    'two-deck': 'd75ec449c83a5b48bcf8fc58da5876d3f7cef7538933145f7b49203aa3fbdb22',
    'selection': 'f987a68dc67fcd30bf9d581f4af802b59b9b8a83ea3d124c0a1b79b14a290ad9',
}
MANAGER_POINTS = ('usb_manager_initializer', 'usb_manager_constructor')
ARRIVAL = {'high': 0x1cc5, 'middle': 1, 'low': 0}
SL3 = {'vid': 0x1cc5, 'pid': 1, 'rev': 0}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(label, path):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SOURCES[label], f'{label} trace hash differs')
    observer = path.with_name('observe-selection.js').read_bytes()
    require(hashlib.sha256(observer).hexdigest() == OBSERVERS[label], f'{label} observer hash differs')
    trace = json.loads(raw)
    events = trace['events']
    require(not trace['errors'] and events[0]['event'] == 'trace_ready', f'{label} trace is incomplete')
    required = {*MANAGER_POINTS, 'usb_handler', 'scalar_message', 'primary_message',
                'primary_integer_message_created', 'engine_primary_message_state', 'default_audio', 'named_audio'}
    require(required.issubset(events[0]['points']), f'{label} probe declarations differ')
    return events


def find(events, start, name, **fields):
    for index in range(start + 1, len(events)):
        event = events[index]
        if event['event'] == name and all(event.get(key) == value for key, value in fields.items()):
            return index
    raise ValueError(f'Missing ordered event: {name}')


def summarize(events, label):
    zero = find(events, 0, 'primary_integer_message_created', value=0, caller='0x154ae69')
    default = find(events, zero, 'default_audio')
    received = find(events, default, 'engine_primary_message_state', integerValue=0,
                    priorState=False, constantFalseGetter=False)
    engine = find(events, received, 'engine_message', id=0x2ca)
    arrival = find(events, engine, 'arrival_message', **ARRIVAL)
    result = {
        'traceSha256': SOURCES[label],
        'savedObserverSha256': OBSERVERS[label],
        'eventCount': len(events),
        'initialEventIndices': {'integerZeroCreated': zero, 'defaultAudio': default,
                                'engineReceivedIntegerZero': received, 'sl3ArrivalConstructed': arrival},
        'managerLifecycleEvents': {name: sum(event['event'] == name for event in events)
                                   for name in MANAGER_POINTS},
        'usbHandlerDeliveryCoverage': 'unconfirmed_wrong_argument_in_saved_probe',
    }
    if label == 'workspace':
        absent = ('installer_complete', 'primary_message', 'primary_set', 'named_audio', 'rebuilt_asio_loaded')
        require(not any(event['event'] in absent for event in events), 'Workspace trace includes a selection event')
        result['selectionOrNamedAudioObserved'] = False
        return result

    require('rebuilt_asio_loaded' in events[0]['points'], 'Rebuilt module probe was not declared')
    click = find(events, arrival, 'message_create', id=0x4ff, caller='0x13801ba')
    supplied = find(events, click, 'diagnostic_panel_identity_supplied', **SL3)
    action = find(events, supplied, 'installer_action', **SL3)
    complete = find(events, action, 'installer_complete', installerResult=0)
    pointer = find(events, complete, 'primary_message', caller='0x5b0c4d', descriptorPresent=True)
    setter = find(events, pointer, 'primary_set', inSl3Arrival=False)
    one = find(events, setter, 'primary_integer_message_created', value=1, caller='0x4b4dc5')
    state = find(events, one, 'engine_primary_message_state', integerValue=1,
                 priorState=False, constantFalseGetter=False)
    engine = find(events, state, 'engine_message', id=0x2ca)
    named = find(events, engine, 'named_audio', rebuiltName=True, asioApi=True, legacy=True)
    loaded = find(events, named, 'rebuilt_asio_loaded')
    initialized = find(events, loaded, 'asio_live_init_end', result=1)
    connected = find(events, initialized, 'named_audio_result', rebuiltName=True, connectionReturned=True)
    buffer192 = find(events, connected, 'asio_live_create_buffers_begin', frames=192)
    instance = {'object': events[buffer192]['object'], 'thread': events[buffer192]['thread']}
    declined = find(events, buffer192, 'asio_live_create_buffers_end', result=-997, **instance)
    buffer128 = find(events, declined, 'asio_live_create_buffers_begin', frames=128, **instance)
    accepted = find(events, buffer128, 'asio_live_create_buffers_end', result=0, **instance)
    begin = find(events, accepted, 'asio_live_start_begin', **instance)
    started = find(events, begin, 'asio_live_start_end', result=0, **instance)
    timeline = {'installerComplete': complete, 'installerPrimaryPointerRequest': pointer,
                'primarySetterEntered': setter, 'integerOneCreated': one, 'engineReceivedIntegerOne': state,
                'rebuiltAsioRequested': named, 'rebuiltAsioModuleLoaded': loaded, 'firstInitSucceeded': initialized,
                'namedConnectionReturned': connected, 'buffer192Rejected': declined,
                'buffer128Accepted': accepted, 'asioStartSucceeded': started}
    if label == 'two-deck':
        timeline['tracerDetached'] = find(events, started, 'diagnostic_tracer_detached')
    else:
        selected = find(events, started, 'primary_manager_after_message', selected=True, sl3=True)
        timeline['selectedSl3Confirmed'] = selected
        timeline['laterSl3ArrivalConstructed'] = find(events, selected, 'arrival_message', **ARRIVAL)

    origin = events[complete]['timeMs']
    offsets = [events[index]['timeMs'] - origin for index in timeline.values()]
    require(offsets == sorted(offsets), 'Trace clock reverses within the checked timeline')
    result['installerClickEventIndex'] = click
    result['timeline'] = {name: {'eventIndex': index, 'msAfterInstallerComplete': offset}
                          for (name, index), offset in zip(timeline.items(), offsets)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in SOURCES:
        parser.add_argument('--' + label, type=Path, required=True)
    args = vars(parser.parse_args())
    try:
        report = {label: summarize(load(label, args[label.replace('-', '_')]), label) for label in SOURCES}
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({'schema': 'sl3.serato-startup-routes.v1', 'seratoVersion': '5.0.0.1278',
                      'captures': report}, indent=2))


if __name__ == '__main__':
    main()
