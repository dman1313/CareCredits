import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from main import app, today, migrate_schema
from database import Base, get_db
from portal_models import Account, Course, Record, Job, Candidate, SchemaVersion, fill_course
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
        self.env=patch.dict(os.environ,{'APP_ENV':'test','DEMO_MODE':'false','SCRAPER_SERVICE_TOKEN':'test-service-token','ALLOW_SIGNUP':'true'})
        self.env.start()
        self.client=TestClient(app,headers={'X-Care-Client':'1'})
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
        self.assertEqual(self.client.post('/api/v1/auth/logout').status_code,200)
        self.assertEqual(self.client.get('/api/v1/me').status_code,401)
        self.assertEqual(self.client.get('/users/').status_code,404)

    def test_two_user_isolation_and_roles(self):
        self.assertEqual(self.save().status_code,200)
        self.login('b@example.com')
        self.assertEqual(self.client.get('/api/v1/me/trainings').json()['items'],[])
        self.assertIsNone(self.client.get('/api/v1/trainings/'+self.course).json()['record'])
        self.assertEqual(self.client.get('/api/v1/admin/candidates').status_code,403)
        self.assertEqual(self.client.post('/internal/v1/jobs/claim').status_code,403)
        self.assertNotIn('PRIVATE NOTE', self.client.get('/api/v1/me/export/csv').text)

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

    def test_invalid_evidence_cannot_publish(self):
        with self.Session() as db:
            j=Job(account_id=self.a,request_key='j',query='GP');db.add(j);db.flush()
            c=Candidate(job_id=j.id,source_key='fake',data={**sample(),'evidence':{'title':'invented'}});db.add(c);db.commit();cid=c.id
        self.assertEqual(self.client.post('/api/v1/admin/candidates/'+cid+'/review',json={'action':'publish'}).status_code,422)

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
        self.assertEqual(self.client.get('/api/v1/trainings?page=0').status_code,422)

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
            self.assertEqual(max(v.version for v in db.query(SchemaVersion).all()), 2)

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
        claim=self.client.post('/internal/v1/jobs/claim',headers=service)
        self.assertEqual(claim.status_code,200)
        self.assertEqual(claim.json()['id'], job['id'])

    def test_signup_and_password_validation(self):
        r=self.client.post('/api/v1/auth/register',json={'email':'new@example.com','password':PASSWORD,'name':'New Doctor'})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.post('/api/v1/auth/register',json={'email':'bad','password':'short'}).status_code,422)
        self.assertEqual(self.client.post('/api/v1/auth/login',json={'email':'new@example.com','password':'wrong-password-long'}).status_code,401)
        self.assertEqual(self.client.post('/api/v1/auth/login',json={'email':'new@example.com','password':PASSWORD}).status_code,200)
