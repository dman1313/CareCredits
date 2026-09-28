import os
import unittest
from unittest.mock import patch
import httpx
from scraper.extraction import extract_training, ExtractionError
from scraper.worker import run_job


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'MODEL_ID':'test/open-weight-model','MODEL_API_KEY':'test-secret','MODEL_WEIGHTS_URL':'https://example.org/weights','MODEL_LICENSE_URL':'https://example.org/license','MODEL_OPEN_WEIGHT_CONFIRMED':'true','MODEL_BASE_URL':'https://example.org/v1','MODEL_MAX_INPUT_CHARS':'12000','MODEL_MAX_OUTPUT_TOKENS':'4000'})
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
            return httpx.Response(status,json={'choices':[{'message':{'content':json.dumps({'trainings':[row]})}}],'usage':{'prompt_tokens':11,'completion_tokens':19,'total_tokens':30}})
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_source_backed_output_and_unknowns(self):
        usage = {}
        with self.client(self.row) as client:
            result=extract_training(self.source,client,usage=usage)
        self.assertEqual(result[0]['source_url'],self.source['url'])
        self.assertIsNone(result[0]['points'])
        self.assertIsNone(result[0]['fee'])
        self.assertEqual(result[0]['model_id'],'test/open-weight-model')
        self.assertEqual(usage['model_tokens'], 30)

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

    def test_missing_model_still_runs_tavily(self):
        sources=[{
            'url':'https://example.org/event','title':'GP course','snippet':'Snippet',
            'raw_content':'Page text','extraction_status':'success','verification_status':'unverified',
        }]
        with patch.dict(os.environ,{'MODEL_API_KEY':''}),patch('scraper.worker.discover',return_value={'sources':sources,'warnings':[]}) as search:
            result=run_job({'query':'GP','lease_token':'test'},lambda:None)
        search.assert_called_once()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['candidates'],[])
        self.assertEqual(result['sources'][0]['url'],'https://example.org/event')
        self.assertNotIn('raw_content',result['sources'][0])
        self.assertTrue(any('model' in warning.lower() or 'heuristic' in warning.lower() for warning in result['warnings']))

    def test_snippet_only_sources_are_held_not_auto_saved(self):
        from types import SimpleNamespace
        snippet = (
            'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
            'Conference 2026-06-12. In-person primary care conference.'
        )
        sources = [{
            'url': 'https://example.org/primary-care',
            'title': 'Primary Care Update',
            'snippet': snippet,
            'raw_content': None,
            'extraction_status': 'failed',
            'verification_status': 'unverified',
        }]
        called = []

        class FakeClient:
            def get(self, path):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {})

            def post(self, path, json=None):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {'decision': 'new'})

        with patch('scraper.worker.discover', return_value={'sources': sources, 'warnings': []}):
            result = run_job({'query': 'GP', 'lease_token': 'test', 'id': 'job-1'}, lambda: None, FakeClient())
        self.assertTrue(result['candidates'], result)
        self.assertTrue(any('snippet-only' in warning.lower() for warning in result['warnings']))
        self.assertFalse(any('catalogue/save' in path or 'catalogue/connect' in path for path in called))

    def test_missing_model_holds_heuristic_extracts(self):
        from types import SimpleNamespace
        text = (
            'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
            'Conference 2026-06-12. In-person primary care conference.'
        )
        sources = [{
            'url': 'https://example.org/primary-care',
            'title': 'Primary Care Update',
            'snippet': text,
            'raw_content': text,
            'extraction_status': 'success',
            'verification_status': 'unverified',
        }]
        called = []

        class FakeClient:
            def get(self, path):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {})

            def post(self, path, json=None):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {'decision': 'new'})

        with patch.dict(os.environ, {'MODEL_API_KEY': ''}), patch(
            'scraper.worker.discover', return_value={'sources': sources, 'warnings': []}
        ):
            result = run_job({'query': 'GP', 'lease_token': 'test', 'id': 'job-1'}, lambda: None, FakeClient())
        self.assertTrue(result['candidates'], result)
        self.assertEqual(result['candidates'][0]['model_id'], 'heuristic-v1')
        self.assertTrue(any('open-weight model is not configured' in warning.lower() for warning in result['warnings']))
        self.assertFalse(any('catalogue/save' in path or 'catalogue/connect' in path for path in called))

    def test_heuristic_extracts_malaysia_event_without_model(self):
        from scraper.extraction import heuristic_extract
        text = (
            'DD CON 2026 Conference\n'
            'Organised by Disruptive Doctors in Kuala Lumpur, Malaysia.\n'
            'Conference dates 2026-09-04. In-person primary care conference.'
        )
        rows = heuristic_extract({
            'url': 'https://disruptive-doctors.com/dd-con-2026',
            'title': 'DD CON 2026 Conference',
            'raw_content': text,
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'DD CON 2026 Conference')
        self.assertEqual(rows[0]['city'], 'Kuala Lumpur')
        self.assertEqual(rows[0]['start_date'], '2026-09-04')
        self.assertEqual(rows[0]['model_id'], 'heuristic-v1')
        self.assertIsNone(rows[0]['points'])

    def test_heuristic_extracts_malay_kursus(self):
        from scraper.extraction import heuristic_extract
        text = (
            'Kursus Klinikal Johor anjuran Kementerian Kesihatan Malaysia di Johor Bahru, Malaysia. '
            'Tarikh 2026-07-03. Mata CPD 4. Beginner.'
        )
        rows = heuristic_extract({
            'url': 'https://moh.gov.my/kursus-klinik',
            'title': 'Kursus Klinikal Johor',
            'raw_content': text,
        })
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]['title'], 'Kursus Klinikal Johor')
        self.assertEqual(rows[0]['provider'], 'Kementerian Kesihatan Malaysia')
        self.assertEqual(rows[0]['city'], 'Johor Bahru')
        self.assertEqual(rows[0]['start_date'], '2026-07-03')
        self.assertIsNone(rows[0]['points'])
        self.assertIsNone(rows[0]['difficulty'])
        self.assertIsNone(rows[0]['fee'])

    def test_heuristic_reads_hybrid_mode_and_stated_prerequisites(self):
        from scraper.extraction import heuristic_extract
        hybrid = heuristic_extract({
            'url': 'https://penangmed.org/hybrid-cme',
            'title': 'Hybrid CME day',
            'raw_content': (
                'Hybrid CME day organised by Penang Medical Society in George Town, Malaysia. '
                'Hybrid 2026-09-01. Prerequisites: valid APC.'
            ),
        })
        self.assertEqual(len(hybrid), 1, hybrid)
        self.assertEqual(hybrid[0]['mode'], 'hybrid')
        self.assertEqual(hybrid[0]['city'], 'George Town')
        self.assertEqual(hybrid[0]['prerequisites'], 'valid APC')
        none = heuristic_extract({
            'url': 'https://sarawakmed.my/seminar',
            'title': 'Family medicine seminar',
            'raw_content': (
                'Family medicine seminar hosted by Sarawak Medical Association in Kuching, Malaysia. '
                '2026-12-02. Prerequisites none stated by provider.'
            ),
        })
        self.assertEqual(len(none), 1, none)
        self.assertEqual(none[0]['prerequisites'], 'none stated by provider')
        self.assertIsNone(heuristic_extract({
            'url': 'https://example.org/silent-prereq',
            'title': 'Primary Care Update',
            'raw_content': (
                'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
                'Conference 2026-06-12. In-person primary care conference.'
            ),
        })[0]['prerequisites'])

    def test_heuristic_reads_explicit_end_date_venue_and_timezone(self):
        from scraper.extraction import heuristic_extract
        rows = heuristic_extract({
            'url': 'https://example.org/weekend',
            'title': 'Primary Care Update',
            'raw_content': (
                'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
                'Conference 2026-01-01. Ends 2026-01-02 at Menara. Asia/Kuala_Lumpur.'
            ),
        })
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]['start_date'], '2026-01-01')
        self.assertEqual(rows[0]['end_date'], '2026-01-02')
        self.assertEqual(rows[0]['venue'], 'Menara')
        self.assertEqual(rows[0]['timezone'], 'Asia/Kuala_Lumpur')
        two = heuristic_extract({
            'url': 'https://example.org/two-dates',
            'title': 'Primary Care Update',
            'raw_content': (
                'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
                'Conference 2026-05-16 and 2026-05-17.'
            ),
        })
        self.assertEqual(len(two), 1, two)
        self.assertEqual(two[0]['start_date'], '2026-05-16')
        self.assertIsNone(two[0]['end_date'])
        self.assertIsNone(two[0]['timezone'])
        self.assertIsNone(two[0]['venue'])

    def test_heuristic_keeps_two_titled_sessions_distinct(self):
        from scraper.extraction import heuristic_extract
        rows = heuristic_extract({
            'url': 'https://melakacme.my/weekend',
            'title': 'Weekend clinic skills',
            'raw_content': (
                'Saturday clinic skills and Sunday clinic skills by Melaka CME Group in Malacca, Malaysia. '
                '2026-05-16 and 2026-05-17.'
            ),
        })
        self.assertEqual({(row['title'], row['start_date']) for row in rows}, {
            ('Saturday clinic skills', '2026-05-16'),
            ('Sunday clinic skills', '2026-05-17'),
        })
        self.assertTrue(all(row['provider'] == 'Melaka CME Group' for row in rows))
        self.assertTrue(all(row['end_date'] is None for row in rows))
        same_title = heuristic_extract({
            'url': 'https://example.org/weekend-workshop',
            'title': 'Weekend workshop',
            'raw_content': (
                'Saturday and Sunday workshop organised by Medical School in Kuala Lumpur, Malaysia. '
                '2026-05-16 and 2026-05-17.'
            ),
        })
        self.assertEqual(len(same_title), 1, same_title)
        self.assertEqual(same_title[0]['start_date'], '2026-05-16')
        self.assertIsNone(same_title[0]['end_date'])

    def test_heuristic_does_not_infer_difficulty_points_or_fee(self):
        from scraper.extraction import heuristic_extract
        text = (
            'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
            'Conference 2026-06-12. 8 CPD points. Fee MYR 350. Sounds advanced and expensive.'
        )
        rows = heuristic_extract({
            'url': 'https://example.org/primary-care-update',
            'title': 'Primary Care Update',
            'raw_content': text,
        })
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['difficulty'])
        self.assertIsNone(rows[0]['points'])
        self.assertIsNone(rows[0]['fee'])
        self.assertIsNone(rows[0]['currency'])
        self.assertEqual(heuristic_extract({
            'url': 'https://www.instagram.com/reel/abc',
            'title': 'Instagram',
            'raw_content': 'Malaysia CME event in Kuala Lumpur conference',
        }), [])
        self.assertEqual(heuristic_extract({
            'url': 'https://www.eventbrite.com/d/malaysia/medical-conferences',
            'title': 'Medical conferences Events and Things to do in Malaysia',
            'raw_content': 'Medical conferences Events and Things to do in Malaysia. CPD courses in Kuala Lumpur.',
        }), [])
        self.assertEqual(heuristic_extract({
            'url': 'https://example.org/listing',
            'title': 'Upcoming Medical Conferences in Malaysia 2026',
            'raw_content': 'Upcoming Medical Conferences in Malaysia 2026. Browse CPD courses in Kuala Lumpur.',
        }), [])

    def test_empty_search_has_no_model_call(self):
        with patch('scraper.worker.discover',return_value={'sources':[],'warnings':[]}),patch('scraper.worker.extract_training') as model:
            result=run_job({'query':'GP','lease_token':'test'},lambda:None)
            self.assertEqual(result['status'],'succeeded')
            self.assertEqual(result['candidates'],[])
            model.assert_not_called()

    def test_missing_model_key_or_confirmation_blocks_configuration(self):
        from scraper.extraction import configuration
        with patch.dict(os.environ, {'MODEL_API_KEY': ''}, clear=False):
            with self.assertRaises(ExtractionError):
                configuration()
        with patch.dict(os.environ, {'MODEL_OPEN_WEIGHT_CONFIRMED': 'false'}, clear=False):
            with self.assertRaises(ExtractionError):
                configuration()

    def test_open03_defaults_fill_blank_identity_and_caps(self):
        from scraper.extraction import configuration, model_caps
        blank = {
            'MODEL_ID': '',
            'MODEL_WEIGHTS_URL': '',
            'MODEL_LICENSE_URL': '',
            'MODEL_BASE_URL': '',
            'MODEL_MAX_INPUT_CHARS': '',
            'MODEL_MAX_OUTPUT_TOKENS': '',
        }
        with patch.dict(os.environ, blank, clear=False):
            self.assertEqual(configuration(), 'https://api.tokenfactory.nebius.com/v1')
            self.assertEqual(model_caps(), (12000, 4000))

    def test_run_job_tavily_timeout_is_failed(self):
        from scraper.tavily import ProviderError
        with patch('scraper.worker.discover', side_effect=ProviderError(504, 'Tavily is unavailable or timed out.')):
            result = run_job({'id': 'j', 'query': 'GP', 'lease_token': 'test', 'max_results': 1}, lambda: None)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['candidates'], [])
        self.assertTrue(result['warnings'])
        self.assertIsNone(result['usage']['tavily_credits'])
        self.assertEqual(result['usage']['catalogue_saved'], 0)

    def test_model_extract_failure_holds_heuristic(self):
        from types import SimpleNamespace
        text = (
            'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
            'Conference 2026-06-12. In-person primary care conference.'
        )
        sources = [{
            'url': 'https://example.org/primary-care',
            'title': 'Primary Care Update',
            'snippet': text,
            'raw_content': text,
            'extraction_status': 'success',
            'verification_status': 'unverified',
        }]
        called = []

        class FakeClient:
            def get(self, path):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {})

            def post(self, path, json=None):
                called.append(path)
                return SimpleNamespace(status_code=200, json=lambda: {'decision': 'new'})

        with patch('scraper.worker.discover', return_value={'sources': sources, 'warnings': [], 'usage': {'tavily_credits': 2}}), patch(
            'scraper.worker.extract_training', side_effect=ExtractionError('Model request failed.')
        ):
            result = run_job({'query': 'GP', 'lease_token': 'test', 'id': 'job-1'}, lambda: None, FakeClient())
        self.assertTrue(result['candidates'], result)
        self.assertEqual(result['candidates'][0]['model_id'], 'heuristic-v1')
        self.assertEqual(result['usage']['tavily_credits'], 2)
        self.assertTrue(any('held for review' in warning.lower() for warning in result['warnings']))
        self.assertFalse(any('catalogue/save' in path or 'catalogue/connect' in path for path in called))

    def test_run_job_tavily_credit_limit_is_failed(self):
        from scraper.tavily import ProviderError
        with patch('scraper.worker.discover', side_effect=ProviderError(429, 'Tavily rate or credit limit reached. Try again later.')):
            result = run_job({'id': 'j', 'query': 'GP', 'lease_token': 'test', 'max_results': 1}, lambda: None)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('credit', result['warnings'][0].lower())

    def test_job_deadline_keeps_extracted_candidates_and_usage(self):
        text = (
            'Primary Care Update organised by Medical School in Kuala Lumpur, Malaysia. '
            'Conference 2026-06-12. In-person primary care conference.'
        )
        sources = [
            {
                'url': 'https://example.org/primary-care',
                'title': 'Primary Care Update',
                'snippet': text,
                'raw_content': text,
                'extraction_status': 'success',
                'verification_status': 'unverified',
            },
            {
                'url': 'https://example.org/second',
                'title': 'Second course',
                'snippet': text,
                'raw_content': text,
                'extraction_status': 'success',
                'verification_status': 'unverified',
            },
        ]
        beats = {'n': 0}

        def heartbeat():
            beats['n'] += 1
            if beats['n'] > 1:
                raise ExtractionError('Job deadline reached; retry explicitly if needed.')

        with patch.dict(os.environ, {'MODEL_API_KEY': ''}), patch(
            'scraper.worker.discover',
            return_value={'sources': sources, 'warnings': [], 'usage': {'tavily_credits': 2}},
        ):
            result = run_job({'query': 'GP', 'lease_token': 'test', 'id': 'job-1'}, heartbeat)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(result['candidates'][0]['source_url'], 'https://example.org/primary-care')
        self.assertEqual(result['usage']['tavily_credits'], 2)
        self.assertTrue(any('deadline' in warning.lower() for warning in result['warnings']))
