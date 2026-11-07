import runpy
import unittest
from pathlib import Path


summarize = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "summarize-serato-installer-trace.py")
)["summarize"]


class InstallerTraceTest(unittest.TestCase):
    def test_arrival_dispatch_distinguishes_policy_and_listener_outcomes(self):
        events = [{"event": "trace_ready", "points": ["sl3_arrival_phase", "sl3_arrival_publish_policy"]}]

        def phase(sequence, name, **fields):
            events.append({"event": "sl3_arrival_phase", "sequence": sequence, "phase": name, **fields})

        for sequence in range(1, 6):
            phase(sequence, "constructed")
        phase(1, "publish_policy", decision="discard")
        phase(2, "publish_policy", decision="replace")
        for sequence, count in [(3, 0), (4, 1), (5, 2)]:
            phase(sequence, "publish_policy", decision="queue_original")
            phase(sequence, "enqueued")
            phase(sequence, "listener_lookup", listenerCount=count)
            if sequence == 5:
                phase(sequence, "usb_handler_entry")
            phase(sequence, "dispatch_finished")
        trace = {"pid": 1, "errors": [], "events": events}
        dispatch = summarize(trace)["sl3ArrivalDispatch"]
        self.assertFalse(dispatch["trackingMayBeIncomplete"])
        self.assertEqual([arrival["boundary"] for arrival in dispatch["arrivals"]], [
            "policy_discard", "policy_replace", "empty_listener_vector_observed",
            "dispatch_finished_without_usb_handler_sample", "usb_handler_observed",
        ])
        for extra_events, errors in [([{"event": "sl3_arrival_tracking_limit"}], []), ([], ["probe failed"])]:
            limited = summarize(dict(trace, events=events + extra_events, errors=errors))["sl3ArrivalDispatch"]
            self.assertTrue(limited["trackingMayBeIncomplete"])
            self.assertEqual(limited["arrivals"][3]["boundary"], "inconclusive_after_dispatch_finished")
            self.assertEqual(limited["arrivals"][4]["boundary"], "usb_handler_observed")

    def test_incomplete_arrival_and_impossible_sequence_are_distinct(self):
        events = [
            {"event": "trace_ready", "points": ["sl3_arrival_phase"]},
            {"event": "sl3_arrival_phase", "sequence": 1, "phase": "constructed"},
        ]
        trace = {"pid": 1, "errors": [], "events": events}
        self.assertEqual(summarize(trace)["sl3ArrivalDispatch"]["arrivals"][0]["boundary"],
                         "inconclusive_after_constructed")
        events.append({"event": "sl3_arrival_phase", "sequence": 1, "phase": "usb_handler_entry"})
        with self.assertRaisesRegex(ValueError, "phase order"):
            summarize(trace)

    def test_generic_helper_and_click_use_the_same_message_id(self):
        events = [
            {"event": "message_create", "id": 0x4FF, "caller": "0x154b5b5"},
            {"event": "driver_web_dispatch"},
            {"event": "message_create", "id": 0x4FF, "caller": "0x13801ba"},
            {"event": "installer_action", "vid": 0, "pid": 0, "thread": 7},
            {"event": "installer_descriptor_lookup", "found": False, "thread": 7},
        ]
        summary = summarize({"pid": 1, "errors": [], "events": events})
        self.assertEqual(
            [event["event"] for event in summary["installerTimeline"]],
            [
                "installer_helper_message",
                "driver_web_action_prepared",
                "installer_click_message",
                "installer_action",
                "installer_descriptor_lookup",
            ],
        )
        self.assertEqual(summary["localAttempts"], [{"thread": 7, "vid": 0, "pid": 0}])
        self.assertEqual(summary["observedResults"]["installer_descriptor_lookup"], [False])
        self.assertEqual(summary["eventCounts"]["installer_resolved_filename"], 0)

    def test_bundle_path_follows_resolved_filename(self):
        events = [
            {"event": "installer_filename", "filename": "configured.exe", "thread": 9},
            {"event": "installer_resolved_filename", "filename": "override.exe", "thread": 9},
            {"event": "installer_bundle_input", "path": "bundles/override.bin", "thread": 9},
        ]
        summary = summarize({"pid": 1, "errors": [], "events": events})
        self.assertEqual(summary["observedResults"]["installer_filename"], ["configured.exe"])
        self.assertEqual(summary["observedResults"]["installer_resolved_filename"], ["override.exe"])
        self.assertEqual(summary["installerTimeline"][2]["path"], "bundles/override.bin")

    def test_absence_requires_an_armed_probe_and_no_trace_errors(self):
        events = [
            {"event": "trace_ready", "points": ["message_create", "installer_extract"]},
            {"event": "message_create", "id": 0x4FF, "caller": "0x13801ba"},
        ]
        trace = {"pid": 1, "errors": [], "events": events}
        coverage = summarize(trace)["probeCoverage"]
        self.assertEqual(coverage["installer_click_message"], "observed")
        self.assertEqual(coverage["installer_extract_result"], "armed_no_event")
        self.assertEqual(coverage["rebuilt_asio_loaded"], "unconfirmed")
        trace["errors"] = ["observer error"]
        coverage = summarize(trace)["probeCoverage"]
        self.assertEqual(coverage["installer_click_message"], "observed")
        self.assertEqual(coverage["installer_extract_result"], "unconfirmed")

    def test_completion_and_post_detection_do_not_imply_primary_selection(self):
        events = [
            {"event": "trace_ready", "points": ["primary_message", "installer_driver_detected"]},
            {"event": "primary_message", "caller": "0x123"},
            {"event": "installer_complete", "installerResult": 0},
            {"event": "installer_driver_detected", "caller": "0x5b0c1b"},
        ]
        trace = {"pid": 1, "errors": [], "events": events}
        summary = summarize(trace)
        self.assertEqual(summary["probeCoverage"]["installer_primary_message"], "armed_no_event")
        self.assertEqual(summary["installerPrimaryPublications"], 0)
        events.append({"event": "primary_message", "caller": "0x5b0c4d"})
        summary = summarize(trace)
        self.assertEqual(summary["eventCounts"]["primary_message"], 2)
        self.assertEqual(summary["installerPrimaryPublications"], 1)
        self.assertEqual(summary["installerTimeline"][-1]["event"], "installer_primary_message")

    def test_failed_file_check_is_distinct_from_missing_resource_reader_coverage(self):
        trace = {"pid": 1, "errors": [], "events": [
            {"event": "trace_ready", "points": ["installer_path_check", "installer_size"]},
            {"event": "installer_path_check", "found": False, "thread": 7},
        ]}
        summary = summarize(trace)
        self.assertEqual(summary["installerTimeline"][-1]["found"], False)
        self.assertEqual(summary["probeCoverage"]["installer_path_check"], "observed")
        self.assertEqual(summary["probeCoverage"]["installer_bundle_input"], "armed_no_event")
        self.assertEqual(summary["probeCoverage"]["resource_reader_input"], "unconfirmed")

    def test_module_load_and_connection_result_are_separate(self):
        events = [
            {"event": "trace_ready", "points": ["named_audio", "rebuilt_asio_loaded"]},
            {"event": "named_audio", "rebuiltName": False},
            {"event": "named_audio", "rebuiltName": True, "asioApi": True, "legacy": False},
            {"event": "rebuilt_asio_loaded", "path": "local-path"},
            {"event": "named_audio_result", "rebuiltName": True, "connectionReturned": False},
        ]
        summary = summarize({"pid": 1, "errors": [], "events": events})
        self.assertEqual(summary["rebuiltNamedAudioResults"], [False])
        self.assertEqual(summary["eventCounts"]["named_audio"], 2)
        self.assertEqual(
            [event["event"] for event in summary["installerTimeline"]],
            ["rebuilt_named_audio", "rebuilt_asio_loaded", "rebuilt_named_audio_result"],
        )
        self.assertNotIn("path", summary["installerTimeline"][1])
        self.assertFalse(summary["hardwareStreamingVerified"])

    def test_decoded_calls_require_matching_pid_and_observed_module_load(self):
        trace = {"pid": 12, "errors": [], "events": [{"event": "rebuilt_asio_loaded"}]}
        calls = {
            "schema": "sl3.asio-call-analysis.v1",
            "pid": 12,
            "build": "production",
            "actualEtwCaptureDecoded": True,
            "sessionMetadataComplete": True,
            "observedPairsComplete": True,
            "methods": {"init": {"rawResults": {"0": 1}}, "name": {}},
        }
        summary = summarize(trace, calls)
        self.assertEqual(summary["matchedPidAsioCalls"]["selectedMethods"], {
            "init": {"rawResults": {"0": 1}},
        })
        self.assertFalse(summary["hardwareStreamingVerified"])
        with self.assertRaisesRegex(ValueError, "module load and PID"):
            summarize(trace, dict(calls, pid=13))
        with self.assertRaisesRegex(ValueError, "module load and PID"):
            summarize(dict(trace, events=[]), calls)
        with self.assertRaisesRegex(ValueError, "module load and PID"):
            summarize(trace, dict(calls, actualEtwCaptureDecoded=False))
        trace["processFileTimeRange"] = {"first": "100", "last": "200"}
        with self.assertRaisesRegex(ValueError, "process lifetime"):
            summarize(trace, calls)
        calls["eventFileTimeRange"] = {"first": "101", "last": "199"}
        self.assertTrue(summarize(trace, calls)["matchedPidAsioCalls"]["processLifetimeMatched"])
        calls["eventFileTimeRange"] = {"first": "99", "last": "100"}
        with self.assertRaisesRegex(ValueError, "process lifetime"):
            summarize(trace, calls)
