"""Summarise saved finite USB records; no live USB or error-tolerance changes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

SYMBOLS = {0: 'USBD_STATUS_SUCCESS', 0xc0000012: 'USBD_STATUS_BABBLE_DETECTED',
           0xc0010000: 'USBD_STATUS_CANCELED', 0xc0020000: 'USBD_STATUS_ISO_NOT_ACCESSED_BY_HW',
           0xc0040000: 'USBD_STATUS_ISO_NA_LATE_USBPORT', 0xc0050000: 'USBD_STATUS_ISO_NOT_ACCESSED_LATE'}
SDK_HEADER = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.19041.0/shared/usb.h')


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value):
    require(type(value) is int and 0 <= value <= 0xffffffffffffffff, 'Invalid unsigned USB result')
    return value


def decode(value):
    value = integer(value)
    low, high = value & 0xffffffff, value >> 32
    canonical = high == 0 or (high == 0xffffffff and bool(low & 0x80000000))
    return {'rawHex': f'0x{value:016X}', 'canonical32BitValue': canonical,
            'usbdHex': f'0x{low:08X}' if canonical else None,
            'symbol': SYMBOLS.get(low, 'UNKNOWN_USBD_STATUS') if canonical else 'NONCANONICAL_64_BIT_STATUS'}


def summarise(record):
    packets = record.get('packets')
    require(type(packets) is list and len(packets) <= 1024, 'Expected a bounded finite packet record')
    groups = {}
    for packet in packets:
        require(type(packet) is dict, 'Malformed packet row')
        direction = packet.get('direction', 'IN')
        require(direction in ('IN', 'OUT'), 'Unknown packet direction')
        index = integer(packet.get('slot', packet.get('request')))
        require(index < 8, 'Invalid finite request slot')
        groups.setdefault((direction, index), []).append(packet)
    results = []
    for (direction, index), rows in sorted(groups.items()):
        def common(name):
            values = [row[name] for row in rows]
            require(all(value == values[0] and type(value) is type(values[0]) for value in values), 'Inconsistent per-request result')
            return values[0]
        attempted, submitted, terminal = [common(key) for key in ('request_attempted', 'request_submitted', 'request_terminal')]
        require(all(type(value) is bool for value in (attempted, submitted, terminal)), 'Request flags must be explicit booleans')
        require(not submitted or attempted, 'Submitted request was not attempted')
        general = integer(common('request_usbd_status'))
        completion_error = integer(common('completion_win32_error'))
        interpreted = submitted and terminal
        histogram = Counter(integer(row['status']) for row in rows) if interpreted else {}
        results.append({'direction': direction, 'slot': index, 'packetRows': len(rows),
                        'attempted': attempted, 'submitted': submitted, 'terminal': terminal,
                        'requestStatus': decode(general) if submitted else None,
                        'completionWin32Error': completion_error if attempted else None,
                        'packetResultsInterpreted': interpreted,
                        'packetStatusHistogram': [{**decode(status), 'packets': count} for status, count in sorted(histogram.items())]})
    return {'schema': 'sl3.finite-usbd-status-summary.v1', 'requests': results,
            'submittedRequests': sum(row['submitted'] for row in results),
            'unsubmittedPacketRowsExcludedFromCompletionResults': sum(row['packetRows'] for row in results if not row['submitted']),
            'limits': ['Status names do not identify the electrical, device or scheduling cause',
                       'Cancellation results may follow the first fault; no causal ordering is inferred automatically',
                       'Unsubmitted/nonterminal packet storage is not completion evidence',
                       'No validation policy is relaxed and no hardware result is promoted to success']}


def verify_sdk_header(path):
    header = path.read_bytes()
    text = header.decode('utf-8-sig')
    # Bind symbolic labels to the installed primary SDK definition rather than
    # decoding sign-extended values by an unverified remembered number.
    for value, symbol in SYMBOLS.items():
        if value:
            require(re.search(r'#define\s+'+symbol+r'\s+\(\(USBD_STATUS\)0x'+f'{value:08X}'+r'L\)', text, re.IGNORECASE),
                    'SDK status definition differs: '+symbol)
    return hashlib.sha256(header).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--sdk-header', type=Path, default=SDK_HEADER)
    args = parser.parse_args()
    require(args.record.stat().st_size <= 2*1024*1024, 'Oversized finite record')
    raw = args.record.read_bytes()
    result = summarise(json.loads(raw.decode('utf-8-sig')))
    result['recordSha256'] = hashlib.sha256(raw).hexdigest()
    result['sdkHeaderSha256'] = verify_sdk_header(args.sdk_header)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
