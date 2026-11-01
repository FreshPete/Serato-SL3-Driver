"""Byte-level contract tests, independent of USB hardware."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from sl3_protocol import rate_query_frame, parse_interrupt_frame, decode_pcm24_frames


class ProtocolTests(unittest.TestCase):
    def test_rate_getter_is_exact_and_has_no_setter_payload(self):
        self.assertEqual(rate_query_frame(), bytes.fromhex('301cc50001') + bytes(59))

    def test_rate_reply_big_endian(self):
        for rate in [44100, 48000]:
            frame = bytes.fromhex('301cc50001') + rate.to_bytes(2, 'big') + bytes(57)
            self.assertEqual(parse_interrupt_frame(frame)['rate_hz'], rate)
            self.assertEqual(len(parse_interrupt_frame(frame)['payload']), 2)

    def test_notification_marker_is_not_reply_marker(self):
        frame = bytes.fromhex('3800000002') + bytes([1, 2, 3]) + bytes(56)
        self.assertEqual(parse_interrupt_frame(frame)['payload'], [1, 2, 3])
        with self.assertRaises(ValueError):
            parse_interrupt_frame(bytes.fromhex('381cc50001') + bytes(59))

    def test_rejects_truncation_and_unknown_tag(self):
        for frame in [bytes(63), bytes(64)]:
            with self.assertRaises(ValueError): parse_interrupt_frame(frame)

    def test_pcm24_signed_boundaries_and_channel_order(self):
        values = (-8388608, -1, 0, 1, 0x123456, 8388607)
        packet = b''.join(v.to_bytes(3, 'little', signed=True) for v in values)
        self.assertEqual(decode_pcm24_frames(packet * 7), [values] * 7)
        self.assertEqual(decode_pcm24_frames(b''), [])

    def test_rejects_partial_audio_frames_and_oversize_packets(self):
        for packet in [bytes(17), bytes(127), bytes(144)]:
            with self.assertRaises(ValueError): decode_pcm24_frames(packet)


if __name__ == '__main__': unittest.main()
