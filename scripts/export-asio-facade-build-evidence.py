"""Pin the tested ASIO facade/ABI checkpoint; no execution or USB access."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import pefile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def export():
    builds = []
    for configuration in ("Release", "Debug"):
        folder = ROOT / "artifacts/build/native"
        path = folder / f"native-build-{configuration}.json"
        build = load(path)
        for name, expected in build["inputs"].items():
            require(digest(ROOT / name) == expected.upper(), f"Stale input: {name}")
        require(digest(ROOT / "scripts/build-native.ps1") == build["buildScriptSha256"], "Stale build script")
        log = folder / f"ctest-{configuration}.log"
        require(digest(log) == build["ctestLogSha256"], "Stale CTest log")
        require("100% tests passed, 0 tests failed out of 25" in log.read_text(encoding="utf-8"), "Incomplete CTest suite")
        require(len(build["ctestTests"]) == 25 and "sl3_asio_session_tests" in build["ctestTests"], "Actual ASIO ABI test absent")
        require(build["streamSession"]["protocolVersion"] == 2, "Wrong session version")
        host = build["asioComponent"]["hostSession"]
        facade = build["asioComponent"]["driverFacade"]
        fixture_path = folder / configuration / "sl3_asio_session_fixture.dll"
        require(digest(fixture_path) == facade["sessionFixtureDllSha256"], "Stale facade DLL")
        production = pefile.PE(str(folder / configuration / "sl3_asio.dll"))
        fixture = pefile.PE(str(fixture_path))
        exports = sorted(x.name.decode() for x in fixture.DIRECTORY_ENTRY_EXPORT.symbols if x.name)
        production_exports = sorted(x.name.decode() for x in production.DIRECTORY_ENTRY_EXPORT.symbols if x.name)
        imports = sorted(x.dll.decode() for x in fixture.DIRECTORY_ENTRY_IMPORT)
        require(exports == ["DllCanUnloadNow", "DllGetClassObject", "sl3_test_configure"], "Unexpected test DLL exports")
        require(production_exports == ["DllCanUnloadNow", "DllGetClassObject"], "Test provider escaped into production")
        require(not any("usbdk" in x.lower() for x in imports), "Native helper imported by ASIO fixture")
        require(facade["testsPassed"] and facade["actualAsioVtableSessionsTested"] and facade["timingProfileSynthetic"] and not facade["productionProviderConfigured"], "Unexpected facade claim")
        for field, name in (("librarySha256", "sl3_driver_facade.lib"), ("testExecutableSha256", "sl3_driver_facade_tests.exe"), ("sessionAbiTestExecutableSha256", "sl3_asio_session_tests.exe")):
            require(digest(folder / configuration / name) == facade[field], f"Stale facade binary: {name}")
        for field, name in (("librarySha256", "sl3_host_session.lib"), ("testExecutableSha256", "sl3_host_session_tests.exe")):
            require(digest(folder / configuration / name) == host[field], f"Stale host binary: {name}")
        for name, expected in (
            ("sl3_usbdk.exe", build["usbdk"]["executableSha256"]),
            ("sl3_session_fixture.exe", build["streamSession"]["fixtureSha256"]),
            ("sl3_session_tests.exe", build["streamSession"]["testExecutableSha256"]),
            ("sl3_asio.dll", build["asioComponent"]["comDllSha256"]),
        ):
            require(digest(folder / configuration / name) == expected, f"Stale peer binary: {name}")
        require(host["testsPassed"] and not host["physicalAudioTested"] and not host["comDllConnected"], "Unexpected readiness claim")
        builds.append({"configuration": configuration, "utc": build["utc"], "manifestSha256": digest(path),
                       "ctestLogSha256": digest(log), "ctestTests": build["ctestTests"], "hostSession": host, "driverFacade": facade, "testDllExports": exports, "productionDllExports": production_exports, "testDllImports": imports,
                       "streamSession": build["streamSession"], "inputs": build["inputs"],
                       "nativeSha256": build["usbdk"]["executableSha256"],
                       "productionComDllSha256": build["asioComponent"]["comDllSha256"]})
    without = ROOT / "artifacts/build/native-without-sdk/ctest-Release.log"
    require("100% tests passed, 0 tests failed out of 18" in without.read_text(encoding="utf-8"), "SDK-free suite incomplete")
    cache = (without.parent / "CMakeCache.txt").read_text(encoding="utf-8")
    require("SL3_BUILD_ASIO_COMPONENT:BOOL=OFF" in cache and "SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk" in cache, "SDK-free configuration differs")
    preflight_path = ROOT / "tests/results/local/usbdk-preflight-15.json"
    preflight = load(preflight_path)
    require(not preflight["helperLoaded"] and not preflight["installedDriver"] and preflight["audioSubmissions"] == 0, "Unexpected live USB state")
    require(preflight["nativeSha256"] == builds[0]["nativeSha256"], "Preflight used a different native binary")
    workers_path = ROOT / "tests/results/local/asio-facade-workers.json"
    workers = load(workers_path)
    require(workers["count"] == 0 and workers["workers"] == [], "Native worker remains")
    return {"utc": datetime.now(timezone.utc).isoformat(),
            "scope": "ASIO facade and actual unregistered ASIO DLL ABI over simulated worker sessions with synthetic timing; native absent-helper rejection only",
            "builds": builds, "sdkFree": {"testsPassed": 18, "ctestLogSha256": digest(without), "sdkRootDeliberatelyAbsent": True},
            "preflight": {"sha256": digest(preflight_path), "record": preflight},
            "workersAfterTests": {"sha256": digest(workers_path), "record": workers},
            "productionAsioInitializationAvailable": False, "physicalAudioTested": False,
            "currentSeratoDvsValidated": False, "macOSValidated": False,
            "exportScriptSha256": digest(Path(__file__).resolve())}


if __name__ == "__main__":
    output = ROOT / "docs/evidence/asio-facade-build.json"
    output.write_text(json.dumps(export(), indent=2) + "\n", encoding="utf-8")
    print(f"Validated and wrote {output.relative_to(ROOT)}")
