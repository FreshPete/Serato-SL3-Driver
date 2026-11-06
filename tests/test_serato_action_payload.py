import runpy
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(ROOT/'scripts/run-serato-startup-session.py'))


class ActionPayloadTest(unittest.TestCase):
    ready={'event':'action_observer_ready','ordinal':1,'guardedEntries':4,
           'invokesCallbacks':False,'readsAudio':False,'maximumEvents':128}

    def test_known_typed_payloads_preserve_only_the_declared_data(self):
        payloads=[self.ready,
            {'event':'driver_action_receiver_observed','ordinal':2,'controller':1,'thread':7,
             'callbackSlot':16,'captureOffset':8,'receiverMatchesPopup':True},
            {'event':'driver_popup_returned','ordinal':3,'controller':1,'thread':7,'callbacks':1},
            {'event':'driver_controller_message_returned','ordinal':4,'controller':1,'thread':7,'message':0x4f},
            {'event':'genuine_sl3_arrival_published','ordinal':5,'thread':7},
            {'event':'action_observer_fault','ordinal':6,'stage':'callback_read'}]
        for payload in payloads:
            self.assertEqual(api['action_observation'](payload),{k:v for k,v in payload.items() if k!='event'})
        self.assertIsNone(api['action_observation']({'event':'trace_ready'}))

    def test_unknown_fields_and_invalid_types_or_bounds_are_refused(self):
        for change in ({'address':'0x1234'},{'ordinal':True},{'ordinal':129},{'invokesCallbacks':0},
                       {'readsAudio':True},{'maximumEvents':129},{'guardedEntries':3}):
            with self.subTest(change=change),self.assertRaises(ValueError):api['action_observation']({**self.ready,**change})
        for change in ({'controller':0},{'thread':False},{'message':True}):
            payload={'event':'driver_controller_message_returned','ordinal':2,'controller':1,'thread':7,'message':1}
            with self.subTest(change=change),self.assertRaises(ValueError):api['action_observation']({**payload,**change})

    def test_supervisor_retains_fields_and_rejects_a_sequence_gap_with_cleanup(self):
        helpers=runpy.run_path(str(ROOT/'tests/test_serato_startup_supervisor.py'))
        for gap in (False,True):
            clock=helpers['Clock']();owner=self
            class Backend(helpers['FakeBackend']):
                def start(self,script,callback):
                    self.calls.append('start')
                    for payload in (owner.ready,{'event':'trace_ready'},
                        {'event':'driver_popup_returned','ordinal':3 if gap else 2,'controller':1,'thread':7,'callbacks':1},
                        {'event':'installer_action'},{'event':'asio_live_start_end','result':0}):
                        callback({'type':'send','payload':payload})
            backend=Backend(clock)
            result=api['supervise'](backend,'synthetic',lambda:None,lambda:False,clock,viewing_seconds=.1)
            self.assertEqual(backend.calls[-1],'cleanup')
            if gap:
                self.assertFalse(result['asioStartObserved']);self.assertIn('event sequence',result['error'])
            else:
                self.assertTrue(result['asioStartObserved']);self.assertTrue(result['tracerDetached'])
                observations=[e['actionObservation'] for e in result['events'] if 'actionObservation' in e]
                self.assertEqual(observations[1],{'ordinal':2,'controller':1,'thread':7,'callbacks':1})


if __name__=='__main__':unittest.main()
