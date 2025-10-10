import random
import time
from typing import List, Optional, Dict, Any
import requests

from utils.utils import logger


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible client (chat.completions).

    Works with providers that expose OpenAI API schema (e.g., OpenAI/DeepSeek/others).
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = 20, max_retries: int = 3):
        self.base_url = base_url.rstrip('/') or 'https://api.openai.com'
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def chat_completion(
            self,
            model: str,
            messages: List[Dict[str, str]],
            temperature: float = 1.5,
            max_tokens: Optional[int] = None,
            extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        # url = f"{self.base_url}/v1/chat/completions"
        url = f"{self.base_url}/chat/completions"
        logger.info("请求的URL为:", url)
        # url = f"{self.base_url}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        if extra_headers:
            headers.update(extra_headers)
        payload = {
            'model': model,
            'messages': messages,
            'temperature': random.uniform(0.7, temperature),
            'top_p': 0.9,
            'frequency_penalty': 0.5 # 介于 -2.0 和 2.0 之间的数字。如果该值为正，那么新 token 会根据其在已有文本中的出现频率受到相应的惩罚，降低模型重复相同内容的可能性。
        }

        if max_tokens is not None:
            payload['max_tokens'] = max_tokens

        attempt = 0
        last_exc = None
        while attempt < self.max_retries:
            attempt += 1
            start = time.time()
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                latency_ms = int((time.time() - start) * 1000)
                # Retry only on 5xx
                if 500 <= resp.status_code < 600:
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise

        # normalized output
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = data.get('usage', {})
        return {
            'raw': data,
            'content': content,
            'latency_ms': latency_ms,
            'tokens': {
                'prompt': usage.get('prompt_tokens'),
                'completion': usage.get('completion_tokens'),
                'total': usage.get('total_tokens'),
            }
        }
