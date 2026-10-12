import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('capture', Path(__file__).resolve().parents[2] / 'tools/research/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

class CaptureTests(unittest.TestCase):
    def test_nested_secrets(self):
        self.assertEqual(capture.sanitize({'items': [{'session_id': 'secret', 'hp': 1}]}),
                         {'items': [{'session_id': '[REDACTED]', 'hp': 1}]})

    def test_token_not_in_url(self):
        self.assertNotIn('sensitive', capture.safe_url('http://localhost/sse?token=sensitive&since=7'))
        self.assertIn('since=7', capture.safe_url('http://localhost/sse?token=sensitive&since=7'))
