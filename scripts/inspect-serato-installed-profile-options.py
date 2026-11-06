"""Inspect declared startup options in the pinned native-device schema; no app execution."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SHA = '9e15093df616f9b9eac7f2f0fc1dbebfc55ce353415e22569fcfa00b98c1cc56'
NS = '{http://www.w3.org/2001/XMLSchema}'
KNOWN_DOCTYPE = (b'<!DOCTYPE xs:schema\n  PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
                 b'"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def declarations(raw, type_name='midi_native_pro_device_type'):
    require(0 < len(raw) <= 16 * 1024 * 1024 and b'<!ENTITY' not in raw.upper(),
            'Bounded schema without entity declarations required')
    # The pinned vendor schema carries this unrelated external XHTML DTD.
    # Remove only its exact declaration before parsing: never resolve a URL.
    parsed = raw.replace(KNOWN_DOCTYPE, b'', 1)
    require(b'<!DOCTYPE' not in parsed.upper(), 'Unknown or repeated document type declaration')
    root = ET.fromstring(parsed)
    require(root.tag == NS + 'schema', 'XML Schema document required')
    types = {}
    for node in root.findall(NS + 'complexType'):
        name = node.get('name')
        require(name and name not in types, 'Unique named complex types required')
        types[name] = node
    hierarchy, elements, attributes = [], [], []

    def visit(name):
        require(name in types and name not in hierarchy and len(hierarchy) < 32, 'Known acyclic device hierarchy required')
        hierarchy.append(name)
        node = types[name]
        extension = node.find(NS + 'complexContent/' + NS + 'extension')
        content = node
        if extension is not None:
            visit(extension.get('base'))
            content = extension
        # Refuse unexpanded constructs instead of treating them as an absence.
        require(not any(child.tag in (NS + 'choice', NS + 'all', NS + 'group', NS + 'any', NS + 'anyAttribute',
                                     NS + 'attributeGroup', NS + 'simpleContent') for child in content),
                'Unexpanded device declaration construct')
        require(node.find(NS + 'complexContent/' + NS + 'restriction') is None, 'Device restriction not supported')
        local_elements, local_attributes = [], []
        for sequence in content.findall(NS + 'sequence'):
            for field in sequence:
                require(field.tag == NS + 'element' and field.get('name') and field.get('ref') is None,
                        'Explicit named top-level device element required')
                local_elements.append(field.get('name'))
        for attribute in content.findall(NS + 'attribute'):
            require(attribute.get('name') and attribute.get('ref') is None, 'Explicit named device attribute required')
            local_attributes.append(attribute.get('name'))
        require(len(set(local_elements)) == len(local_elements) and len(set(local_attributes)) == len(local_attributes),
                'Duplicate declaration within one type')
        elements.extend(local_elements)
        attributes.extend(local_attributes)
    visit(type_name)
    return hierarchy, elements, attributes


def inspect():
    archive_api = runpy.run_path(str(ROOT / 'scripts/inspect-serato-resource-archive.py'))
    reader = runpy.run_path(str(ROOT / 'scripts/export-serato-clock-handshake-evidence.py'))
    image = reader['Image'](archive_api['APP_RELATIVE'], archive_api['APP_SHA'])
    source = ROOT / archive_api['APP_RELATIVE']
    archive = source.with_name('userio_resources.bin').read_bytes()
    require(hashlib.sha256(archive).hexdigest() == archive_api['ARCHIVE_SHA'], 'Original resource archive differs')
    seed = image.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes((((x ^ 0xcf) >> (n & 7)) | ((x ^ 0xcf) << ((8 - (n & 7)) & 7))) & 255
                                  for n, x in enumerate(seed)))
    size = struct.unpack_from('<Q', archive)[0]
    entries = archive_api['parse_index'](archive_api['decode_block'](archive[8:8 + size], key), len(archive), 8 + size)
    selected = [row for row in entries if row['name'] == 'midi/MIDI.xsd']
    require(len(entries) == 229 and len(selected) == 1, 'Original schema resource inventory differs')
    row = selected[0]
    schema, crc = archive_api['unpack_member'](archive[row['offset']:row['offset'] + row['size']], key, row['name'])
    require(hashlib.sha256(schema).hexdigest() == SCHEMA_SHA, 'Original schema differs')
    hierarchy, elements, attributes = declarations(schema)
    driver_hierarchy, driver_elements, driver_attributes = declarations(schema, 'device_driver_type')
    probes = ('connect_on_start', 'connect_on_launch', 'connect_on_arrival', 'auto_connect')
    return {'schema': 'sl3.serato-installed-profile-options.v1', 'applicationSha256': image.sha,
            'archiveSha256': archive_api['ARCHIVE_SHA'], 'schemaSha256': SCHEMA_SHA, 'schemaZipCrc32': crc,
            'deviceTypeHierarchyDerivedFirst': hierarchy, 'topLevelElementCount': len(elements),
            'topLevelAttributeCount': len(attributes),
            'uniqueTopLevelElementNames': len(set(elements)), 'uniqueTopLevelAttributeNames': len(set(attributes)),
            'connectionDeclarations': sorted({name for name in elements + attributes if 'connect' in name.lower()}),
            'driverDeclarations': sorted({name for name in elements + attributes if 'driver' in name.lower()}),
            'driverTypeHierarchyDerivedFirst': driver_hierarchy,
            'driverTypeElements': sorted(set(driver_elements)), 'driverTypeAttributes': sorted(set(driver_attributes)),
            'namedStartupOptionDeclared': {name: name in elements or name in attributes for name in probes},
            'scope': 'Declared top-level options inherited by native_pro_device in this exact schema; '
                     'nested definitions, other descriptor kinds and executable parser extensions are not exhausted',
            'knownExternalDoctypeRemovedBeforeParsing': KNOWN_DOCTYPE in schema,
            'externalDtdLoaded': False,
            'noXmlOnlySolutionProven': True, 'vendorCodeExecuted': False, 'xmlPublished': False,
            'keyMaterialPublished': False, 'installedFilesChanged': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inspect()
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(rendered)
    else:
        print(rendered, end='')
