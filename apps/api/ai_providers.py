"""OpenAI-compatible Darl LLM/image adapters. Credentials stay on the server."""
from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIProviderError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class _DarlJson:
    def __init__(self, key: str | None = None, base_url: str | None = None, opener=urlopen):
        self.key = key or os.getenv('DARL_API_KEY')
        self.base_url = (base_url or os.getenv('DARL_BASE_URL') or 'https://api.darl.cn').rstrip('/')
        self.opener = opener
        if not self.key:
            raise AIProviderError('NOT_CONFIGURED', 'AI 服务尚未配置。')

    def request(self, path: str, payload: dict) -> dict:
        request = Request(self.base_url + path, data=json.dumps(payload, ensure_ascii=False).encode(),
                          headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'},
                          method='POST')
        try:
            with self.opener(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            category = 'AUTH' if exc.code in (401, 403) else 'RATE_LIMIT' if exc.code == 429 else 'PROVIDER_ERROR'
            raise AIProviderError(category, f'AI 服务暂时无法完成请求（HTTP {exc.code}）。') from None
        except (URLError, TimeoutError, ValueError) as exc:
            raise AIProviderError('NETWORK', 'AI 服务暂时无法连接或返回内容无效。') from exc


class DarlLLMAdapter:
    model = 'deepseek-v4.1-flash'
    provider = 'darl'

    def __init__(self, **kwargs):
        self.client = _DarlJson(**kwargs)

    def propose(self, system: str, context: dict) -> dict:
        result = self.client.request('/v1/chat/completions', {
            'model': self.model, 'temperature': 0.4, 'stream': False,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]})
        try:
            content = result['choices'][0]['message']['content']
            if isinstance(content, list):
                content = ''.join(part.get('text', '') for part in content)
            content = content.strip()
            if content.startswith('```'):
                content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            proposal = json.loads(content)
            if not isinstance(proposal, dict):
                raise ValueError('not an object')
            return proposal
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError('MALFORMED_OUTPUT', 'AI 提案格式无效，未修改项目。') from exc


class DarlImageAdapter:
    model = 'gpt-image-2'
    provider = 'darl'

    def __init__(self, **kwargs):
        self.client = _DarlJson(**kwargs)

    def generate(self, prompt: str) -> tuple[bytes, str, dict]:
        result = self.client.request('/v1/images/generations', {
            'model': self.model, 'prompt': prompt, 'size': '1024x1024',
            'quality': 'medium', 'n': 1, 'output_format': 'png'})
        try:
            data = base64.b64decode(result['data'][0]['b64_json'], validate=True)
            if len(data) > 20 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('invalid PNG')
            return data, 'image/png', {'revised_prompt': result['data'][0].get('revised_prompt', '')}
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError('MALFORMED_IMAGE', '图片服务没有返回有效图片，未创建候选。') from exc
