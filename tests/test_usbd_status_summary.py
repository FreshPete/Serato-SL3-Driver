"""Saved result interpretation only; no native code or USB execution."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('usbd_summary', Path(__file__).resolve().parents[1]/'scripts/summarise-usbdk-packet-status.py')
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def row(slot=0, submitted=True, terminal=True, status=0, general=0):
    return {'direction': 'IN' if slot % 2 == 0 else 'OUT', 'slot': slot, 'status': status,
            'request_attempted': submitted, 'request_submitted': submitted,
            'request_terminal': terminal, 'request_usbd_status': general, 'completion_win32_error': 0}


class UsbdStatusSummaryTests(unittest.TestCase):
    def test_signed_and_unsigned_status_encoding(self):
        for value in (0xc0000012, 0xffffffffc0000012):
            decoded = summary.decode(value)
            self.assertTrue(decoded['canonical32BitValue'])
            self.assertEqual(decoded['symbol'], 'USBD_STATUS_BABBLE_DETECTED')
        self.assertNotEqual(summary.decode(0xc0000012)['rawHex'], summary.decode(0xffffffffc0000012)['rawHex'])

    def test_noncanonical_high_bits_are_not_success(self):
        for value in (0x100000000, 0xffffffff00000000, 0xffffffff00000001):
            decoded = summary.decode(value)
            self.assertFalse(decoded['canonical32BitValue'])
            self.assertIsNone(decoded['usbdHex'])

    def test_unsubmitted_and_nonterminal_storage_is_not_completion(self):
        result = summary.summarise({'packets': [row(), row(1, False, False), row(2, True, False)]})
        self.assertEqual(result['submittedRequests'], 2)
        self.assertEqual(result['unsubmittedPacketRowsExcludedFromCompletionResults'], 1)
        for request in result['requests']:
            if request['slot'] in (1, 2):
                self.assertFalse(request['packetResultsInterpreted'])
                self.assertEqual(request['packetStatusHistogram'], [])

    def test_packet_fault_and_cancellation_remain_distinct(self):
        result = summary.summarise({'packets': [row(status=0xffffffffc0000012),
                                               row(2, status=0xffffffffc0020000, general=0xffffffffc0010000)]})
        first, canceled = result['requests']
        self.assertEqual(first['requestStatus']['symbol'], 'USBD_STATUS_SUCCESS')
        self.assertEqual(first['packetStatusHistogram'][0]['symbol'], 'USBD_STATUS_BABBLE_DETECTED')
        self.assertEqual(canceled['requestStatus']['symbol'], 'USBD_STATUS_CANCELED')
        self.assertEqual(canceled['packetStatusHistogram'][0]['symbol'], 'USBD_STATUS_ISO_NOT_ACCESSED_BY_HW')

    def test_invalid_flags_and_inconsistent_requests_rejected(self):
        invalid = row()
        invalid['request_submitted'] = 1
        for packets in ([invalid], [row(), row(terminal=False)], [row(general=True)], [row(slot=8)]):
            with self.assertRaises(ValueError):
                summary.summarise({'packets': packets})


if __name__ == '__main__':
    unittest.main()
