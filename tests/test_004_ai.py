"""#004 contextual proposal and candidate asset integration; provider calls are patched."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from apps.api.main import create_app
from film_core import Core
from film_core.fixture import seed


class AIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'studio.sqlite'
        self.media=Path(self.tmp.name)/'media'
        seed(Core(str(self.path),test_mode=True),production=True).close()
        self.client=TestClient(create_app(self.path,self.media,test_mode=True))
        self.base='/api/projects/station-film'

    def tearDown(self):
        self.client.close();self.tmp.cleanup()

    def llm(self,result):
        mock=patch('apps.api.main.DarlLLMAdapter')
        adapter=mock.start();self.addCleanup(mock.stop)
        adapter.return_value.provider='test-only';adapter.return_value.model='test-only-llm'
        adapter.return_value.propose.return_value=result
        return adapter

    def test_scene_proposal_accept_only_then_formal_version(self):
        self.llm({'change':{'scenes':[{'place':'站台外','story':'她停下脚步，决定等待。'}]},'explanation':'把决定拆为独立场次。'})
        before=len(self.client.get(self.base+'/scenes').json())
        result=self.client.post(self.base+'/proposals',json={'task':'scene_plan','instruction':'单独表现决定'}).json()
        self.assertEqual(result['status'],'pending')
        self.assertEqual(len(self.client.get(self.base+'/scenes').json()),before)
        self.assertEqual(result['context']['items'][0]['authority'],'FORMAL')
        self.assertFalse(any(x['kind']=='shot' for x in result['context']['items']))
        accepted=self.client.post(self.base+'/proposals/'+result['id']+'/accept').json()
        self.assertEqual(accepted['status'],'accepted')
        self.assertEqual(len(self.client.get(self.base+'/scenes').json()),before+1)
        self.assertEqual(self.client.post(self.base+'/proposals/'+result['id']+'/accept').status_code,200)
        self.assertEqual(len(self.client.get(self.base+'/scenes').json()),before+1)

    def test_reject_and_stale_proposal_preserve_formal_state(self):
        self.llm({'change':{'shots':[{'purpose':'等待','description':'人物看向站台','action':'抬眼','performance':'呼吸一顿','camera':'中近景固定','sound':'雨声','duration':4}]},'explanation':'更清楚地拍等待。'})
        before=len(self.client.get(self.base+'/shots').json())
        first=self.client.post(self.base+'/proposals',json={'task':'shot_plan','target_id':'station-scene'}).json()
        self.assertEqual(self.client.post(self.base+'/proposals/'+first['id']+'/reject').json()['status'],'rejected')
        self.assertEqual(len(self.client.get(self.base+'/shots').json()),before)
        second=self.client.post(self.base+'/proposals',json={'task':'shot_plan','target_id':'station-scene'}).json()
        scene=self.client.get(self.base+'/scenes').json()[0]
        self.client.patch(self.base+'/scenes/station-scene',json={'payload':{'story':'正式故事已改'},'expected_version':scene['version'],'status':'approved'})
        self.assertEqual(self.client.post(self.base+'/proposals/'+second['id']+'/accept').status_code,409)
        self.assertEqual(next(p['status'] for p in self.client.get(self.base+'/proposals').json() if p['id']==second['id']),'superseded')
        self.assertEqual(len(self.client.get(self.base+'/shots').json()),before)

    def test_malformed_llm_output_rejected_without_proposal(self):
        self.llm({'change':{'shots':[{'purpose':'缺字段'}]},'explanation':'无效'})
        result=self.client.post(self.base+'/proposals',json={'task':'shot_plan','target_id':'station-scene'})
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.client.get(self.base+'/proposals').json(),[])

    def test_image_candidate_is_not_asset_until_human_adopts(self):
        mock=patch('apps.api.main.DarlImageAdapter');adapter=mock.start();self.addCleanup(mock.stop)
        adapter.return_value.provider='test-only';adapter.return_value.model='gpt-image-2-test-only'
        adapter.return_value.generate.return_value=(b'\x89PNG\r\n\x1a\n'+b'TEST-ONLY' * 64,'image/png',{'revised_prompt':''})
        before=len(self.client.get(self.base+'/world/asset_version').json())
        result=self.client.post(self.base+'/assets/candidates',json={
            'owner_id':'linxia','purpose':'人物身份','prompt':'林夏的写实身份参考照片，深灰风衣'}).json()
        self.assertEqual(result['status'],'pending')
        self.assertEqual(len(self.client.get(self.base+'/world/asset_version').json()),before)
        self.assertEqual(self.client.get(self.base+'/assets/candidates/'+result['id']+'/image').status_code,200)
        adopted=self.client.post(self.base+'/assets/candidates/'+result['id']+'/adopt').json()
        self.assertEqual(adopted['status'],'adopted')
        self.assertEqual(adopted['asset']['payload']['provenance']['source'],'generated')
        self.assertEqual(len(self.client.get(self.base+'/world/asset_version').json()),before+1)
        self.assertTrue(any(x['is_current'] for x in self.client.get(self.base+'/world/asset_version').json()))
        self.assertEqual(self.client.post(self.base+'/assets/candidates/'+result['id']+'/adopt').status_code,200)


if __name__=='__main__': unittest.main()
