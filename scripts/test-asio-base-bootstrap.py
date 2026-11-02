"""Real ordinary-token bootstrap/recovery faults in workspace fixtures only."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('base_bootstrap_tests',ROOT/'scripts/asio-install-base.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
j=m.journal_module();s=j.stage_module()


def main():
    s.require(not s.elevated(),'Ordinary-token workspace suite required')
    policy=s.Policy(s.user_sid(),(s.SYSTEM,s.ADMINS,s.user_sid()))
    folder=ROOT/'artifacts/build/base-bootstrap-tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
    before=m.check_production_base();cases=[];details={}
    def case(name,action):
        value=action();cases.append({'name':name,'passed':True});details[name]=value;return value
    def fresh(name):
        base=folder/name
        with m.prepared_base(base,policy) as value:result=dict(value)
        return base,Path(result['bootstrapJournal']),result['bootstrapJournalSha256'],result
    def recover(base,path,digest):return m.recover_empty_base(base,path,digest,policy)
    def refused(action):
        try:action()
        except m.BasePreparationFailure as error:
            s.require(not error.report.get('successful',False),'Failure must not claim successful recovery');return error.report
        raise AssertionError('Expected refusal')
    def snapshot():return {p.name:j.digest(p.read_bytes()) for p in folder.iterdir() if p.is_file()}
    def positive():
        base,path,digest,receipt=fresh('positive');raw=path.read_bytes()
        parsed=j.parse(raw);s.require(len(parsed['records'])==2 and receipt['creationWitnessPersisted'],'Two complete durable records')
        sentinel=folder/'foreign-sibling.txt';sentinel.write_bytes(b'preserve sibling')
        value=recover(base,path,digest)
        s.require(value['successful'] and value['baseDeletionMarked'] and value['baseAbsentObserved'] and path.read_bytes()==raw and sentinel.read_bytes()==b'preserve sibling','Exact empty base only')
        return {'result':value,'sourceSha256':digest}
    result=case('witnessed-empty-base-removed-source-and-siblings-preserved',positive)
    path=next(p for p in folder.glob('positive.bootstrap-*.jsonl'))
    value=case('explicit-retry-observes-already-absent-base',lambda:recover(folder/'positive',path,result['sourceSha256']))
    s.require(value['baseAlreadyAbsentObserved'] and not value['baseDeletionMarked'],'Retry records observation, not another delete')
    base,path,digest,receipt=fresh('reused')
    def reuse():
        before_files=snapshot()
        with m.prepared_base(base,policy) as r:
            s.require(r['existingDirectoryReused'] and r['bootstrapJournal'] is None and not r['creationWitnessPersisted'],'Existing data never newly claimed')
        s.require(snapshot()==before_files,'No bootstrap file for reuse');return {'newJournal':False}
    case('existing-base-reuse-does-not-claim-new-creation',reuse)
    def contents(name,data):
        base,path,digest,_=fresh(name);file=base/data;file.write_bytes(b'preserve contents')
        value=refused(lambda:recover(base,path,digest));s.require(file.read_bytes()==b'preserve contents' and not value['baseDeletionMarked'],'Nonempty base preserved');return value
    case('foreign-content-refused',lambda:contents('foreign','foreign.txt'))
    case('installer-lock-content-refused',lambda:contents('locked-data','installer-lock.json'))
    def mismatch():
        base,path,digest,_=fresh('replaced');backup=folder/'replaced-original'
        s.require(base.resolve().is_relative_to(folder.resolve()) and backup.parent==folder,'Verified fixture move boundary')
        base.rename(backup)
        with m.prepared_base(base,policy):pass
        value=refused(lambda:recover(base,path,digest));s.require(base.exists() and backup.exists(),'Both original and replacement retained');return value
    case('replacement-directory-identity-refused',mismatch)
    base,path,digest,_=fresh('wrong-hash')
    case('wrong-reviewed-hash-refused',lambda:refused(lambda:recover(base,path,'0'*64)))
    case('wrong-target-refused',lambda:refused(lambda:recover(folder/'different-target',path,digest)))
    case('non-lowercase-hash-refused',lambda:refused(lambda:recover(base,path,digest.upper())))
    def copy_refusal():
        base,path,digest,_=fresh('copied');copy=base.with_name(base.name+'.bootstrap-'+uuid.uuid4().hex+'.jsonl')
        with s.descriptor(policy.sddl(False)) as attrs:
            with s.open_file(copy,access=0xc0000000,share=0,create=1,security=attrs) as handle:j.write_flush(handle,path.read_bytes())
        value=refused(lambda:recover(base,copy,digest));s.require(base.exists(),'Copied journal cannot own original namespace');return value
    case('copied-journal-file-identity-refused',copy_refusal)
    def hardlink():
        base,path,digest,_=fresh('linked');alias=folder/'private-journal-link'
        s.require(alias.resolve().is_relative_to(folder.resolve()),'Private link boundary')
        alias.hardlink_to(path)
        try:value=refused(lambda:recover(base,path,digest));s.require(base.exists(),'Linked source preserved');return value
        finally:alias.unlink()
    case('hardlinked-source-journal-refused',hardlink)
    def held():
        base,path,digest,_=fresh('held')
        with s.open_file(base,True,access=0x20080,share=3):value=refused(lambda:recover(base,path,digest))
        s.require(base.exists() and not value['baseDeletionMarked'],'Active base lease excludes deletion');return value
    case('active-base-read-lease-refuses-delete-open',held)
    def creation_fault(name,mode):
        base=folder/name;real=j.Journal.append
        def append(writer,payload):
            if payload.get('event')=='base_created':
                if mode=='after':real(writer,payload)
                elif mode=='torn':j.write_flush(writer.handle,b'{"incomplete":')
                raise OSError('Injected creation-witness failure '+mode)
            return real(writer,payload)
        with patch.object(j.Journal,'append',append):
            value=refused(lambda:next_context(base))
        s.require(value['created'] and value['policyVerified'] and not value['creationWitnessPersisted'],'Observed directory is not a persisted-witness claim')
        path=Path(value['bootstrapJournal']);digest=j.digest(path.read_bytes())
        if mode=='after':
            recovery=recover(base,path,digest);s.require(recovery['successful'],'Persisted record permits explicit reviewed recovery')
        else:
            recovery=refused(lambda:recover(base,path,digest));s.require(base.exists(),'Unwitnessed/torn gap preserved')
        return {'preparationFailure':value,'recovery':recovery}
    def next_context(base):
        with m.prepared_base(base,policy):pass
    for mode in ['before','torn','after']:
        case('creation-witness-failure-'+mode,lambda mode=mode:creation_fault('creation-'+mode,mode))
    def header_fault():
        base=folder/'header-failure';real=j.Journal.append
        def append(writer,payload):
            if payload.get('event')=='transaction_header':raise OSError('Injected initial journal failure')
            return real(writer,payload)
        with patch.object(j.Journal,'append',append):value=refused(lambda:next_context(base))
        s.require(not base.exists() and not value['creationAttempted'],'No directory create before durable header')
        return value
    case('initial-header-failure-prevents-directory-creation',header_fault)
    def cleanup_fault(name,event):
        base,path,digest,_=fresh(name);raw=path.read_bytes();real=j.Journal.append
        def append(writer,payload):
            if payload.get('event')==event:raise OSError('Injected recovery journal failure')
            return real(writer,payload)
        with patch.object(j.Journal,'append',append):value=refused(lambda:recover(base,path,digest))
        s.require(path.read_bytes()==raw,'Original reviewed witness remains unchanged')
        if event=='before_base_delete':s.require(base.exists() and not value['baseDeletionMarked'],'No delete without persisted intent')
        else:s.require(not base.exists() and value['baseDeletionMarked'] and value['baseAbsentObserved'],'Post-delete failure does not report success')
        retry=recover(base,path,digest);s.require(retry['successful'],'Explicit retry with same immutable source')
        return {'failure':value,'retry':retry}
    case('before-delete-journal-failure-preserves-base',lambda:cleanup_fault('before-delete','before_base_delete'))
    case('after-delete-completion-failure-and-explicit-retry',lambda:cleanup_fault('after-delete','empty_base_recovery_completed'))
    def gained_data():
        base,path,digest,_=fresh('gained-data');real=s.mark_delete
        def mark(handle):
            (base/'late-foreign.txt').write_bytes(b'preserve late arrival')
            return real(handle)
        with patch.object(s,'mark_delete',mark):value=refused(lambda:recover(base,path,digest))
        s.require((base/'late-foreign.txt').read_bytes()==b'preserve late arrival' and not value['baseDeletionMarked'],
                  'Native nonempty-directory deletion refusal preserves late arrival')
        return value
    case('data-arriving-after-empty-check-preserved-by-native-delete-refusal',gained_data)
    def production():
        value=refused(lambda:m.recover_empty_base(m.production_base(),path,digest,s.PRODUCTION))
        s.require('administrator' in value['error'],'Ordinary production refusal');return value
    case('production-cleanup-refuses-ordinary-token',production)
    s.require(m.check_production_base()==before,'Host base/ancestors unchanged')
    (folder/'case-details.json').write_text(json.dumps(details,indent=2)+'\n',encoding='utf-8',newline='\n')
    sources=['scripts/asio-install-base.py','scripts/test-asio-base-bootstrap.py','scripts/asio-install-journal.py','scripts/asio-file-stage.py']
    value={'schema':'sl3.base-bootstrap-tests.v1','cases':cases,'sourceSha256':{n:j.digest((ROOT/n).read_bytes()) for n in sources},
           'files':{p.relative_to(folder).as_posix():j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
           'productionBaseStateUnchanged':True,'nonElevated':True,'productionPreparationOrRecoveryExecuted':False,'registryWritten':False,'deviceAccess':False}
    index=folder/'index.json';index.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    pointer=ROOT/'artifacts/build/base-bootstrap-tests-last.json';pointer.write_text(json.dumps({'directory':str(folder),'indexSha256':j.digest(index.read_bytes())},indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'passed':True,'cases':len(cases),'directory':str(folder),'productionPreparationOrRecoveryExecuted':False}))


if __name__=='__main__':main()
