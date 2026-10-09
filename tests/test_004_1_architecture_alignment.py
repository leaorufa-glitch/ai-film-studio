"""#004.1 retry alignment contracts; all providers and media are TEST ONLY."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import create_app
from film_core import Core, DomainError
from film_core.darl_h3 import ProviderError
from film_core.fixture import seed
from film_core.h3_profile import CLOUD_H3_MODEL, LOCAL_H3_MODEL


class ArchitectureAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'studio.sqlite'
        self.media = Path(self.tmp.name) / 'media'
        seed(Core(str(self.path), test_mode=True), production=True).close()
        environment = patch.dict(os.environ, {
            'DARL_API_KEY': 'TEST-ONLY', 'H3_SERVER_ON': '1',
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.adapters = {}
        for provider, name in (('darl', 'DarlH3Adapter'),):
            adapter_patch = patch('apps.api.main.' + name)
            adapter = adapter_patch.start().return_value
            self.addCleanup(adapter_patch.stop)
            adapter.build_request.return_value = {}
            adapter.submit.return_value = {'id': 'TEST-ONLY-' + provider, 'status': 'queued'}
            self.adapters[provider] = adapter
        self.client = TestClient(create_app(self.path, self.media, test_mode=True, start_worker=False))
        self.addCleanup(self.client.close)

    def core(self):
        core = Core(str(self.path), test_mode=True)
        self.addCleanup(core.close)
        return core

    def failed_job(self, execution_model=LOCAL_H3_MODEL):
        self.adapters['darl'].submit.side_effect = ProviderError('NETWORK_ERROR', 'TEST ONLY', transient=True)
        with patch.dict(os.environ, {'H3_SERVER_ON': '1' if execution_model == LOCAL_H3_MODEL else '0'}):
            response = self.client.post('/api/projects/station-film/clips/A/generate', params={'provider': 'darl'})
        self.assertEqual(response.status_code, 503, response.text)
        job = self.core().job(response.json()['detail']['job_id'])
        self.adapters['darl'].submit.side_effect = None
        return job

    def retry(self, job, endpoint='creator', **parameters):
        if endpoint == 'admin':
            return self.client.post('/api/admin/jobs/' + job['id'] + '/technical-retry',
                                    json={'request_id': 'TEST-ONLY-' + job['id']})
        return self.client.post('/api/projects/station-film/clips/A/generate',
                                params={'retry_of': job['id'], **parameters})

    def revise_brief(self):
        core = self.core()
        original = core.get('brief', 'brief:A')
        payload = copy.deepcopy(original['payload'])
        payload['purpose'] = 'TEST ONLY 新创作方案：延长人物停顿'
        response = self.client.post('/api/projects/station-film/clips/A/briefs',
                                    json={'payload': payload, 'expected_version': original['version'],
                                          'source': 'TEST-ONLY-creator-revision'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_darl_creator_retry_preserves_provider_and_original_task(self):
        self.assert_retry_preserved(LOCAL_H3_MODEL, 'creator')

    def test_darl_admin_retry_preserves_provider_and_original_task(self):
        self.assert_retry_preserved(LOCAL_H3_MODEL, 'admin')

    def test_cloud_creator_retry_preserves_model_and_original_task(self):
        self.assert_retry_preserved(CLOUD_H3_MODEL, 'creator')

    def test_cloud_admin_retry_preserves_model_with_self_hosted_offline(self):
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            self.assert_retry_preserved(CLOUD_H3_MODEL, 'admin')

    def assert_retry_preserved(self, execution_model, endpoint):
        original = self.failed_job(execution_model)
        before = copy.deepcopy(original)
        brief = self.core().get('brief', 'brief:A')
        response = self.retry(original, endpoint)
        self.assertEqual(response.status_code, 200, response.text)
        retried = response.json()['job']
        self.assertEqual(retried['metadata']['provider'], 'darl')
        self.assertEqual(retried['snapshot']['cost_estimate']['provider'], 'darl')
        self.assertEqual(retried['snapshot']['task']['execution_model'], execution_model)
        self.assertEqual(retried['snapshot']['retry_of'], original['id'])
        self.assertEqual(retried['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(self.adapters['darl'].submit.call_args.args[0], original['snapshot']['task'])
        self.assertEqual(self.core().get('brief', 'brief:A'), brief)
        self.assertEqual(self.core().job(original['id']), before)

    def test_latest_brief_and_profile_changes_do_not_change_retry_inputs(self):
        original = self.failed_job(CLOUD_H3_MODEL)
        revised = self.revise_brief()
        core = self.core()
        profile = core.get('model_profile', 'h3-darl-cloud')
        core.put('model_profile', profile['id'], {**profile['payload'], 'note': 'TEST ONLY new profile'}, 'TEST-ONLY')
        with patch('film_core.core.Core.compile_h3', side_effect=AssertionError('retry must not recompile')):
            response = self.retry(original, 'admin')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(core.get('brief', 'brief:A'), revised)

    def test_creator_retry_after_latest_brief_change_preserves_original_version(self):
        original = self.failed_job()
        revised = self.revise_brief()
        response = self.retry(original)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(self.core().get('brief', 'brief:A'), revised)

    def add_reference(self):
        core = self.core()
        uri = str(Path(self.tmp.name) / 'TEST-ONLY-original.png')
        core.put('asset_version', 'TEST-ONLY-asset', {'uri': uri}, 'TEST-ONLY')
        binding = core.put('reference_binding', 'TEST-ONLY-reference', {
            'asset_id': 'TEST-ONLY-asset', 'asset_version': 1, 'uri': uri,
            'role': 'character_identity', 'media_type': 'image'}, 'TEST-ONLY')
        brief = core.get('brief', 'brief:A')
        core.save_brief('A', {**brief['payload'], 'references': [binding['id']]}, 'TEST-ONLY')
        return binding

    def test_reference_and_asset_updates_do_not_replace_original_inputs(self):
        binding = self.add_reference()
        original = self.failed_job()
        core = self.core()
        uri = str(Path(self.tmp.name) / 'TEST-ONLY-new.png')
        core.put('asset_version', 'TEST-ONLY-asset', {'uri': uri}, 'TEST-ONLY')
        core.put('reference_binding', binding['id'], {**binding['payload'], 'uri': uri, 'asset_version': 2}, 'TEST-ONLY')
        response = self.retry(original)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(self.adapters['darl'].submit.call_args.args[0]['media_bindings'][0]['uri'], binding['payload']['uri'])

    def test_missing_original_reference_is_rejected(self):
        binding = self.add_reference()
        original = self.failed_job()
        core = self.core()
        core.db.execute("DELETE FROM objects WHERE kind='reference_binding' AND id=?", (binding['id'],))
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original)
        self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()

    def test_missing_original_profile_is_rejected(self):
        original = self.failed_job()
        core = self.core()
        profile = core.get('model_profile', 'h3-darl')
        core.put('model_profile', profile['id'], profile['payload'], 'TEST-ONLY')
        core.db.execute("DELETE FROM objects WHERE kind='model_profile' AND id='h3-darl' AND version=1")
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original, 'admin')
        self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()

    def test_new_creative_task_cannot_be_recorded_as_technical_retry(self):
        original = self.failed_job()
        self.revise_brief()
        core = self.core()
        task = core.compile_h3('TEST-ONLY-new-task', 'brief:A', 'h3-darl',
                               parameters=original['snapshot']['task']['parameters'])
        with self.assertRaisesRegex(DomainError, 'unchanged original'):
            core.create_job('TEST-ONLY-invalid-retry', task['id'], retry_of=original['id'])
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_changed_compiled_snapshot_is_rejected(self):
        original = self.failed_job()
        core = self.core()
        task = copy.deepcopy(original['snapshot']['task'])
        task['compiled_prompt'] += ' TEST ONLY changed input'
        core.db.execute('UPDATE compiled_tasks SET payload=? WHERE id=?', (json.dumps(task), original['task_id']))
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original)
        self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()

    def test_missing_original_version_metadata_is_rejected(self):
        original = self.failed_job()
        core = self.core()
        snapshot = copy.deepcopy(original['snapshot'])
        snapshot['task']['source_brief'].pop('version')
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.execute('UPDATE compiled_tasks SET payload=? WHERE id=?',
                        (json.dumps(snapshot['task']), original['task_id']))
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('original inputs unavailable', response.text)
        self.adapters['darl'].submit.assert_not_called()

    def test_missing_original_brief_is_rejected_without_latest_fallback(self):
        original = self.failed_job()
        self.revise_brief()
        core = self.core()
        core.db.execute("DELETE FROM objects WHERE kind='brief' AND id='brief:A' AND version=1")
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('original', response.text)
        self.adapters['darl'].submit.assert_not_called()
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM active_generation').fetchone()[0], 0)
        self.assertEqual(core.get('brief', 'brief:A')['version'], 2)

    def test_missing_original_compiled_task_is_rejected(self):
        original = self.failed_job()
        core = self.core()
        self.adapters['darl'].submit.reset_mock()
        with patch('film_core.core.Core.task', side_effect=DomainError('original task missing')):
            response = self.retry(original, 'admin')
        self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_provider_switch_on_retry_is_rejected(self):
        original = self.failed_job()
        self.adapters['darl'].submit.reset_mock()
        response = self.retry(original, provider='retired-provider')
        self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()
        self.assertEqual(self.core().db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_unavailable_original_provider_is_reported_without_fallback(self):
        original = self.failed_job()
        self.adapters['darl'].submit.reset_mock()
        with patch.dict(os.environ, {'DARL_API_KEY': ''}):
            for endpoint in ('creator', 'admin'):
                with self.subTest(endpoint=endpoint):
                    response = self.retry(original, endpoint)
                    self.assertEqual(response.status_code, 503, response.text)
                    self.assertEqual(response.json()['detail']['code'], 'PROVIDER_UNAVAILABLE')
        self.adapters['darl'].submit.assert_not_called()

    def test_creative_regenerate_uses_latest_brief_and_is_not_a_retry(self):
        original = self.failed_job()
        revised = self.revise_brief()
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            response = self.client.post('/api/projects/station-film/clips/A/generate',
                                        params={'creative_reason': 'TEST ONLY 接受新方案', 'provider': 'darl'})
        self.assertEqual(response.status_code, 200, response.text)
        regenerated = response.json()['job']
        self.assertIsNone(regenerated['snapshot']['retry_of'])
        self.assertEqual(regenerated['snapshot']['cost_estimate']['attempt_kind'], 'creative_regenerate')
        self.assertEqual(regenerated['snapshot']['task']['source_brief']['version'], revised['version'])
        self.assertNotEqual(regenerated['task_id'], original['task_id'])
        self.assertEqual(regenerated['snapshot']['task']['execution_model'], CLOUD_H3_MODEL)
        self.assertEqual(self.core().job(original['id']), original)

    def test_retry_and_creative_reason_cannot_be_combined(self):
        original = self.failed_job()
        for reason in ('TEST ONLY 新方案', ''):
            response = self.retry(original, creative_reason=reason)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.core().db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_multiple_retries_preserve_job_and_take_history(self):
        original = self.failed_job()
        self.adapters['darl'].submit.side_effect = ProviderError('NETWORK_ERROR', 'TEST ONLY', transient=True)
        failed_retry = self.retry(original)
        self.assertEqual(failed_retry.status_code, 503, failed_retry.text)
        core = self.core()
        middle = core.job(failed_retry.json()['detail']['job_id'])
        self.adapters['darl'].submit.side_effect = None
        response = self.retry(middle, 'admin')
        self.assertEqual(response.status_code, 200, response.text)
        newest = response.json()['job']
        self.assertEqual(newest['snapshot']['retry_of'], middle['id'])
        self.assertEqual(middle['snapshot']['retry_of'], original['id'])
        for job in (original, middle, newest):
            self.assertEqual(job['snapshot']['task'], original['snapshot']['task'])
        core.job_event(newest['id'], 'succeeded')
        core.record_take('TEST-ONLY-retry-take', newest['id'], 'test-only://retry-take', test_only=True)
        self.assertEqual(core.take('TEST-ONLY-retry-take')['job_id'], newest['id'])
        self.assertEqual(core.job(original['id']), original)
        self.assertEqual(core.job(middle['id']), middle)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 3)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM takes').fetchone()[0], 1)

    def test_retry_limit_still_applies(self):
        original = self.failed_job()
        self.adapters['darl'].submit.side_effect = ProviderError('NETWORK_ERROR', 'TEST ONLY', transient=True)
        for endpoint in ('creator', 'admin'):
            response = self.retry(original, endpoint)
            self.assertEqual(response.status_code, 503, response.text)
            original = self.core().job(response.json()['detail']['job_id'])
        response = self.retry(original)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.core().db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 3)

    def test_legacy_darl_job_without_provider_fields_remains_retryable(self):
        original = self.failed_job()
        core = self.core()
        snapshot = copy.deepcopy(original['snapshot'])
        snapshot['cost_estimate'].pop('provider')
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.execute("UPDATE job_events SET metadata=? WHERE job_id=? AND status='failed'",
                        ('{"error_category":"NETWORK_ERROR"}', original['id']))
        core.db.commit()
        response = self.retry(original, 'admin')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['metadata']['provider'], 'darl')

    def test_cloud_profile_recovers_provider_when_legacy_fields_are_missing(self):
        original = self.failed_job(CLOUD_H3_MODEL)
        core = self.core()
        snapshot = copy.deepcopy(original['snapshot'])
        snapshot['cost_estimate'].pop('provider')
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.execute("UPDATE job_events SET metadata=? WHERE job_id=? AND status='failed'",
                        ('{"error_category":"NETWORK_ERROR"}', original['id']))
        core.db.commit()
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            response = self.retry(original, 'admin')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['metadata']['provider'], 'darl')
        self.assertEqual(response.json()['job']['snapshot']['task']['execution_model'], CLOUD_H3_MODEL)

    def test_conflicting_provider_provenance_is_rejected(self):
        original = self.failed_job(CLOUD_H3_MODEL)
        core = self.core()
        snapshot = copy.deepcopy(original['snapshot'])
        snapshot['cost_estimate']['provider'] = 'retired-provider'
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.commit()
        self.adapters['darl'].submit.reset_mock()
        for endpoint in ('creator', 'admin'):
            response = self.retry(original, endpoint)
            self.assertEqual(response.status_code, 400, response.text)
        self.adapters['darl'].submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
