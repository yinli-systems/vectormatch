import unittest
from watcher import wait_state,EXPECTED
class NaturalExitStates(unittest.TestCase):
 def test_absence_is_only_ready_state(self):self.assertEqual(wait_state(None),'PID_STRICTLY_ABSENT')
 def test_exact_original_process_waits(self):self.assertEqual(wait_state(dict(EXPECTED,state='S')),'WAITING_ORIGINAL_GRADLE')
 def test_zombie_never_qualifies_as_absence(self):self.assertEqual(wait_state(dict(EXPECTED,state='Z')),'WAITING_UNREAPED_ORIGINAL_ZOMBIE')
 def test_reused_pid_requires_fresh_qualification(self):self.assertEqual(wait_state(dict(EXPECTED,state='S',startTicks=EXPECTED['startTicks']+1)),'PID_REUSED_OR_OBSERVATION_RACED')
 def test_raced_observation_never_becomes_ready(self):self.assertEqual(wait_state(dict(pid=5669,state='RACED')),'PID_REUSED_OR_OBSERVATION_RACED')
 def test_changed_argv_never_becomes_ready(self):self.assertEqual(wait_state(dict(EXPECTED,state='S',commandSha256='0'*64)),'ORIGINAL_PID_ARGV_CHANGED')
if __name__=='__main__':unittest.main()
