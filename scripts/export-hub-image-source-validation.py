"""Verify retained validate-only evidence and publish a compact local report."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    positive_path = ROOT / 'analysis/hub-image-source-validation-20261031-03.json'
    tests_path = ROOT / 'analysis/hub-image-source-validation-tests-20261031-02.json'
    ast_path = ROOT / 'analysis/hub-image-source-validation-ast.json'
    positive, tests, ast = read(positive_path), read(tests_path), read(ast_path)
    require(positive['valid'] and positive['producer']['tokenQueried'] and
            positive['producer']['elevated'] is False and positive['producer']['elevationType'] == 3,
            'Actual limited-token positive differs')
    require(positive['before']['error']['hresult'] == positive['after']['error']['hresult'] == '0x80300002' and
            positive['commitMode'] == 4096 and len(positive['validationItems']) == 2, 'Validation/absence differs')
    require(len(tests['checks']) == 16 and tests['validatorSha256'] == positive['sourceSha256'] ==
            ast['sourceSha256'] == sha(ROOT / 'scripts/validate-hub-image-source.ps1'), 'Validator source/results differ')
    require(tests['testSourceSha256'] == sha(ROOT / 'scripts/test-hub-image-source-validation.py') and
            ast['literalCommitMode'] == 4096 and ast['prohibitedOperationalCalls'] == 0, 'Test/AST scope differs')
    for field, name in [('preparerSha256', 'scripts/prepare-hub-image-source.ps1'),
                        ('processInspectorSha256', 'scripts/inspect-process.psm1')]:
        require(positive[field] == sha(ROOT / name), 'Source dependency differs')
    require(positive['preparationRecordSha256'] == tests['preparationSha256'] ==
            sha(ROOT / 'analysis/prepared-hub-image-source-20261031-02.json'), 'Prepared-input binding differs')
    require(all(positive[key] is False for key in ('sourceStarted', 'runtimeFlagForwardingVerified',
            'independentStopValidated', 'readinessAdmission')), 'Unobserved scope was upgraded')
    sdk = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.19041.0')
    pla, errors = sdk / 'um/pla.h', sdk / 'shared/winerror.h'
    require(re.search(r'plaValidateOnly\s*=\s*0x1000', pla.read_text(encoding='utf-8-sig')),
            'SDK validate-only constant differs')
    error_text = errors.read_text(encoding='utf-8-sig')
    require(re.search(r'PLA_E_DCS_NOT_FOUND\s+_HRESULT_TYPEDEF_\(0x80300002L\)', error_text) and
            re.search(r'PLA_S_PROPERTY_IGNORED\s+_HRESULT_TYPEDEF_\(0x00300100L\)', error_text), 'SDK status constants differ')
    result = {'scope': 'Actual limited-token PLA validate-only API and 16 CLI cases; no persistent commit, trace start or USB request',
              'positive': positive, 'positiveReportSha256': sha(positive_path), 'actualCliChecks': tests['checks'],
              'cliTestReportSha256': sha(tests_path), 'testSourceSha256': tests['testSourceSha256'],
              'astAudit': ast, 'astAuditSha256': sha(ast_path), 'exporterSha256': sha(Path(__file__)),
              'sdkFacts': {'plaValidateOnly': 4096, 'PLA_E_DCS_NOT_FOUND': '0x80300002',
                           'PLA_S_PROPERTY_IGNORED': '0x00300100', 'plaHeaderSha256': sha(pla),
                           'winerrorHeaderSha256': sha(errors)},
              'productionNativeInputsChanged': False, 'runtimeFlagForwardingVerified': False,
              'independentStopValidated': False, 'readinessAdmission': False,
              'apiDocs': ['https://learn.microsoft.com/en-us/windows/win32/api/pla/ne-pla-commitmode',
                          'https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-idatacollectorset-commit'],
              'limits': ['Commit-time validation does not verify effective live session properties or image-event emission.',
                         'Only exact ignored warnings for blank inactive fields are accepted.',
                         'No separate service-process execution, new source, independent expiry or USB/app result is inferred.']}
    (ROOT / 'docs/evidence/hub-image-source-validation-20261031.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Verified current API/CLI/AST/source bindings and SDK constants; wrote compact evidence')


if __name__ == '__main__':
    main()
