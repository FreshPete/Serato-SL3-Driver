"""Small, execution-free SL3 codecs recovered from the original driver.

Command replies and asynchronous notifications have different four-byte tags.
Physical channel labels and converter alignment still need an audio fixture.
"""
REPLY_TAG = bytes.fromhex('1cc50001')
NOTIFICATIONS = {0x34: (bytes.fromhex('00000001'), 6),
                 0x38: (bytes.fromhex('00000002'), 3),
                 0x39: (bytes.fromhex('00000003'), 4)}


def rate_query_frame():
    # Only the rate getter is constructible here; no general command sender.
    return bytes([0x30]) + REPLY_TAG + bytes(59)


def parse_interrupt_frame(frame):
    if len(frame) != 64:
        raise ValueError('Expected one complete 64-byte interrupt frame')
    command = frame[0]
    if command in NOTIFICATIONS:
        tag, length = NOTIFICATIONS[command]
        if frame[1:5] != tag:
            raise ValueError('Notification tag does not match original parser')
        return dict(kind='notification', command=command, payload=list(frame[5:5+length]))
    if frame[1:5] != REPLY_TAG:
        raise ValueError('Unrecognized command-reply tag')
    result = dict(kind='reply', command=command, payload=list(frame[5:]))
    if command == 0x30:
        # The original driver consumes exactly two bytes for this reply. The
        # remaining device-buffer contents are not additional status fields.
        result['payload'] = list(frame[5:7])
        result['ignored_tail_bytes'] = 57
        result['rate_hz'] = int.from_bytes(frame[5:7], 'big')
    return result


def decode_pcm24_frames(packet):
    if len(packet) > 126 or len(packet) % 18:
        raise ValueError('SL3 packet must contain whole six-channel/18-byte frames, at most 126 bytes')
    return [tuple(int.from_bytes(packet[p+c*3:p+c*3+3], 'little', signed=True) for c in range(6))
            for p in range(0, len(packet), 18)]
