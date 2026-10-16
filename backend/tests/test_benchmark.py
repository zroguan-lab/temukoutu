"""Budget runner uses only fake adapters here; no paid model calls."""
import json

import pytest
from PIL import Image

from scripts import benchmark_qwen
from backend.providers.qwen import ProviderError
from tests.synthetic import sample


def inputs(tmp_path):
    image, _ = sample()
    first, second = tmp_path / "one.png", tmp_path / "two.png"
    image.save(first); image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(second)
    return ["--input", str(first), "--input", str(second), "--output", str(tmp_path / "results")]


def test_plan_does_not_read_credentials_or_start_adapter(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs): raise AssertionError("dry runs never create a network adapter")
    monkeypatch.setattr(benchmark_qwen.QwenImageProvider, "__init__", forbidden)
    monkeypatch.delenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", raising=False)
    assert benchmark_qwen.main(inputs(tmp_path)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["outputs"] == 4 and plan["estimated_cost_cny"] == 0.70
    assert not (tmp_path / "results").exists()
    with pytest.raises(SystemExit): benchmark_qwen.main(inputs(tmp_path) + ["--max-estimated-cost", "0.69"])


def test_execution_is_saved_once_and_reruns_do_not_pay_again(tmp_path, monkeypatch):
    calls = []
    def edit(self, image, model):
        calls.append(model)
        return image
    monkeypatch.setattr(benchmark_qwen.QwenImageProvider, "edit", edit)
    monkeypatch.setenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "test-only-key")
    args = inputs(tmp_path) + ["--execute"]
    assert benchmark_qwen.main(args) == 0 and len(calls) == 4
    assert benchmark_qwen.main(args) == 0 and len(calls) == 4
    assert len(list((tmp_path / "results").glob("*.json"))) == 4


def test_failure_stops_round_and_uncertain_billing_is_not_replayed(tmp_path, monkeypatch):
    calls = []
    def edit(self, image, model):
        calls.append(model)
        raise ProviderError("模拟超时")
    monkeypatch.setattr(benchmark_qwen.QwenImageProvider, "edit", edit)
    monkeypatch.setenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "test-only-key")
    args = inputs(tmp_path) + ["--execute"]
    assert benchmark_qwen.main(args) == 1 and len(calls) == 1
    assert benchmark_qwen.main(args) == 1
    assert len(calls) == 1


def test_parallel_run_lock_prevents_duplicate_submissions(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "test-only-key")
    args = inputs(tmp_path) + ["--execute"]
    output = tmp_path / "results"; output.mkdir()
    with benchmark_qwen.exclusive_run(output):
        assert benchmark_qwen.main(args) == 1
    assert not (output / ".run.lock").exists()
