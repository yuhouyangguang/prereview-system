"""Z.AI / 智谱 GLM 调用封装（OpenAI 兼容 HTTP，无 SDK 路由限制）。

设计要点：
- API Key 从 ZAI_API_KEY 读取，Base URL 从 ZAI_BASE_URL 读取，模型从 ZAI_MODEL 读取。
- 直接 POST /chat/completions（OpenAI 兼容），绕过 SDK 内部路由，兼容所有代理端点。
- 未配置 Key、调用失败时 is_enabled()/analyze_json() 返回 None，调用方回退规则引擎。
- 统一负责 JSON 结构化输出的请求与解析，屏蔽模型偶发的 markdown 包裹 / 多余文本。
"""

import json
import logging
import os
import re

import requests as _requests

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get('ZAI_MODEL', 'glm-4.5-air')
DEFAULT_BASE_URL = os.environ.get(
    'ZAI_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4'
).rstrip('/')

_SESSION = _requests.Session()
_SESSION.headers.update({'Content-Type': 'application/json'})


def is_enabled() -> bool:
    return bool(os.environ.get('ZAI_API_KEY'))


def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


def analyze_json(system_prompt: str, user_prompt: str,
                 model: str | None = None, temperature: float = 0.2):
    """调用 Z.AI 并返回解析后的 dict；失败返回 None（由调用方回退规则引擎）。"""
    api_key = os.environ.get('ZAI_API_KEY', '')
    if not api_key:
        return None

    base_url = os.environ.get('ZAI_BASE_URL', DEFAULT_BASE_URL).rstrip('/')
    url = f'{base_url}/chat/completions'
    model = model or os.environ.get('ZAI_MODEL', DEFAULT_MODEL)

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': temperature,
    }
    try:
        resp = _SESSION.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        return _extract_json(content)
    except Exception as e:
        log.warning('Z.AI 调用失败（%s %s）: %s', model, url, e)
        return None
