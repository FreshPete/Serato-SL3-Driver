"""Prepare/validate a genuine-SL3 offline XML hypothesis; never installs or launches Serato."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NAME='SL3 Rebuild Development'
HISTORY_SHA='a63a02804e5a00cc1da48faff9c9bdfa962da0f1c3b09a7019d9eec0570fab3a'
SCHEMA_SHA='9e15093df616f9b9eac7f2f0fc1dbebfc55ce353415e22569fcfa00b98c1cc56'
XML_NAME='rane-sl3-windows-candidate.xml'
KEEP=('vendor_id','product_id','requires_usb','midi_direction','sample_rate','num_decks','dvs_device',
      'hardware_mixer','output_calibration_gain','braking_type',
      'software_mic_gain','software_cue_gain','software_cf_curve','software_uf_curve','software_master_cue',
      'software_cue_mix','software_split_cue','software_crossfader_reverse',
      'provides_talk_over','cue_crossfader_type','mac_audio_api','mac_audio_device_name')

def require(ok,message):
    if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path,limit=16*1024*1024):
    require(path.is_file() and not path.is_symlink() and not path.is_junction(),'Regular non-reparse input required')
    with path.open('rb') as f:raw=f.read(limit+1)
    require(0<len(raw)<=limit,'Input exceeds bounded size');return raw
def pairs(rows):
    result={}
    for k,v in rows:require(k not in result,'Duplicate JSON field');result[k]=v
    return result
def parsed(raw):
    def invalid(value):raise ValueError('Nonfinite JSON number: '+value)
    value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)
    require(type(value) is dict,'JSON object required');return value
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def schema_device_order(schema):
    require(b'<!ENTITY' not in schema.upper(),'Schema entities refused')
    root=ET.fromstring(schema);ns={'x':'http://www.w3.org/2001/XMLSchema'}
    types={n.get('name'):n for n in root.findall('x:complexType',ns)}
    def fields(name,seen):
        require(name in types and name not in seen and len(seen)<32,'Known acyclic schema type required')
        node=types[name];extension=node.find('x:complexContent/x:extension',ns)
        result=fields(extension.get('base'),seen|{name}) if extension is not None else []
        return result+[n.get('name') for n in (extension if extension is not None else node).findall('x:sequence/x:element',ns)]
    return fields('midi_native_pro_device_type',set())

def candidate_bytes(history,order=None):
    require(history['name']=='Rane SL3' and history['type']=='native_pro_device' and history['supportedApps']==['Serato DJ'], 'Historical SL3 identity/type/apps differ')
    f=history['fields']
    require(f['vendor_id']=='0x1CC5' and f['product_id']=='0x0001' and f['handshake_type']=='HANDSHAKE_TYPE_DRIVER_API', 'Genuine SL3 identity/legacy path required')
    require(f['midi_direction']=='none' and f['requires_usb']=='true' and f['sample_rate']=='HZ48000' and f['num_decks']=='3' and f['dvs_device']=='DVS_DEVICE_YES','Historical component/rate/deck contract differs')
    require(history['resource']['deviceSecretFieldEmpty'] is True,'No nonempty secret may enter the candidate')
    require(history['inputsInDeclaredOrder']==['Deck3In','Deck1In','Deck2In'] and history['outputsInDeclaredOrder']==['Deck3Out','Deck1Out','Deck2Out'],'Historical endpoint order differs')
    require(history['bufferAlignments']==[{'sampleRate':'HZ48000','values':['48']}],'Historical alignment differs')
    root=ET.Element('root',creation_date='2026-11-02');root.append(ET.Comment('Offline compatibility hypothesis only; no provider, deployment or runtime approval'))
    apps=ET.SubElement(root,'supported_apps');ET.SubElement(apps,'app',value='Serato DJ')
    device=ET.SubElement(root,'native_pro_device',name='Rane SL3')
    for key in KEEP:
        require(type(f[key]) is str and len(f[key])<=128,'Bounded historical scalar required')
        ET.SubElement(device,key,value=f[key])
    for key,value in [('secret_key',''),('has_hid','false'),('handshake_type','HANDSHAKE_TYPE_NONE'),
                      ('use_legacy_portaudio','true'),('win_audio_api','ASIO'),('win_audio_device_name',NAME)]:
        ET.SubElement(device,key,value=value)
    alignment=ET.SubElement(device,'buffer_alignments',sample_rate='HZ48000');ET.SubElement(alignment,'buffer_alignment',value='48')
    for tag,child,key in [('input_endpoint','mixer_in','inputsInDeclaredOrder'),('output_endpoints','mixer_out','outputsInDeclaredOrder')]:
        group=ET.SubElement(device,tag)
        for value in history[key]:ET.SubElement(group,child,value=value)
    sources=ET.SubElement(device,'record_sources')
    for value in history['recordSources']:
        require(set(value)=={'rec_src','endpoint'},'Unexpected historical recording attribute')
        ET.SubElement(sources,'map',**value)
    driver=ET.SubElement(device,'driver');detect=ET.SubElement(driver,'driver_detection')
    for platform in ['osx','win_x86']:ET.SubElement(detect,platform,name='')
    ET.SubElement(detect,'win_x64',name='SOFTWARE\\ASIO\\'+NAME)
    if order is not None:
        require(all(node.tag in order for node in device),'Candidate field absent from current schema sequence')
        device[:]=sorted(device,key=lambda node:order.index(node.tag))
    ET.indent(root,space='  ')
    raw=ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'
    require(len(raw)<=65536,'Candidate size bound exceeded')
    return raw

def source_context():
    pins={}
    def pin(relative,limit=16*1024*1024):
        raw=read(ROOT/relative,limit);pins[relative]=digest(raw);return raw
    historical=parsed(pin('docs/evidence/serato-legacy-sl3-descriptors.json'))
    require(pins['docs/evidence/serato-legacy-sl3-descriptors.json']==HISTORY_SHA,'Historical evidence differs')
    targets=historical['targets'];require(len(targets)==2 and {t['version'] for t in targets}=={'2.5.5','2.5.6'},'Both historical versions required')
    for t in targets:
        path=f"artifacts/extracted/Serato DJ Pro {t['version']}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe"
        require(digest(pin(path,256*1024*1024))==t['binarySha256'],'Historical executable differs')
    first=targets[0]
    require(all(t['resource']['xmlSha256']==first['resource']['xmlSha256'] and t['fields']==first['fields'] and
                candidate_bytes(t)==candidate_bytes(first) for t in targets),'Historical candidate inputs disagree')
    for rel in ['scripts/prepare-serato-sl3-candidate.py','scripts/validate-descriptor-schema.ps1',
                'scripts/export-serato-clock-handshake-evidence.py','scripts/inspect-serato-resource-archive.py',
                'src/asio/com_server.cpp','scripts/prepare-asio-deployment.py']:
        pin(rel)
    require(('constexpr char value[]="'+NAME+'";').encode() in read(ROOT/'src/asio/com_server.cpp'),'ASIO driver name differs')
    require(("NAME = '"+NAME+"'").encode() in read(ROOT/'scripts/prepare-asio-deployment.py'),'ASIO registry name differs')
    manifest_rel='artifacts/build/native/native-build-Release.json';build=parsed(pin(manifest_rel))
    for rel,sha in build['inputs'].items():require(digest(read(ROOT/rel))==sha.lower(),'Native build source changed: '+rel)
    dll='artifacts/build/native/Release/sl3_asio.dll'
    require(digest(pin(dll))==build['asioComponent']['comDllSha256'].lower(),'Native ASIO DLL differs')
    h=module('candidate_image','export-serato-clock-handshake-evidence.py');r=module('candidate_archive','inspect-serato-resource-archive.py')
    require(digest(pin(r.APP_RELATIVE,256*1024*1024))==h.CURRENT_SHA,'Current original differs')
    require(digest(read(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'),256*1024*1024))==h.CURRENT_SHA,'Installed executable differs')
    app=h.Image(r.APP_RELATIVE,h.CURRENT_SHA)
    archive_rel=str(Path(r.APP_RELATIVE).with_name('userio_resources.bin'));archive=pin(archive_rel)
    require(digest(archive)==r.ARCHIVE_SHA and read(Path('C:/Program Files/Serato/Serato DJ Pro/userio_resources.bin'))==archive,'Current archive differs')
    seed=app.data(0x142f2de98,16)
    key=struct.unpack('<4I',bytes((((x^0xcf)>>(n&7))|((x^0xcf)<<((8-(n&7))&7)))&255 for n,x in enumerate(seed)))
    size=struct.unpack_from('<Q',archive)[0];entries=r.parse_index(r.decode_block(archive[8:8+size],key),len(archive),8+size)
    selected=[e for e in entries if e['name']=='midi/MIDI.xsd'];require(len(entries)==229 and len(selected)==1,'Current schema inventory differs')
    e=selected[0];schema,crc=r.unpack_member(archive[e['offset']:e['offset']+e['size']],key,e['name'])
    require(digest(schema)==SCHEMA_SHA and b'<!ENTITY' not in schema.upper(),'Current schema differs')
    contract={}
    for name in ['component-profiles','audio-routing','bank-adaptation','endpoint-consumers','output-routing','primary-pointer','usb-arrival']:
        rel=f'docs/evidence/serato500-{name}.json';value=parsed(pin(rel))
        require(value.get('binarySha256',value.get('currentSeratoSha256'))==h.CURRENT_SHA,'Current contract image differs')
        contract[name]=pins[rel]
    return {'history':first,'pins':pins,'schemaBytes':schema,'schemaMetadata':{'resource':e['name'],'sha256':SCHEMA_SHA,'crc32':crc},
            'contracts':contract,'nativeBuildInputPinsVerified':len(build['inputs']),'currentApplicationSha256':h.CURRENT_SHA}

def validate_schema(xml,schema):
    temp=tempfile.TemporaryDirectory(prefix='sl3-descriptor-schema-');folder=Path(temp.name).resolve()
    require(folder.parent==Path(tempfile.gettempdir()).resolve() and folder.name.startswith('sl3-descriptor-schema-'),'Owned temporary folder required')
    try:
        for name,raw in [('schema.xsd',schema),('descriptor.xml',xml)]:
            with (folder/name).open('xb') as f:f.write(raw)
        result=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/validate-descriptor-schema.ps1'),
            '-SchemaPath',str(folder/'schema.xsd'),'-XmlPath',str(folder/'descriptor.xml')],capture_output=True,timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        value=parsed(result.stdout)
        require(result.returncode==0 and value.get('valid') is True,'Schema rejected candidate: '+str(value.get('errors')))
        require(value['schemaSha256']==digest(schema) and value['xmlSha256']==digest(xml) and value['externalResolution'] is False,'Schema input binding differs')
        return value
    finally:temp.cleanup()

def manifest(context,raw,validation):
    return {'schema':'sl3.serato-descriptor-candidate.v1','status':'offline_hypothesis','candidateFile':XML_NAME,'candidateSha256':digest(raw),
      'historicalXmlSha256':context['history']['resource']['xmlSha256'],'currentApplicationSha256':context['currentApplicationSha256'],
      'sourceSha256':context['pins'],'contractEvidenceSha256':context['contracts'],'nativeBuildInputPinsVerified':context['nativeBuildInputPinsVerified'],
      'schemaMetadata':context['schemaMetadata'],'schemaValidation':validation,
      'intentionalChanges':{'handshake_type':{'from':'HANDSHAKE_TYPE_DRIVER_API','to':'HANDSHAKE_TYPE_NONE','status':'Unverified control/connection hypothesis'},
        'win_audio_device_name':{'from':'SL 3','to':NAME},'win_x64_driver_detection':{'from':'SOFTWARE\\ASIO\\Rane SL 3','to':'SOFTWARE\\ASIO\\'+NAME},
        'explicitCurrentDefaults':{'has_hid':'false','use_legacy_portaudio':'true'},'otherDriverDetectionPlatforms':'Empty schema-required placeholders; only Windows x64 driver proposed',
        'historicalFieldsOmittedWithoutReplacement':['has_faders','platter_resolution','provides_software_through'],
        'fieldOrdering':'Current schema base/extension sequence rather than historical element order'},
      'preserved':{'identity':'Rane SL3, VID 0x1CC5/PID 0x0001','midi_direction':'none','requires_usb':True,'nominalRateHz':48000,
        'declaredDecks':3,'dvs_device':'DVS_DEVICE_YES','applicationFrameAlignment':48,'historicalMacStringsRetainedWithoutValidation':True},
      'logicalMaps':{'input':{'Deck3In':[0,1],'Deck1In':[2,3],'Deck2In':[4,5]},'output':{'Deck3Out':[0,1],'Deck1Out':[2,3],'Deck2Out':[4,5]},'physicalMappingVerified':False},
      'candidateKnownSourceShapeVerified':True,'schemaAcceptanceIsApplicationAcceptance':False,
      'applicationExecuted':False,'applicationModified':False,'archiveModified':False,'providerInstalled':False,'descriptorRegistered':False,
      'driverInstalled':False,'deviceAccess':False,'audioPlayed':False,'firmwareModified':False,'accountOrEntitlementModified':False,
      'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False,'deploymentApproved':False,
      'remaining':['Current provider/container registration and integrity/signature/rollback design',
        'Validate the genuine SL3 control contract behind the explicit NONE hypothesis; do not treat it as implemented DRIVER_API',
        'Resolve service/state-message eligibility and unique actual ASIO selection',
        'Measured native timing/profile, physical mapping/levels/reopening and protected driver deployment',
        'Real current Serato admission, legitimate account/product behavior and two-deck DVS; Mac deferred']}

def location(path):
    require(not path.is_symlink() and not path.is_junction(),'Reparse output refused')
    absolute=path.absolute()
    require(absolute.parent.resolve()==(ROOT/'analysis').resolve() and re.fullmatch(r'sl3-descriptor-candidate-[A-Za-z0-9-]{1,64}',absolute.name),'Use direct analysis/sl3-descriptor-candidate-* directory')
    return absolute

def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare',type=Path);mode.add_argument('--validate',type=Path);args=parser.parse_args()
    path=location(args.prepare or args.validate) if args.prepare or args.validate else None
    if args.prepare:require(not path.exists() and path.parent.is_dir(),'Fresh candidate directory required')
    context=source_context();raw=candidate_bytes(context['history'],schema_device_order(context['schemaBytes']))
    if path is None:
        print(json.dumps(manifest(context,raw,None),indent=2));return
    if args.validate:
        require(path.is_dir() and {p.name for p in path.iterdir()}=={XML_NAME,'candidate.json'},'Exact candidate bundle files required')
        require(read(path/XML_NAME,65536)==raw,'Candidate XML differs from fixed reviewed construction')
    validation=validate_schema(raw,context['schemaBytes']);value=manifest(context,raw,validation)
    for relative,expected in context['pins'].items():require(digest(read(ROOT/relative,256*1024*1024))==expected,'Source changed during preparation')
    if args.prepare:
        path.mkdir()
        with (path/XML_NAME).open('xb') as f:f.write(raw)
        with (path/'candidate.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    else:require(parsed(read(path/'candidate.json'))==value,'Candidate manifest/runtime differs')
    print(json.dumps({'valid':True,'status':'offline_hypothesis','candidateSha256':digest(raw),'schemaValidationPassed':True,
                      'currentSeratoAdmissionVerified':False,'deviceAccess':False,'deploymentApproved':False}))

if __name__=='__main__':main()
