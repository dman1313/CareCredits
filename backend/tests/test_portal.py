import os
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from main import app, today, migrate_schema
from database import Base, get_db
from portal_models import Account, Audit, Course, Record, Job, Candidate, FieldEvidence, SchemaVersion, SourceDocument, fill_course, purge_expired_source_text
from security import password_hash

PASSWORD = 'Testing-strong-password'
HASH = password_hash(PASSWORD)


def sample(title='GP training'):
    quote='GP training by Learning Institute in Malaysia Kuala Lumpur online. 2026-01-01. CPD points 2.'
    return {'title':title, 'provider':'Learning Institute', 'mode':'online', 'country':'MY', 'start_date':'2026-01-01', 'city':None, 'source_url':'https://example.org/course', 'source_text':quote, 'points':2, 'credit_label':'CPD', 'evidence':{key:quote for key in ['title','provider','mode','country','start_date','points','credit_label']}}


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+self.folder.name+'/test.db',connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine)
        def dependency():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db]=dependency
        self.env=patch.dict(os.environ,{'APP_ENV':'test','DEMO_MODE':'false','SCRAPER_SERVICE_TOKEN':'test-service-token','ALLOW_SIGNUP':'true','DAILY_SCRAPE_ENABLED':'false','DIGEST_ENABLED':'false'})
        self.env.start()
        self.client=TestClient(app,headers={'X-Care-Client':'1','Origin':'http://127.0.0.1:3000'})
        with self.Session() as db:
            a=Account(email='a@example.com',name='Doctor A',password_hash=HASH,role='operator')
            b=Account(email='b@example.com',name='Doctor B',password_hash=HASH)
            data=sample()
            course=fill_course(Course(source_key='sample'), data)
            db.add_all([a,b,course]);db.commit()
            self.a,self.b,self.course=a.id,b.id,course.id
            self.slug=a.public_slug
        self.login()

    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.env.stop();self.engine.dispose();self.folder.cleanup()

    def login(self,email='a@example.com'):
        result=self.client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD})
        self.assertEqual(result.status_code,200,result.text)
        return result

    def save(self,**updates):
        body={'signed_up':True,'attended':True,'attended_on':today().isoformat(),'points':3,'credit_label':'CPD','notes':'PRIVATE NOTE','public':True,'version':0,**updates}
        return self.client.put('/api/v1/me/trainings/'+self.course,json=body)

    def test_authentication_csrf_and_logout(self):
        self.assertIn('HttpOnly',self.login().headers['set-cookie'])
        self.assertEqual(self.client.post('/api/v1/auth/logout',headers={'Origin':'https://evil.example'}).status_code,403)
        bare=TestClient(app,headers={'X-Care-Client':'1'})
        bare.cookies.update(self.client.cookies)
        self.assertEqual(bare.post('/api/v1/auth/logout').status_code,403)
        no_client=TestClient(app,headers={'Origin':'http://127.0.0.1:3000'})
        no_client.cookies.update(self.client.cookies)
        self.assertEqual(no_client.post('/api/v1/auth/logout').status_code,403)
        self.assertEqual(self.client.post('/api/v1/auth/logout').status_code,200)
        self.assertEqual(self.client.get('/api/v1/me').status_code,401)
        self.assertEqual(self.client.get('/users/').status_code,404)
        self.assertEqual(self.client.get('/internal/v1/catalogue/connect').status_code,403)

    def test_login_without_peer_address_still_authenticates(self):
        from starlette.requests import Request
        from main import client_host

        scope = {
            'type': 'http',
            'asgi': {'spec_version': '2.3', 'version': '3.0'},
            'http_version': '1.1',
            'method': 'POST',
            'scheme': 'http',
            'path': '/api/v1/auth/login',
            'raw_path': b'/api/v1/auth/login',
            'query_string': b'',
            'headers': [],
            'client': None,
            'server': ('127.0.0.1', 8000),
        }
        self.assertEqual(client_host(Request(scope)), 'unknown')
        with patch('main.client_host', return_value='unknown'):
            result = self.client.post('/api/v1/auth/login', json={'email': 'a@example.com', 'password': PASSWORD})
        self.assertEqual(result.status_code, 200, result.text)

    def test_two_user_isolation_and_roles(self):
        self.assertEqual(self.save().status_code,200)
        self.login('b@example.com')
        self.assertEqual(self.client.get('/api/v1/me/trainings').json()['items'],[])
        self.assertIsNone(self.client.get('/api/v1/trainings/'+self.course).json()['record'])
        self.assertEqual(self.client.get('/api/v1/admin/candidates').status_code,403)
        self.assertEqual(self.client.post('/internal/v1/jobs/claim').status_code,403)
        self.assertNotIn('PRIVATE NOTE', self.client.get('/api/v1/me/export/csv').text)
        self.assertEqual(self.client.get('/api/v1/me/progress').json()['attended'], 0)
        self.assertEqual(self.client.get('/api/v1/me/trainings/' + self.course + '/history').json()['items'], [])
        self.assertEqual(self.client.get('/api/v1/admin/audit').status_code, 403)
        own = self.client.get('/api/v1/me/audit').json()
        self.assertEqual(own['items'], [])
        self.assertEqual(self.client.get('/api/v1/me/digest').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me/suggestions').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/me/certificates', json={'year': 2026}).status_code, 201)
        self.assertNotIn('PRIVATE NOTE', self.client.get('/api/v1/me/progress').text)

    def test_personal_notes_stay_out_of_logs_and_audit(self):
        import io
        import logging

        from observe import setup

        setup()
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        log = logging.getLogger('carecredits')
        log.addHandler(handler)
        try:
            self.assertEqual(self.save().status_code, 200)
            self.assertNotIn('PRIVATE NOTE', buffer.getvalue())
        finally:
            log.removeHandler(handler)
        with self.Session() as db:
            dumped = ' '.join(str(row.changed) for row in db.query(Audit).all())
            self.assertNotIn('PRIVATE NOTE', dumped)
        mine = self.client.get('/api/v1/me/audit').json()
        self.assertGreaterEqual(mine['total'], 1)
        self.assertNotIn('PRIVATE NOTE', str(mine))
        admin = self.client.get('/api/v1/admin/audit').json()
        self.assertGreaterEqual(admin['total'], 1)
        self.assertTrue(all('notes' not in (item.get('changed') or {}) for item in admin['items']))
        self.assertEqual(self.client.get('/api/v1/me/audit?page=0').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/me/audit?page_size=51').status_code, 422)
        paged = self.client.get('/api/v1/admin/audit?page=1&page_size=1').json()
        self.assertEqual(paged['page'], 1)
        self.assertEqual(paged['page_size'], 1)
        self.assertEqual(len(paged['items']), 1)

    def test_record_idempotency_and_points_corrections(self):
        first=self.save();self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.save().json()['version'],1)
        progress=self.client.get('/api/v1/me/progress').json()
        self.assertEqual((progress['points'],progress['attended']),(3,1))
        self.assertEqual(self.save(points=4,version=0).status_code,409)
        self.assertEqual(self.save(points=4,version=1).status_code,200)
        self.assertEqual(self.client.get('/api/v1/me/progress').json()['points'],4)
        self.assertEqual(self.save(attended=False,version=2).status_code,200)
        self.assertEqual(self.client.get('/api/v1/me/progress').json()['points'],0)

    def test_future_and_unknown_credits(self):
        self.assertEqual(self.save(attended_on=(today()+timedelta(days=1)).isoformat()).status_code,422)
        self.assertEqual(self.save(points=None,credit_label='CME').status_code,200)
        p=self.client.get('/api/v1/me/progress').json();self.assertEqual((p['points'],p['excluded']),(0,1))
        self.assertEqual(p['excluded_reasons'][0]['reason'],'unknown_points')
        self.assertEqual(self.save(points=2,credit_label='CME',version=1).status_code,200)
        p=self.client.get('/api/v1/me/progress').json()
        self.assertEqual((p['points'],p['excluded']),(0,1))
        self.assertEqual(p['excluded_reasons'][0]['reason'],'unmapped_credit_label')

    def test_public_opt_in_and_revocation(self):
        self.save()
        url='/api/v1/public/'+self.slug
        self.assertEqual(self.client.get(url).status_code,404)
        body={'name':'Doctor A','city':'KL','bio':'Learning','public_enabled':True}
        self.assertEqual(self.client.patch('/api/v1/me',json=body).status_code,200)
        public=self.client.get(url)
        self.assertEqual(len(public.json()['items']),1)
        for private in ['PRIVATE NOTE','a@example.com','password_hash','signed_up','points']:
            self.assertNotIn(private,public.text)
        self.assertEqual(public.headers['cache-control'],'no-store')
        self.client.patch('/api/v1/me',json={**body,'public_enabled':False})
        self.assertEqual(self.client.get(url).status_code,404)

    def test_export_is_download_only_and_neutralizes_formulas(self):
        with self.Session() as db:
            c=db.get(Course,self.course);fill_course(c,{**c.data,'title':'=HYPERLINK("evil")'});db.commit()
        self.save()
        csv=self.client.get('/api/v1/me/export/csv')
        self.assertIn("'=HYPERLINK",csv.text)
        eml=self.client.get('/api/v1/me/export/eml')
        self.assertIn('X-Unsent: 1',eml.text)
        self.assertNotIn('\nTo:',eml.text)

    def test_job_idempotency_leases_and_completion(self):
        header={'Idempotency-Key':'test-unique-key'}
        first=self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP course'},headers=header)
        self.assertEqual(first.status_code,202,first.text)
        job=first.json()
        self.assertEqual(self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP course'},headers=header).json()['id'],job['id'])
        self.assertEqual(self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'different'},headers=header).status_code,409)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        self.assertEqual(self.client.post('/internal/v1/jobs/claim',headers=service).status_code,204)
        payload={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[sample()]}
        complete='/internal/v1/jobs/'+claim['id']+'/complete'
        self.assertEqual(self.client.post(complete,json=payload,headers=service).status_code,200)
        self.assertEqual(self.client.post(complete,json=payload,headers=service).status_code,200)
        queue=self.client.get('/api/v1/admin/candidates').json()['items'];self.assertEqual(len(queue),1)
        review=self.client.post('/api/v1/admin/candidates/'+queue[0]['id']+'/review',json={'action':'publish'})
        self.assertEqual(review.status_code,200,review.text)
        self.assertEqual(self.client.get('/api/v1/admin/candidates').json()['items'],[])

    def test_concurrent_complete_does_not_duplicate_candidates(self):
        from concurrent.futures import ThreadPoolExecutor
        header={'Idempotency-Key':'concurrent-complete-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP concurrent complete'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        payload={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[sample('Concurrent GP')]}
        url='/internal/v1/jobs/'+claim['id']+'/complete'
        with ThreadPoolExecutor(2) as pool:
            first, second = pool.submit(self.client.post, url, json=payload, headers=service), pool.submit(self.client.post, url, json=payload, headers=service)
            codes=sorted([first.result().status_code, second.result().status_code])
        self.assertTrue(all(code in (200, 409) for code in codes))
        self.assertEqual(len(self.client.get('/api/v1/admin/candidates').json()['items']),1)

    def test_job_completion_keeps_tavily_sources(self):
        header={'Idempotency-Key':'tavily-sources-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP Tavily sources'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        payload={
            'lease_token':claim['lease_token'],'status':'partial','candidates':[],
            'warnings':['Configure an open-weight model. Tavily sources were saved for review.'],
            'sources':[{'url':'https://example.org/afpm','title':'Primary Care Update','snippet':'CPD workshop in Kuala Lumpur','extraction_status':'success','verification_status':'unverified'}],
        }
        self.assertEqual(self.client.post('/internal/v1/jobs/'+claim['id']+'/complete',json=payload,headers=service).status_code,200)
        stored=self.client.get('/api/v1/admin/ingestion-jobs').json()['items'][0]
        self.assertEqual(stored['status'],'partial')
        self.assertEqual(stored['result']['sources'][0]['title'],'Primary Care Update')
        self.assertEqual(stored['result']['candidate_count'],0)
        detail=self.client.get('/api/v1/admin/ingestion-jobs/'+claim['id'])
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['id'],claim['id'])
        self.assertEqual(detail.json()['result']['sources'][0]['url'],'https://example.org/afpm')
        self.assertEqual(self.client.get('/api/v1/admin/ingestion-jobs/missing-job').status_code,404)
        self.login('b@example.com')
        self.assertEqual(self.client.get('/api/v1/admin/ingestion-jobs/'+claim['id']).status_code,403)

    def test_expired_lease_complete_does_not_publish(self):
        header={'Idempotency-Key':'expired-lease-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP lease timeout'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        with self.Session() as db:
            job=db.get(Job, claim['id'])
            job.lease_until=1
            db.commit()
        complete=self.client.post(
            '/internal/v1/jobs/'+claim['id']+'/complete',
            json={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[sample('Late crash')]},
            headers=service,
        )
        self.assertEqual(complete.status_code,409)
        listed=self.client.get('/api/v1/trainings?period=all&q=Late%20crash').json()
        self.assertEqual(listed['total'],0)
        stored=self.client.get('/api/v1/admin/ingestion-jobs/'+claim['id']).json()
        self.assertEqual(stored['status'],'interrupted')

    def test_heartbeat_extends_lease(self):
        header={'Idempotency-Key':'heartbeat-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP heartbeat'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        beat=self.client.post('/internal/v1/jobs/'+claim['id']+'/heartbeat',json={'lease_token':claim['lease_token']},headers=service)
        self.assertEqual(beat.status_code,200,beat.text)
        stale=self.client.post('/internal/v1/jobs/'+claim['id']+'/heartbeat',json={'lease_token':'wrong'},headers=service)
        self.assertEqual(stale.status_code,409)

    def test_invalid_evidence_cannot_publish(self):
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='j',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='fake',data={**sample(),'evidence':{'title':'invented'}});db.add(c);db.commit();cid=c.id
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish'}).status_code,422)

    def test_review_corrections_require_source_excerpts(self):
        quote='Corrected GP Day by Learning Institute in Malaysia Kuala Lumpur online. 2026-01-01. CPD points 2.'
        payload={**sample('Wrong title'),'source_text':quote,'evidence':{key:quote for key in ['title','provider','mode','country','start_date','points','credit_label']}}
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='corr',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='corr-source',data=payload);db.add(c);db.commit();cid=c.id
        missing=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish','corrections':{'title':'Corrected GP Day'}})
        self.assertEqual(missing.status_code,422)
        published=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish','corrections':{'title':'Corrected GP Day'},'evidence':{'title':quote}})
        self.assertEqual(published.status_code,200,published.text)
        found=self.client.get('/api/v1/trainings?period=all&q=Corrected').json()['items']
        self.assertEqual(found[0]['title'],'Corrected GP Day')

    def test_review_cannot_publish_unsafe_registration_url(self):
        quote='Clinic day javascript:alert(1) by Learning Institute in Malaysia Kuala Lumpur online. 2026-01-01. CPD points 2.'
        payload={**sample('Unsafe link'),'source_text':quote,'evidence':{key:quote for key in ['title','provider','mode','country','start_date','points','credit_label']}}
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='unsafe-url',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='unsafe-source',data=payload);db.add(c);db.commit();cid=c.id
        result=self.client.post(
            '/api/v1/admin/candidates/'+cid+'/review',
            json={'action':'publish','corrections':{'registration_url':'javascript:alert(1)'},'evidence':{'registration_url':'javascript:alert(1)'}},
        )
        self.assertEqual(result.status_code,422)
        titles=[item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']]
        self.assertNotIn('Unsafe link', titles)

    def test_hold_requires_reason_and_stays_out_of_catalogue(self):
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='hold-job',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='hold-source',data=sample('Held GP session'));db.add(c);db.commit();cid=c.id
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'hold'}).status_code,422)
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'reject'}).status_code,422)
        held=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'hold','reason':'Need MMC confirmation'})
        self.assertEqual(held.status_code,200,held.text)
        self.assertEqual(held.json()['status'],'held')
        queue=self.client.get('/api/v1/admin/candidates').json()['items']
        self.assertEqual([(item['id'],item['status'],item['reason']) for item in queue],[(cid,'held','Need MMC confirmation')])
        titles=[item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']]
        self.assertNotIn('Held GP session',titles)
        published=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish','reason':'Source confirmed on the provider page'})
        self.assertEqual(published.status_code,200,published.text)
        self.assertEqual(self.client.get('/api/v1/admin/candidates').json()['items'],[])
        titles=[item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']]
        self.assertIn('Held GP session',titles)

    def test_reject_requires_reason_and_stays_out_of_catalogue(self):
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='reject-job',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='reject-source',data=sample('Rejected GP session'));db.add(c);db.commit();cid=c.id
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'reject'}).status_code,422)
        rejected=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'reject','reason':'Not a Malaysia CPD event'})
        self.assertEqual(rejected.status_code,200,rejected.text)
        self.assertEqual(rejected.json()['status'],'rejected')
        self.assertEqual(self.client.get('/api/v1/admin/candidates').json()['items'],[])
        titles=[item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']]
        self.assertNotIn('Rejected GP session',titles)

    def add_course(self, key, **fields):
        data={**sample(fields.pop('title', 'GP training')), **fields}
        with self.Session() as db:
            course=Course(source_key=key)
            fill_course(course, data)
            db.add(course)
            db.commit()
            return course.id

    def test_filter_semantics(self):
        with self.Session() as db:
            c=db.get(Course,self.course);fill_course(c,{**c.data,'fee':None,'currency':None,'mode':'in_person','city':'Kuala Lumpur','state':'Wilayah Persekutuan','latitude':3.139,'longitude':101.687});db.commit()
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&city=Kuala').json()['total'],1)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&max_fee=0').json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&max_fee_myr=0').json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&latitude=3.139&longitude=101.687&radius_km=25').json()['total'],1)
        self.assertEqual(self.client.get('/api/v1/trainings?latitude=3').status_code,422)
        self.assertEqual(self.client.get('/api/v1/trainings?latitude=3.139&longitude=101.687&radius_km=15').status_code,422)
        self.assertEqual(self.client.get('/api/v1/trainings?page=0').status_code,422)

    def test_catalogue_paginates_and_hides_non_malaysia_or_cancelled(self):
        extra=self.add_course('page-two', title='Second GP seminar', start_date='2026-02-01')
        foreign=self.add_course('sg-event', title='Singapore seminar', country='SG', start_date='2026-03-01')
        first=self.client.get('/api/v1/trainings?period=all&page=1&page_size=1').json()
        second=self.client.get('/api/v1/trainings?period=all&page=2&page_size=1').json()
        self.assertEqual(first['page_size'],1)
        self.assertGreaterEqual(first['total'],2)
        self.assertEqual(len(first['items']),1)
        self.assertEqual(len(second['items']),1)
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        titles={item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']}
        self.assertNotIn('Singapore seminar', titles)
        self.assertEqual(self.client.get('/api/v1/trainings/'+foreign).json()['country'],'SG')
        cancel=self.client.post('/api/v1/admin/trainings/'+extra+'/cancel')
        self.assertEqual(cancel.status_code,200,cancel.text)
        hidden={item['id'] for item in self.client.get('/api/v1/trainings?period=all').json()['items']}
        self.assertNotIn(extra, hidden)
        detail=self.client.get('/api/v1/trainings/'+extra)
        self.assertEqual(detail.status_code,200)
        self.assertEqual(detail.json()['publication_status'],'cancelled')
        self.login('b@example.com')
        self.assertEqual(self.client.post('/api/v1/admin/trainings/'+extra+'/cancel').status_code,403)

    def test_nearby_keeps_city_matches_without_coordinates(self):
        with self.Session() as db:
            c=db.get(Course,self.course)
            fill_course(c,{**c.data,'mode':'in_person','city':'Kuala Lumpur','state':'Wilayah Persekutuan','latitude':3.139,'longitude':101.687})
            db.commit()
        self.add_course('no-coords', title='Clinic workshop', mode='in_person', city='Kuala Lumpur', state='Wilayah Persekutuan', latitude=None, longitude=None, start_date='2026-01-01')
        nearby=self.client.get('/api/v1/trainings?period=all&city=Kuala&latitude=3.139&longitude=101.687&radius_km=25').json()
        self.assertEqual(nearby['total'], 2)
        untitled={item['title']: item['distance_km'] for item in nearby['items']}
        self.assertIsNotNone(untitled['GP training'])
        self.assertIsNone(untitled['Clinic workshop'])

    def test_nearby_includes_online_only_when_mode_allows_it(self):
        with self.Session() as db:
            c=db.get(Course,self.course)
            fill_course(c,{**c.data,'mode':'online','city':None,'latitude':None,'longitude':None})
            db.commit()
        in_person=self.client.get('/api/v1/trainings?period=all&mode=in_person&latitude=3.139&longitude=101.687&radius_km=25').json()
        any_mode=self.client.get('/api/v1/trainings?period=all&mode=online&latitude=3.139&longitude=101.687&radius_km=25').json()
        self.assertEqual(in_person['total'], 0)
        self.assertEqual(any_mode['total'], 1)
        self.assertIsNone(any_mode['items'][0]['distance_km'])

    def test_unknown_dates_and_fees_need_explicit_inclusion(self):
        with self.Session() as db:
            c=db.get(Course,self.course)
            fill_course(c,{**c.data,'start_date':None,'fee':None,'currency':None,'mode':'online'})
            db.commit()
        upcoming=self.client.get('/api/v1/trainings?period=upcoming').json()
        included=self.client.get('/api/v1/trainings?period=upcoming&include_unknown=true').json()
        fee_filter=self.client.get('/api/v1/trainings?period=all&max_fee_myr=100').json()
        fee_with_unknown=self.client.get('/api/v1/trainings?period=all&max_fee_myr=100&include_unknown=true').json()
        self.assertEqual(upcoming['total'], 0)
        self.assertEqual(included['total'], 1)
        self.assertEqual(fee_filter['total'], 0)
        self.assertEqual(fee_with_unknown['total'], 1)

    def test_myr_fee_filter_excludes_other_currencies(self):
        with self.Session() as db:
            c = db.get(Course, self.course)
            fill_course(c, {**c.data, 'fee': 80, 'currency': 'SGD', 'mode': 'online', 'start_date': '2026-01-01'})
            db.commit()
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&max_fee_myr=200').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&max_fee_myr=200&include_unknown=true').json()['total'], 0)
        with self.Session() as db:
            c = db.get(Course, self.course)
            fill_course(c, {**c.data, 'fee': 80, 'currency': 'MYR'})
            db.commit()
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&max_fee_myr=200').json()['total'], 1)

    def test_state_and_date_range_filters_and_applied_filters(self):
        with self.Session() as db:
            c=db.get(Course,self.course)
            fill_course(c,{**c.data,'city':'Petaling Jaya','state':'Selangor','start_date':'2026-03-15','mode':'in_person'})
            db.commit()
        missed=self.client.get('/api/v1/trainings?period=all&state=Penang').json()
        matched=self.client.get('/api/v1/trainings?period=all&state=Selangor&date_from=2026-03-01&date_to=2026-03-31').json()
        outside=self.client.get('/api/v1/trainings?period=all&date_from=2026-04-01&date_to=2026-04-30').json()
        self.assertEqual(missed['total'], 0)
        self.assertEqual(matched['total'], 1)
        self.assertEqual(outside['total'], 0)
        self.assertEqual(matched['applied_filters']['state'], 'Selangor')
        self.assertEqual(matched['applied_filters']['date_from'], '2026-03-01')

    def test_schema_upgrade_backfills_filter_columns(self):
        with self.Session() as db:
            db.add(SchemaVersion(version=1))
            course=db.get(Course,self.course)
            course.title=''
            course.city=None
            course.data={**course.data,'title':'Backfilled GP','city':'Johor Bahru'}
            db.commit()
        with self.Session() as db:
            migrate_schema(db)
            stored=db.get(Course,self.course)
            self.assertEqual((stored.title, stored.city), ('Backfilled GP','Johor Bahru'))
            self.assertEqual(max(v.version for v in db.query(SchemaVersion).all()), 17)
            self.assertIn('identity_issuer', {c['name'] for c in inspect(db.get_bind()).get_columns('accounts')})
            self.assertIn('verification_status', {c['name'] for c in inspect(db.get_bind()).get_columns('courses')})
            self.assertIn('publication_status', {c['name'] for c in inspect(db.get_bind()).get_columns('courses')})
            self.assertIn('end_date', {c['name'] for c in inspect(db.get_bind()).get_columns('courses')})
            self.assertIn('review_reason', {c['name'] for c in inspect(db.get_bind()).get_columns('course_candidates')})
            self.assertIn('signup_status', {c['name'] for c in inspect(db.get_bind()).get_columns('doctor_records')})
            self.assertIn('state', {c['name'] for c in inspect(db.get_bind()).get_columns('accounts')})
            self.assertIn('max_results', {c['name'] for c in inspect(db.get_bind()).get_columns('ingestion_jobs')})
            self.assertIn('attempt', {c['name'] for c in inspect(db.get_bind()).get_columns('ingestion_jobs')})
            self.assertIn('version', {c['name'] for c in inspect(db.get_bind()).get_columns('course_candidates')})
            self.assertIn('attendance_status', {c['name'] for c in inspect(db.get_bind()).get_columns('doctor_records')})
            self.assertIn('latitude', {c['name'] for c in inspect(db.get_bind()).get_columns('accounts')})
            self.assertIn('location_consent_at', {c['name'] for c in inspect(db.get_bind()).get_columns('accounts')})
            self.assertIn('created_at', {c['name'] for c in inspect(db.get_bind()).get_columns('accounts')})
            self.assertIn('event_count', {c['name'] for c in inspect(db.get_bind()).get_columns('digest_sends')})
            self.assertIn('resulting_course_id', {c['name'] for c in inspect(db.get_bind()).get_columns('course_candidates')})
            self.assertIn('schema_version', {c['name'] for c in inspect(db.get_bind()).get_columns('course_candidates')})
            self.assertIn('source_document_id', {c['name'] for c in inspect(db.get_bind()).get_columns('field_evidence')})
            tables = inspect(db.get_bind()).get_table_names()
            self.assertIn('fail_count', {c['name'] for c in inspect(db.get_bind()).get_columns('digest_preferences')})
            self.assertIn('digest_preferences', tables)
            self.assertIn('affiliation_certificates', tables)
            self.assertIn('record_history', tables)
            self.assertIn('field_evidence', tables)
            self.assertIn('source_documents', tables)

    def test_catalogue_filters_use_columns_not_json(self):
        with self.Session() as db:
            course=db.get(Course,self.course)
            course.data={**course.data,'city':'Penang','state':'Penang','mode':'in_person','start_date':'2026-01-01'}
            course.title='GP training'
            course.provider='Learning Institute'
            course.city='Ipoh'
            course.state='Perak'
            course.mode='in_person'
            course.start_date='2026-03-15'
            db.commit()
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&city=Ipoh').json()['total'],1)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&city=Penang').json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/trainings?period=all&state=Perak&date_from=2026-03-01&date_to=2026-03-31').json()['total'],1)

    def test_publish_stores_filter_columns(self):
        header={'Idempotency-Key':'publish-columns-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP course'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        quote='Ipoh clinic day by Learning Institute in Malaysia Ipoh Perak in person. 2026-06-01. CPD points 2.'
        payload=sample('Ipoh clinic day')
        payload.update(source_text=quote, mode='in_person', city='Ipoh', state='Perak', start_date='2026-06-01', evidence={key:quote for key in ['title','provider','mode','country','start_date','points','credit_label','city','state']})
        self.client.post('/internal/v1/jobs/'+claim['id']+'/complete',json={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[payload]},headers=service)
        cid=self.client.get('/api/v1/admin/candidates').json()['items'][0]['id']
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish'}).status_code,200)
        found=self.client.get('/api/v1/trainings?period=all&city=Ipoh').json()
        self.assertGreaterEqual(found['total'],1)
        self.assertTrue(any(item['title']=='Ipoh clinic day' and item['city']=='Ipoh' for item in found['items']))
        with self.Session() as db:
            stored=db.query(Course).filter(Course.title=='Ipoh clinic day').one()
            self.assertEqual((stored.city, stored.state, stored.mode), ('Ipoh','Perak','in_person'))

    def test_interrupted_job_requires_explicit_retry(self):

        header={'Idempotency-Key':'retry-job-key'}
        job=self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP course'},headers=header).json()
        with self.Session() as db:
            stored=db.get(Job, job['id'])
            stored.status='interrupted'
            stored.lease_token='stale'
            stored.lease_until=0
            db.commit()
        service={'Authorization':'Bearer test-service-token'}
        self.assertEqual(self.client.post('/internal/v1/jobs/claim',headers=service).status_code,204)
        retry=self.client.post('/api/v1/admin/ingestion-jobs/'+job['id']+'/retry')
        self.assertEqual(retry.status_code,202,retry.text)
        self.assertEqual(retry.json()['status'],'queued')
        self.assertEqual(retry.json()['attempt'],2)
        claim=self.client.post('/internal/v1/jobs/claim',headers=service)
        self.assertEqual(claim.status_code,200)
        self.assertEqual(claim.json()['id'], job['id'])

    def test_cancelled_signup_keeps_attendance_and_history(self):
        first = self.save(signup_status='signed_up')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['signup_status'], 'signed_up')
        cancelled = self.save(signup_status='cancelled', attended=True, attended_on=today().isoformat(), version=1)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = cancelled.json()
        self.assertEqual(body['signup_status'], 'cancelled')
        self.assertFalse(body['signed_up'])
        self.assertTrue(body['attended'])
        self.assertEqual(body['attendance_status'], 'attended')
        history = self.client.get('/api/v1/me/trainings/' + self.course + '/history')
        self.assertEqual(history.status_code, 200, history.text)
        self.assertGreaterEqual(len(history.json()['items']), 1)
        progress = self.client.get('/api/v1/me/progress').json()
        self.assertEqual(progress['attended'], 1)
        self.assertEqual(progress['signed_up'], 0)

    def test_profile_city_state_and_me_fields(self):
        body={'name':'Doctor A','city':'Petaling Jaya','state':'Selangor','bio':'Family medicine','public_enabled':False}
        saved=self.client.patch('/api/v1/me',json=body)
        self.assertEqual(saved.status_code,200,saved.text)
        me=self.client.get('/api/v1/me').json()
        self.assertEqual((me['city'],me['state']),('Petaling Jaya','Selangor'))
        self.assertNotIn('password_hash',me)
        half=self.client.patch('/api/v1/me',json={**body,'latitude':3.139})
        self.assertEqual(half.status_code,422)
        located=self.client.patch('/api/v1/me',json={**body,'latitude':3.139,'longitude':101.687})
        self.assertEqual(located.status_code,200,located.text)
        self.assertEqual(located.json()['latitude'],3.139)
        self.assertTrue(located.json()['location_consent_at'])
        cleared=self.client.patch('/api/v1/me',json=body)
        self.assertEqual(cleared.json()['latitude'],None)
        self.assertIsNone(cleared.json()['location_consent_at'])

    def test_two_sessions_on_one_page_stay_distinct(self):
        from main import source_key
        page='https://example.org/afpm-weekend'
        first={**sample('Saturday workshop'),'start_date':'2026-08-01','source_url':page}
        second={**sample('Sunday workshop'),'start_date':'2026-08-02','source_url':page}
        self.assertNotEqual(source_key(first),source_key(second))
        header={'Idempotency-Key':'two-sessions-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'AFPM weekend'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        quote='Saturday workshop Sunday workshop by Learning Institute in Malaysia Kuala Lumpur online. 2026-08-01. 2026-08-02. CPD points 2.'
        first['source_text']=second['source_text']=quote
        first['evidence']=second['evidence']={key:quote for key in ['title','provider','mode','country','start_date','points','credit_label']}
        complete=self.client.post('/internal/v1/jobs/'+claim['id']+'/complete',json={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[first,second]},headers=service)
        self.assertEqual(complete.status_code,200,complete.text)
        queue=self.client.get('/api/v1/admin/candidates').json()['items']
        self.assertEqual(len(queue),2)
        for item in queue:
            self.assertEqual(self.client.post('/api/v1/admin/candidates/'+item['id']+'/review',json={'action':'publish'}).status_code,200)
        titles=sorted(item['title'] for item in self.client.get('/api/v1/trainings?period=all').json()['items'] if 'workshop' in item['title'])
        self.assertEqual(titles,['Saturday workshop','Sunday workshop'])

    def test_opening_detail_does_not_create_a_record(self):
        before = self.client.get('/api/v1/me/trainings').json()['items']
        detail = self.client.get('/api/v1/trainings/' + self.course)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertIsNone(detail.json()['record'])
        self.assertNotIn('source_text', detail.json())
        self.assertNotIn('model_license_url', detail.json())
        after = self.client.get('/api/v1/me/trainings').json()['items']
        self.assertEqual(len(before), len(after))

    def test_progress_year_boundary(self):
        with self.Session() as db:
            course = db.get(Course, self.course)
            fill_course(course, {**course.data, 'start_date': '2025-12-01'})
            db.commit()
        self.assertEqual(self.save(attended_on='2025-12-31').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me/progress?year=2025').json()['attended'], 1)
        self.assertEqual(self.client.get('/api/v1/me/progress?year=2026').json()['attended'], 0)

    def test_radius_boundary_excludes_far_venues(self):
        with self.Session() as db:
            c = db.get(Course, self.course)
            fill_course(c, {**c.data, 'mode': 'in_person', 'city': 'Kuala Lumpur', 'latitude': 3.139, 'longitude': 101.687})
            db.commit()
        self.add_course(
            'far-venue',
            title='Far clinic day',
            mode='in_person',
            city='Kuantan',
            latitude=3.807,
            longitude=103.326,
            start_date='2026-01-01',
        )
        inside = self.client.get('/api/v1/trainings?period=all&mode=in_person&latitude=3.139&longitude=101.687&radius_km=25').json()
        titles = [item['title'] for item in inside['items']]
        self.assertIn('GP training', titles)
        self.assertNotIn('Far clinic day', titles)

    def test_operator_integrations_omit_secrets(self):
        blank = {
            'MODEL_ID': '',
            'MODEL_PUBLISHER': '',
            'MODEL_HOST': '',
            'MODEL_WEIGHTS_URL': '',
            'MODEL_LICENSE_URL': '',
            'MODEL_MAX_INPUT_CHARS': '',
            'MODEL_MAX_OUTPUT_TOKENS': '',
            'MODEL_API_KEY': '',
            'MODEL_OPEN_WEIGHT_CONFIRMED': 'false',
        }
        with patch.dict(os.environ, blank, clear=False):
            result=self.client.get('/api/v1/admin/integrations')
        self.assertEqual(result.status_code,200,result.text)
        body=result.json()
        self.assertEqual(body['model_id'], 'Qwen/Qwen3-30B-A3B-Instruct-2507')
        self.assertEqual(body['model_publisher'], 'Qwen')
        self.assertEqual(body['model_host'], 'Nebius Token Factory')
        self.assertTrue(body['model_caps_configured'])
        self.assertEqual(body['model_max_input_chars'], 12000)
        self.assertEqual(body['model_max_output_tokens'], 4000)
        self.assertFalse(body['model_open_weight_confirmed'])
        self.assertFalse(body['model_key_configured'])
        self.assertIn('model_key_configured', body)
        self.assertIn('model_caps_configured', body)
        self.assertIn('model_publisher', body)
        self.assertIn('model_host', body)
        self.assertIn('model_max_input_chars', body)
        self.assertIn('model_max_output_tokens', body)
        self.assertIn('catalogue_auto_publish_new', body)
        self.assertFalse(body['catalogue_auto_publish_new'])
        blob=result.text
        self.assertNotIn('TAVILY_API_KEY', blob)
        self.assertNotIn('MODEL_API_KEY', blob)
        self.assertNotIn('TYPESAFE_API_KEY', blob)
        self.assertNotIn('test-service-token', blob)
        self.login('b@example.com')
        self.assertEqual(self.client.get('/api/v1/admin/integrations').status_code,403)

    def test_operator_services_report_database_owner_without_secrets(self):
        with patch.dict(os.environ, {'SCRAPER_HEALTH_URL': ''}, clear=False):
            result = self.client.get('/api/v1/admin/services')
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body['backend'], 'ready')
        self.assertEqual(body['database'], 'ready')
        self.assertEqual(body['database_owner'], 'backend')
        self.assertEqual(body['scraper']['status'], 'unconfigured')
        self.assertFalse(body['scraper']['reachable'])
        self.assertFalse(body['paid_scrape_ready'])
        self.assertNotIn('TAVILY_API_KEY', result.text)
        self.assertNotIn('MODEL_API_KEY', result.text)
        self.assertNotIn('test-service-token', result.text)
        self.login('b@example.com')
        self.assertEqual(self.client.get('/api/v1/admin/services').status_code, 403)

    def test_operator_services_read_scraper_ready_flags(self):
        class FakeResponse:
            def read(self):
                return b'{"status":"ready","tavily_configured":true,"model_ready":false,"missing":["SECRET"]}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.dict(os.environ, {'SCRAPER_HEALTH_URL': 'http://127.0.0.1:8002'}, clear=False), patch(
            'main.urlopen', return_value=FakeResponse()
        ):
            self.login()
            body = self.client.get('/api/v1/admin/services').json()
        self.assertEqual(body['scraper']['status'], 'ready')
        self.assertTrue(body['scraper']['reachable'])
        self.assertTrue(body['scraper']['tavily_configured'])
        self.assertFalse(body['scraper']['model_ready'])
        self.assertFalse(body['paid_scrape_ready'])
        self.assertNotIn('SECRET', str(body))
        self.assertNotIn('missing', body['scraper'])

        class LiveReadyResponse:
            def read(self):
                return b'{"status":"ready","tavily_configured":true,"model_ready":true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.dict(os.environ, {'SCRAPER_HEALTH_URL': 'http://127.0.0.1:8002'}, clear=False), patch(
            'main.urlopen', return_value=LiveReadyResponse()
        ):
            ready = self.client.get('/api/v1/admin/services').json()
        self.assertTrue(ready['paid_scrape_ready'])
        self.assertNotIn('missing', body['scraper'])

    def test_public_config_is_login_flags_only(self):
        body = self.client.get('/api/v1/config').json()
        self.assertEqual(set(body), {'demo', 'signup_enabled', 'oauth_google'})

    def test_publish_stores_source_review_and_field_evidence(self):
        from portal_models import FieldEvidence
        header={'Idempotency-Key':'evidence-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP evidence'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        payload=sample('Reviewed clinic')
        self.client.post('/internal/v1/jobs/'+claim['id']+'/complete',json={'lease_token':claim['lease_token'],'status':'succeeded','candidates':[payload],'sources':[{'url':payload['source_url'],'title':payload['title'],'snippet':payload['source_text'][:200],'extraction_status':'success','verification_status':'unverified'}]},headers=service)
        cid=self.client.get('/api/v1/admin/candidates').json()['items'][0]['id']
        published=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish'})
        self.assertEqual(published.status_code,200)
        found=self.client.get('/api/v1/trainings?period=all&q=Reviewed').json()['items'][0]
        self.assertEqual(published.json()['resulting_course_id'],found['id'])
        self.assertEqual(found['verification_status'],'source_reviewed')
        self.assertIsNotNone(found['reviewed_at'])
        with self.Session() as db:
            rows=db.query(FieldEvidence).filter_by(course_id=found['id']).all()
            self.assertGreaterEqual(len(rows),4)
            self.assertTrue(all(row.reviewed_by and row.reviewed_at for row in rows))
            self.assertTrue(all(row.source_document_id for row in rows))
        detail=self.client.get('/api/v1/trainings/'+found['id']).json()
        self.assertGreaterEqual(len(detail.get('field_evidence') or []),4)
        self.assertTrue(all(item.get('excerpt') for item in detail['field_evidence']))

    def test_signed_up_at_and_points_origin(self):
        saved=self.save(signup_status='signed_up')
        self.assertEqual(saved.status_code,200,saved.text)
        body=saved.json()
        self.assertEqual(body['points_origin'],'self_reported')
        self.assertTrue(body['signed_up_at'])

    def test_my_trainings_are_paginated(self):
        self.assertEqual(self.save().status_code,200)
        page=self.client.get('/api/v1/me/trainings?page=1&page_size=1&attended=true')
        self.assertEqual(page.status_code,200,page.text)
        self.assertEqual(page.json()['page_size'],1)
        self.assertEqual(page.json()['total'],1)
        self.assertEqual(len(page.json()['items']),1)
        empty=self.client.get('/api/v1/me/trainings?attendance_status=not_recorded')
        self.assertEqual(empty.json()['total'],0)
        attended=self.client.get('/api/v1/me/trainings?attendance_status=attended')
        self.assertEqual(attended.json()['total'],1)

    def test_concurrent_claim_gives_one_owner(self):
        import threading
        header={'Idempotency-Key':'concurrent-claim-key'}
        self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP concurrent'},headers=header)
        service={'Authorization':'Bearer test-service-token'}
        codes=[]
        def claim():
            codes.append(self.client.post('/internal/v1/jobs/claim',headers=service).status_code)
        workers=[threading.Thread(target=claim) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sorted(codes),[200,204])

    def test_concurrent_worker_stress_does_not_duplicate(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        service={'Authorization':'Bearer test-service-token'}
        job_ids=[]
        for i in range(8):
            created=self.client.post(
                '/api/v1/admin/ingestion-jobs',
                json={'query':'GP stress topic '+str(i)+' extra'},
                headers={'Idempotency-Key':'stress-key-'+str(i)},
            )
            self.assertEqual(created.status_code,202,created.text)
            job_ids.append(created.json()['id'])

        def worker():
            owned=[]
            while True:
                response=self.client.post('/internal/v1/jobs/claim',headers=service)
                if response.status_code==204:
                    break
                self.assertEqual(response.status_code,200,response.text)
                job=response.json()
                complete=self.client.post(
                    '/internal/v1/jobs/'+job['id']+'/complete',
                    json={'lease_token':job['lease_token'],'status':'succeeded','candidates':[sample('Stress GP '+job['id'][:8])]},
                    headers=service,
                )
                self.assertEqual(complete.status_code,200,complete.text)
                owned.append(job['id'])
            return owned

        with ThreadPoolExecutor(8) as pool:
            owned=[item for future in as_completed([pool.submit(worker) for _ in range(8)]) for item in future.result()]
        self.assertEqual(sorted(owned),sorted(job_ids))
        self.assertEqual(len(set(owned)),8)
        items=self.client.get('/api/v1/admin/candidates').json()['items']
        self.assertEqual(len(items),8)
        self.assertEqual(len({item['data']['title'] for item in items}),8)
        statuses={row['id']:row['status'] for row in self.client.get('/api/v1/admin/ingestion-jobs').json()['items'] if row['id'] in job_ids}
        self.assertEqual(set(statuses.values()),{'succeeded'})

    def test_signup_and_password_validation(self):
        r=self.client.post('/api/v1/auth/register',json={'email':'new@example.com','password':PASSWORD,'name':'New Doctor'})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.post('/api/v1/auth/register',json={'email':'bad','password':'short'}).status_code,422)
        self.assertEqual(self.client.post('/api/v1/auth/login',json={'email':'new@example.com','password':'wrong-password-long'}).status_code,401)
        self.assertEqual(self.client.post('/api/v1/auth/login',json={'email':'new@example.com','password':PASSWORD}).status_code,200)

    def test_job_max_results_and_source_documents(self):
        from portal_models import SourceDocument
        header={'Idempotency-Key':'max-results-key'}
        created=self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP source pages','max_results':3},headers=header)
        self.assertEqual(created.status_code,202,created.text)
        self.assertEqual(created.json()['max_results'],3)
        self.assertEqual(self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP source pages','max_results':2},headers=header).status_code,409)
        self.assertEqual(self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP source pages','max_results':6},headers=header).status_code,422)
        service={'Authorization':'Bearer test-service-token'}
        claim=self.client.post('/internal/v1/jobs/claim',headers=service).json()
        self.assertEqual(claim['max_results'],3)
        payload={
            'lease_token':claim['lease_token'],'status':'partial','candidates':[],
            'sources':[{'url':'https://example.org/afpm#section','title':'Primary Care Update','snippet':'CPD workshop in Kuala Lumpur','extraction_status':'success','verification_status':'unverified'}],
        }
        self.assertEqual(self.client.post('/internal/v1/jobs/'+claim['id']+'/complete',json=payload,headers=service).status_code,200)
        with self.Session() as db:
            rows=db.query(SourceDocument).all()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].canonical_url,'https://example.org/afpm')
            self.assertEqual(rows[0].job_id,claim['id'])
        created=self.client.get('/api/v1/admin/ingestion-jobs/'+claim['id'])
        self.assertEqual(created.json()['attempt'],1)

    def test_candidates_are_paginated_and_review_is_versioned(self):
        with self.Session() as db:
            job=Job(account_id=self.a,request_key='review-page',query='GP')
            db.add(job);db.flush()
            first=Candidate(job_id=job.id,source_key='one',data=sample('First queue item'))
            second=Candidate(job_id=job.id,source_key='two',data=sample('Second queue item'))
            db.add_all([first,second]);db.commit()
            cid=first.id
        page=self.client.get('/api/v1/admin/candidates?page=1&page_size=1')
        self.assertEqual(page.status_code,200,page.text)
        self.assertEqual(page.json()['total'],2)
        self.assertEqual(page.json()['page_size'],1)
        self.assertEqual(len(page.json()['items']),1)
        self.assertEqual(page.json()['items'][0]['version'],1)
        self.assertEqual(page.json()['items'][0]['schema_version'],1)
        stale=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'hold','reason':'Need MMC confirmation','version':99})
        self.assertEqual(stale.status_code,409)
        held=self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'hold','reason':'Need MMC confirmation','version':1})
        self.assertEqual(held.status_code,200,held.text)
        self.assertEqual(held.json()['version'],2)

    def test_scraper_token_cannot_read_personal_data(self):
        self.save()
        self.client.cookies.clear()
        headers={'Authorization':'Bearer test-service-token'}
        self.assertEqual(self.client.get('/api/v1/me',headers=headers).status_code,401)
        self.assertEqual(self.client.get('/api/v1/me/trainings',headers=headers).status_code,401)
        self.assertEqual(self.client.get('/api/v1/me/export/csv',headers=headers).status_code,401)

    def test_operator_job_hourly_limit(self):
        for i in range(10):
            result=self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP CPD topic '+str(i)+' extra'},headers={'Idempotency-Key':'limit-key-'+str(i)})
            self.assertEqual(result.status_code,202,result.text)
        blocked=self.client.post('/api/v1/admin/ingestion-jobs',json={'query':'GP CPD extra topic overflow'},headers={'Idempotency-Key':'limit-key-10'})
        self.assertEqual(blocked.status_code,429)

    def test_expired_source_documents_are_purged(self):
        with self.Session() as db:
            old=SourceDocument(canonical_url='https://example.org/old',content_hash='abc',retrieved_at=1,snippet='old page')
            kept=SourceDocument(canonical_url='https://example.org/kept',content_hash='def',retrieved_at=1,snippet='reviewed page')
            db.add(old)
            db.add(kept)
            db.flush()
            db.add(FieldEvidence(course_id=self.course, source_document_id=kept.id, field_name='title', excerpt='reviewed excerpt'))
            job=Job(account_id=self.a,request_key='old-raw',query='GP',created_at=1,result={'sources':[{'url':'https://example.org/old','snippet':'job page'}]})
            fresh=Job(account_id=self.a,request_key='fresh-raw',query='GP',result={'sources':[{'url':'https://example.org/fresh','snippet':'fresh job page'}]})
            db.add(job)
            db.add(fresh)
            db.flush()
            candidate=Candidate(job_id=job.id,source_key='old-raw',data={**sample(),'source_text':'candidate page'})
            recent=Candidate(job_id=fresh.id,source_key='fresh-raw',data={**sample('Fresh GP'),'source_text':'recent candidate page'})
            db.add(candidate)
            db.add(recent)
            course=db.get(Course,self.course)
            fill_course(course,{**course.data,'source_text':'course page','retrieved_at':'2000-01-01T00:00:00'})
            db.commit()
            old_id=old.id
            kept_id=kept.id
            candidate_id=candidate.id
            recent_id=recent.id
            job_id=job.id
            fresh_id=fresh.id
            purge_expired_source_text(db, now=time.time())
            self.assertIsNone(db.get(SourceDocument, old_id))
            remaining=db.get(SourceDocument, kept_id)
            self.assertIsNotNone(remaining)
            self.assertEqual(remaining.snippet,'')
            self.assertEqual((db.get(Candidate, candidate_id).data or {}).get('source_text'),'')
            self.assertEqual((db.get(Candidate, candidate_id).data or {}).get('evidence')['title'],sample()['evidence']['title'])
            self.assertEqual((db.get(Candidate, recent_id).data or {}).get('source_text'),'recent candidate page')
            self.assertEqual((db.get(Course, self.course).data or {}).get('source_text'),'')
            self.assertEqual((db.get(Job, job_id).result or {}).get('sources')[0]['snippet'],'')
            self.assertEqual((db.get(Job, fresh_id).result or {}).get('sources')[0]['snippet'],'fresh job page')
            excerpt=db.query(FieldEvidence).filter_by(source_document_id=kept_id).first()
            self.assertEqual(excerpt.excerpt,'reviewed excerpt')

    def test_end_date_cannot_precede_start(self):
        with self.assertRaises(ValueError):
            fill_course(Course(source_key='bad-dates'), {**sample(), 'end_date':'2025-01-01'})

    def test_session_schedule_fields_persist(self):
        quote=sample()['source_text']+' Ends 2026-01-02 at Menara venue Asia/Kuala_Lumpur.'
        cid=self.add_course(
            'scheduled',
            title='Scheduled GP',
            start_date='2026-01-01',
            end_date='2026-01-02',
            timezone='Asia/Kuala_Lumpur',
            venue='Menara',
            source_text=quote,
            evidence={key:quote for key in ['title','provider','mode','country','start_date','end_date','timezone','venue']},
        )
        detail=self.client.get('/api/v1/trainings/'+cid).json()
        self.assertEqual(detail['end_date'],'2026-01-02')
        self.assertEqual(detail['timezone'],'Asia/Kuala_Lumpur')
        self.assertEqual(detail['venue'],'Menara')

    def test_demo_seed_exposes_provider_registration_urls(self):
        from seed_demo import seed
        from security import password_hash, password_matches
        from portal_models import Candidate, Record
        with self.Session() as db:
            seed(db)
            rows=db.query(Course).filter(Course.source_key.like('demo-%')).all()
            self.assertGreaterEqual(len(rows),6)
            for row in rows:
                url=(row.data or {}).get('registration_url')
                self.assertTrue(url and url.startswith('https://example.org/carecredits-demo-') and url.endswith('/register'), row.source_key)
            pending=db.query(Candidate).filter(Candidate.status=='pending', Candidate.source_key.like('demo-candidate-%')).all()
            self.assertGreaterEqual(len(pending),2)
            for cand in pending:
                self.assertIn('Demonstration source only', (cand.data or {}).get('source_text',''))
                self.assertTrue((cand.data or {}).get('_fixture'))
            from portal_models import Job
            job=db.query(Job).filter_by(request_key='demo-review-queue').one()
            self.assertEqual((job.result or {}).get('extraction_status'), 'fixture')
            doctor=db.query(Account).filter_by(email='doctor@carecredits.local').one()
            operator=db.query(Account).filter_by(email='demo@carecredits.local').one()
            self.assertGreaterEqual(db.query(Record).filter_by(account_id=doctor.id).count(),2)
            self.assertGreaterEqual(db.query(Record).filter_by(account_id=operator.id).count(),2)
            first=rows[0]
            first.data={**(first.data or {}), 'registration_url': None}
            demo=db.query(Account).filter_by(email='demo@carecredits.local').one()
            demo.password_hash=password_hash('Wrong-demo-password-999')
            db.commit()
            seed(db)
            refreshed=db.get(Course, first.id)
            self.assertTrue((refreshed.data or {}).get('registration_url', '').endswith('/register'))
            demo=db.query(Account).filter_by(email='demo@carecredits.local').one()
            self.assertTrue(password_matches('CareCredits-demo-2026', demo.password_hash))
            # Reseed keeps pending review candidates when already present.
            self.assertGreaterEqual(
                db.query(Candidate).filter(Candidate.status=='pending', Candidate.source_key.like('demo-candidate-%')).count(),
                2,
            )

    def test_demo_mode_login_reseeds_documented_accounts(self):
        from seed_demo import DEMO_PASSWORD
        blocked = self.client.post(
            '/api/v1/auth/login',
            json={'email': 'demo@carecredits.local', 'password': DEMO_PASSWORD},
        )
        self.assertEqual(blocked.status_code, 401, blocked.text)
        with patch.dict(os.environ, {'DEMO_MODE': 'true'}):
            restored = self.client.post(
                '/api/v1/auth/login',
                json={'email': 'demo@carecredits.local', 'password': DEMO_PASSWORD},
            )
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()['email'], 'demo@carecredits.local')
            self.client.post('/api/v1/auth/logout')
            doctor = self.client.post(
                '/api/v1/auth/login',
                json={'email': 'doctor@carecredits.local', 'password': DEMO_PASSWORD},
            )
            self.assertEqual(doctor.status_code, 200, doctor.text)
            self.assertEqual(doctor.json()['role'], 'doctor')
            wrong = self.client.post(
                '/api/v1/auth/login',
                json={'email': 'demo@carecredits.local', 'password': 'Wrong-demo-password-999'},
            )
            self.assertEqual(wrong.status_code, 401, wrong.text)
