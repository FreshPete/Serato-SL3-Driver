"""Query one private SL3 image-source session; cannot start, update or stop logging."""
import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import uuid

HEADER_BYTES = 120  # Windows x64 EVENT_TRACE_PROPERTIES
STRING_BYTES = 4096
BUFFER_BYTES = HEADER_BYTES + 2*STRING_BYTES
NOT_FOUND = 4201  # ERROR_WMI_INSTANCE_NOT_FOUND


def require(ok, message):
    if not ok:
        raise ValueError(message)


class SessionIdentityMismatch(ValueError):
    """Validated property layout, rejected identity; metadata never admits a source."""
    def __init__(self, message, properties):
        super().__init__(message)
        self.properties = dict(properties)


def validate_identity(name, identity):
    require(isinstance(name, str) and re.fullmatch(r'SL3Image-[a-f0-9]{32}', name),
            'Expected an exact private SL3 image session name')
    identity = uuid.UUID(str(identity))
    require(identity.int != 0 and identity != uuid.UUID('9e814aad-3204-11d2-9a82-006008a86939'),
            'Expected a private nonzero source GUID')
    return identity


def request_buffer(name, identity):
    identity = validate_identity(name, identity)
    raw = bytearray(BUFFER_BYTES)
    struct.pack_into('<I', raw, 0, len(raw))
    raw[24:40] = identity.bytes_le
    struct.pack_into('<II', raw, 112, HEADER_BYTES+STRING_BYTES, HEADER_BYTES)
    encoded = name.encode('utf-16-le')+b'\0\0'
    raw[HEADER_BYTES:HEADER_BYTES+len(encoded)] = encoded
    return raw


def parse_properties(raw, name, identity):
    identity = validate_identity(name, identity)
    require(HEADER_BYTES <= len(raw) <= BUFFER_BYTES, 'Invalid properties buffer extent')
    size = struct.unpack_from('<I', raw)[0]
    require(HEADER_BYTES <= size <= len(raw), 'Invalid returned buffer size')
    returned_guid = uuid.UUID(bytes_le=raw[24:40])
    file_offset, name_offset = struct.unpack_from('<II', raw, 112)

    def text(offset):
        require(HEADER_BYTES <= offset < size and offset % 2 == 0, 'Invalid returned string offset')
        end = offset
        while end+2 <= size and end-offset < STRING_BYTES:
            if raw[end:end+2] == b'\0\0':
                return raw[offset:end].decode('utf-16-le', errors='strict'), end+2
            end += 2
        raise ValueError('Unterminated or oversized returned string')

    logger, logger_end = text(name_offset)
    logfile, file_end = text(file_offset)
    require(logger_end <= file_offset or file_end <= name_offset, 'Overlapping returned strings')
    mode, flush, flags = struct.unpack_from('<III', raw, 64)
    events_lost, buffers_written, log_lost, realtime_lost = struct.unpack_from('<IIII', raw, 88)
    properties = {'sessionName': logger, 'sessionGuid': str(returned_guid), 'logFileName': logfile,
            'sessionGuidMatchesExpected': returned_guid == identity, 'sessionNameMatchesExpected': logger.casefold() == name.casefold(),
            'logFileMode': mode, 'systemLoggerModePresent': bool(mode & 0x02000000),
            'maximumFileSizeMiB': struct.unpack_from('<I', raw, 60)[0],
            'clockType': struct.unpack_from('<I', raw, 40)[0], 'flushTimer': flush,
            'enableFlags': flags, 'eventsLost': events_lost, 'buffersWritten': buffers_written,
            'logBuffersLost': log_lost, 'realTimeBuffersLost': realtime_lost}
    errors = []
    if returned_guid != identity:
        errors.append(f'Session GUID differs from expected source (expected {identity}, returned {returned_guid})')
    if logger.casefold() != name.casefold():
        errors.append('Returned session name differs')
    if errors:
        raise SessionIdentityMismatch('; '.join(errors), properties)
    return properties


def query(name, identity):
    raw = request_buffer(name, identity)
    require(os.name == 'nt' and C.sizeof(C.c_void_p) == 8, 'Requires x64 Windows')
    # Fixed System32 search mode; no caller-controlled DLL or operational code.
    api = C.WinDLL('advapi32.dll', winmode=0x800)
    control = api.ControlTraceW
    control.argtypes = [C.c_ulonglong, C.c_wchar_p, C.c_void_p, C.c_uint32]
    control.restype = C.c_uint32
    buffer = C.create_string_buffer(bytes(raw), len(raw))
    started = datetime.now(timezone.utc).isoformat()
    status = control(0, name, buffer, 0)  # EVENT_TRACE_CONTROL_QUERY only
    finished = datetime.now(timezone.utc).isoformat()
    properties, error = None, None
    accepted = status in (0, NOT_FOUND)
    if status == 0:
        try:
            properties = parse_properties(buffer.raw, name, identity)
        except SessionIdentityMismatch as failure:
            properties, error, accepted = failure.properties, str(failure), False
        except ValueError as failure:
            error, accepted = str(failure), False
    elif status != NOT_FOUND:
        error = f'Trace query failed with Windows error {status}'
    return {'scope': 'Read-only query of one private source; no USB or logger lifecycle operation',
            'queryStartedUtc': started, 'queryFinishedUtc': finished, 'producerPid': os.getpid(),
            'sessionName': name, 'expectedSessionGuid': str(uuid.UUID(str(identity))),
            'controlCode': 0, 'win32Status': status, 'sourceActive': True if status == 0 else False if status == NOT_FOUND else None,
            'diagnosticAccepted': accepted, 'validationError': error,
            'properties': properties, 'sourceStarted': False, 'sourceStopped': False,
            'readinessAdmission': False, 'bufferBytes': len(raw),
            'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limits': ['A query is a point observation; it does not prove timed expiry or image rundown.',
                       'An absent-source result does not exercise successful live-property decoding.',
                       'Source flags do not establish provider enablement, event completeness or USB readiness.',
                       'No returned kernel pointer or logger handle is published.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-name', required=True)
    parser.add_argument('--session-guid', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), 'Expected a new output in an existing directory')
    result = query(args.session_name, args.session_guid)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('sessionName', 'controlCode', 'win32Status', 'sourceActive', 'diagnosticAccepted', 'validationError', 'readinessAdmission')}))
    return 0 if result['diagnosticAccepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
