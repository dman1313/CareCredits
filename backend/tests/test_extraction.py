import os
import unittest
from unittest.mock import patch
import httpx
from scraper.extraction import extract_training, ExtractionError
from scraper.worker import run_job


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'MODEL_ID':'test/open-weight-model','MODEL_API_KEY':'test-secret','MODEL_WEIGHTS_URL':'https://example.org/weights','MODEL_LICENSE_URL':'https://example.org/license','MODEL_OPEN_WEIGHT_CONFIRMED':'true','MODEL_BASE_URL':'https://example.org/v1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.text='Primary care seminar. Provider: Medical School. Online for Malaysian doctors.'
        self.row={'title':'Primary care seminar','provider':'Medical School','mode':'online','country':'MY','evidence':{k:self.text for k in ['title','provider','mode','country']}}
        self.source={'url':'https://example.org/event','raw_content':self.text}

    def client(self,row,status=200):
        import json
        def handler(request):
            self.assertEqual(str(request.url),'https://example.org/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer test-secret')
            body=json.loads(request.content)
            self.assertEqual(body['model'],'test/open-weight-model')
            self.assertIn('untrusted',body['messages'][0]['content'])
            return httpx.Response(status,json={'choices':[{'message':{'content':json.dumps({'trainings':[row]})}}]})
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_source_backed_output_and_unknowns(self):
        with self.client(self.row) as client:
            result=extract_training(self.source,client)
        self.assertEqual(result[0]['source_url'],self.source['url'])
        self.assertIsNone(result[0]['points'])
        self.assertIsNone(result[0]['fee'])
        self.assertEqual(result[0]['model_id'],'test/open-weight-model')

    def test_unsupported_facts_are_rejected(self):
        row={**self.row,'points':10,'credit_label':'CPD'}
        with self.client(row) as client:
            with self.assertRaises(ExtractionError):extract_training(self.source,client)

    def test_non_malaysian_and_unsafe_urls_rejected(self):
        for row in [{**self.row,'country':'SG'},{**self.row,'registration_url':'javascript:alert(1)'}]:
            with self.client(row) as client:
                with self.assertRaises(ExtractionError):extract_training(self.source,client)

    def test_model_error_sanitized(self):
        with self.client(self.row,401) as client:
            with self.assertRaises(ExtractionError) as error:extract_training(self.source,client)
            self.assertNotIn('test-secret',str(error.exception))

    def test_missing_model_prevents_paid_tavily_call(self):
        with patch.dict(os.environ,{'MODEL_API_KEY':''}),patch('scraper.worker.discover') as search:
            result=run_job({'query':'GP','lease_token':'test'},lambda:None)
            self.assertEqual(result['status'],'failed')
            search.assert_not_called()

    def test_empty_search_has_no_model_call(self):
        with patch('scraper.worker.discover',return_value={'sources':[],'warnings':[]}),patch('scraper.worker.extract_training') as model:
            result=run_job({'query':'GP','lease_token':'test'},lambda:None)
            self.assertEqual(result['status'],'succeeded')
            self.assertEqual(result['candidates'],[])
            model.assert_not_called()
