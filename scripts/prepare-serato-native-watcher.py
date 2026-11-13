"""Assemble a private, relocatable native watcher payload without installing it."""

import argparse
import json
from pathlib import Path
import runpy
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "artifacts/build"
RUNTIME = BUILD / "embedded-python-setup-20261106"
RUNTIME_SHA = "8844fb82d10df8c34d20d8a450d8f7e38c3271e41175d04cc469655820dc8152"
SOURCES = (
    "setup-serato-native-watcher.py", "watch-serato-native-startup.py", "run-serato-native-descriptor-trial.py",
    "run-serato-memory-descriptor-probe.py",
    "run-serato-startup-session.py", "serato-owned-notice-poll.py", "inspect-sl3-session-readiness.py",
    "serato-memory-descriptor-profile.json", "serato-on-demand-test.py", "prepare-asio-deployment.py",
    "asio-file-stage.py", "asio-install-journal.py", "asio-install.py", "asio-registry.py",
    "asio-install-base.py", "asio-runtime-check.py", "asio-uninstall.py",
    "read-installed-asio-start.py", "read-retained-start-result.py",
)


def prepare(plan_path, plan_sha, output, application_lifetime=False, buffer_frames=64, output_deadline_trial=False,
            output_ready_trial=False):
    trial = runpy.run_path(str(ROOT / "scripts/run-serato-native-descriptor-trial.py"))
    require, digest = trial["require"], trial["digest"]
    require(output.parent == BUILD and output.name.startswith("serato-native-watcher-") and not output.exists(),
            "Fresh watcher payload directory under artifacts/build required")
    plan = trial["read_plan"](plan_path, plan_sha)
    notice = trial["NOTICE"]
    require(plan["noticeLibrarySha256"] == notice["RETIRING_HELPER_SHA"], "Self-restoring notice helper plan required")
    probe = trial["PROBE"]
    driver = probe["driver"](output_ready_trial=output_ready_trial, application_lifetime=application_lifetime, buffer_frames=buffer_frames,
                             output_deadline_trial=output_deadline_trial)
    runtime_api = runpy.run_path(str(ROOT / "scripts/prepare-embedded-python.py"))
    runtime = runtime_api["verify"](RUNTIME, RUNTIME_SHA)
    require(runtime["dependencyProfile"] == "compatibility-setup" and runtime["instrumentationIncluded"] is False and
            set(runtime["dependencies"]) == {"pefile"}, "Reviewed setup-only Python runtime required")
    source_paths = [ROOT / "scripts" / name for name in SOURCES] + [ROOT / "LICENSE"]
    files = {path.relative_to(ROOT).as_posix(): (path, digest(path)) for path in source_paths}
    files[trial["PACKAGED_PLAN"].name] = (plan_path, plan_sha)
    files[trial["LIBRARY"].relative_to(ROOT).as_posix()] = (trial["LIBRARY"], plan["librarySha256"])
    helper = notice["RETIRING_HELPER"]
    files[helper.relative_to(ROOT).as_posix()] = (helper, plan["noticeLibrarySha256"])
    runtime_pins = {name: row["sha256"] for name, row in runtime["files"].items()}
    runtime_pins["runtime-manifest.json"] = RUNTIME_SHA
    for name, identity in runtime_pins.items():
        files[f"runtime/python/{name}"] = (RUNTIME / name, identity)
    driver_pins = {name: row["sha256"] for name, row in driver.manifest["files"].items()}
    driver_pins["bundle-manifest.json"] = driver.expected
    for name, identity in driver_pins.items():
        source = driver.bundle / name
        files[source.relative_to(ROOT).as_posix()] = (source, identity)

    with tempfile.TemporaryDirectory(prefix="watcher-payload-", dir=BUILD) as scratch:
        pending = Path(scratch) / output.name
        inventory = {}
        for name, (source, identity) in sorted(files.items()):
            require(source.is_file() and not source.is_symlink(), "Regular watcher payload input required: " + name)
            destination = pending / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            require(digest(destination) == identity, "Watcher payload differs: " + name)
            inventory[name] = {"sha256": identity, "bytes": destination.stat().st_size}
        bootstrap = pending / "watch.pyw"
        bootstrap.write_text(
            "import runpy\nfrom pathlib import Path\n\n"
            "watcher = Path(__file__).resolve().parent / 'scripts/watch-serato-native-startup.py'\n"
            f"raise SystemExit(runpy.run_path(str(watcher))['run_registered']({plan_sha!r}))\n",
            encoding="utf-8", newline="\n")
        inventory[bootstrap.name] = {"sha256": digest(bootstrap), "bytes": bootstrap.stat().st_size}
        record = {"schema": "sl3.private-native-watcher-payload.v1", "startupPlanSha256": plan_sha,
                  "applicationLifetime": application_lifetime, "diagnosticBufferFrames": buffer_frames,
                  "runtimeManifestSha256": RUNTIME_SHA, "files": inventory}
        if output_deadline_trial:
            record["outputDeadlineTrial"] = True
        if output_ready_trial:
            record["outputReadyTrial"] = True
        manifest = pending / "watcher-payload.json"
        with manifest.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
        manifest_sha = digest(manifest)
        pending.rename(output)
    return {"directory": str(output), "manifestSha256": manifest_sha, "files": len(inventory),
            "bytes": sum(row["bytes"] for row in inventory.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--startup-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--application-lifetime", action="store_true", help="Use the published 64-frame beta driver package")
    parser.add_argument("--buffer-frames", type=int, choices=(32, 64), default=64)
    parser.add_argument("--output-deadline-trial", action="store_true", help="Use the matched private diagnostic build")
    parser.add_argument("--output-ready-trial", action="store_true", help="Use the private synchronous 64-frame build")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.startup_plan.absolute(), args.expected_plan_sha256, args.output.absolute(),
                                 args.application_lifetime, args.buffer_frames, args.output_deadline_trial,
                                 args.output_ready_trial), indent=2))
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
