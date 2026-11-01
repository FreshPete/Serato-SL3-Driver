"""Check pinned UsbDk cleanup source and prepare invariant lifecycle WPP formats.

Default: print a checked plan only. --prepare DIR writes local decoder inputs;
neither mode loads the helper, enables tracing, or accesses the USB device.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '84752c30037956149d53b498005b5368616f9257'
SYS_SHA = 'c92b6c15bd550023312ae4cfe49a39757952a3c2ebdc7d1d143ac5e695f69a63'
TMF_SHA = 'dd84f5dd432baf179dd400641d37f046bc206e885daf83f59783b48910f454ec'
SOURCE_LF = {
    'DeviceAccess.cpp': '1e58b0b4a30aba0114c92357e2cc0b67b60f25b0754821c8062c5d30d6920b8e',
    'DeviceAccess.h': '19823af47f3381cda899718a4e7cc312e636af1d25093fe62358c188886d724f',
    'Irp.cpp': '0819c4a33de8cc8b4057008eda9d3e8aacb9edd7815b943a3c1575b280f11b8d',
    'Irp.h': '97d945e30a0bd5df880cd55a42fa25ef9cfd1375f28eda309654d99808195d9f',
    'UsbDkUtil.cpp': '67e23da5bae686aaea1967cf9562fb78e1f207e3ca639c7d7f8eebb49d1fc66a',
    'UsbDkUtil.h': 'b1bb40666238d7af7c6ff7c314000e09a0898eeced8b2785c571012ea95246e8',
    'ControlDevice.cpp': '84b14f706926b0ee4548e029eb24092b50929cf361e791e95b99b5671362f178',
    'ControlDevice.h': 'ea77a0bd73f7b2007dfc11990f8a20253fbc909878f7f6b508c727ae920c590f',
    'FilterDevice.cpp': 'c33df424c4ffcec5ead464835a08937714b889f4139fe3cfd76a0c50710c5600',
    'RedirectorStrategy.cpp': '21bfc6522d18301435f5060fe00990d85652ffe62a0b67b9d8760ff283fc9e81',
    'WdfDevice.h': '5071f9afb4759bc1334fc0085722ead4b49ea1b25199824a6f26e7d50a9fdff4',
    'Trace.h': '439ccea826e5b9ed751109524b4b8698a786a609485dd5a114fb6844c9ebbc46',
    'UsbDkHelper.cpp': '6790c5a9a67c7f64164198511cd855c1c7054d80850a86d7713831f5ed4b5350',
    'DriverFile.h': '079dcf53753e4fac7629585ca6d5dc6ac2498748c83bf5dd6f41f604fe0f31b6',
}
SELECTED = {
    'DeviceAccess.cpp': {17, 18, 21, 22, 23},
    'ControlDevice.cpp': {36, 37, 38, 39, 51, 52, 53, 54, 55, 56, 57, 58,
                          59, 60, 61, 62, 63, 64, 66, 67, 68, 69, 70, 71, 72},
    'RedirectorStrategy.cpp': {28, 29},
}
PROVIDER = '88e1661f-48b6-410f-b096-ba84e9f0656f'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_function(source, name):
    match = re.search(r'(?m)^.*\b' + re.escape(name) + r'\([^;]*?\)\s*\{', source)
    require(match is not None, f'Missing source function {name}')
    end = source.index('\n}', match.end()) + 2
    return source[match.start():end], [source.count('\n', 0, match.start()) + 1,
                                      source.count('\n', 0, end) + 1]


def check():
    sources = {}
    for name, expected in SOURCE_LF.items():
        raw = (ROOT/'artifacts/references/usbdk-1.0.22'/name).read_bytes().replace(b'\r\n', b'\n')
        require(sha(raw) == expected, f'Exact-commit source changed: {name}')
        sources[name] = raw.decode('utf-8')
    regions = {}
    def body(file, name):
        text, lines = source_function(sources[file], name)
        regions[name] = {'file': file, 'lines': lines, 'normalizedBodySha256': sha(text.encode())}
        return text
    helper = body('UsbDkHelper.cpp', 'UsbDk_StopRedirect')
    require(helper.index('RedirectorAccess.reset();') < helper.index('return TRUE;'), 'Helper close path changed')
    on_close = body('RedirectorStrategy.cpp', 'CUsbDkRedirectorStrategy::OnClose')
    require('m_ControlDevice->RemoveRedirect(ID)' in on_close and 'return status' not in on_close,
            'Void kernel close callback changed')
    removal = body('ControlDevice.cpp', 'CUsbDkControlDevice::RemoveRedirect')
    ordered = ['NotifyRedirectorRemovalStarted(DeviceId)', 'ResetUsbDevice(DeviceId, false)',
               'WaitForDetachment(DeviceId)', 'm_Redirections.Delete(&DeviceId)']
    require([removal.index(x) for x in ordered] == sorted(removal.index(x) for x in ordered),
            'Removal ordering changed')
    require('return STATUS_DEVICE_NOT_CONNECTED;' in removal and 'return res;' in removal,
            'Kernel removal failure path changed')
    require(removal.index('res = STATUS_OBJECT_NAME_NOT_FOUND;') < removal.index('return STATUS_SUCCESS;'),
            'Kernel redirection-set deletion status handling changed')
    detached = body('ControlDevice.cpp', 'CUsbDkRedirection::WaitForDetachment')
    require('m_RedirectionRemoved.Wait(true, -SecondsTo100Nanoseconds(120))' in detached,
            'Detachment wait changed')
    notify = body('ControlDevice.cpp', 'CUsbDkRedirection::NotifyRedirectionRemoved')
    require('IsPreparedForRemove()' in notify and 'm_RedirectionRemoved.Set()' in notify,
            'Removal notification changed')
    drop = body('FilterDevice.cpp', 'CUsbDkHubFilterStrategy::DropRemovedDevices')
    require('!Relations.Contains(*Child)' in drop and 'NotifyRedirectionRemoved(*Device)' in drop,
            'Hub relation notification changed')
    filter_create = body('FilterDevice.cpp', 'CUsbDkFilterDeviceInit::Configure')
    require('Strategy(Device)->OnClose();' in filter_create and 'WDF_NO_EVENT_CALLBACK' in filter_create,
            'File-close registration changed')
    require('WDF_FILEOBJECT_CONFIG_INIT(&fileConfig, EvtDeviceFileCreate, EvtFileClose, EvtFileCleanup)' in sources['WdfDevice.h'],
            'WDF callback parameter ordering changed')
    addition = body('ControlDevice.cpp', 'CUsbDkControlDevice::AddRedirect')
    add_order = ['AddRedirectionToSet(', 'ResetUsbDevice(DeviceId, true)', 'WaitForAttachment()', 'CreateRedirectorHandle(']
    require([addition.index(x) for x in add_order] == sorted(addition.index(x) for x in add_order),
            'Acquisition ordering changed')
    handle = body('ControlDevice.cpp', 'CUsbDkRedirection::CreateRedirectorHandle')
    require('10000 / RETRY_TIMEOUT_MS' in handle, 'Handle polling bound changed')
    require('CloseHandle(m_hDriver);' in sources['DriverFile.h'], 'Helper handle owner changed')

    reset = body('DeviceAccess.cpp', 'CWdmUsbDeviceAccess::Reset')
    reset_order = ['ForceD0 && QueryPowerData(powerData)', 'PoRequestPowerIrp(', 'Event.Wait();',
                   'IOCTL_INTERNAL_USB_CYCLE_PORT', 'Irp.SendSynchronously()']
    require([reset.index(x) for x in reset_order] == sorted(reset.index(x) for x in reset_order),
            'Power request / port-cycle ordering changed')
    require('powerData.PD_MostRecentPowerState != PowerDeviceD0' in reset and
            'if (NT_SUCCESS(status))' in reset, 'Conditional power-wait path changed')
    completion = body('DeviceAccess.cpp', 'PowerRequestCompletion')
    require('pev->Set();' in completion and 'UNREFERENCED_PARAMETER(IoStatus);' in completion,
            'Power completion event/status handling changed')
    require('Wait(bool WithTimeout = false, LONGLONG Timeout = 0, bool Alertable = false)' in sources['UsbDkUtil.h'],
            'Default event timeout changed')
    event = body('UsbDkUtil.cpp', 'CWdmEvent::Wait')
    require('KeWaitForSingleObject(' in event and 'WithTimeout ? &PackedTimeout : nullptr' in event,
            'Event timeout argument changed')
    ioctl = body('Irp.cpp', 'CIoControlIrp::SendSynchronously')
    require('if (res == STATUS_PENDING)' in ioctl and
            'KeWaitForSingleObject(&m_Event, Executive, KernelMode, FALSE, nullptr)' in ioctl,
            'Pending synchronous IOCTL wait changed')

    image = (ROOT/'artifacts/extracted/usbdk-msi/UsbDk.sys10').read_bytes()
    tmf_raw = (ROOT/'artifacts/extracted/usbdk-msi/UsbDk_TMF').read_bytes()
    require(sha(image) == SYS_SHA and sha(tmf_raw) == TMF_SHA, 'Reviewed MSI driver/TMF changed')
    require(uuid.UUID(PROVIDER).bytes_le in image, 'WPP control GUID absent from reviewed driver')
    records = defaultdict(set)
    current = None
    lines = tmf_raw.decode('utf-8').splitlines()
    index = 0
    while index < len(lines):
        header = re.match(r'([0-9a-f-]{36}) UsbDk // SRC=(\w+\.cpp)', lines[index])
        if header:
            current = header.groups()
        entry = re.match(r'#typev\s+\w+\s+(\d+) ', lines[index])
        if entry and current and int(entry[1]) in SELECTED.get(current[1], set()):
            start = index
            while index < len(lines) and lines[index] != '}':
                index += 1
            require(index < len(lines), 'Truncated TMF record')
            records[current + (int(entry[1]),)].add('\n'.join(lines[start:index+1]))
        index += 1
    require(len(records) == sum(map(len, SELECTED.values())), 'Lifecycle TMF inventory differs')
    blocks, inventory = defaultdict(list), []
    for (guid, file, number), variants in sorted(records.items()):
        require(len(variants) == 1, f'Architecture/OS-ambiguous lifecycle record {file}:{number}')
        offset = image.find(uuid.UUID(guid).bytes_le)
        require(offset >= 0, f'TMF message GUID absent from actual x64 driver: {guid}')
        record = next(iter(variants))
        function = re.search(r'FUNC=(\S+)', record)[1]
        blocks[(guid, file)].append(record)
        inventory.append({'file': file, 'messageGuid': guid, 'driverGuidFileOffset': offset,
                          'messageId': number, 'function': function, 'formatSha256': sha(record.encode())})
    sections = [f'{guid} UsbDk // SRC={file} MJ= MN=\n' + '\n'.join(entries)
                for (guid, file), entries in blocks.items()]
    selected = ('// Lifecycle-only invariant formats from reviewed UsbDk MSI; raw trace remains local.\n'
                + '\n'.join(sections) + '\n').encode('utf-8')
    plan = {'scope': 'Static source and matching driver/TMF message-GUID checks; no USB, tracing or driver execution',
            'sourceCommit': COMMIT, 'sourceLfSha256': SOURCE_LF, 'sourceFunctions': regions,
            'driverSha256': SYS_SHA, 'bundledTmfSha256': TMF_SHA, 'selectedTmfSha256': sha(selected),
            'providerGuid': PROVIDER, 'flags': '0x650', 'level': 4,
            'selectedFlags': ['TRACE_DEVACCESS', 'TRACE_CONTROLDEVICE', 'TRACE_WDFDEVICE', 'TRACE_REDIRECTOR'],
            'messages': inventory, 'kernelRemoveStatusReachesHelperBoolean': False,
            'kernelRedirectionDeleteFailurePropagated': False,
            'detachmentEventMeaning': 'Removed child absent from a hub relations snapshot while removal is in progress',
            'reacquisitionReadinessProven': False,
            'resetPath': {'operation': 'IOCTL_INTERNAL_USB_CYCLE_PORT',
                          'addRedirectForceD0': True, 'removeRedirectForceD0': False,
                          'conditionalPowerWaitHasTimeout': False, 'pendingCycleIoctlHasTimeout': False,
                          'powerCompletionStatusPropagated': False,
                          'attachmentTimeoutBoundsEntireStartRedirect': False,
                          'selectedPowerMessages': {'queryFailure': 17, 'completion': 18, 'request': 21,
                                                    'cycleIrpCreationFailure': 22, 'cycleSendFailure': 23}},
            'limits': ['Exact source review is not a complete signed-binary equivalence proof',
                       'The helper result cannot attest successful kernel reset/detachment or normal device readiness',
                       'GUID presence and invariant message definitions do not establish runtime emission/decoding',
                       'No live WPP capture performed; earlier USB-stack-only traces cannot supply missing WPP messages',
                       'Selected TMF omits unrelated messages; decoding omissions must not imply events never occurred']}
    flags = re.findall(r'WPP_DEFINE_BIT\((\w+)\)', sources['Trace.h'])
    require(sum(1 << flags.index(name) for name in plan['selectedFlags']) == 0x650, 'WPP flag mapping differs')
    return plan, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    plan, selected = check()
    if args.prepare:
        args.prepare.mkdir(parents=True, exist_ok=False)
        (args.prepare/'lifecycle.tmf').write_bytes(selected)
        (args.prepare/'plan.json').write_text(json.dumps(plan, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
