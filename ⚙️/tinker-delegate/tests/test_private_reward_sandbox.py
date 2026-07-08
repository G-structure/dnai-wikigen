import unittest

from tinker_delegate.private_reward import Candidate
from tinker_delegate.private_reward_sandbox import (
    PythonCandidateSandbox,
    SandboxOutcome,
    SandboxPolicy,
)


class PythonCandidateSandboxTest(unittest.TestCase):
    def test_runs_candidate_with_bounded_public_result(self):
        sandbox = PythonCandidateSandbox()

        result = sandbox.run(Candidate(b"print(sum([1, 2, 3]))"))

        self.assertTrue(result.accepted)
        self.assertEqual(result.outcome, SandboxOutcome.PASS)
        self.assertEqual(result.stdout, "6\n")
        public = result.to_public_dict()
        self.assertIn("candidate_hash", public)
        self.assertNotIn("sum([1, 2, 3])", str(public))

    def test_rejects_network_file_and_process_escape_attempts(self):
        sandbox = PythonCandidateSandbox()

        cases = [
            b"import socket\nprint(socket.socket())",
            b"print(open('/etc/passwd').read())",
            b"import subprocess\nsubprocess.run(['echo', 'x'])",
            b"__builtins__",
            b"().__class__",
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                result = sandbox.run(Candidate(payload))
                self.assertEqual(result.outcome, SandboxOutcome.POLICY_REJECTED)
                self.assertFalse(result.accepted)
                self.assertEqual(result.stdout, "")

    def test_runtime_import_guard_fails_closed(self):
        sandbox = PythonCandidateSandbox()

        result = sandbox.run(Candidate(b"mod = __import__('socket')\nprint(mod)"))

        self.assertEqual(result.outcome, SandboxOutcome.POLICY_REJECTED)
        self.assertIn("not allowed", result.stderr)

    def test_stdout_is_capped(self):
        sandbox = PythonCandidateSandbox(SandboxPolicy(max_stdout_bytes=12))

        result = sandbox.run(Candidate(b"print('x' * 100)"))

        self.assertEqual(result.outcome, SandboxOutcome.PASS)
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 12)
        self.assertTrue(result.stdout_truncated)

    def test_stderr_is_capped(self):
        sandbox = PythonCandidateSandbox(SandboxPolicy(max_stderr_bytes=20))

        result = sandbox.run(Candidate(b"raise ValueError('x' * 100)"))

        self.assertEqual(result.outcome, SandboxOutcome.RUNTIME_ERROR)
        self.assertLessEqual(len(result.stderr.encode("utf-8")), 20)
        self.assertTrue(result.stderr_truncated)

    def test_timeout_is_bounded(self):
        sandbox = PythonCandidateSandbox(SandboxPolicy(timeout_seconds=0.1, cpu_seconds=5))

        result = sandbox.run(Candidate(b"while True:\n    pass"))

        self.assertEqual(result.outcome, SandboxOutcome.TIMEOUT)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)

    def test_random_seed_is_deterministic(self):
        sandbox = PythonCandidateSandbox(SandboxPolicy(deterministic_seed=42))
        candidate = Candidate(b"print(random.random())")

        first = sandbox.run(candidate)
        second = sandbox.run(candidate)

        self.assertEqual(first.outcome, SandboxOutcome.PASS)
        self.assertEqual(first.stdout, second.stdout)

    def test_policy_rejects_unsupported_escape_flags(self):
        with self.assertRaisesRegex(ValueError, "network"):
            SandboxPolicy(allow_network=True)
        with self.assertRaisesRegex(ValueError, "process"):
            SandboxPolicy(allow_process_spawn=True)
        with self.assertRaisesRegex(ValueError, "filesystem"):
            SandboxPolicy(allow_filesystem=True)

    def test_rejects_non_utf8_and_oversized_source(self):
        sandbox = PythonCandidateSandbox(SandboxPolicy(max_source_bytes=8))

        non_utf8 = sandbox.run(Candidate(b"\xff"))
        oversized = sandbox.run(Candidate(b"print(12345)"))

        self.assertEqual(non_utf8.outcome, SandboxOutcome.POLICY_REJECTED)
        self.assertEqual(oversized.outcome, SandboxOutcome.POLICY_REJECTED)


if __name__ == "__main__":
    unittest.main()
