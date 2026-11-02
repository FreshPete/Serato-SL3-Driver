import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('origin',ROOT/'scripts/audit-capture-origin.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)

def fixture():
    metadata={'transport':'UsbDk 1.0.22','error':'','capture_succeeded':True,'transfers_succeeded':True,
              'buffer_cleanup_complete':True,'redirect_and_alternates_cleanup_succeeded':True,'reported_rate_hz':44100,
              'planned_intervals':256,'planned_ms':32,'submitted_requests':4,'completed_requests':4,'zero_packets':0,
              'audio_output_submissions':0,'continuity_verified':False,'frames':256,'packets':[]}
    buffers=[bytearray([0xdd])*8064 for _ in range(4)];packed=bytearray()
    extrema=[-8388608,-1,0,1,8388607,0x123456]
    for n in range(256):
        request,packet=divmod(n,64);raw=b''.join((extrema[c] if n==0 else n*8+c).to_bytes(3,'little',signed=True) for c in range(6))
        offset=packet*126;buffers[request][offset:offset+18]=raw;packed.extend(raw)
        metadata['packets'].append({'request':request,'packet':packet,'offset':offset,'length':18,'status':0,
            'completion_win32_error':0,'request_usbd_status':0,'request_attempted':True,'request_submitted':True,'request_terminal':True})
    return metadata,bytes(packed),[bytes(b) for b in buffers]

class OriginTests(unittest.TestCase):
    def test_all_channels_extrema_padding_and_source_peak_locations(self):
        m,p,b=fixture();r=o.audit(m,p,b)
        self.assertTrue(r['exactPacketSlicesMatch']);self.assertTrue(r['selectedOriginalStylePlanesMatch'])
        self.assertEqual(r['ignoredPaddingBytes'],4*8064-len(p));self.assertEqual(r['samplesDiscarded'],0)
        self.assertEqual(r['channelPeakOrigins'][0]['signedCode'],-8388608)
        self.assertEqual(r['channelPeakOrigins'][0]['registeredByteOffset'],0)
        for k in ['startupCauseDiagnosed','continuityVerified','physicalAudioVerified','currentSeratoAdmissionVerified','twoDeckDvsVerified']:self.assertIs(r[k],False)

    def test_changed_source_and_changed_pcm_are_refused(self):
        m,p,b=fixture();changed=bytearray(b[0]);changed[0]^=1;b[0]=bytes(changed)
        with self.assertRaises(ValueError):o.audit(m,p,b)
        m,p,b=fixture();changed=bytearray(p);changed[-1]^=1
        with self.assertRaises(ValueError):o.audit(m,bytes(changed),b)

    def test_padding_is_ignored_and_never_flattened(self):
        m,p,b=fixture();changed=bytearray(b[0]);changed[18:126]=bytes([0x7f])*108;b[0]=bytes(changed)
        self.assertTrue(o.audit(m,p,b)['exactPacketSlicesMatch'])
        with self.assertRaises(ValueError):o.audit(m,b''.join(b)[:len(p)],b)

    def test_raw_request_size_count_and_types_are_strict(self):
        m,p,b=fixture()
        for bad in [b[:3],b+[b[0]],[b[0][:-1]]+b[1:],[bytearray(b[0])]+b[1:]]:
            with self.assertRaises(ValueError):o.audit(m,p,bad)

    def test_packet_fault_zero_length_order_and_partial_frame_are_refused(self):
        original,p,b=fixture()
        for key,value in [('status',1),('length',0),('length',17),('offset',1),('packet',1),('request',True),('request_terminal',False)]:
            m=copy.deepcopy(original);m['packets'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):o.audit(m,p,b)

    def test_store_guard_and_empty_invalid_width(self):
        m,p,b=fixture();planes=o.masked_planes(p,0);self.assertEqual(planes,o.masked_planes(p,255))
        self.assertEqual(planes[0][:3],b'\x00\x00\x80');self.assertEqual(planes[4][:3],b'\xff\xff\x7f')
        for raw,guard in [(p[:-1],0),(p,True),(p,256),(bytearray(p),0)]:
            with self.assertRaises(ValueError):o.masked_planes(raw,guard)

if __name__=='__main__':unittest.main()
