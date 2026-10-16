"""Plan a small explicit paid comparison, or run it after account authorization.

Default is a dry run: no credentials read and no network. Reuse the same output
directory to prevent accidentally retrying a request whose billing is uncertain.
"""
import argparse
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from PIL import Image

# Allow `python scripts/benchmark_qwen.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.providers.qwen import MODELS, QwenImageProvider, ProviderError
from extractor_core.io import atomic_bytes, read_image, save_png
from backend.app.settings import read_settings, user_config_path


@contextmanager
def exclusive_run(directory):
    lock = directory / ".run.lock"
    try:
        with lock.open("x") as stream:
            stream.write("Check provider usage before removing a stale lock.\n")
    except FileExistsError:
        raise ProviderError("已有运行或中断的测试；请先核对进程与账单，勿并发重复提交") from None
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/qwen-comparison"))
    parser.add_argument("--max-estimated-cost", type=float, default=1.0)
    parser.add_argument("--execute", action="store_true", help="Explicitly authorize uploads and billable requests")
    args = parser.parse_args(argv)
    plan = []
    images = {}
    for index, path in enumerate(args.input):
        data = path.read_bytes()
        image = read_image(data)
        QwenImageProvider.validate_input(image)
        digest = hashlib.sha256(data).hexdigest()
        images[digest] = image
        for model, price in MODELS.items():
            identity = hashlib.sha256((digest + model).encode()).hexdigest()[:32]
            if not any(item["id"] == identity for item in plan):
                plan.append({"id": identity, "case": index+1, "model": model,
                             "input_sha256": digest, "estimated_cost_cny": price})
    estimate = round(sum(item["estimated_cost_cny"] for item in plan), 2)
    if not 0 < args.max_estimated_cost <= 1 or estimate > args.max_estimated_cost:
        parser.error("预计费用超过本脚本 ¥1 以内的单轮预算；请缩小测试范围")
    print(json.dumps({"mode": "execute" if args.execute else "plan_only", "outputs": len(plan),
                      "estimated_cost_cny": estimate, "plan": plan}, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0
    key = os.environ.get("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "")
    workspace = os.environ.get("PRINT_EXTRACTOR_DASHSCOPE_WORKSPACE", "")
    if not key:
        saved = read_settings(user_config_path())
        key, workspace = saved.api_key, saved.workspace_id
    if not key:
        parser.error("请先在工作台配置 AI，或在当前终端设置百炼 Key；不要把密钥贴入聊天")
    adapter = QwenImageProvider(key, workspace)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        with exclusive_run(args.output):
            return execute_plan(args.output, plan, images, adapter)
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def execute_plan(output, plan, images, adapter):
    # Fail before spending anything if any previous attempt needs billing review.
    for item in plan:
        record = output / (item["id"] + ".json")
        if record.exists() and json.loads(record.read_text())["state"] != "completed":
            raise ProviderError("有失败或中断记录，请先核对账单；不会自动重新付费")
    for item in plan:
        record = output / (item["id"] + ".json")
        if record.exists():
            print(f"case {item['case']} {item['model']}: using saved result")
            continue
        item.update(state="pending", quality="unreviewed", preserves_source_rgb=False)

        def persist():
            atomic_bytes(record, json.dumps(item, ensure_ascii=False, indent=2).encode())

        persist()
        try:
            result = adapter.edit(images[item["input_sha256"]], item["model"])
            save_png(record.with_suffix(".png"), result)
            for label, color in [("white", "white"), ("black", "black")]:
                preview = Image.new("RGBA", result.size, color)
                preview.alpha_composite(result)
                save_png(record.with_name(record.stem + "-" + label + ".png"), preview)
            alpha = result.getchannel("A")
            item.update(state="completed", width=result.width, height=result.height,
                        alpha_min=alpha.getextrema()[0], alpha_max=alpha.getextrema()[1],
                        transparent_fraction=alpha.histogram()[0] / (result.width * result.height))
            persist()
            print(f"case {item['case']} {item['model']}: saved, quality unreviewed")
        except ProviderError as exc:
            item.update(state="failed", error=str(exc))
            persist()
            print("已停止；失败可能计费，请先核对用量。" + str(exc), file=sys.stderr)
            return 1
        except Exception:
            item["state"] = "failed"
            persist()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
