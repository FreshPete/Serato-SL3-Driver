"""Inventory both historical startup arrays offline; export no XML or keys."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


legacy=module('export-serato-legacy-descriptors.py')
images=module('export-serato-clock-handshake-evidence.py')
require=legacy.require
def sha(raw):return hashlib.sha256(raw).hexdigest()


def project(decoded):
    require(8<=len(decoded)<=4*1024*1024 and len(decoded)%8==0,'Invalid decoded block bound')
    xml,separator,padding=decoded.partition(b'\0')
    require(not separator or not any(padding),'Nonzero bytes after XML terminator')
    require(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper(),'DTD/entity declarations refused')
    root=ET.fromstring(xml);identities=[]
    for node in root.iter():
        fields={child.tag:child.get('value') for child in node if child.get('value') is not None}
        if 'vendor_id' not in fields or 'product_id' not in fields:continue
        vendor,product=int(fields['vendor_id'],0),int(fields['product_id'],0)
        require(0<=vendor<=65535 and 0<=product<=65535,'Non-scalar/out-of-range declared identity')
        identities.append({'type':node.tag,'name':node.get('name'),'vendor':vendor,'product':product})
    return {'xmlSha256':sha(xml),'xmlBytes':len(xml),'bounds':'zero-padded XML' if separator else 'whole-block XML',
            'identities':identities,'supportedApps':[n.get('value') for n in root.findall('./supported_apps/app')]}


def inventory(target):
    proven,*_=legacy.inspect(target) # Pins binary/array/reader/decoder and checks six ECB vector directions.
    binary=ROOT/f'artifacts/extracted/Serato DJ Pro {target["version"]}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe'
    image=images.Image(binary,target['sha']);data=image.data
    key_row=image.at(target['key'],'movabs')
    key=struct.pack('<Q',key_row.operands[1].imm)
    cipher=legacy.ResourceBlowfish(struct.unpack('<18I',data(target['p'],72)),struct.unpack('<1024I',data(target['s'],4096)),key)
    ids=struct.unpack(f'<{target["count"]}I',data(target['ids'],target['count']*4));rows=[];total=0
    for index,rid in enumerate(ids):
        size=struct.unpack('<I',data(target['lengths']+rid*4,4))[0]
        address=struct.unpack('<Q',data(target['pointers']+rid*8,8))[0];total+=size
        require(8<=size<=4*1024*1024 and size%8==0 and total<=64*1024*1024,'Registered resource size exceeds bounds')
        raw=data(address,size);decoded=cipher.decrypt(raw)
        rows.append({'registrationIndex':index,'resourceId':rid,'cipherSha256':sha(raw),
                     'decodedSha256':sha(decoded),**project(decoded)})
    matching=[row for row in rows if any(n['vendor']==0x1cc5 and n['product']==1 for n in row['identities'])]
    require(len(rows)==target['count'] and len(matching)==1 and matching[0]['resourceId']==target['resource_id'] and
            matching[0]['xmlSha256']==proven['resource']['xmlSha256'],'SL3 resource match differs from independently checked descriptor')
    report=ROOT/f'analysis/serato{target["version"].replace(".","")}-startup-cutoff-20261101.json'
    focused=json.loads(report.read_text(encoding='utf-8-sig'));functions=focused['functions']
    require(focused['binary_sha256'].lower()==target['sha'] and len(functions)==1 and functions[0]['complete'] is True and
            int(functions[0]['start'],16)==target['startup'][0] and int(functions[0]['end_exclusive'],16)==target['startup'][1] and
            not functions[0].get('diagnostic'),'Startup focused report differs')
    return {'version':target['version'],'binarySha256':target['sha'],'registeredResources':len(rows),
            'allRegisteredResourcesParsed':True,'cipherBytes':total,'sl3Matches':matching,
            'xmlBoundsCounts':{name:sum(r['bounds']==name for r in rows) for name in ('zero-padded XML','whole-block XML')},
            'startupReportSha256':sha(report.read_bytes()),'startupRange':[hex(n) for n in target['startup']],
            'rows':rows}


def product_branch(target,site):
    image=images.Image(f'artifacts/extracted/Serato DJ Pro {target["version"]}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe',target['sha'])
    expected=[(0,'mov','ecx, 0x1cc5'),(5,'mov','rax, qword ptr [rsp + 0x48]'),
              (10,'cmp','word ptr [rax + 0xa8], cx'),(23,'movzx','eax, word ptr [rax + 0xaa]'),
              (30,'sub','ax, 0x18'),(34,'cmp','ax, 1')]
    facts=[]
    for offset,mnemonic,operands in expected:
        row=image.at(site+offset,mnemonic,operands);facts.append({'va':hex(row.address),'assembly':row.mnemonic+' '+row.op_str})
    skip=image.at(site+38,'ja');require(skip.operands[0].imm>skip.address,'Unexpected range skip direction')
    return {'version':target['version'],'selectedInstructions':facts,'rangeSkipVA':hex(skip.address),
            'selectedProductRange':[24,25],'sl3ProductOneEntersRangeBody':False,
            'limit':'This one literal predicate only; not an exhaustive eligibility search or runtime branch observation'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory-output',type=Path,required=True);args=parser.parse_args()
    output=args.inventory_output.resolve()
    require(output.parent==(ROOT/'analysis').resolve() and not output.exists(),'Choose a fresh direct analysis inventory file')
    records=[]
    for target in legacy.TARGETS:
        records.append(inventory(target));print('Inventoried '+target['version']+' startup resources',flush=True)
    saved={'scope':'All listed startup resources and scalar declared vendor_id/product_id fields only','versions':records}
    output.write_text(json.dumps(saved,indent=2)+'\n')
    old,new=[{r['xmlSha256'] for r in version['rows']} for version in records]
    compact={'scope':saved['scope'],'versions':[{k:v for k,v in record.items() if k!='rows'} for record in records],
             'unchangedXmlHashes':len(old&new),'oldOnlyXmlHashes':len(old-new),'newOnlyXmlHashes':len(new-old),
             'sl3XmlUnchanged':records[0]['sl3Matches'][0]['xmlSha256']==records[1]['sl3Matches'][0]['xmlSha256'],
             'selectedRaneProductBranches':[product_branch(t,site) for t,site in zip(legacy.TARGETS,(0x1400fa7a8,0x1400fb258))],
             'inventoryPath':output.relative_to(ROOT).as_posix(),'inventorySha256':sha(output.read_bytes()),
             'exporterSha256':sha(Path(__file__).read_bytes()),'legacyReaderSha256':sha((ROOT/'scripts/export-serato-legacy-descriptors.py').read_bytes()),
             'vendorCodeExecuted':False,'runtimeAdmissionVerified':False,'currentSeratoIntegrationVerified':False,
             'limits':['No second scalar SL3 identity in these registered resource XMLs; external/later/runtime registration is outside scope',
                       'Retained declarations do not prove startup parser acceptance or any supported runtime session',
                       'The inspected Rane range body selects products 24/25 and does not explain an SL3 support cutoff',
                       'No descriptor, executable, registration, account, driver or USB identity was modified']}
    (ROOT/'docs/evidence/serato-cutoff-registration-20261101.json').write_text(json.dumps(compact,indent=2)+'\n')
    print('Checked complete historical resource inventory; no runtime support claim')


if __name__=='__main__':main()
