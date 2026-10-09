"""#004 runtime integration with a clearly TEST ONLY provider; no real H3 request."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app
from apps.api.job_runtime import JobWorker
from film_core import Core
from film_core.fixture import seed
from film_core.darl_h3 import ProviderError


class FakeVideo:
    state='succeeded'
    fail_download=False
    poll_calls=0
    def poll(self,task_id):
        FakeVideo.poll_calls+=1
        if FakeVideo.state=='transient' and FakeVideo.poll_calls==1:
            raise ProviderError('HTTP_429','temporary',transient=True,http_status=429)
        return {'id':task_id,'status':'succeeded' if FakeVideo.state=='transient' else FakeVideo.state}
    def download(self,task_id,destination):
        if FakeVideo.fail_download:raise ProviderError('NETWORK_ERROR','download failed',transient=True)
        data=b'\x00\x00\x00\x18ftypisom'+b'TEST ONLY VIDEO CONTRACT'*100
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
        return {'local_path':str(destination),'sha256':hashlib.sha256(data).hexdigest(),
                'size_bytes':len(data),'mime':'video/mp4','duration':5.0,'metadata':{'source':'TEST ONLY adapter'}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'studio.sqlite';self.media=Path(self.tmp.name)/'media'
        seed(Core(str(self.path),test_mode=True),production=True).close()
        self.app=create_app(self.path,self.media,test_mode=True)
        self.client=TestClient(self.app)
        self.env=patch.dict(os.environ,{'DARL_API_KEY':'TEST-ONLY','H3_SERVER_ON':'1'});self.env.start()
        self.adapter=patch('apps.api.main.DarlH3Adapter');mock=self.adapter.start()
        mock.return_value.build_request.return_value={'model':'MiniMax-H3'}
        mock.return_value.submit.return_value={'id':'test-provider-task','status':'queued'}
        FakeVideo.state='succeeded';FakeVideo.fail_download=False;FakeVideo.poll_calls=0

    def tearDown(self):
        self.adapter.stop();self.env.stop();self.client.close();self.tmp.cleanup()

    def submit(self,extra=''):
        response=self.client.post('/api/projects/station-film/clips/A/generate?request_id=test-request-1'+extra)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['job']

    def worker(self,**kwargs):
        return JobWorker(self.path,self.media,test_mode=True,adapter_factory=FakeVideo,poll_seconds=0,**kwargs)

    def due(self,jid):
        c=Core(str(self.path),test_mode=True)
        c.db.execute("UPDATE job_runtime SET next_poll_at='2000-01-01T00:00:00+00:00' WHERE job_id=?",(jid,));c.db.commit();c.close()

    def test_submit_idempotency_restart_poll_media_take(self):
        job=self.submit()
        same=self.client.post('/api/projects/station-film/clips/A/generate?request_id=test-request-1').json()
        self.assertTrue(same['idempotent']);self.assertEqual(same['job']['id'],job['id'])
        duplicate=self.client.post('/api/projects/station-film/clips/A/generate?request_id=test-request-2')
        self.assertIn(duplicate.status_code,(400,409))
        restarted=self.worker();restarted.recover();self.due(job['id']);restarted.tick()
        detail=self.client.get('/api/projects/station-film/jobs/'+job['id']).json()
        self.assertEqual(detail['status'],'succeeded')
        takes=self.client.get('/api/projects/station-film/takes').json()
        self.assertEqual(len(takes),1);self.assertEqual(takes[0]['test_only'],1)
        c=Core(str(self.path),test_mode=True);media=c.media(takes[0]['media_id'])
        self.assertEqual(media['metadata']['kind'],'video_take')
        self.assertEqual(media['metadata']['project_id'],'station-film')
        self.assertTrue(Path(media['local_path']).is_file())
        c.close()
        restarted.tick();self.assertEqual(len(self.client.get('/api/projects/station-film/takes').json()),1)

    def test_failed_poll_and_explicit_transient_retry(self):
        job=self.submit();FakeVideo.state='failed'
        worker=self.worker();self.due(job['id']);worker.tick()
        failed=self.client.get('/api/projects/station-film/jobs/'+job['id']).json()
        self.assertEqual(failed['status'],'failed')
        self.assertEqual(failed['metadata']['error_category'],'PROVIDER_FAILED')
        disallowed=self.client.post('/api/projects/station-film/clips/A/generate?retry_of='+job['id'])
        self.assertEqual(disallowed.status_code,400)

    def test_transient_poll_then_success_preserves_brief(self):
        job=self.submit();FakeVideo.state='transient'
        c=Core(str(self.path),test_mode=True);brief_before=c.get('brief','brief:A')['version'];c.close()
        worker=self.worker();self.due(job['id']);worker.tick()
        self.assertEqual(self.client.get('/api/projects/station-film/jobs/'+job['id']).json()['status'],'running')
        self.due(job['id']);worker.tick()
        self.assertEqual(self.client.get('/api/projects/station-film/jobs/'+job['id']).json()['status'],'succeeded')
        c=Core(str(self.path),test_mode=True);self.assertEqual(c.get('brief','brief:A')['version'],brief_before);c.close()

    def test_download_failure_never_creates_take(self):
        job=self.submit();FakeVideo.fail_download=True
        worker=self.worker(max_download=2);self.due(job['id']);worker.tick()
        self.assertEqual(self.client.get('/api/projects/station-film/jobs/'+job['id']).json()['status'],'running')
        self.due(job['id']);worker.tick()
        failed=self.client.get('/api/projects/station-film/jobs/'+job['id']).json()
        self.assertEqual(failed['metadata']['error_category'],'MEDIA_DOWNLOAD_FAILED')
        self.assertEqual(self.client.get('/api/projects/station-film/takes').json(),[])

    def test_submit_failure_requires_bounded_explicit_retry(self):
        self.app.state.job_worker.stop_event.set()
        with patch('apps.api.main.DarlH3Adapter') as adapter:
            adapter.return_value.build_request.return_value={}
            adapter.return_value.submit.side_effect=ProviderError('NETWORK_ERROR','temporary',transient=True)
            failed=self.client.post('/api/projects/station-film/clips/A/generate')
        self.assertEqual(failed.status_code,503)
        jid=failed.json()['detail']['job_id']
        retry=self.client.post('/api/projects/station-film/clips/A/generate?retry_of='+jid)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(retry.json()['job']['snapshot']['retry_of'],jid)
        self.assertEqual(retry.json()['job']['snapshot']['task']['source_brief']['version'],1)

    def test_stale_task_before_submit_is_rejected(self):
        def change_brief(_task):
            c=Core(str(self.path),test_mode=True);old=c.get('brief','brief:A')['payload']
            c.save_brief('A',{**old,'purpose':'并发更新的制作目的'});c.close();return {}
        self.adapter.stop()
        with patch('apps.api.main.DarlH3Adapter') as adapter:
            adapter.return_value.build_request.side_effect=change_brief
            response=self.client.post('/api/projects/station-film/clips/A/generate')
        self.adapter=patch('apps.api.main.DarlH3Adapter');self.adapter.start()
        self.assertEqual(response.status_code,400,response.text)
        self.assertEqual(self.client.get('/api/projects/station-film/jobs').json(),[])


if __name__=='__main__':unittest.main()
