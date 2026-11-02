"""Audit saved packet slices and original-style low-24-bit copies; no device access."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
p=module('pcm_origin','analyse-capture-pcm.py')
v=module('origin_json','validate-asio-private-trace.py')

def masked_planes(raw,guard):
    """Independent selected-store model; never overread a three-byte source sample."""
    p.require(type(raw) is bytes and len(raw)%18==0 and type(guard) is int and 0<=guard<=255,'Whole six-channel frames and byte guard required')
    frames=len(raw)//18;planes=[bytearray([0xa5])*(frames*3+1) for _ in range(6)]
    for frame in range(frames):
        for channel in range(6):
            start=frame*18+channel*3;at=frame*3
            source=int.from_bytes(raw[start:start+3],'little')|(guard<<24)
            target=int.from_bytes(planes[channel][at:at+4],'little')
            value=target^((source^target)&0xffffff)
            planes[channel][at:at+4]=value.to_bytes(4,'little')
    p.require(all(plane[-1]==0xa5 for plane in planes),'Fourth destination byte must stay unchanged')
    return [bytes(plane[:-1]) for plane in planes]

def audit(metadata,pcm,registered):
    summary=p.analyse(metadata,pcm)
    p.require(type(registered) is list and len(registered)==4 and all(type(b) is bytes and len(b)==8064 for b in registered),'Four exact registered request buffers required')
    selected=[];coverage=[];cursor=0
    for ordinal,packet in enumerate(metadata['packets']):
        request,offset,length=packet['request'],packet['offset'],packet['length']
        selected.append(registered[request][offset:offset+length])
        coverage.append((cursor,cursor+length,request,ordinal%64,offset));cursor+=length
    reconstructed=b''.join(selected)
    p.require(reconstructed==pcm,'Stored PCM differs from exact registered packet slices')
    first=masked_planes(reconstructed,0);second=masked_planes(reconstructed,255)
    p.require(first==second,'Discarded source high byte affected PCM')
    for channel,plane in enumerate(first):
        expected=b''.join(pcm[frame*18+channel*3:frame*18+channel*3+3] for frame in range(len(pcm)//18))
        p.require(plane==expected,'Selected original-style copy differs from channel bytes')
    peaks=[]
    for stats in summary['fullCapture']['channels']:
        frame=stats['firstMaximumMagnitudeFrame'];channel=stats['streamChannel'];packed_offset=frame*18+channel*3
        lo,hi,request,packet,offset=next(row for row in coverage if row[0]<=packed_offset<row[1])
        raw_offset=offset+packed_offset-lo
        p.require(registered[request][raw_offset:raw_offset+3]==pcm[packed_offset:packed_offset+3],'Peak is not present in recorded source bytes')
        peaks.append({'streamChannel':channel,'retainedFrame':frame,'magnitudeCode':stats['maximumMagnitudeCode'],
                      'signedCode':int.from_bytes(registered[request][raw_offset:raw_offset+3],'little',signed=True),
                      'request':request,'packet':packet,'registeredByteOffset':raw_offset,'packedByteOffset':packed_offset,'sourceBytesMatch':True})
    return {'schema':'sl3.capture-byte-origin.v1','scope':'Saved source buffers and selected low-24-bit store model only',
            'reportedRateHz':metadata['reported_rate_hz'],'frames':len(pcm)//18,'packets':256,'registeredBytes':4*8064,
            'selectedBytes':len(pcm),'ignoredPaddingBytes':4*8064-len(pcm),'exactPacketSlicesMatch':True,
            'selectedOriginalStylePlanesMatch':True,'sourceHighByteIndependenceChecked':True,'destinationGuardPreserved':True,
            'planeSha256':[p.digest(plane) for plane in first],'channelPeakOrigins':peaks,
            'samplesDiscarded':0,'samplesReplaced':0,'captureTimeRegisteredHashesProvided':False,
            'inputSignalKnown':False,'physicalJackMappingVerified':False,
            'startupCauseDiagnosed':False,'continuityVerified':False,'physicalAudioVerified':False,'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False}

def audit_directory(directory):
    paths=[directory/'capture.json',directory/'capture.pcm']+[directory/f'registered-{n}.bin' for n in range(4)]
    raw=[v.bounded(path,128*1024 if path.suffix=='.json' else 4*8064) for path in paths]
    result=audit(v.parse(raw[0]),raw[1],raw[2:])
    result['sourceFiles']={path.name:hashlib.sha256(data).hexdigest() for path,data in zip(paths,raw)}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--capture',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:p.require(not args.output.exists() and not args.output.is_symlink(),'Fresh output required')
    result=audit_directory(args.capture);raw=json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as f:f.write(raw)
    else:print(raw,end='')
