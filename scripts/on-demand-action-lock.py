"""Trusted-caller setup/restore lock; no actions at import and no mutating CLI."""
from contextlib import contextmanager,ExitStack
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
LOCK_NAME='userio_resources.bin.sl3-on-demand-action.lock'


class ActionLockBusy(ValueError):
    pass


class Lease:
    def __init__(self,s,handle,report):
        self.s,self.handle,self.report=s,handle,report

    @contextmanager
    def child(self):
        """Pass a scoped duplicate only to the selected mutating helper."""
        s=self.s;s.require(self.handle is not None,'Action lock is already closed')
        process=s.api('kernel32.dll','GetCurrentProcess',W.HANDLE,[])();duplicate=W.HANDLE()
        s.check(s.api('kernel32.dll','DuplicateHandle',W.BOOL,[W.HANDLE,W.HANDLE,W.HANDLE,ctypes.POINTER(W.HANDLE),W.DWORD,W.BOOL,W.DWORD])(
            process,self.handle,process,ctypes.byref(duplicate),0,True,2))
        with s.Handle(duplicate.value):
            startup=subprocess.STARTUPINFO();startup.lpAttributeList={'handle_list':[duplicate.value]}
            self.report['helperSharesIssued']+=1
            yield duplicate.value,{'startupinfo':startup,'close_fds':True}


@contextmanager
def hold(s,path,policy):
    """Create one exact temporary kernel lock; never open/remove an existing object."""
    path=Path(path).absolute();s.local(path)
    s.require(path.name==LOCK_NAME,'Exact on-demand action lock name required')
    production=policy==s.PRODUCTION
    if production:
        s.require(s.elevated(),'Explicit elevation required for production action lock; no automatic UAC')
        s.require(path.parent==s.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'Serato/Serato DJ Pro',
                  'Fixed reviewed application lock directory required')
    else:
        s.require(not s.elevated() and policy.owner==s.user_sid() and path.parent.is_relative_to(ROOT/'artifacts/build'),
                  'Ordinary owned workspace fixture lock only')
    report={'schema':'sl3.on-demand-action-lock.v1','productionPolicy':production,'exclusive':True,
            'deleteOnClose':True,'handleClosed':False,'pid':os.getpid(),'fileIdentity':None,'helperSharesIssued':0}
    with ExitStack() as stack:
        parents=stack.enter_context(s.pinned_parents(path))
        if production:
            trusted={s.SYSTEM,s.ADMINS,s.account_sid('NT SERVICE\\TrustedInstaller')}
            for parent in parents:s.safe_parent(parent,trusted)
        else:s.inspect_policy(parents[-1],policy,True)
        with s.descriptor(policy.sddl(False)) as attributes:
            raw=s.api('kernel32.dll','CreateFileW',W.HANDLE,
                [W.LPCWSTR,W.DWORD,W.DWORD,ctypes.POINTER(s.Attributes),W.DWORD,W.DWORD,W.HANDLE])(
                str(path),0xc0030000,0,ctypes.byref(attributes),1,0x04200080,None)
        if raw is None or raw==s.INVALID:
            code=ctypes.get_last_error()
            if code in (5,32,80,183) or not s.absent(path):
                raise ActionLockBusy('On-demand action lock exists or is held; preserve it and do not start another action')
            raise ctypes.WinError(code)
        # DELETE_ON_CLOSE belongs to the newly created file object, not a later
        # path lookup. Kernel closure also applies if this process is killed.
        owner=s.Handle(raw)
        lease=Lease(s,raw,report)
        try:
            details=s.inspect_policy(raw,policy,False)['file']
            s.require(details['size']==0 and Path(details['path'])==path,'Fresh exact action lock identity required')
            report['fileIdentity']=details['identity']
            data=(json.dumps({'schema':'sl3.on-demand-action-lock-marker.v1','pid':os.getpid()},sort_keys=True)+'\n').encode('ascii')
            count=W.DWORD()
            s.check(s.api('kernel32.dll','WriteFile',W.BOOL,[W.HANDLE,s.P,W.DWORD,ctypes.POINTER(W.DWORD),s.P])(
                raw,data,len(data),ctypes.byref(count),None))
            s.require(count.value==len(data),'Complete action lock marker write required')
            s.check(s.api('kernel32.dll','FlushFileBuffers',W.BOOL,[W.HANDLE])(raw))
            s.require(s.read_handle(raw,4096)==data,'Action lock marker readback differs')
            yield lease
        finally:
            owner.close();lease.handle=None;report['handleClosed']=True
            # Do not delete by name or insist on path absence: the next action
            # may already own a different newly created lock at this same path.
