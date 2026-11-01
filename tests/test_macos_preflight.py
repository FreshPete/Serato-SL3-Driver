import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("mac_preflight", Path(__file__).parents[1]/"scripts/preflight-macos.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MacPreflightTests(unittest.TestCase):
    def test_plan_and_non_mac_collection_execute_nothing(self):
        def forbidden(_):
            raise AssertionError("Command executed")
        self.assertTrue(MODULE.make_report(False, forbidden)["plan_only"])
        with patch.object(MODULE.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "actual macOS"):
                MODULE.make_report(True, forbidden)

    def test_exact_device_and_service_projection_omit_unrelated_serials(self):
        matching = {"idVendor": 7365, "idProduct": 1, "USB Serial Number": "DEVICE_SECRET", "IOObjectClass": "IOUSBHostDevice",
                    "IORegistryEntryName": "SL3", "IORegistryEntryChildren": [{"IOObjectClass": "IOUSBHostInterface", "bInterfaceNumber": 2, "bAlternateSetting": 0,
                    "idVendor": 7365, "idProduct": 1, "IORegistryEntryChildren": [{"IOObjectClass": "com_rane_sl3_audiodevice"}]}]}
        unrelated = {"idVendor": 7365, "idProduct": 2, "USB Serial Number": "UNRELATED_SECRET", "IORegistryEntryName": "Unrelated"}
        result = MODULE.usb_projection(plistlib.dumps([matching, unrelated]))
        self.assertEqual(len(result["sl3_devices"]), 1)
        self.assertEqual(result["sl3_devices"][0]["services"][1]["bInterfaceNumber"], 2)
        self.assertTrue(result["sl3_devices"][0]["driver_service_labels"])
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("Unrelated", str(result))

    def test_failed_collection_is_unknown_not_absent(self):
        def runner(argv):
            return {"argv": argv, "status": "completed", "exit_code": 1, "stdout": b"", "stderr": "Access denied"}
        with patch.object(MODULE.platform, "system", return_value="Darwin"):
            result = MODULE.make_report(True, runner)
        self.assertIsNone(result["usb_registry"]["sl3_devices"])
        self.assertEqual(result["legacy_loaded_extension"]["status"], "unknown")
        self.assertIsNone(result["host"]["hardware_arm64"])
        self.assertFalse(result["physical_audio_compatibility_verified"])

    def test_successful_queries_keep_architecture_and_translation_separate(self):
        def runner(argv):
            data = plistlib.dumps([]) if argv == MODULE.IOREG else b"1\n" if argv[-1] in ("hw.optional.arm64", "sysctl.proc_translated") else b"x86_64\n"
            return {"argv": argv, "status": "completed", "exit_code": 0, "stdout": data, "stderr": ""}
        result = MODULE.collect(runner)
        self.assertTrue(result["host"]["hardware_arm64"])
        self.assertTrue(result["host"]["process_translated"])
        self.assertEqual(result["usb_registry"]["sl3_devices"], [])
        self.assertNotIn("stdout", result["commands"]["usb_registry"])
        self.assertNotIn("stdout", result["commands"]["loaded_extensions"])

    def test_malformed_registry_cannot_be_promoted_to_compatibility(self):
        for data in (b"", b"not a plist", plistlib.dumps([{"IORegistryEntryChildren": "invalid"}])):
            with self.assertRaises((ValueError, plistlib.InvalidFileException)):
                MODULE.usb_projection(data)
        self.assertIsNone(MODULE.integer(True))

    def test_registry_aliases_deduplicate_but_distinct_devices_survive(self):
        device = {"IOObjectClass": "IOUSBHostDevice", "IORegistryEntryID": 123, "idVendor": 7365, "idProduct": 1}
        hub = {"IOObjectClass": "IOUSBHostDevice", "idVendor": 1, "idProduct": 2, "IORegistryEntryChildren": [device]}
        other = {**device, "IORegistryEntryID": 124}
        result = MODULE.usb_projection(plistlib.dumps([hub, device, other]))
        self.assertEqual(len(result["sl3_devices"]), 2)

    def test_signature_result_is_separate_from_driver_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)/"Sl3Driver.10.9.kext"
            (bundle/"Contents").mkdir(parents=True)
            (bundle/"Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.rane.driver.sl3", "CFBundleVersion": "2.0.1f2"}))
            def runner(argv):
                return {"argv": argv, "status": "completed", "exit_code": 0, "stdout": b"", "stderr": "valid on disk"}
            result = MODULE.legacy_signature(runner, bundle)
            self.assertEqual(result["status"], "verification_succeeded")
            self.assertIn("not established", result["loaded_or_admitted"])
            self.assertEqual(result["bundle"]["CFBundleVersion"], "2.0.1f2")


if __name__ == "__main__":
    unittest.main()
