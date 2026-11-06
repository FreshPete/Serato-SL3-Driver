"""Shared source-bound session configuration; no installation at import time."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
PERMIT_NAME = '8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-permit'
SOURCES = (
    'scripts/serato-session-capsule.py','scripts/prepare-serato-session-capsule.py',
    'scripts/serato-session-installer.py','scripts/serato-session-broker.py',
    'scripts/asio-install.py','scripts/asio-install-base.py','scripts/asio-uninstall.py','scripts/asio-install-journal.py',
    'scripts/asio-file-stage.py','scripts/asio-registry.py','scripts/asio-runtime-check.py',
    'scripts/prepare-asio-deployment.py','scripts/asio-diagnostic-session.py','scripts/serato-installer-permit.py',
    'src/installer/SessionLauncher.cs',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def encoded(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True)+'\n').encode('ascii')


def source_hashes():
    return {name:sha(ROOT/name) for name in SOURCES}


def module(name, function):
    return runpy.run_path(str(ROOT/'scripts'/name))[function]


def verify(path, expected):
    path = Path(path).absolute()
    require(path.name == 'session-capsule.json' and path.stat().st_size <= 65536 and
            re.fullmatch('[0-9a-f]{64}',expected) and sha(path) == expected,'Session capsule identity differs')
    record = json.loads(path.read_bytes())
    require(record['schema'] == 'sl3.session-capsule.v1' and record['projectRoot'] == str(ROOT),
            'Session capsule project binding differs')
    require(record['sessionDirectory'] == str(path.parent),'Session capsule was moved; prepare a new binding')
    require(record['sources'] == source_hashes(),'Reviewed session sources differ')
    require(type(record['brokerLimitMs']) is int and record['brokerLimitMs'] == 600000 and
            type(record['captureOutput']) is bool,'Unsupported session policy')
    python = Path(record['python']['path']); application = Path(record['application']['path'])
    require(python.is_absolute() and python == Path(sys.executable).absolute() and
            sha(python) == record['python']['sha256'],'Reviewed Python interpreter differs')
    require(application.is_absolute() and application.name == 'Serato DJ Pro.exe' and
            record['application']['sha256'] == APP_SHA and sha(application) == APP_SHA,'Reviewed application differs')
    require(record['permitPath'] == str(application.parent/'bundles'/PERMIT_NAME),'Permit must belong to the reviewed application')
    bundle = Path(record['bundle']['path'])
    module('prepare-asio-deployment.py','verify')(bundle,record['bundle']['sha256'])
    plan = json.loads((bundle/'deployment-plan.json').read_bytes())
    module('prepare-asio-deployment.py','require_session_locator')(plan)
    require(plan['timingMode'] == 'unmeasured-diagnostic-44100-128','Reviewed diagnostic package required')
    return record,plan,path.parent


def layout(directory):
    return {name:directory/name for name in ('install-receipt.json','broker-session','broker-clean.json',
        'broker-timing.txt','broker-input.conf','output-capture')}


def require_retired(directory,plan):
    require(not Path(plan['pointerPath']).exists(),'An active broker pointer remains')
    files = layout(directory)
    report = json.loads(files['broker-clean.json'].read_bytes())
    require(report.get('controllerExited') is True,'Broker controller retirement is unverified')
    if report.get('brokerStarted') is False:
        session = files['broker-session']
        require(session.with_suffix('.closed').is_file() and not session.exists() and
                not session.with_suffix('.stdout').exists() and not session.with_suffix('.stderr').exists() and
                not session.with_suffix('.pointer.json').exists(),'Unused broker handoff is not closed')
    else:
        require(all(report.get(key) is True for key in ('processExited','jobEmpty','ioRetiredVerified','deviceReleasedVerified')),
                'Broker worker retirement is incomplete')
        raw = json.loads((files['broker-session']/'result.json').read_bytes())
        require(report == {**raw,'controllerExited':True},'Broker cleanup report differs from its owned result')
