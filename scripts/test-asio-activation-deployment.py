"""On-demand bundle contract and isolated Windows install/removal/recovery suites; no hardware."""
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/prepare-asio-activation-deployment.py'
NEW = runpy.run_path(str(TOOL))
API = NEW['API']
require = API['require']
sha = lambda p: API['digest'](p.read_bytes())
SUITES = ('test-asio-file-stage.py', 'test-asio-file-cleanup.py', 'test-asio-install.py', 'test-asio-uninstall.py',
          'test-asio-recover-install.py', 'test-asio-recover-uninstall.py', 'test-asio-recover-files.py', 'test-asio-recover-copy.py')


def main():
    require(len(sys.argv) == 2 or (len(sys.argv) == 3 and sys.argv[2] == '--application-bound'),
            'Build manifest and optional --application-bound required')
    build = Path(sys.argv[1]).absolute()
    application_bound = len(sys.argv) == 3
    mode = API['APPLICATION_ACTIVATION_MODE'] if application_bound else API['ACTIVATION_MODE']
    source_paths = sorted(set([TOOL, Path(__file__), ROOT/'scripts/rebind-asio-deployment.py',
        ROOT/'scripts/prepare-serato-session-capsule.py', ROOT/'scripts/serato-session-capsule.py',
        *(ROOT/'scripts'/name for name in SUITES),
        *(ROOT/'scripts').glob('asio-*.py'), *(ROOT/'scripts').glob('prepare-asio-*.py')]))
    source_pins = {p.relative_to(ROOT).as_posix():sha(p) for p in source_paths}
    identity = uuid.uuid4().hex
    folder = ROOT/'artifacts/build/activation-deployment-tests'/identity
    origin = ROOT/'artifacts/build/deployment-bundles'/('activation-deployment-origin-'+identity)
    bundle = ROOT/'artifacts/build/deployment-bundles'/('activation-deployment-'+identity)
    installation = Path(os.environ['ProgramFiles'])/'SL3 Rebuild'/('activation-diagnostic-'+identity)
    pointer = Path(os.environ['LOCALAPPDATA'])/'SL3Rebuild'/('unused-activation-'+identity)/'reserved.txt'
    require(not installation.exists() and not pointer.parent.exists(), 'Unoccupied planned locations required')
    cases = []

    def good(name, operation):
        value = operation(); cases.append({'name': name, 'passed': True}); return value

    def refused(name, operation):
        try:
            operation()
        except (ValueError, FileNotFoundError):
            cases.append({'name': name, 'passed': True}); return
        raise AssertionError('Unexpected admission: '+name)

    API['prepare'](build, sha(build), ROOT/'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10', origin,
                   installation, pointer, True)
    origin_sha = sha(origin/'bundle-manifest.json')
    origin_before = {p.name: sha(p) for p in origin.iterdir()}
    result = good('prepare-protected-destination-activation-records', lambda: NEW['prepare'](origin, origin_sha, build, sha(build), bundle, application_bound))
    expected = result['bundleManifestSha256']
    good('verify-v2', lambda: API['verify'](bundle, expected))
    good('legacy-v1-still-verifies', lambda: API['verify'](origin, origin_sha))
    good('temporary-session-still-admits-locator-plan', lambda: API['require_session_locator'](API['record']((origin/'deployment-plan.json').read_bytes())))
    manifest, payload = API['capture_bundle'](bundle, expected)
    refused('temporary-session-refuses-self-starting-plan', lambda: API['require_session_locator'](API['record'](payload['deployment-plan.json'])))
    prepare_capsule = runpy.run_path(str(ROOT/'scripts/prepare-serato-session-capsule.py'))['prepare']
    refused('actual-capsule-preparation-refuses-before-session-output', lambda: prepare_capsule(
        Path(os.environ['ProgramFiles'])/'Serato/Serato DJ Pro/Serato DJ Pro.exe', bundle, expected))
    require(len(payload) == len(API['REQUIRED'])+2 and manifest['schema'] == 'sl3.deployment-bundle.v2', 'Versioned exact activation inventory')
    header = API['ACTIVATION_HEADERS'][mode].encode() + b'\n'
    require(manifest['activationMode'] == mode and payload['sl3-asio.conf'].startswith(header) and
            str(pointer).encode() not in payload['sl3-asio.conf'] and str(pointer).encode() not in payload['sl3-worker.conf'],
            'Runtime activation records do not use the legacy pointer')
    good('all-native-payload-bytes-preserved', lambda: require(all(payload[n] == (origin/n).read_bytes() for n in
         ('sl3_asio.dll','sl3_broker_controller.exe','sl3_usbdk.exe','UsbDkHelper.dll')), 'Native bytes unchanged'))
    refused('existing-output-preserved', lambda: NEW['prepare'](origin, origin_sha, build, sha(build), bundle))
    for name, key, value in [('unknown-version','schema','sl3.deployment-bundle.v3'),
                             ('v1-cannot-carry-activation','schema','sl3.deployment-bundle.v1'),
                             ('unknown-activation-mode','activationMode','service'),
                             ('reviewed-timing-cannot-mask-diagnostic','timingMode','measured')]:
        bad = copy.deepcopy(manifest); bad[key] = value
        refused(name, lambda bad=bad: API['verify_payloads'](bad, payload))
    for name in ('sl3-asio.conf', 'sl3-worker.conf', 'sl3-timing.conf'):
        changed = {**payload, name: payload[name]+b'kind=simulated\n'}
        bad = copy.deepcopy(manifest); bad['files'][name] = {'bytes':len(changed[name]), 'sha256':API['digest'](changed[name])}
        refused('rehashed-'+name+'-refused', lambda bad=bad,changed=changed: API['verify_payloads'](bad,changed))
    other = API['ACTIVATION_MODE'] if application_bound else API['APPLICATION_ACTIVATION_MODE']
    entry = payload['sl3-asio.conf'].replace(header, API['ACTIVATION_HEADERS'][other].encode() + b'\n', 1)
    changed = {**payload, 'sl3-asio.conf': entry}
    bad = copy.deepcopy(manifest)
    bad['files']['sl3-asio.conf'] = {'bytes': len(entry), 'sha256': API['digest'](entry)}
    refused('rehashed-entry-for-other-mode-refused', lambda: API['verify_payloads'](bad, changed))
    for name, key, value in [('unbounded-lifetime','maximumLifetimeMs',43200000), ('service-policy','serviceCreated',True),
                             ('claimed-measured-latency','latencyAvailable',True), ('pointer-runtime-policy','sessionPointerUsed',True)]:
        plan = API['record'](payload['deployment-plan.json']); plan[key] = value
        changed = {**payload,'deployment-plan.json':API['encoded'](plan)}
        bad = copy.deepcopy(manifest); bad['files']['deployment-plan.json'] = {
            'bytes':len(changed['deployment-plan.json']),'sha256':API['digest'](changed['deployment-plan.json'])}
        refused(name, lambda bad=bad,changed=changed: API['verify_payloads'](bad,changed))
    require(API['allowed_receipt_inventory'](manifest['files'].keys() | {'bundle-manifest.json'}) and
            not API['allowed_receipt_inventory'](manifest['files'].keys() | {'bundle-manifest.json','../foreign'}),
            'Receipt admission cannot expand fixed inventories')
    cases.append({'name':'receipt-path-expansion-refused','passed':True})
    rebind = runpy.run_path(str(ROOT/'scripts/rebind-asio-deployment.py'))['rebind']
    rebound = good('v2-account-path-rebinding', lambda: rebind(bundle, expected,
        ROOT/'analysis'/('sl3-deployment-rebound-activation-'+identity),
        installation.with_name('activation-rebound-'+identity), pointer.with_name('other-reserved.txt')))
    rebound_manifest, rebound_payload = API['capture_bundle'](Path(rebound['directory']), rebound['bundleManifestSha256'])
    require(rebound_manifest['activationMode'] == mode and rebound_payload['sl3-asio.conf'].startswith(header),
            'Rebinding preserves the activation mode')
    require({name for name in payload if payload[name] != rebound_payload[name]} ==
            {'provenance.json','deployment-plan.json','sl3-asio.conf','sl3-worker.conf'}, 'Rebinding changes metadata/path records only')
    folder.mkdir(parents=True)
    index = folder/'index.json'
    index.write_bytes(API['encoded']({'positiveBundle':bundle.relative_to(ROOT).as_posix(),'bundleManifestSha256':expected}))
    package_pointer = folder/'test-package-pointer.json'
    package_pointer.write_bytes(API['encoded']({'directory':str(folder),'indexSha256':sha(index)}))
    suite_reports = []
    for name in SUITES:
        try:
            child = subprocess.run([sys.executable,'-I','-B',str(ROOT/'scripts'/name),str(package_pointer)],
                                   capture_output=True,timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as error:
            (folder/(name+'-stdout.txt')).write_bytes(error.stdout or b'')
            (folder/(name+'-stderr.txt')).write_bytes(error.stderr or b'')
            (folder/(name+'-timeout.json')).write_bytes(API['encoded']({'timedOut':True,'limitSeconds':900,'passed':False}))
            raise
        (folder/(name+'-stdout.txt')).write_bytes(child.stdout)
        (folder/(name+'-stderr.txt')).write_bytes(child.stderr)
        require(child.returncode == 0, name+': '+child.stderr.decode('utf-8',errors='replace'))
        summary = API['record'](child.stdout)
        require(summary['passed'] is True, 'Isolated suite did not pass')
        suite_reports.append({'suite':name,'cases':summary['cases'],'stdoutSha256':sha(folder/(name+'-stdout.txt')),
                              'stderrSha256':sha(folder/(name+'-stderr.txt')),'summary':summary})
        print(json.dumps({'suite':name,'passed':True,'cases':summary['cases']}),flush=True)
    require(origin_before == {p.name:sha(p) for p in origin.iterdir()}, 'Origin review package preserved')
    API['verify'](bundle,expected)
    require(all(sha(ROOT/name) == value for name,value in source_pins.items()), 'Deployment test source changed during run')
    require(not installation.exists() and not pointer.parent.exists(), 'No planned native installation or user pointer writes')
    report = {'schema':'sl3.activation-deployment-tests.v1','passed':True,'cases':cases,'suites':suite_reports,
              'bundle':str(bundle),'bundleManifestSha256':expected,'buildManifestSha256':sha(build),'activationMode':mode,
              'sourceSha256':source_pins,
              'productionInstallationPerformed':False,'nativeDeviceAccess':False,'seratoLaunched':False,
              'nativePackageBinariesExecuted':False,'originBundleUnchanged':True,'plannedDestinationsUnchanged':True}
    path = folder/'result.json'; path.write_bytes(API['encoded'](report))
    print(json.dumps({'passed':True,'contractCases':len(cases),'isolatedCases':sum(x['cases'] for x in suite_reports),
                      'report':str(path),'bundle':str(bundle)},indent=2))


if __name__ == '__main__':
    main()
