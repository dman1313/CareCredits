import io
import logging
import unittest
from observe import failure_line, job_line, request_line, setup


class ObserveTests(unittest.TestCase):
    def setUp(self):
        setup()
        self.buffer = io.StringIO()
        self.handler = logging.StreamHandler(self.buffer)
        log = logging.getLogger('carecredits')
        log.addHandler(self.handler)
        self.addCleanup(log.removeHandler, self.handler)

    def test_request_and_job_lines_omit_secrets(self):
        request_line('abc123', 'GET', '/api/v1/trainings', 200, 12)
        job_line('job-1', 'partial', 2, 3, {'tavily_credits': 1, 'model_tokens': 30}, 1)
        failure_line('abc123', 429, 'Tavily rate or credit limit reached. Try again later.')
        text = self.buffer.getvalue()
        self.assertIn('request id=abc123', text)
        self.assertIn('job id=job-1 status=partial candidates=2 sources=3 tavily_credits=1 model_tokens=30', text)
        self.assertIn('failure id=abc123 status=429', text)
        self.assertNotIn('sk-', text)
        self.assertNotIn('Bearer', text)
        self.assertNotIn('TAVILY_API_KEY', text)
