"""Read bounded host-probe observations; never opens a device or approves latency."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value, minimum=0):
    require(type(value) is int and minimum <= value <= 0xffffffffffffffff, 'Invalid timing integer')
    return value


def distribution(values):
    ordered = sorted(values)
    return {name: ordered[max(0, math.ceil(len(ordered)*fraction)-1)]
            for name, fraction in (('minimum', 0), ('median', .5), ('p95', .95), ('p99', .99), ('maximum', 1))}


def analyse(report):
    require(report.get('schema') == 'sl3.host-probe.v1', 'Unknown probe schema')
    require(type(report.get('simulated')) is bool, 'Missing transport identity')
    frequency = integer(report.get('callback_counter_frequency'), 1)
    rate = integer(report.get('reported_rate_hz'), 1)
    require(rate in (44100, 48000), 'Unsupported observed rate')
    bank = integer(report.get('bank_frames'), 1)
    require(bank == 128, 'Unsupported probe bank')
    count = integer(report.get('callbacks'))
    dropped = integer(report.get('timing_records_dropped'))
    rows = report.get('callback_timings')
    require(type(rows) is list and 2 <= len(rows) <= 2048, 'At least two bounded observations required')
    require(len(rows) + dropped == count and (not dropped or len(rows) == 2048), 'Timing coverage mismatch')
    first = integer(report.get('first_frame'))
    require(integer(report.get('last_frame')) == first + (count-1)*bank, 'Callback endpoint mismatch')
    for index, row in enumerate(rows):
        require(type(row) is list and len(row) == 3, 'Malformed timing observation')
        frame, publication, ticks = (integer(value) for value in row)
        require(frame == first + index*bank and ticks > 0, 'Logical frame sequence mismatch')
        if index:
            require(publication >= rows[index-1][1] and ticks >= rows[index-1][2], 'Timing clock regressed')
    ticks_span = rows[-1][2] - rows[0][2]
    require(ticks_span > 0, 'No observable callback time span')
    callback_deltas = [(b[2]-a[2])*1_000_000_000//frequency for a, b in zip(rows, rows[1:])]
    publication_deltas = [b[1]-a[1] for a, b in zip(rows, rows[1:])]
    frames_span = rows[-1][0]-rows[0][0]
    return {
        'schema': 'sl3.callback-timing-analysis.v1',
        'simulated': report['simulated'], 'probeSuccessful': report.get('successful') is True,
        'rateHz': rate, 'bankFrames': bank, 'observations': len(rows), 'recordsDropped': dropped,
        'completeCallbackCoverage': dropped == 0,
        'nominalBankPeriodNs': bank*1_000_000_000/rate,
        'callbackSpacingNs': distribution(callback_deltas),
        'publicationSpacingNs': distribution(publication_deltas),
        'repeatedPublicationTimestamps': sum(delta == 0 for delta in publication_deltas),
        'observationWindowFrames': frames_span,
        'callbackSpanNs': ticks_span*1_000_000_000//frequency,
        'softwareDeliveryFramesPerSecond': frames_span*frequency/ticks_span,
        'latencyMeasured': False, 'physicalClockVerified': False, 'usbContinuityVerified': False,
        'limits': ['Callback entry times and backend publication observations are software timing only',
                   'Multiple banks may share one publication observation; neither clock is a DAC or ADC playhead',
                   'Logical frame increments do not prove that USB packets or analogue samples were gap-free',
                   'No ASIO timing profile or approval is generated'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe_json', type=Path)
    args = parser.parse_args()
    require(args.probe_json.stat().st_size <= 1024*1024, 'Oversized probe record')
    raw = args.probe_json.read_bytes()
    result = analyse(json.loads(raw.decode('utf-8-sig')))
    result['probeRecordSha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
