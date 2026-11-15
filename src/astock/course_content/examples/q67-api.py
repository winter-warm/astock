"""可选真实聊天接口。默认仅离线演练，不会访问网络。"""
import json
import os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class ModelClient:
    def __init__(self, base_url, model, key="", max_calls=3, timeout=20):
        parsed = urlsplit(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("接口地址不得包含凭据、查询串或片段")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ValueError("远程接口必须HTTPS；HTTP仅允许本机")
        if not parsed.hostname or not model:
            raise ValueError("需要接口地址和模型名称")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.key = model, key
        self.max_calls = min(max(int(max_calls), 1), 3)
        self.timeout = min(max(float(timeout), 1), 20)
        self.calls = 0
        self.opener = build_opener(NoRedirect())

    def ask(self, prompt):
        if self.calls >= self.max_calls:
            raise RuntimeError("已达到本次调用次数上限")
        self.calls += 1
        payload = json.dumps({"model": self.model,
                              "messages": [{"role": "user", "content": prompt}],
                              "temperature": 0, "max_tokens": 600}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(128*1024+1)
            if len(raw) > 128*1024:
                raise ValueError("响应超过128 KiB")
            answer = json.loads(raw)["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or len(answer) > 20000:
                raise ValueError("响应正文格式或长度无效")
            return answer
        except HTTPError as error:
            raise RuntimeError(f"模型接口HTTP错误 {error.code}，不自动重试") from None
        except URLError:
            raise RuntimeError("模型接口连接失败，不自动重试") from None

def configured_client():
    if os.environ.get("ASTOCK_LLM_ONLINE") != "1":
        return None
    base = os.environ.get("ASTOCK_LLM_BASE_URL", "")
    model = os.environ.get("ASTOCK_LLM_MODEL", "")
    if not base or not model:
        raise ValueError("真实调用需显式配置 BASE_URL 和 MODEL")
    return ModelClient(base, model, os.environ.get("ASTOCK_LLM_API_KEY", ""))

if __name__ == "__main__":
    client = configured_client()
    if client is None:
        print("离线流程演练：未调用真实模型。")
        answer = '{"hypothesis":"测试五期动量","lookback":5,"synthetic":true}'
    else:
        answer = client.ask("请仅返回JSON，提出一个使用人工价格数据的动量研究假设，字段hypothesis和lookback。禁止收益承诺。")
        print("真实模型响应（尚未验证）：")
    print(answer)

