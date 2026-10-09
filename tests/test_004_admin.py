"""#004 local Admin/Ops views; no secret is exposed."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app
from film_core import Core
from film_core.fixture import seed
from film_core.darl_h3 import ProviderError


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'studio.sqlite';self.media=Path(self.tmp.name)/'media'
        seed(Core(str(self.path),test_mode=True),production=True).close()
        self.client=TestClient(create_app(self.path,self.media,test_mode=True))

    def tearDown(self):self.client.close();self.tmp.cleanup()

    def test_provider_status_and_profile_history_hide_secret(self):
        secret='TEST-ONLY-SECRET-DO-NOT-DISPLAY'
        with patch.dict(os.environ,{'DARL_API_KEY':secret,'DARL_BASE_URL':'https://user:password@api.darl.cn/v1?token=hidden'}):
            providers=self.client.get('/api/admin/providers').json()
            profile=self.client.get('/api/admin/profiles').json()
            encoded=str(providers)+str(profile)+str(self.client.get('/api/admin/overview').json())
        self.assertNotIn(secret,encoded);self.assertNotIn('password',encoded);self.assertNotIn('token=hidden',encoded)
        self.assertEqual(providers[0]['model'],'deepseek-v4.1-flash')
        self.assertTrue(profile[0]['version']>=1)
        self.assertEqual(self.client.get('/api/admin/capability-packages').json(),[])

    def test_failed_job_query_and_admin_retry_guard(self):
        with patch.dict(os.environ,{'DARL_API_KEY':'TEST-ONLY','H3_SERVER_ON':'1'}),patch('apps.api.main.DarlH3Adapter') as adapter:
            adapter.return_value.build_request.return_value={}
            adapter.return_value.submit.side_effect=ProviderError('NETWORK_ERROR','temporary',transient=True)
            failed=self.client.post('/api/projects/station-film/clips/A/generate')
        jid=failed.json()['detail']['job_id']
        rows=self.client.get('/api/admin/jobs?status=failed').json()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],jid)
        self.assertEqual(rows[0]['error_category'],'NETWORK_ERROR')
        with patch.dict(os.environ,{'DARL_API_KEY':'TEST-ONLY','H3_SERVER_ON':'1'}),patch('apps.api.main.DarlH3Adapter') as adapter:
            adapter.return_value.build_request.return_value={}
            adapter.return_value.submit.return_value={'id':'test-provider-task','status':'queued'}
            retried=self.client.post('/api/admin/jobs/'+jid+'/technical-retry',json={'request_id':'admin-test-retry'})
        self.assertEqual(retried.status_code,200,retried.text)
        self.assertEqual(retried.json()['job']['snapshot']['retry_of'],jid)
        with patch.dict(os.environ,{'DARL_API_KEY':'TEST-ONLY','H3_SERVER_ON':'1'}):
            self.assertEqual(self.client.post('/api/admin/jobs/'+jid+'/technical-retry',json={'request_id':'another'}).status_code,400)

    def test_media_missing_and_versioned_profile_read(self):
        source=self.media/'TEST-ONLY.png';self.media.mkdir();source.write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*64)
        c=Core(str(self.path),test_mode=True)
        c.register_media('test-media',str(source),hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_size,'image/png',metadata={'kind':'image_candidate','project_id':'station-film','test_only':True})
        old=c.get('model_profile','h3-unverified');c.put('model_profile','h3-unverified',{**old['payload'],'note':'new version'},'test-version');c.close()
        source.unlink()
        media=self.client.get('/api/admin/media').json()
        self.assertEqual(media[0]['available'],False);self.assertEqual(media[0]['test_only'],True)
        self.assertEqual(self.client.get('/api/admin/overview').json()['media']['missing'],1)
        versions=[p['version'] for p in self.client.get('/api/admin/profiles').json() if p['id']=='h3-unverified']
        self.assertEqual(versions,[2,1])

    def test_config_validation_and_provider_disable(self):
        self.assertEqual(self.client.post('/api/admin/config',json={'key':'poll_seconds','value':'10'}).status_code,400)
        self.assertEqual(self.client.post('/api/admin/config',json={'key':'secret','value':'x'}).status_code,400)
        changed=self.client.post('/api/admin/config',json={'key':'h3_enabled','value':'false'})
        self.assertEqual(changed.status_code,200)
        self.assertEqual(self.client.get('/api/providers').json()['h3'],'服务未启动')


if __name__=='__main__':unittest.main()
