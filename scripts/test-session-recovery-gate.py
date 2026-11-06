"""Recovery handoff policy: fail closed without executing a repair or elevation."""
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
decision=runpy.run_path(str(ROOT/'scripts/recover-serato-session.py'))['decision']
base={'schema':'sl3.session-recovery-check.v1','ordinaryToken':True,
    'phase':'recovery_required','originalSetupClean':False,'activeSessionObserved':False,
    'issues':[],'brokerRetirementReported':True,'resourcePlan':{'protectedSessionOwnerPresent':True},
    **{name:False for name in ('repairAttempted','filesWritten','registryWritten','elevationRequested','deviceOpened')}}
cases=[]
def check(name,report,expected):
    assert decision(report)==expected,name
    cases.append({'name':name,'passed':True,'exitCode':expected})
check('verified-retired-owned-interruption-requires-handoff',base,10)
clean={**base,'phase':'clean','originalSetupClean':True}
check('clean-needs-no-elevation',clean,0)
for phase in ('active_session','review_required','broker_retirement_required','unknown'):
    check(phase,{**base,'phase':phase},3)
for name in ('ordinaryToken','brokerRetirementReported'):
    check('missing-'+name,{**base,name:False},3)
for name in ('repairAttempted','filesWritten','registryWritten','elevationRequested','deviceOpened'):
    check('unexpected-'+name,{**base,name:True},3)
check('missing-protected-owner',{**base,'resourcePlan':{}},3)
check('live-owner',{**base,'activeSessionObserved':True},3)
check('preflight-issue',{**base,'issues':[{'record':'preflight'}]},3)
check('uncertain-clean',{**clean,'originalSetupClean':False},3)
check('missing-report',{},3)
print(json.dumps({'cases':cases,'repairExecuted':False,'elevationRequested':False},indent=2))
