"""Read-only consistency check for explicit traced SL3 rate diagnostics.

Records and synthetic tests are not hardware attestation, an oscillator
measurement, audio validation, restoration proof or permission to run a test.
"""
import argparse
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("capture_evidence", Path(__file__).with_name("validate-usbdk-capture.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
digest, read_json, require, integer, utc = capture.digest, capture.read_json, capture.require, capture.integer, capture.utc


def state_contract(state):
    keys = ("secureBoot", "deviceGuard", "hvciRegistry", "devices", "asio", "application")
    require(all(key in state for key in keys), "Incomplete recovery snapshot")
    require(state["secureBoot"] is True and isinstance(state["devices"], list)
            and len(state["devices"]) == 1, "Recovery snapshot lacks one SL3 and Secure Boot")
    row = state["devices"][0]
    require(isinstance(row, dict) and isinstance(row.get("device"), dict)
            and str(row["device"].get("InstanceId", "")).upper().startswith("USB\\VID_1CC5&PID_0001\\")
            and isinstance(row.get("properties"), list), "Recovery snapshot device identity missing")
    normalized = {key: state[key] for key in keys}
    normalized["devices"] = [{"device": row["device"], "properties": sorted(row["properties"], key=lambda p: p["KeyName"])}]
    return normalized


def observation_fields(r,expected_target=None):
    """Completed v2 observation consistency, including failed operations.

    Returning this record never qualifies the traced experiment or restoration.
    Only accepted pre-deadline frames populate acknowledgement/readback fields.
    """
    require(r.get('schema')=='sl3.rate-diagnostic.v2' and r.get('phase')=='finished','Expected a completed v2 rate observation')
    for key in ('target_rate_hz','initial_rate_hz','verified_rate_hz','readback_rate_hz','write_attempts','read_attempts',
                'setter_attempts','control_transfer_attempts','diagnostic_error','transaction_error','exchange_error'):
        require(integer(r.get(key)) and r[key]>=0,'Invalid rate observation integer: '+key)
    target,initial,verified,readback=(r[k] for k in ('target_rate_hz','initial_rate_hz','verified_rate_hz','readback_rate_hz'))
    require(target in (44100,48000) and (expected_target is None or target==expected_target),'Invalid observation target')
    require(all(value in (0,44100,48000) for value in (initial,verified,readback)),'Unsupported clock observation')
    for key in ('device_may_have_changed','acknowledgement_received','last_io_retired','redirect_closed'):
        require(type(r.get(key)) is bool,'Invalid rate observation flag: '+key)
    require(r.get('automatic_rollback') is False and r.get('audio_submissions')==0 and type(r.get('audio_submissions')) is int
            and r.get('alternate_changes')==0 and type(r.get('alternate_changes')) is int,'Unexpected rate-side operation')
    require(type(r.get('error')) is str and len(r['error'])<=512,'Invalid native diagnostic error')
    writes,reads,setters=(r[k] for k in ('write_attempts','read_attempts','setter_attempts'))
    ack=r['acknowledgement_received'];error,transaction,exchange=(r[k] for k in ('diagnostic_error','transaction_error','exchange_error'))
    require(writes<=3 and reads<=12 and reads<=4*writes and setters<=1 and
            r['control_transfer_attempts']==writes+reads<=15,'Unbounded observation attempt counts')
    require(r['device_may_have_changed']==bool(setters) and (writes<2 or setters==1),'Setter effect/count mismatch')
    require(not setters or (writes>=2 and initial and initial!=target),'Setter lacks a different initial clock')
    require(not initial or (writes>=1 and reads>=1),'Initial clock precedes its getter')
    require(not ack or (setters==1 and writes>=2 and reads>=2),'Acknowledgement precedes setter/getter')
    require(writes!=3 or ack,'Verification request precedes accepted acknowledgement')
    require(not readback or (ack and writes==3 and reads>=3),'Readback precedes verification request')
    require(error in (0,2,3,4,5) and transaction in (0,2,3,4) and exchange<=6,'Unknown rate diagnostic outcome')
    if error==0:
        require(transaction==exchange==0 and initial and verified==target and r['error']=='','Successful operation lacks verified target')
        require((setters==1 and ack and readback==target and writes==3 and reads>=3) or
                (setters==0 and not ack and not readback and initial==target and writes==1 and reads>=1),
                'Successful observation contradicts selected/no-op path')
    else:
        require(not verified and initial!=target,'Failed operation claims a verified/no-op target')
        if transaction==3:
            require(error==5 and exchange==0 and readback and readback!=target,'Mismatch lacks actual different readback')
        else:
            require(not readback,'Failed operation has an unexplained accepted verification getter')
            require((error==5 and transaction==2 and exchange>0) or
                    (transaction==4 and exchange==0),'Failure category differs from transaction result')
            if transaction==2:
                require((not initial or writes>=2) and (not ack or writes==3),'Exchange failure contradicts accepted stage')
    utc(r.get('utc'));return r


def observation_result(path,expected_target=None):
    return observation_fields(read_json(Path(path)),expected_target)


def native_result(path, expected_target=None):
    result = read_json(Path(path))
    require(result.get("schema") in ("sl3.rate-diagnostic.v1","sl3.rate-diagnostic.v2") and result.get("phase") == "finished", "Rate diagnostic did not reach a final record")
    if result['schema']=='sl3.rate-diagnostic.v2':observation_fields(result,expected_target)
    else:require(not any(k in result for k in ('readback_rate_hz','setter_attempts','acknowledgement_received')),
                 'Version-one record cannot claim version-two observation fields')
    for key in ("diagnostic_error", "transaction_error", "exchange_error", "audio_submissions", "alternate_changes"):
        require(integer(result.get(key)) and result[key] == 0, f"Nonzero/missing rate result: {key}")
    for key in ("last_io_retired", "redirect_closed"):
        require(result.get(key) is True, f"Rate cleanup not proved: {key}")
    require(result.get("automatic_rollback") is False and result.get("error") == "", "Unexpected rollback or error")
    target, initial, verified = (result.get(key) for key in ("target_rate_hz", "initial_rate_hz", "verified_rate_hz"))
    require(type(target) is int and target in (44100, 48000) and type(initial) is int and initial in (44100, 48000)
            and type(verified) is int and verified == target, "Invalid or mismatched rate readback")
    require(expected_target is None or target == expected_target, "Rate target differs from requested target")
    writes, reads, total = (result.get(key) for key in ("write_attempts", "read_attempts", "control_transfer_attempts"))
    changed = initial != target
    require(integer(writes) and writes == (3 if changed else 1), "Unexpected control-write count")
    require(integer(reads) and (3 if changed else 1) <= reads <= (12 if changed else 4), "Unbounded/missing control reads")
    require(integer(total) and total == writes + reads and total <= 15, "Control attempt count mismatch")
    require(result.get("device_may_have_changed") is changed, "Possible device effect contradicts transaction path")
    utc(result.get("utc"))
    return result


def validate(folder, expected_native_sha256=None, expected_target=None):
    folder = Path(folder).resolve(strict=True)
    run = read_json(folder / "run.json")
    require(run.get("schema") == "sl3.usbdk.traced-run.v1" and run.get("mode") == "Rate", "A traced Rate-mode record is required")
    require(run.get("completed") is True and run.get("error") is None
            and integer(run.get("nativeExitCode")) and run["nativeExitCode"] == 0, "Rate scenario did not complete successfully")
    require(run.get("secureBootBefore") is True and run.get("secureBootAfter") is True
            and run.get("recoveryConfirmed") is True and run.get("driverChanges") is False, "Driver/security baseline recovery not confirmed")
    require(run.get("rateRestorationAttempted") is False and run.get("deviceRateEffectUnknown") is False, "Rate effect unresolved or unexpected restoration")
    for name, field in (("before-state.json", "beforeStateSha256"), ("after-state.json", "afterStateSha256"),
                        ("rate/rate.json", "nativeRecordSha256"), ("prior-capture-validation.json", "priorCaptureValidationSha256")):
        read_json(folder / name)  # Size bound before hashing/reading the record again.
        require(digest(folder / name).lower() == str(run.get(field, "")).lower(), f"Evidence hash changed: {name}")
    require(state_contract(read_json(folder / "before-state.json")) == state_contract(read_json(folder / "after-state.json")),
            "Recorded driver/security/application contracts differ")
    sha = run.get("nativeSha256", "")
    require(isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdefABCDEF" for c in sha), "Missing native identity")
    require(expected_native_sha256 is None or sha.lower() == expected_native_sha256.lower(), "Different native executable")
    prior = read_json(folder / "prior-capture-validation.json")
    require(prior.get("valid") is True and str(prior.get("nativeSha256", "")).lower() == sha.lower()
            and type(prior.get("reportedRateHz")) is int and prior["reportedRateHz"] in (44100, 48000), "Missing same-build validated capture prerequisite")
    require(integer(run.get("traceExitCode")) and run["traceExitCode"] == 0
            and run.get("traceCleanupConfirmed") is True, "Trace did not retire cleanly")
    stats = capture.trace_statistics(folder / "events.xml")
    require(stats == run.get("traceStats"), "Trace statistics/hash mismatch")
    require(stats["eventsLost"] == 0 and stats["buffersLost"] == 0 and stats["eventCount"] > 0, "Trace is empty or lossy")
    trace = read_json(folder / "trace/capture.json")
    require(trace.get("status") == "window completed" and not trace.get("deleteError")
            and trace.get("session") == stats["session"]
            and trace.get("startedUtc") == run.get("traceStartedUtc")
            and trace.get("stoppedUtc") == run.get("traceStoppedUtc"), "Trace identity/window mismatch")
    etls = list((folder / "trace").glob("*.etl"))
    require(len(etls) == 1 and 0 < etls[0].stat().st_size <= 65 * 1024 * 1024
            and digest(etls[0]).lower() == str(run.get("etlSha256", "")).lower(), "ETL identity/size mismatch")
    target = run.get("targetRate")
    require(type(target) is int and target in (44100, 48000)
            and (expected_target is None or target == expected_target), "Missing or changed requested target")
    native = native_result(folder / "rate/rate.json", target)
    require(run.get("lastKnownDeviceMayHaveChanged") is native["device_may_have_changed"]
            and run.get("lastIoRetired") is True, "Runner/native effect or retirement mismatch")
    # Native SYSTEMTIME records whole milliseconds; wrapper launch/exit times
    # have finer precision. Compare that one-ms observation interval rather
    # than falsely rejecting a fast result rounded below its launch timestamp.
    native_time = utc(native["utc"])
    launch, completed = utc(run.get("nativeStartedUtc")), utc(run.get("nativeCompletedUtc"))
    require(utc(trace["startedUtc"]) <= launch <= completed <= utc(trace["stoppedUtc"])
            and launch <= native_time + timedelta(milliseconds=1) and native_time <= completed,
            "Native rate operation lies outside trace window")
    return {"valid": True, "scope": "Recorded rate diagnostic consistency only", "nativeSha256": sha,
            "initialRateHz": native["initial_rate_hz"], "verifiedRateHz": native["verified_rate_hz"],
            "deviceMayHaveChanged": native["device_may_have_changed"], "rateRestorationAttempted": False,
            "limits": ["Not hardware attestation or permission to execute a test",
                       "Trace header integrity does not establish USB command/payload correlation",
                       "Driver/security snapshot recovery does not restore the prior sample rate",
                       "Physical clock, audio, latency and Serato/DVS remain unverified"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", nargs="?")
    parser.add_argument("--native-record")
    parser.add_argument("--observation-record",help="Check completed v2 observation consistency without qualifying a successful experiment")
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-target", type=int, choices=(44100, 48000))
    args = parser.parse_args()
    try:
        require(sum(map(bool,(args.run_directory,args.native_record,args.observation_record)))==1, "Choose one run directory, native record or observation record")
        if args.observation_record:
            record=observation_result(args.observation_record,args.expected_target)
            result={'validObservation':True,'scope':'Recorded v2 observation consistency only; not a traced experiment pass',
                    'operationVerified':record['diagnostic_error']==0,'readbackRateHz':record['readback_rate_hz'],
                    'deviceMayHaveChanged':record['device_may_have_changed'],
                    'cleanupConfirmed':record['last_io_retired'] and record['redirect_closed'],'rateRestorationVerified':False}
        elif args.native_record:
            record = native_result(args.native_record, args.expected_target)
            result = {"valid": True, "scope": "Native result consistency only", "verifiedRateHz": record["verified_rate_hz"]}
        else:
            result = validate(args.run_directory, args.expected_native_sha256, args.expected_target)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({"valid": False, "error": str(error), "rateEffectEstablishedByValidation": False}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
