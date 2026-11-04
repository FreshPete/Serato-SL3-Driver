"""Validate a saved single-shot SL3 timer exchange. Never opens hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate timer record field')
        result[key] = value
    return result


def validate(raw, challenge, cadence=False, silent_stream=False):
    require(re.fullmatch('[0-9a-fA-F]{16}', challenge), 'Expected eight challenge bytes in hex')
    require(0 < len(raw) <= 8192, 'Timer record exceeds size bound')
    record = json.loads(raw, object_pairs_hook=unique)
    require(record.get('schema') == 'sl3.driver-timer-diagnostic.v1' and record.get('phase') == 'finished',
            'Expected a completed timer diagnostic')
    require(record.get('challenge_hex') == challenge.lower(), 'Challenge differs from the planned exchange')
    require(re.fullmatch('[0-9a-f]{16}', record.get('response_hex', '')), 'Missing eight-byte reply')
    for name in ('redirect_attempted', 'redirect_opened', 'last_io_retired', 'redirect_closed', 'response_parsed'):
        require(record.get(name) is True, 'Missing completion evidence: '+name)
    for name in ('response_verified', 'serato_admission_verified', 'reopen_ready_verified'):
        require(record.get(name) is False, 'Unsupported claim: '+name)
    require(not silent_stream or cadence, 'Silent stream requires cadence validation')
    require(record.get('silent_stream') is True if silent_stream else 'silent_stream' not in record,
            'Timer stream mode differs')
    zero_fields = ('diagnostic_error', 'exchange_error', 'native_error', 'rate_changes')
    zero_fields += ('stream_fault',) if silent_stream else ('audio_submissions', 'alternate_changes')
    for name in zero_fields:
        require(type(record.get(name)) is int and record[name] == 0, 'Nonzero or invalid field: '+name)
    count = 10 if cadence else 1
    require(type(record.get('write_attempts')) is int and record['write_attempts'] == count and
            type(record.get('read_attempts')) is int and count <= record['read_attempts'] <= count * 4,
            'Transfer attempts differ from the planned contract')
    require(record.get('error') == '', 'Timer diagnostic reported an error')
    result = {'valid': True, 'recordSha256': hashlib.sha256(raw).hexdigest(),
              'writeAttempts': record['write_attempts'], 'readAttempts': record['read_attempts'],
              'responseVerified': False, 'physicalProvenanceVerified': False, 'readinessAdmission': False}
    cadence_fields = {'cadence_ms', 'completed_exchanges', 'exchanges'}
    if not cadence:
        require(not cadence_fields.intersection(record), 'Cadence record requires explicit cadence validation')
        return result
    require(record.get('cadence_ms') == 100 and type(record.get('cadence_ms')) is int and
            record.get('completed_exchanges') == count and type(record.get('completed_exchanges')) is int,
            'Incomplete or unexpected cadence')
    rows = record.get('exchanges')
    require(type(rows) is list and len(rows) == count, 'Missing cadence observations')
    fields = {'start_us', 'end_us', 'writes', 'reads'}
    previous_outputs = 0
    if silent_stream:
        fields.update(('output_completions_before', 'output_completions_after'))
        require(record.get('audio_submissions_known') is True and record.get('output_payload') == 'zero PCM only',
                'Missing silent-output completion evidence')
        for name in ('input_frames', 'audio_submissions', 'output_completions', 'observed_rate_hz', 'alternate_activation_attempts'):
            require(type(record.get(name)) is int and record[name] > 0, 'Invalid stream field: '+name)
        require(record['observed_rate_hz'] in (44100, 48000) and record['alternate_activation_attempts'] == 2 and
                record['output_completions'] <= record['audio_submissions'], 'Stream geometry or completion count differs')
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) == fields and
                all(type(value) is int for value in row.values()), 'Malformed cadence observation')
        due = index * 100_000
        require(due <= row['start_us'] <= due + 20_000 and
                row['start_us'] <= row['end_us'] < due + 100_000,
                'Exchange fell outside its cadence slot')
        require(row['writes'] == 1 and 1 <= row['reads'] <= 4, 'Invalid per-slot transfer count')
        if silent_stream:
            require(previous_outputs <= row['output_completions_before'] < row['output_completions_after'] <= record['output_completions'],
                    'No proven output progress within a timer exchange')
            previous_outputs = row['output_completions_after']
    require(sum(row['reads'] for row in rows) == record['read_attempts'], 'Cadence read count differs')
    spacings = [b['start_us'] - a['start_us'] for a, b in zip(rows, rows[1:])]
    result.update(completedExchanges=count, minimumDispatchSpacingUs=min(spacings),
                  maximumDispatchSpacingUs=max(spacings), wireTimingVerified=False)
    if silent_stream:
        result.update(inputFrames=record['input_frames'], outputCompletions=record['output_completions'],
                      exchangesWithOutputProgress=count, analogueOutputVerified=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--challenge', required=True)
    parser.add_argument('--cadence', action='store_true')
    parser.add_argument('--silent-stream', action='store_true')
    args = parser.parse_args()
    try:
        with args.record.open('rb') as stream:
            result = validate(stream.read(8193), args.challenge, args.cadence, args.silent_stream)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
