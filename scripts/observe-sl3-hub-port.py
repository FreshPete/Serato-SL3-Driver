"""Fixed, normal-user cached port sampler tied to one fresh USB trace context.

Preparation/default inspection starts nothing. The supervised worker uses the
base interpreter directly, waits at most ninety seconds, samples for eighteen
seconds, and never launches a device probe or grants acquisition readiness.
"""
import argparse
import ctypes as c
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


query=module('query-sl3-hub-port.py')
require,sha,now=query.require,query.sha,query.now
SOURCES=('observe-sl3-hub-port.py','query-sl3-hub-port.py','inspect-loaded-hub.py','capture-usb-startup.ps1')


def read(path):
    require(0<path.stat().st_size<=2*1024*1024,'JSON evidence exceeds bound')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_new(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def runtime():
    base=Path(sys._base_executable).resolve()
    return {'baseInterpreter':str(base),'baseInterpreterSha256':sha(base),
            'sources':{n:sha(ROOT/'scripts'/n) for n in SOURCES}}


def plan(context,hub,port,created):
    context=context.resolve()
    require(context.is_relative_to((ROOT/'tests/results/local').resolve()) and context.parent.is_dir(),
            'Expected a local controls context')
    return {'schema':'sl3.hub-port-observer.v1','createdUtc':created,'contextDirectory':str(context),
            'query':query.plan(hub,port),'runtime':runtime(),'waitSeconds':90,'sampleSeconds':18,
            'devnodeInstance':r'USB\VID_1CC5&PID_0001\SL3.01.00',
            'intervalSeconds':0.25,'maximumSamples':128,'supervisorDeadlineSeconds':115,
            'launchesProbe':False,'startsTrace':False,'readinessAdmission':False,'automaticRetry':False}


def prepare(directory,context,hub,port):
    directory=directory.resolve()
    require(directory.parent==(ROOT/'analysis').resolve() and
            re.fullmatch(r'hub-port-observer-[a-zA-Z0-9-]{1,64}',directory.name) and not directory.exists(),
            'Expected a fresh direct analysis/hub-port-observer-* folder')
    require(not context.exists(),'Context must be fresh at preparation')
    value=plan(context,hub,port,now());directory.mkdir();write_new(directory/'plan.json',value)
    return value


def validate(directory):
    directory=directory.resolve()
    require(directory.parent==(ROOT/'analysis').resolve() and
            re.fullmatch(r'hub-port-observer-[a-zA-Z0-9-]{1,64}',directory.name),'Unexpected observer job location')
    value=read(directory/'plan.json')
    expected=plan(Path(value['contextDirectory']),value['query']['hubInstance'],value['query']['port'],value['createdUtc'])
    require(value==expected,'Observer plan/runtime changed')
    return value


def utc(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.utcoffset() is not None,'Timestamp needs a timezone')
    return result


def process_identity(pid):
    require(type(pid) is int and 0<pid<2**32,'Invalid collector PID')
    kernel=c.WinDLL('kernel32',use_last_error=True);ptr=c.c_void_p;u32=c.c_uint32
    kernel.OpenProcess.argtypes=[u32,c.c_int32,u32];kernel.OpenProcess.restype=ptr
    kernel.GetProcessTimes.argtypes=[ptr]+[c.POINTER(c.c_uint64)]*4;kernel.GetProcessTimes.restype=c.c_int32
    kernel.QueryFullProcessImageNameW.argtypes=[ptr,u32,ptr,c.POINTER(u32)];kernel.QueryFullProcessImageNameW.restype=c.c_int32
    kernel.GetExitCodeProcess.argtypes=[ptr,c.POINTER(u32)];kernel.GetExitCodeProcess.restype=c.c_int32
    kernel.CloseHandle.argtypes=[ptr];kernel.CloseHandle.restype=c.c_int32
    handle=kernel.OpenProcess(0x1000,False,pid);require(handle,'Cannot inspect collector process')
    try:
        times=[c.c_uint64() for _ in range(4)]
        require(kernel.GetProcessTimes(handle,*[c.byref(t) for t in times]),'Collector creation query failed')
        size=u32(32768);image=c.create_unicode_buffer(size.value);code=u32()
        require(kernel.QueryFullProcessImageNameW(handle,0,image,c.byref(size)) and
                kernel.GetExitCodeProcess(handle,c.byref(code)),'Collector image/liveness query failed')
        return {'pid':pid,'creationFileTimeUtc':str(times[0].value),'imagePath':image.value,'alive':code.value==259}
    finally:kernel.CloseHandle(handle)


def admit(trace,observed,settings,checked):
    require(trace['status']=='recording' and re.fullmatch(r'SL3Startup-[0-9a-f]{32}',trace['session']) and
            trace['producerSha256'].lower()==settings['runtime']['sources']['capture-usb-startup.ps1'] and
            trace['plan']['durationSeconds']==20 and trace['plan']['withStateObserver'] is True,
            'Unexpected collector mode/source')
    require(utc(settings['createdUtc'])<=utc(trace['startedUtc'])<=utc(checked) and
            (utc(checked)-utc(trace['startedUtc'])).total_seconds()<=5,'Collector window is stale')
    require(observed['pid']==trace['collectorPid'] and observed['alive'] is True and
            observed['creationFileTimeUtc']==trace['collectorCreationFileTimeUtc'] and
            observed['imagePath'].casefold()==trace['collectorImagePath'].casefold(),'Collector identity changed')


def await_trace(settings,producer_alive=lambda:True):
    path=Path(settings['contextDirectory'])/'trace/capture.json';deadline=time.monotonic()+settings['waitSeconds']
    while time.monotonic()<deadline:
        require(producer_alive(),'Producer no longer active')
        try:trace=read(path)
        except (OSError,ValueError):trace=None
        if trace and trace.get('status') in ('failed','window completed','cleanup requires attention'):
            raise ValueError('Collector already terminal; no hub queries started')
        if trace and trace.get('status')=='recording':
            observed=process_identity(trace['collectorPid']);checked=now();admit(trace,observed,settings,checked)
            return {'trace':trace,'collector':observed,'checkedUtc':checked}
        time.sleep(.05)
    raise ValueError('No fresh collector window; no hub queries started')


def devnode_fields(locate,status,flags,problem):
    require(all(type(value) is int and 0<=value<2**32 for value in (locate,status,flags,problem)),
            'Invalid Config Manager result')
    present=locate==0 and status==0
    complete=present or locate==13 or locate==0 and status==13
    has_problem=bool(flags&0x400) if present else None
    return {'locateStatus':locate,'queryStatus':status if locate==0 else None,'complete':complete,
            'present':present,'statusFlags':flags if present else None,'hasProblem':has_problem,
            'started':bool(flags&8) if present else None,'problemCode':problem if has_problem else None}


def devnode_status(instance):
    cfg=c.WinDLL('cfgmgr32',use_last_error=True);u32=c.c_uint32
    cfg.CM_Locate_DevNodeW.argtypes=[c.POINTER(u32),c.c_wchar_p,u32];cfg.CM_Locate_DevNodeW.restype=u32
    cfg.CM_Get_DevNode_Status.argtypes=[c.POINTER(u32),c.POINTER(u32),u32,u32];cfg.CM_Get_DevNode_Status.restype=u32
    node=u32();flags=u32();problem=u32()
    locate=int(cfg.CM_Locate_DevNodeW(c.byref(node),instance,0))
    status=int(cfg.CM_Get_DevNode_Status(c.byref(flags),c.byref(problem),node,0)) if locate==0 else 0
    return devnode_fields(locate,status,int(flags.value),int(problem.value))


def samples(settings,emit):
    start=time.monotonic();deadline=start+settings['sampleSeconds'];count=0;gaps=0
    while time.monotonic()<deadline:
        require(count<settings['maximumSamples'],'Sample count exceeded fixed bound')
        entry=now();value=query.run(settings['query']);count+=1
        node=devnode_status(settings['devnodeInstance']) if value['successful'] else None
        emit({'record':'sample','sequence':count,'entryUtc':entry,'completedUtc':now(),
              'elapsedSeconds':time.monotonic()-start,'query':value,'devnode':node})
        require(value['producerToken']['pid']==os.getpid() and value['producerToken']['elevated'] is False,
                'Query did not execute in the normal observer process')
        if query.enumeration_gap(value):
            gaps+=1
        else:
            require(value['successful'] is True and value['error'] is None and value['handleClosed'] is True,
                    'Hub query failed; sampling stopped without retry')
            require(node['complete'] is True,'Devnode observation was incomplete; sampling stopped')
        require(time.monotonic()<=deadline,'Synchronous query crossed the sample deadline')
        remaining=deadline-time.monotonic()
        if remaining>0:time.sleep(min(settings['intervalSeconds'],remaining))
    return {'samples':count,'enumerationGaps':gaps,'elapsedSeconds':time.monotonic()-start}


def worker(directory,expected_sha):
    require(sha(directory/'plan.json')==expected_sha,'Observer plan changed before worker')
    settings=validate(directory);token=query.own_token()
    require(token['queried'] is True and token['elevated'] is False,'Observer requires normal user token')
    require(Path(sys.executable).resolve()==Path(settings['runtime']['baseInterpreter']),
            'Worker must be the pinned base interpreter, not a venv launcher')
    with (directory/'observations.ndjson').open('x',encoding='utf-8') as stream:
        def emit(value):stream.write(json.dumps(value)+'\n');stream.flush()
        emit({'record':'header','planSha256':expected_sha,'producerToken':token,'startedUtc':now(),'readinessAdmission':False})
        result={'record':'summary','successful':False,'error':None,'readinessAdmission':False}
        try:
            admission=await_trace(settings);emit({'record':'admission',**admission})
            result.update(samples(settings,emit))
            require(settings['runtime']==runtime(),'Observer runtime changed during sampling')
            result['successful']=result['samples']-result['enumerationGaps']>1
        except Exception as error:result['error']=str(error)
        finally:result['completedUtc']=now();emit(result)
    return result


def supervise(directory):
    settings=validate(directory);token=query.own_token()
    require(token['queried'] is True and token['elevated'] is False,'Supervisor requires normal user token')
    expected_sha=sha(directory/'plan.json')
    write_new(directory/'started.json',{'planSha256':expected_sha,'startedUtc':now(),'producerToken':token})
    result={'schema':'sl3.hub-port-observer.supervision.v1','planSha256':expected_sha,'startedUtc':now(),
            'successful':False,'pid':None,'exitCode':None,'timedOut':False,'directProducerRetired':False,
            'error':None,'readinessAdmission':False}
    child=None
    try:
        with (directory/'stdout.log').open('xb') as out,(directory/'stderr.log').open('xb') as err:
            child=subprocess.Popen([settings['runtime']['baseInterpreter'],str(Path(__file__)),
                                    '--worker',str(directory),'--expected-sha256',expected_sha],
                                   stdout=out,stderr=err,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            result['pid']=child.pid
            try:result['exitCode']=child.wait(timeout=settings['supervisorDeadlineSeconds'])
            except subprocess.TimeoutExpired:
                result['timedOut']=True;child.kill();result['exitCode']=child.wait(timeout=5)
            result['directProducerRetired']=child.poll() is not None
        path=directory/'observations.ndjson'
        require(0<path.stat().st_size<=2*1024*1024,'Missing or oversized observations')
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        require(rows[0]['record']=='header' and rows[0]['producerToken']['pid']==child.pid,
                'Supervised PID differs from actual query producer')
        result['observationsSha256']=sha(path)
        result['workerError']=rows[-1].get('error')
        result['successful']=bool(not result['timedOut'] and result['exitCode']==0 and rows[-1].get('successful') is True)
    except Exception as error:result['error']=str(error)
    finally:
        if child is not None and child.poll() is None:
            try:
                child.kill();result['exitCode']=child.wait(timeout=5)
                result['directProducerRetired']=True
            except Exception as error:result['retirementError']=str(error)
        result['completedUtc']=now();write_new(directory/'supervision.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',type=Path);group.add_argument('--job',type=Path);group.add_argument('--worker',type=Path)
    parser.add_argument('--context',type=Path);parser.add_argument('--hub-instance');parser.add_argument('--port',type=int)
    parser.add_argument('--run',action='store_true');parser.add_argument('--expected-sha256')
    args=parser.parse_args()
    if args.prepare:
        require(not args.run and args.context is not None,'Preparation requires a fresh context and never executes')
        result=prepare(args.prepare,args.context,args.hub_instance,args.port)
    elif args.worker:
        require(not args.run and args.expected_sha256 is not None,'Internal worker requires exact plan hash')
        result=worker(args.worker.resolve(),args.expected_sha256)
    else:result=supervise(args.job.resolve()) if args.run else validate(args.job.resolve())
    print(json.dumps(result,indent=2))
    return int(bool(args.run or args.worker) and not result['successful'])


if __name__=='__main__':raise SystemExit(main())
