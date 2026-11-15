"""Advanced course contracts, real CPU executions, and offline API boundary tests."""
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'src/astock/course_content'
EXAMPLES = CONTENT / 'examples'


def load_adapter():
    spec = importlib.util.spec_from_file_location('advanced_course_model_adapter', EXAMPLES / 'q67-api.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_advanced_publication_contract():
    entries = json.loads((CONTENT / 'catalogue-advanced.json').read_text(encoding='utf-8'))
    assert [entry['id'] for entry in entries] == [f'q{n}' for n in range(49, 73)]
    for entry in entries:
        text = (CONTENT / entry['body']).read_text(encoding='utf-8')
        assert len(re.findall(r'[\u4e00-\u9fff]', re.sub(r'```.*?```', '', text, flags=re.S))) >= 2000
        assert '## 练习\n' in text and '## 参考答案\n' in text
        visible_questions = text.split('## 练习\n', 1)[1].split('## 参考答案\n', 1)[0]
        assert len(re.findall(r'^\d+\.', visible_questions, re.M)) >= 3
        assert entry['status'] == 'published'
        assert all(entry['check'][key] for key in ('question', 'answers', 'explanation'))
        for example in entry['examples']:
            assert example['environment'] == 'notebook'
            assert '{{code:' + example['id'] + '}}' in text
            assert (CONTENT / example['file']).is_file()


def test_model_adapter_default_never_opens_network(monkeypatch):
    module = load_adapter()
    monkeypatch.delenv('ASTOCK_LLM_ONLINE', raising=False)
    monkeypatch.setenv('ASTOCK_LLM_BASE_URL', 'https://invalid.example/v1')
    monkeypatch.setenv('ASTOCK_LLM_MODEL', 'configured-but-not-enabled')
    monkeypatch.setenv('ASTOCK_LLM_API_KEY', 'fake-unit-test-key')
    monkeypatch.setattr(module, 'build_opener', lambda *_: pytest.fail('default must not create client'))
    assert module.configured_client() is None
    monkeypatch.setenv('ASTOCK_LLM_ONLINE', '0')
    assert module.configured_client() is None


@pytest.mark.parametrize('url', [
    'http://remote.example/v1', 'file:///tmp/private', 'https://user:secret@example.com/v1',
    'https://example.com/v1?key=secret', 'https://example.com/v1#fragment',
])
def test_model_adapter_rejects_unsafe_or_ambiguous_address(url):
    with pytest.raises(ValueError):
        load_adapter().ModelClient(url, 'fake-model')


def test_model_adapter_request_and_call_budget_without_network():
    module = load_adapter()
    client = module.ModelClient('http://127.0.0.1:8000/v1', 'local-test', 'test-key', max_calls=99, timeout=99)
    observed = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, limit):
            assert limit == 128 * 1024 + 1
            return json.dumps({'choices': [{'message': {'content': 'unit test response'}}]}).encode()

    class Opener:
        def open(self, request, timeout):
            observed.append((request, timeout))
            return Response()

    client.opener = Opener()
    for _ in range(3):
        assert client.ask('人工样本') == 'unit test response'
    with pytest.raises(RuntimeError, match='次数上限'):
        client.ask('no fourth request')
    assert len(observed) == client.calls == 3
    request, timeout = observed[0]
    assert request.full_url == 'http://127.0.0.1:8000/v1/chat/completions'
    assert request.get_header('Authorization') == 'Bearer test-key'
    assert timeout == 20
    body = json.loads(request.data)
    assert body['messages'][0]['content'] == '人工样本'
    assert body['max_tokens'] == 600


@pytest.mark.parametrize('error', [
    URLError('sensitive service diagnostic'),
    HTTPError('https://private.example', 401, 'secret rejected', {}, None),
])
def test_model_adapter_failure_is_bounded_and_sanitized(error):
    client = load_adapter().ModelClient('https://example.com/v1', 'unit-test')

    class FailingOpener:
        def open(self, *_args, **_kwargs):
            raise error

    client.opener = FailingOpener()
    with pytest.raises(RuntimeError) as captured:
        client.ask('test')
    assert client.calls == 1
    assert 'secret' not in str(captured.value) and 'private.example' not in str(captured.value)
    assert '不自动重试' in str(captured.value)


@pytest.mark.parametrize('raw', [
    b'x' * (128 * 1024 + 1),
    b'not-json',
    json.dumps({'choices': [{'message': {'content': 123}}]}).encode(),
    json.dumps({'choices': [{'message': {'content': 'x' * 20001}}]}).encode(),
])
def test_model_adapter_rejects_bad_response_without_retry(raw):
    client = load_adapter().ModelClient('https://example.com/v1', 'unit-test')

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, limit):
            return raw[:limit]

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    client.opener = Opener()
    with pytest.raises(ValueError):
        client.ask('test')
    assert client.calls == 1


def test_ai_evaluator_returns_only_requested_interval(monkeypatch):
    monkeypatch.setenv('ASTOCK_LLM_ONLINE', '0')
    module = runpy.run_path(str(EXAMPLES / 'q71.py'))
    evaluate = module['evaluation_agent']
    card = {'operator': 'momentum', 'lookback': 5}
    before = evaluate(card, slice(100, 170))
    assert list(before.index) == list(range(100, 170))
    evaluate.__globals__['future'].iloc[180:] = np.nan
    after = evaluate(card, slice(100, 170))
    pd.testing.assert_series_equal(before, after)
    assert after.notna().all()


def test_hypothesis_and_expression_semantics():
    hypothesis = runpy.run_path(str(EXAMPLES / 'q68.py'))
    cls, validate = hypothesis['Hypothesis'], hypothesis['validate']
    for window in [True, '5', 0, 31, 5.0]:
        with pytest.raises(ValueError):
            validate(cls('invalid', 'momentum', window, 'after_completed_bar', 1, 'bad'))
    with pytest.raises(ValueError):
        validate(cls('invalid', 'momentum', 5, 'after_completed_bar', True, 'bad'))
    with pytest.raises(TypeError):
        cls(name='bad', operator='momentum', lookback=5, decision='after_completed_bar',
            target_horizon=1, candidate_id='x', unknown=True)
    evaluate = runpy.run_path(str(EXAMPLES / 'q69.py'))['evaluate']
    prices = pd.Series([100., 101., 102., 103., 90., 92.], index=pd.date_range('2026-01-01', periods=6))
    momentum = evaluate('momentum(close, 3)', prices)
    assert momentum.index.equals(prices.index)
    assert momentum.iloc[:3].isna().all()
    assert np.isclose(momentum.iloc[3], .03)
    pd.testing.assert_series_equal(evaluate('reversal(close, 3)', prices), -momentum)
    for text in ['momentum(close, window=3)', 'momentum(close, int(3))', 'momentum(close, 3.0)',
                 'momentum(close, True)', 'close.shift(-1)', 'unknown(close, 3)']:
        with pytest.raises((ValueError, SyntaxError)):
            evaluate(text, prices)


def notebook_python():
    configured = os.environ.get('ASTOCK_NOTEBOOK_QA_PYTHON')
    candidate = Path(configured) if configured else ROOT / 'output/notebook-qa-env/Scripts/python.exe'
    if candidate.is_file():
        return str(candidate)
    # Notebook dependencies intentionally remain outside the application runtime.
    if importlib.util.find_spec('torch') and importlib.util.find_spec('sklearn'):
        return sys.executable
    pytest.skip('CPU notebook environment required; install the locked notebook_environment and set ASTOCK_NOTEBOOK_QA_PYTHON')


@pytest.mark.parametrize('name', [f'q{n}' for n in range(49, 73)] + ['q67-api'])
def test_advanced_example_runs_with_assertions_on_cpu(name, tmp_path):
    environment = dict(os.environ, PYTHONUTF8='1', MPLBACKEND='Agg', ASTOCK_LLM_ONLINE='0',
                       CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    result = subprocess.run([notebook_python(), str(EXAMPLES / f'{name}.py')], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
    if name == 'q71':
        report = json.loads(result.stdout)
        assert report['mode'] == 'offline-authored' and report['real_model_calls'] == 0
        assert len(report['trace']) == 3
        assert all('holdout' not in row for row in report['trace'])
    if name == 'q72':
        report = json.loads((tmp_path / 'graduation_report.json').read_text(encoding='utf-8'))
        assert report['data_kind'] == 'synthetic' and len(report['data_sha256']) == 64
        assert report['frozen_model'] == min(report['candidate_validation_mse'], key=report['candidate_validation_mse'].get)
        assert report['dependency_versions']['scikit-learn']
        assert report['max_drawdown'] <= 0 and report['limitations']
