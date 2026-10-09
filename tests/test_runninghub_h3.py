"""RunningHub fallback contract; every provider and media response here is TEST ONLY."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.job_runtime import JobWorker
from apps.api.runninghub_h3 import RunningHubH3Adapter, runninghub_h3_profile
from film_core import Core, DomainError
from film_core.fixture import seed


class Response:
    def __init__(self, body):
        self.body=body if isinstance(body,bytes) else json.dumps(body).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n=-1):return self.body if n<0 else self.body[:n]


class FakeHTTP:
    def __init__(self):
        self.requests=[]
    def __call__(self,request,timeout=60):
        self.requests.append(request)
        url=request.full_url
        if url.endswith('/task/openapi/upload'):
            return Response({'code':0,'data':{'fileName':'TEST-ONLY-reference.png'}})
        if url.endswith('/task/openapi/ai-app/run'):
            return Response({'code':0,'data':{'taskId':'123456789','taskStatus':'QUEUED'}})
        if url.endswith('/openapi/v2/query'):
            return Response({'status':'SUCCESS','results':[{'fileUrl':'https://media.example/TEST-ONLY.mp4'}]})
        if url.endswith('/TEST-ONLY.mp4'):
            return Response(b'\x00\x00\x00\x18ftypisom'+b'TEST ONLY VIDEO'*100)
        raise AssertionError(url)


class FakeRunningHub:
    def build_request(self,task):
        return {'nodeInfoList':[]}
    def submit(self,task,job_id):
        return {'id':'123456789','status':'queued'}
    def poll(self,task_id):
        return {'id':task_id,'status':'succeeded'}
    def download(self,task_id,destination):
        data=b'\x00\x00\x00\x18ftypisom'+b'TEST ONLY VIDEO'*100
        target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return {'local_path':str(target),'sha256':hashlib.sha256(data).hexdigest(),
                'size_bytes':len(data),'mime':'video/mp4','duration':10.0,
                'metadata':{'source':'TEST ONLY adapter'}}


class FakeFailedRunningHub(FakeRunningHub):
    def poll(self,task_id):
        return {'id':task_id,'status':'failed','error_code':'NETWORK_ERROR'}


class RunningHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'studio.sqlite'
        self.media=Path(self.tmp.name)/'media'
        seed(Core(str(self.path),test_mode=True),production=True).close()
        self.app=create_app(self.path,self.media,test_mode=True)
        self.client=TestClient(self.app)
        self.env=patch.dict(os.environ,{'RUNNINGHUB_API_KEY':'TEST-ONLY-KEY',
                                         'RUNNINGHUB_WEBAPP_ID':'12345','H3_SERVER_ON':'0'})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.client.close();self.tmp.cleanup()

    def test_documented_nodes_and_upload_submit_query_download(self):
        http=FakeHTTP()
        adapter=RunningHubH3Adapter(key='TEST-ONLY-KEY',webapp_id='12345',opener=http)
        picture=Path(self.tmp.name)/'reference.png'
        picture.write_bytes(b'\x89PNG\r\n\x1a\nTEST ONLY')
        task={'target_model':'MiniMax-H3','task_mode':'MULTI_SHOT_ONE_PASS',
              'duration':10,'aspect_ratio':'16:9','compiled_prompt':'<Picture 1> 人物参考，雨夜车站',
              'parameters':{'resolution':'480P','num_inference_steps':20,'turbo':False,'watermark':False},
              'media_bindings':[{'media_type':'image','role':'character_identity','uri':str(picture)}]}
        spec=adapter.build_request(task)
        self.assertEqual(spec['uploads'][0][0],'51')
        created=adapter.submit(task,'TEST-ONLY-request')
        self.assertEqual(created['id'],'123456789')
        self.assertEqual(adapter.poll(created['id'])['status'],'succeeded')
        with patch('apps.api.runninghub_h3.subprocess.run') as probe:
            probe.return_value.stdout='{"format":{"duration":"10.0"}}'
            info=adapter.download(created['id'],self.media/'result.mp4')
        self.assertTrue(Path(info['local_path']).is_file())
        upload,submit,query,download_query,download=http.requests
        self.assertIn(b'apiKey',upload.data)
        self.assertNotIn('Authorization',upload.headers)
        submit_body=json.loads(submit.data)
        self.assertEqual(submit_body['webappId'],12345)
        self.assertEqual(next(n for n in submit_body['nodeInfoList'] if n['nodeId']=='51'),
                         {'nodeId':'51','fieldName':'image','value':'TEST-ONLY-reference.png'})
        self.assertEqual(next(n for n in submit_body['nodeInfoList'] if n['nodeId']=='49')['value'],'')
        self.assertIn('Authorization',query.headers)
        self.assertIn('Authorization',download_query.headers)
        self.assertNotIn('Authorization',download.headers)

    def test_video_reference_does_not_enable_continuation(self):
        profile=runninghub_h3_profile()
        self.assertNotIn('VIDEO_CONTINUATION',profile['supported_modes'])
        self.assertFalse(profile['temporal_controls']['video_continuation'])
        adapter=RunningHubH3Adapter(key='TEST-ONLY-KEY',webapp_id='12345',opener=FakeHTTP())
        task={'target_model':'MiniMax-H3','task_mode':'VIDEO_CONTINUATION','continuation':{'control_media_id':'tail'},
              'duration':10,'aspect_ratio':'16:9','compiled_prompt':'test',
              'parameters':{'resolution':'480P','num_inference_steps':20,'turbo':False,'watermark':False},
              'media_bindings':[]}
        with self.assertRaises(DomainError):adapter.build_request(task)

    def test_image_audio_video_uploads_have_distinct_workflow_slots(self):
        http=FakeHTTP();adapter=RunningHubH3Adapter(key='TEST-ONLY-KEY',webapp_id='12345',opener=http)
        paths=[]
        for name in ('person.png','sound.wav','motion.mp4'):
            path=Path(self.tmp.name)/name;path.write_bytes(b'TEST ONLY reference');paths.append(path)
        task={'target_model':'MiniMax-H3','task_mode':'VISUAL_ANCHOR','duration':10,'aspect_ratio':'16:9',
              'compiled_prompt':'<Picture 1> <Audio 1> <Video 1>',
              'parameters':{'resolution':'480P','num_inference_steps':20,'turbo':False,'watermark':False},
              'media_bindings':[{'media_type':'image','role':'character_identity','uri':str(paths[0])},
                                {'media_type':'audio','role':'audio_reference','uri':str(paths[1])},
                                {'media_type':'video','role':'motion_reference','uri':str(paths[2])}]}
        self.assertEqual([(slot,field) for slot,field,_ in adapter.build_request(task)['uploads']],
                         [('51','image'),('48','audio'),('27','video')])
        adapter.submit(task,'TEST-ONLY-request')
        self.assertEqual(sum(r.full_url.endswith('/task/openapi/upload') for r in http.requests),3)
        nodes=json.loads(http.requests[-1].data)['nodeInfoList']
        self.assertEqual([n['nodeId'] for n in nodes if n['value']=='TEST-ONLY-reference.png'],['51','48','27'])

    def test_failed_query_is_structured_without_provider_message_or_secret(self):
        def opener(request,timeout=60):
            self.assertIn('Authorization',request.headers)
            return Response({'status':'FAILED','errorCode':'1000',
                             'errorMessage':'TEST ONLY raw provider message'})
        adapter=RunningHubH3Adapter(key='TEST-ONLY-KEY',webapp_id='12345',opener=opener)
        result=adapter.poll('123456789')
        self.assertEqual(result,{'id':'123456789','status':'failed','error_code':'1000'})
        self.assertNotIn('errorMessage',result)

    def test_explicit_fallback_route_job_provenance_restart_and_media(self):
        state=self.client.get('/api/providers').json()
        self.assertEqual(state['h3'],'服务未启动')
        self.assertEqual(state['runninghub_h3'],'可用')
        self.assertIn('本地 H3 未启动，可使用备用 RunningHub H3',state['h3_message'])
        with patch('apps.api.main.RunningHubH3Adapter',return_value=FakeRunningHub()):
            response=self.client.post('/api/projects/station-film/clips/A/generate?provider=runninghub&request_id=TEST-ONLY-request')
        self.assertEqual(response.status_code,200,response.text)
        job=response.json()['job']
        self.assertEqual(job['metadata']['provider'],'runninghub')
        self.assertEqual(job['snapshot']['cost_estimate']['provider'],'runninghub')
        self.assertEqual(job['snapshot']['task']['model_profile']['id'],'h3-runninghub')
        self.assertEqual(job['metadata']['provider_task_id'],'123456789')
        worker=JobWorker(self.path,self.media,test_mode=True,runninghub_factory=FakeRunningHub,poll_seconds=0)
        worker.recover()
        c=Core(str(self.path),test_mode=True)
        c.db.execute("UPDATE job_runtime SET next_poll_at='2000-01-01T00:00:00+00:00' WHERE job_id=?",(job['id'],))
        c.db.commit();c.close()
        worker.tick()
        finished=self.client.get('/api/projects/station-film/jobs/'+job['id']).json()
        self.assertEqual(finished['status'],'succeeded')
        self.assertEqual(finished['runtime']['provider'],'runninghub')
        take=self.client.get('/api/projects/station-film/takes').json()[0]
        self.assertEqual(take['test_only'],1)
        c=Core(str(self.path),test_mode=True)
        media=c.media(take['media_id'])
        self.assertEqual(media['metadata']['provider'],'runninghub')
        self.assertEqual(media['metadata']['source'],'provider')
        c.close()
        rows=self.client.get('/api/admin/jobs').json()
        self.assertEqual(rows[0]['provider'],'runninghub')

    def test_fallback_requires_explicit_choice_and_blocks_continuation(self):
        default=self.client.post('/api/projects/station-film/clips/A/generate')
        self.assertEqual(default.status_code,503)
        self.assertEqual(self.client.get('/api/projects/station-film/jobs').json(),[])
        blocked=self.client.post('/api/projects/station-film/clips/C2/generate?provider=runninghub')
        self.assertEqual(blocked.status_code,400)
        self.assertIn('续接验证',blocked.json()['detail'])
        self.assertEqual(self.client.get('/api/projects/station-film/jobs').json(),[])

    def test_provider_failure_and_same_provider_retry(self):
        with patch('apps.api.main.RunningHubH3Adapter',return_value=FakeRunningHub()):
            response=self.client.post('/api/projects/station-film/clips/A/generate?provider=runninghub')
        jid=response.json()['job']['id']
        worker=JobWorker(self.path,self.media,test_mode=True,runninghub_factory=FakeFailedRunningHub,poll_seconds=0)
        c=Core(str(self.path),test_mode=True)
        c.db.execute("UPDATE job_runtime SET next_poll_at='2000-01-01T00:00:00+00:00' WHERE job_id=?",(jid,))
        c.db.commit();brief_version=c.get('brief','brief:A')['version'];c.close()
        worker.tick()
        failed=self.client.get('/api/projects/station-film/jobs/'+jid).json()
        self.assertEqual(failed['status'],'failed')
        self.assertEqual(failed['metadata']['error_category'],'NETWORK_ERROR')
        self.assertEqual(self.client.get('/api/projects/station-film/takes').json(),[])
        with patch('apps.api.main.RunningHubH3Adapter',return_value=FakeRunningHub()):
            retry=self.client.post('/api/projects/station-film/clips/A/generate?provider=runninghub&retry_of='+jid)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(retry.json()['job']['snapshot']['retry_of'],jid)
        c=Core(str(self.path),test_mode=True)
        self.assertEqual(c.get('brief','brief:A')['version'],brief_version)
        c.close()


if __name__=='__main__':unittest.main()
