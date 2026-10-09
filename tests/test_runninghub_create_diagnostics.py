"""RunningHub create diagnostics with TEST ONLY HTTP and disposable databases."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.runninghub_h3 import RunningHubH3Adapter
from film_core import Core
from film_core.darl_h3 import ProviderError
from film_core.fixture import seed


TEST_KEY = 'TEST-ONLY-CREATE-CREDENTIAL'


class Response:
    def __init__(self, body, status=200):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return None

    def read(self):
        return self.body


class CreateHTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=60):
        if not request.full_url.endswith('/task/openapi/ai-app/run'):
            raise AssertionError('Unexpected TEST ONLY HTTP operation')
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def create_task():
    return {'target_model': 'MiniMax-H3', 'task_mode': 'MULTI_SHOT_ONE_PASS',
            'duration': 10, 'aspect_ratio': '16:9', 'compiled_prompt': 'TEST ONLY 旧信镜头',
            'parameters': {'resolution': '480P', 'num_inference_steps': 20,
                           'turbo': False, 'watermark': False}, 'media_bindings': []}


def adapter(http):
    return RunningHubH3Adapter(key=TEST_KEY, webapp_id='12345', opener=http)


def http_error(status, body):
    return HTTPError('https://www.runninghub.cn/task/openapi/ai-app/run', status,
                     'TEST ONLY HTTP failure', {}, io.BytesIO(json.dumps(body).encode()))


class CreateDiagnosticsTests(unittest.TestCase):
    def test_documented_success_uses_data_task_id(self):
        for task_id in ('123456789', 123456789):
            with self.subTest(task_id=task_id):
                http = CreateHTTP(Response({'code': 0, 'data': {'taskId': task_id, 'taskStatus': 'QUEUED'}}))
                result = adapter(http).submit(create_task(), 'TEST-ONLY-job')
                self.assertEqual(result, {'id': str(task_id), 'status': 'queued'})
                self.assertEqual(len(http.requests), 1)

    def test_nonzero_code_preserves_provider_failure_and_message(self):
        response = {'code': 1007, 'msg': 'TEST ONLY workflow rejected',
                    'data': {'reason': 'TEST ONLY invalid node'}, 'requestId': 'TEST-ONLY-request'}
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(Response(response))).submit(create_task(), 'TEST-ONLY-job')
        error = caught.exception
        self.assertEqual(error.code, 'RUNNINGHUB_CREATE_FAILED')
        self.assertEqual(error.http_status, 200)
        self.assertFalse(error.transient)
        self.assertEqual(str(error), response['msg'])
        self.assertEqual(error.detail, {'provider': 'runninghub', 'operation': 'create',
                                       'provider_code': 1007, 'provider_message': response['msg'],
                                       'http_status': 200, 'response_metadata': response})

    def test_message_field_is_retained_without_inventing_another_schema(self):
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(Response({'code': 1008, 'message': 'TEST ONLY insufficient balance'}))).submit(
                create_task(), 'TEST-ONLY-job')
        self.assertEqual(caught.exception.detail['provider_message'], 'TEST ONLY insufficient balance')

    def test_http_status_is_optional_and_getcode_is_supported(self):
        for expected_status in (None, 202):
            response = Response({'code': 1007, 'msg': 'TEST ONLY rejected'}, status=None)
            if expected_status is not None:
                response.getcode = lambda: expected_status
            with self.subTest(status=expected_status), self.assertRaises(ProviderError) as caught:
                adapter(CreateHTTP(response)).submit(create_task(), 'TEST-ONLY-job')
            self.assertEqual(caught.exception.http_status, expected_status)
            self.assertEqual(caught.exception.detail['http_status'], expected_status)

    def test_nonzero_code_with_task_id_is_still_provider_failure(self):
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(Response({'code': 1007, 'msg': 'TEST ONLY rejected',
                                         'data': {'taskId': '123456789'}}))).submit(create_task(), 'TEST-ONLY-job')
        self.assertEqual(caught.exception.code, 'RUNNINGHUB_CREATE_FAILED')

    def test_zero_code_missing_or_invalid_task_id_is_invalid_create_response(self):
        for data in (None, {}, [], '123456789', {'taskId': ''}, {'taskId': 'invalid'},
                     {'taskId': 0}, {'taskId': '-1'}, {'taskId': 1.5}, {'taskId': True},
                     {'taskId': '１２３'}):
            with self.subTest(data=data), self.assertRaises(ProviderError) as caught:
                adapter(CreateHTTP(Response({'code': 0, 'msg': 'success', 'data': data}))).submit(
                    create_task(), 'TEST-ONLY-job')
            self.assertEqual(caught.exception.code, 'INVALID_CREATE_RESPONSE')
            self.assertEqual(caught.exception.detail['provider_code'], 0)
            self.assertEqual(caught.exception.http_status, 200)

    def test_alternative_task_id_locations_are_not_guessed(self):
        for response in ({'code': 0, 'taskId': '123456789'},
                         {'code': 0, 'data': {'id': '123456789'}},
                         {'code': 0, 'result': {'taskId': '123456789'}}):
            with self.subTest(response=response), self.assertRaises(ProviderError) as caught:
                adapter(CreateHTTP(Response(response))).submit(create_task(), 'TEST-ONLY-job')
            self.assertEqual(caught.exception.code, 'INVALID_CREATE_RESPONSE')

    def test_malformed_json_or_non_object_is_invalid_provider_response_without_raw_body(self):
        for body in (b'not-json ' + TEST_KEY.encode(), b'\xff', [], None):
            with self.subTest(body_type=type(body).__name__), self.assertRaises(ProviderError) as caught:
                adapter(CreateHTTP(Response(body))).submit(create_task(), 'TEST-ONLY-job')
            self.assertEqual(caught.exception.code, 'INVALID_PROVIDER_RESPONSE')
            self.assertEqual(caught.exception.http_status, 200)
            self.assertEqual(caught.exception.detail['operation'], 'create')
            self.assertNotIn(TEST_KEY, json.dumps(caught.exception.as_dict()))

    def test_http_error_keeps_provider_metadata_and_transport_status(self):
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(http_error(400, {'code': 1007, 'msg': 'TEST ONLY rejected',
                                                'apiKey': TEST_KEY}))).submit(create_task(), 'TEST-ONLY-job')
        self.assertEqual(caught.exception.code, 'HTTP_400')
        self.assertEqual(caught.exception.http_status, 400)
        self.assertEqual(caught.exception.detail['provider_code'], 1007)
        self.assertEqual(caught.exception.detail['response_metadata']['apiKey'], '[REDACTED]')
        self.assertNotIn(TEST_KEY, json.dumps(caught.exception.as_dict()))

    def test_recursive_credentials_and_echoed_values_are_redacted(self):
        other_secret = 'TEST-ONLY-OTHER-CREDENTIAL'
        response = {'code': 1007, 'msg': 'TEST ONLY ' + TEST_KEY + ' ' + other_secret,
                    'data': {'API_KEY': TEST_KEY, 'RUNNINGHUB_API_KEY': TEST_KEY,
                             'headers': {'Authorization': 'Bearer ' + other_secret},
                             'credentials': [{'password': other_secret}],
                             'safeEcho': [other_secret, TEST_KEY],
                             'url': 'https://provider.example/?apiKey=' + TEST_KEY}}
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(Response(response))).submit(create_task(), 'TEST-ONLY-job')
        encoded = json.dumps(caught.exception.as_dict())
        for secret in (TEST_KEY, other_secret):
            self.assertNotIn(secret, encoded)
        safe = caught.exception.detail['response_metadata']['data']
        self.assertEqual(safe['API_KEY'], '[REDACTED]')
        self.assertEqual(safe['RUNNINGHUB_API_KEY'], '[REDACTED]')
        self.assertEqual(safe['headers']['Authorization'], '[REDACTED]')
        self.assertEqual(safe['credentials'], '[REDACTED]')
        self.assertIn('TEST ONLY', caught.exception.detail['provider_message'])

    def test_credential_patterns_in_messages_and_encoded_known_key_are_redacted(self):
        key = 'TEST-ONLY-CREDENTIAL/with+encoding='
        response = {'code': 1007, 'message': 'TEST ONLY api_key=TEST-ONLY-UNKNOWN '
                    'Bearer TEST-ONLY-BEARER https://user:TEST-ONLY-password@provider.example '
                    + quote(key, safe='')}
        with self.assertRaises(ProviderError) as caught:
            RunningHubH3Adapter(key=key, webapp_id='12345', opener=CreateHTTP(Response(response))).submit(
                create_task(), 'TEST-ONLY-job')
        encoded = json.dumps(caught.exception.as_dict())
        for secret in (key, quote(key, safe=''), 'TEST-ONLY-UNKNOWN', 'TEST-ONLY-BEARER', 'TEST-ONLY-password'):
            self.assertNotIn(secret, encoded)

    def test_authentication_fields_and_numeric_token_echoes_are_redacted(self):
        number = 1234567890123456
        response = {'code': 1007, 'msg': 'TEST ONLY rejected',
                    'data': {'authentication': 'TEST-ONLY-AUTH', 'access_token': number,
                             'echo': 'TEST-ONLY-AUTH ' + str(number)}}
        with self.assertRaises(ProviderError) as caught:
            adapter(CreateHTTP(Response(response))).submit(create_task(), 'TEST-ONLY-job')
        encoded = json.dumps(caught.exception.as_dict())
        self.assertNotIn('TEST-ONLY-AUTH', encoded)
        self.assertNotIn(str(number), encoded)


class PersistedCreateDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'studio.sqlite'
        self.media = Path(self.tmp.name) / 'media'
        seed(Core(str(self.path), test_mode=True), production=True).close()
        self.client = TestClient(create_app(self.path, self.media, test_mode=True, start_worker=False))
        self.addCleanup(self.client.close)
        environment = patch.dict(os.environ, {'RUNNINGHUB_API_KEY': TEST_KEY,
                                               'RUNNINGHUB_WEBAPP_ID': '12345', 'H3_SERVER_ON': '0'})
        environment.start()
        self.addCleanup(environment.stop)

    def core(self):
        core = Core(str(self.path), test_mode=True)
        self.addCleanup(core.close)
        return core

    def test_provider_failure_is_persisted_recursively_redacted_without_take(self):
        other_secret = 'TEST-ONLY-PERSISTED-CREDENTIAL'
        body = {'code': 1007, 'msg': 'TEST ONLY rejected ' + TEST_KEY + ' ' + other_secret,
                'data': {'RUNNINGHUB_API_KEY': TEST_KEY, 'Authorization': 'Bearer ' + other_secret,
                         'items': [{'client_secret': other_secret, 'echo': TEST_KEY}]}}
        http = CreateHTTP(Response(body))
        with patch('apps.api.main.RunningHubH3Adapter', return_value=adapter(http)), \
                patch('apps.api.main.DarlH3Adapter') as darl, self.assertLogs('film_studio.api', level='INFO') as logs:
            response = self.client.post('/api/projects/station-film/clips/A/generate?provider=runninghub')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail']['code'], 'RUNNINGHUB_CREATE_FAILED')
        job_id = response.json()['detail']['job_id']
        core = self.core()
        job = core.job(job_id)
        persisted = job['metadata']['provider_error']
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['metadata']['provider'], 'runninghub')
        self.assertEqual(persisted['detail']['provider_code'], 1007)
        self.assertEqual(persisted['detail']['operation'], 'create')
        self.assertEqual(persisted['http_status'], 200)
        detail = self.client.get('/api/projects/station-film/jobs/' + job_id).json()
        admin = self.client.get('/api/admin/jobs?status=failed')
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()[0]['id'], job_id)
        encoded = json.dumps(job) + json.dumps(detail) + admin.text + '\n'.join(logs.output)
        for secret in (TEST_KEY, other_secret):
            self.assertNotIn(secret, encoded)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM takes').fetchone()[0], 0)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM active_generation').fetchone()[0], 0)
        self.assertEqual(len(http.requests), 1)
        darl.assert_not_called()

    def test_transient_http_retry_preserves_original_provider_and_compiled_task(self):
        http = CreateHTTP(http_error(429, {'code': 1007, 'msg': 'TEST ONLY throttled', 'apiKey': TEST_KEY}),
                          Response({'code': 0, 'data': {'taskId': '123456789', 'taskStatus': 'QUEUED'}}))
        with patch('apps.api.main.RunningHubH3Adapter', return_value=adapter(http)), \
                patch('apps.api.main.DarlH3Adapter') as darl:
            failed = self.client.post('/api/projects/station-film/clips/A/generate?provider=runninghub')
            self.assertEqual(failed.status_code, 503)
            job_id = failed.json()['detail']['job_id']
            original = self.core().job(job_id)
            switched = self.client.post('/api/projects/station-film/clips/A/generate',
                                        params={'retry_of': job_id, 'provider': 'darl'})
            self.assertEqual(switched.status_code, 400)
            self.assertEqual(len(http.requests), 1)
            response = self.client.post('/api/admin/jobs/' + job_id + '/technical-retry',
                                        json={'request_id': 'TEST-ONLY-diagnostic-retry'})
        self.assertEqual(response.status_code, 200, response.text)
        retried = response.json()['job']
        self.assertEqual(retried['metadata']['provider'], 'runninghub')
        self.assertEqual(retried['task_id'], original['task_id'])
        self.assertEqual(retried['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(retried['snapshot']['retry_of'], job_id)
        self.assertEqual(retried['snapshot']['cost_estimate']['attempt_kind'], 'technical_retry')
        self.assertEqual(self.core().job(job_id), original)
        self.assertEqual(len(http.requests), 2)
        darl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
