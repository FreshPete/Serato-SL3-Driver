import json
import ast
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/serato-session-capsule.py'))


class RetirementTest(unittest.TestCase):
    def test_unused_handoff_requires_explicit_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan = {'pointerPath':str(root/'pointer')}
            (root/'broker-clean.json').write_text(json.dumps({'controllerExited':True,'brokerStarted':False}))
            with self.assertRaisesRegex(ValueError,'handoff'):
                API['require_retired'](root,plan)
            (root/'broker-session.closed').touch()
            API['require_retired'](root,plan)

    def test_failed_session_can_retire_but_each_release_fact_is_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan = {'pointerPath':str(root/'pointer')}
            session = root/'broker-session'; session.mkdir()
            report = {'successful':False,'reason':'owner_failure','processExited':True,'jobEmpty':True,
                      'ioRetiredVerified':True,'deviceReleasedVerified':True}
            (session/'result.json').write_text(json.dumps(report))
            clean = {**report,'controllerExited':True}
            (root/'broker-clean.json').write_text(json.dumps(clean))
            API['require_retired'](root,plan)
            self.assertFalse(json.loads((root/'broker-clean.json').read_bytes())['successful'])
            for key in ('controllerExited','processExited','jobEmpty','ioRetiredVerified','deviceReleasedVerified'):
                for value in (False,1,None):
                    with self.subTest(key=key,value=value):
                        (root/'broker-clean.json').write_text(json.dumps({**clean,key:value}))
                        with self.assertRaises(ValueError): API['require_retired'](root,plan)

    def test_pointer_or_mismatched_owned_result_refuses_rollback_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); pointer = root/'pointer'; pointer.write_text('active')
            with self.assertRaisesRegex(ValueError,'pointer'):
                API['require_retired'](root,{'pointerPath':str(pointer)})
            self.assertEqual(pointer.read_text(),'active')
            pointer.unlink()
            report = {'successful':True,'processExited':True,'jobEmpty':True,'ioRetiredVerified':True,'deviceReleasedVerified':True}
            (root/'broker-session').mkdir()
            (root/'broker-session/result.json').write_text(json.dumps({**report,'successful':False}))
            (root/'broker-clean.json').write_text(json.dumps({**report,'controllerExited':True}))
            with self.assertRaisesRegex(ValueError,'differs'):
                API['require_retired'](root,{'pointerPath':str(pointer)})


class CapsuleBindingTest(unittest.TestCase):
    def test_literal_sibling_imports_are_in_the_source_pin_inventory(self):
        root=Path(__file__).resolve().parents[1]
        pinned=set(API['SOURCES'])
        for relative in pinned:
            if not relative.endswith('.py'):continue
            for node in ast.walk(ast.parse((root/relative).read_text(encoding='utf-8-sig'))):
                if not isinstance(node,ast.Call) or not node.args or not isinstance(node.args[0],ast.Constant) or not isinstance(node.args[0].value,str):continue
                value=node.args[0].value
                if isinstance(node.func,ast.Name) and node.func.id=='sibling':
                    self.assertIn('scripts/'+value+'.py',pinned,relative)
                elif isinstance(node.func,ast.Attribute) and node.func.attr=='with_name' and value.endswith('.py'):
                    self.assertIn('scripts/'+value,pinned,relative)

    def test_source_interpreter_and_session_location_bindings(self):
        verify = API['verify']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); session = root/'capsule'; session.mkdir(); bundle = root/'bundle'; bundle.mkdir()
            app = root/'Serato DJ Pro.exe'; app.write_bytes(b'synthetic image, never executed')
            (bundle/'deployment-plan.json').write_text(json.dumps({'timingMode':'unmeasured-diagnostic-44100-128'}))
            record = {'schema':'sl3.session-capsule.v1','projectRoot':str(root),'sessionDirectory':str(session),
                      'sources':{'fixture':'0'*64},'brokerLimitMs':600000,'captureOutput':True,
                      'python':{'path':str(Path(sys.executable).absolute()),'sha256':API['sha'](sys.executable)},
                      'application':{'path':str(app),'sha256':API['sha'](app)},
                      'permitPath':str(app.parent/'bundles'/API['PERMIT_NAME']),
                      'bundle':{'path':str(bundle),'sha256':'1'*64}}
            manifest = session/'session-capsule.json'
            def save(): manifest.write_bytes(API['encoded'](record));return API['sha'](manifest)
            def modules(name,function):
                self.assertEqual((name,function),('prepare-asio-deployment.py','verify'))
                return lambda path,expected:self.assertEqual((path,expected),(bundle,'1'*64))
            with patch.dict(verify.__globals__,ROOT=root,APP_SHA=API['sha'](app),
                            source_hashes=lambda:{'fixture':'0'*64},module=modules):
                identity = save()
                self.assertEqual(verify(manifest,identity)[2],session)
                moved = root/'moved'; moved.mkdir(); shutil.copyfile(manifest,moved/manifest.name)
                with self.assertRaisesRegex(ValueError,'moved'):verify(moved/manifest.name,identity)
                record['sources']['fixture'] = '2'*64
                with self.assertRaisesRegex(ValueError,'sources differ'):verify(manifest,save())
                record['sources']['fixture'] = '0'*64
                record['python'] = {'path':str(app),'sha256':API['sha'](app)}
                with self.assertRaisesRegex(ValueError,'interpreter'):verify(manifest,save())


if __name__ == '__main__':
    unittest.main()
