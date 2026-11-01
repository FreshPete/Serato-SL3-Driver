"""Local CFG checks preserve uncertainty; no original app or device execution."""
import importlib.util
from pathlib import Path
import unittest
import capstone as cs

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('support_consumer_flow',ROOT/'scripts/export-serato-historical-support-consumer.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class LocalFlowTests(unittest.TestCase):
    def rows(self,text):
        dis=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);dis.detail=True
        return list(dis.disasm(bytes.fromhex(text),0x1000))

    def test_false_branch_skips_call_and_true_can_reach_it(self):
        rows=self.rows('7405e800010000c3')
        self.assertEqual(v.local_reach(rows,0x1007,{0x1002})['reachedTargets'],[])
        self.assertEqual(v.local_reach(rows,0x1002,{0x1002})['reachedTargets'],['0x1002'])

    def test_back_edge_reaches_previously_skipped_call(self):
        rows=self.rows('7405e800010000ebf9')
        self.assertEqual(v.local_reach(rows,0x1007,{0x1002})['reachedTargets'],['0x1002'])

    def test_indirect_branch_preserves_unknown_exit(self):
        result=v.local_reach(self.rows('ffe0'),0x1000,set())
        self.assertEqual(result['unresolvedExits'],[{'site':'0x1000','kind':'indirect-branch'}])
        prefixed=v.local_reach(self.rows('f2ffe0c3'),0x1000,{0x1003})
        self.assertEqual(prefixed['reachedTargets'],[])
        self.assertEqual(prefixed['unresolvedExits'][0]['kind'],'indirect-branch')

    def test_external_branch_and_fallthrough_preserve_unknown_exits(self):
        for text,kind in [('eb7f','external-branch'),('90','external-fallthrough')]:
            result=v.local_reach(self.rows(text),0x1000,set())
            self.assertEqual(result['unresolvedExits'][0]['kind'],kind)

    def test_call_returns_are_an_explicit_model_assumption(self):
        result=v.local_reach(self.rows('e800010000c3'),0x1000,{0x1005})
        self.assertEqual(result['reachedTargets'],['0x1005'])
        self.assertTrue(result['normalCallReturnAssumed'])
        self.assertFalse(result['exceptionsAndCallbacksModeled'])

    def test_conditional_external_path_is_not_hidden_by_local_return(self):
        result=v.local_reach(self.rows('747fc3'),0x1000,set())
        self.assertEqual(len(result['unresolvedExits']),1)
        self.assertEqual(result['visitedInstructions'],2)

    def test_branch_into_instruction_interior_remains_unresolved(self):
        result=v.local_reach(self.rows('eb01b801000000c3'),0x1000,set())
        self.assertEqual(result['unresolvedExits'][0]['kind'],'non-boundary-branch')


if __name__=='__main__':unittest.main()
