"""Check the comparison preserves branches/constants while exposing relocations."""
import importlib.util
from pathlib import Path
import unittest

import capstone as cs

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cutoff_caller_test',ROOT/'scripts/export-serato-cutoff-caller.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class CallerShapeTests(unittest.TestCase):
    def shaped(self,hex_bytes,start=0x1000,end=None):
        data=bytes.fromhex(hex_bytes);dis=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);dis.detail=True
        return v.shape(list(dis.disasm(data,start)),start,end or start+len(data),0x1000,0x10000)

    def test_relocated_local_branch_preserves_instruction_target(self):
        a=self.shaped('740190c3');b=self.shaped('740190c3',0x2000)
        result=v.compare(a,b)
        self.assertTrue(result['localDirectEdgesEqual']);self.assertEqual(result['changes'],[])
        self.assertEqual(a['localDirectEdges'],[[0,'je',2]])

    def test_changed_local_branch_target_is_visible(self):
        result=v.compare(self.shaped('740190c3'),self.shaped('740090c3'))
        self.assertFalse(result['localDirectEdgesEqual']);self.assertEqual(result['changes'][0]['index'],0)

    def test_nonaddress_constant_and_object_field_changes_survive(self):
        for left,right in [('b801000000c3','b802000000c3'),('803800c3','80780100c3')]:
            self.assertTrue(v.compare(self.shaped(left),self.shaped(right))['changes'])

    def test_external_calls_and_rip_data_are_explicitly_uncompared(self):
        a=self.shaped('e800010000488b0500010000c3');b=self.shaped('e800020000488b0500020000c3')
        result=v.compare(a,b)
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['uncomparedReferenceCounts'],[2,2])
        self.assertNotEqual(a['uncomparedReferences'],b['uncomparedReferences'])

    def test_partial_decode_and_branch_into_instruction_refused(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.shaped('c30f')
        with self.assertRaisesRegex(ValueError,'interior'):self.shaped('eb01b801000000c3')

    def test_different_instruction_counts_are_not_aligned_away(self):
        with self.assertRaisesRegex(ValueError,'counts differ'):v.compare(self.shaped('90c3'),self.shaped('c3'))


if __name__=='__main__':unittest.main()
