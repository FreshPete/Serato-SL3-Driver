import argparse
import json
from pathlib import Path


INSTALLER_TIMELINE_FIELDS = {
    'web_notice_message_created': ('caller',),
    'driver_notice_route': ('caller', 'skipsWebBlock'),
    'driver_web_action_prepared': (),
    'device_installer_message': ('id', 'caller'),
    'installer_click_message': ('id', 'caller'),
    'installer_helper_message': ('id', 'caller'),
    'installer_panel_initial_identity': ('vid', 'pid', 'rev'),
    'installer_panel_identity': ('id', 'vid', 'pid', 'rev'),
    'installer_action': ('vid', 'pid', 'rev', 'installerBusy'),
    'installer_descriptor_lookup': ('found',),
    'installer_profile': ('connectAfterInstall',),
    'installer_filename': ('filename',),
    'installer_resolved_filename': ('filename',),
    'installer_path_input': ('check', 'path'),
    'installer_path_check': ('found',),
    'installer_fallback_path_check': ('found',),
    'installer_bundle_input': ('path',),
    'installer_size': ('size',),
    'resource_reader_input': ('relative', 'root'),
    'resource_reader_disk_path': ('path',),
    'installer_extract_result': ('success',),
    'installer_launch_result': ('success',),
    'installer_wait': (),
    'installer_complete': ('installerResult',),
    'installer_driver_detected': ('descriptorPresent', 'caller'),
    'installer_primary_message': ('descriptorPresent', 'caller'),
    'primary_manager_after_message': ('selected', 'sl3'),
    'engine_primary_message_state': ('priorState', 'constantFalseGetter', 'integerValue'),
    'primary_integer_message_created': ('value', 'caller'),
    'rebuilt_named_audio': ('asioApi', 'legacy'),
    'rebuilt_named_audio_result': ('connectionReturned',),
    'rebuilt_asio_loaded': (),
}


def event_name(event):
    name = event['event']
    if name == 'driver_web_dispatch':
        return 'driver_web_action_prepared'
    if name == 'message_create' and event.get('id') == 0x4ff:
        return {
            '0x13801ba': 'installer_click_message',
            '0x154b5b5': 'installer_helper_message',
        }.get(event.get('caller'), name)
    if name == 'primary_message' and event.get('caller') == '0x5b0c4d':
        return 'installer_primary_message'
    if name in ('named_audio', 'named_audio_result') and event.get('rebuiltName') is True:
        return 'rebuilt_' + name
    return name


def summarize_arrival_dispatch(events, armed, errors):
    phases = [event for event in events if event['event'] == 'sl3_arrival_phase']
    if not phases and 'sl3_arrival_phase' not in armed:
        return None
    # The private observer emits at most 24 phase events and tracks 16 live objects.
    limited = len(phases) >= 24 or any(event['event'] == 'sl3_arrival_tracking_limit' for event in events)
    clean = 'sl3_arrival_phase' in armed and not limited and not errors
    arrivals = {}
    for index, event in enumerate(events):
        if event['event'] != 'sl3_arrival_phase':
            continue
        sequence = event.get('sequence')
        phase = event.get('phase')
        if type(sequence) is not int or sequence < 1:
            raise ValueError('Invalid SL3 arrival sequence')
        arrival = arrivals.setdefault(sequence, {'sequence': sequence, 'timeline': []})
        timeline = arrival['timeline']
        previous = timeline[-1]['phase'] if timeline else None
        allowed = {
            None: ('constructed',),
            'constructed': ('publish_policy', 'enqueued'),
            'publish_policy': ('enqueued',) if arrival.get('policyDecision') == 'queue_original' else (),
            'enqueued': ('listener_lookup',),
            'listener_lookup': ('usb_handler_entry', 'dispatch_finished'),
            'usb_handler_entry': ('usb_handler_entry', 'dispatch_finished'),
            'dispatch_finished': (),
        }
        if phase not in allowed[previous]:
            raise ValueError('Invalid SL3 arrival phase order')
        if phase == 'publish_policy':
            decision = event.get('decision')
            if 'sl3_arrival_publish_policy' not in armed or decision not in ('queue_original', 'replace', 'discard'):
                raise ValueError('Invalid or unarmed SL3 arrival policy observation')
            arrival['policyDecision'] = decision
        if phase == 'listener_lookup':
            count = event.get('listenerCount')
            if type(count) is not int or not 0 <= count <= 0xffffffff:
                raise ValueError('Invalid SL3 listener count')
            arrival['listenerCount'] = count
        if phase == 'usb_handler_entry' and not arrival['listenerCount']:
            raise ValueError('SL3 handler sampled with an empty listener vector')
        timeline.append({'index': index, 'phase': phase})
    for arrival in arrivals.values():
        observed = {row['phase'] for row in arrival['timeline']}
        if 'usb_handler_entry' in observed:
            boundary = 'usb_handler_observed'
        elif arrival.get('policyDecision') in ('replace', 'discard'):
            boundary = 'policy_' + arrival['policyDecision']
        elif arrival.get('listenerCount') == 0:
            boundary = 'empty_listener_vector_observed'
        elif clean and 'dispatch_finished' in observed:
            boundary = 'dispatch_finished_without_usb_handler_sample'
        else:
            boundary = 'inconclusive_after_' + arrival['timeline'][-1]['phase']
        arrival['boundary'] = boundary
    return {'phaseProbeArmed': 'sl3_arrival_phase' in armed,
            'policyProbeArmed': 'sl3_arrival_publish_policy' in armed,
            'trackingMayBeIncomplete': not clean, 'arrivals': list(arrivals.values())}


def summarize(trace, call_analysis=None):
    events = trace['events']
    aliases = {'driver_web_dispatch': 'driver_web_action_prepared'}
    armed = [aliases.get(point, point) for point in
             next((event['points'] for event in events if event['event'] == 'trace_ready'), [])]
    evidence = {}
    for name in (
        'driver_notice_route', 'driver_web_action_prepared', 'installer_click_message', 'installer_action',
        'installer_descriptor_lookup', 'installer_filename', 'installer_resolved_filename',
        'installer_path_check', 'installer_fallback_path_check', 'installer_bundle_input',
        'resource_reader_input', 'resource_reader_disk_path',
        'installer_size', 'installer_extract_result', 'installer_launch_result',
        'installer_wait', 'installer_complete', 'installer_driver_detected', 'sl3_registry_detection',
        'primary_message', 'installer_primary_message', 'named_audio', 'named_audio_result',
        'rebuilt_named_audio', 'rebuilt_named_audio_result', 'rebuilt_asio_loaded',
    ):
        evidence[name] = [event for event in events
                          if event_name(event) == name or event['event'] == name]
    summary = {
        'pid': trace['pid'],
        'traceErrors': trace['errors'],
        'armedProbes': armed,
        'eventCounts': {name: len(records) for name, records in evidence.items()},
        'probeCoverage': {
            name: ('observed' if evidence[name] else
                   'armed_no_event' if point in armed and not trace['errors'] else
                   'unconfirmed')
            for name, point in (
                ('installer_click_message', 'message_create'),
                ('installer_action', 'installer_action'),
                ('installer_descriptor_lookup', 'installer_descriptor_lookup'),
                ('installer_resolved_filename', 'installer_resolved_filename'),
                ('installer_path_check', 'installer_path_check'),
                ('installer_fallback_path_check', 'installer_fallback_path_check'),
                ('installer_bundle_input', 'installer_size'),
                ('resource_reader_input', 'resource_reader_input'),
                ('resource_reader_disk_path', 'resource_reader_disk_path'),
                ('installer_extract_result', 'installer_extract'),
                ('installer_launch_result', 'installer_launch'),
                ('installer_complete', 'installer_complete'),
                ('installer_driver_detected', 'installer_driver_detected'),
                ('installer_primary_message', 'primary_message'),
                ('named_audio', 'named_audio'),
                ('rebuilt_named_audio', 'named_audio'),
                ('rebuilt_named_audio_result', 'named_audio'),
                ('rebuilt_asio_loaded', 'rebuilt_asio_loaded'),
            )
        },
        'installerTimeline': [
            {'index': index, 'event': name, **{
                field: event[field]
                for field in ('timeMs', 'thread', *INSTALLER_TIMELINE_FIELDS[name])
                if field in event
            }}
            for index, event in enumerate(events)
            if (name := event_name(event)) in INSTALLER_TIMELINE_FIELDS
        ],
        'localAttempts': [
            {key: event[key] for key in ('thread', 'timeMs', 'vid', 'pid', 'rev', 'installerBusy') if key in event}
            for event in evidence['installer_action']
        ],
        'observedResults': {
            name: [event[field] for event in evidence[name]]
            for name, field in (
                ('installer_descriptor_lookup', 'found'),
                ('installer_filename', 'filename'),
                ('installer_resolved_filename', 'filename'),
                ('installer_extract_result', 'success'),
                ('installer_launch_result', 'success'),
                ('sl3_registry_detection', 'readable'),
            )
        },
        'installerPrimaryPublications': len(evidence['installer_primary_message']),
        'rebuiltNamedAudioRequests': [
            {'asioApi': event['asioApi'], 'legacy': event['legacy']}
            for event in evidence['rebuilt_named_audio']
        ],
        'rebuiltNamedAudioResults': [
            event['connectionReturned'] for event in evidence['rebuilt_named_audio_result']
        ],
        'hardwareStreamingVerified': False,
    }
    arrival_dispatch = summarize_arrival_dispatch(events, armed, trace['errors'])
    if arrival_dispatch is not None:
        summary['sl3ArrivalDispatch'] = arrival_dispatch
    if call_analysis is not None:
        if (
            call_analysis.get('schema') != 'sl3.asio-call-analysis.v1'
            or call_analysis.get('actualEtwCaptureDecoded') is not True
            or call_analysis.get('build') != 'production'
            or call_analysis.get('pid') != trace['pid']
            or not evidence['rebuilt_asio_loaded']
        ):
            raise ValueError('Expected decoded production calls for the observed ASIO module load and PID')
        lifetime = trace.get('processFileTimeRange')
        if lifetime is not None:
            stamps = call_analysis.get('eventFileTimeRange')
            if not stamps or not (
                0 < int(lifetime['first']) <= int(stamps['first'])
                <= int(stamps['last']) <= int(lifetime['last'])
            ):
                raise ValueError('Decoded ASIO events are outside the observed process lifetime or lack timestamps')
        summary['matchedPidAsioCalls'] = {
            'pid': call_analysis['pid'],
            'processLifetimeMatched': lifetime is not None,
            'sessionMetadataComplete': call_analysis['sessionMetadataComplete'],
            'observedPairsComplete': call_analysis['observedPairsComplete'],
            'selectedMethods': {
                name: call_analysis['methods'][name]
                for name in ('class_object', 'init', 'channels', 'create_buffers', 'start', 'stop')
                if name in call_analysis['methods']
            },
        }
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Summarize the Serato installer trace')
    parser.add_argument('source', type=Path)
    parser.add_argument('--call-analysis', type=Path)
    args = parser.parse_args()
    calls = json.loads(args.call_analysis.read_text(encoding='utf-8')) if args.call_analysis else None
    try:
        report = summarize(json.loads(args.source.read_text(encoding='utf-8')), calls)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
