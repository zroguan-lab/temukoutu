# 命令行与开发验证

以下命令均在项目根目录执行。普通使用请看 [README](../README.md)。

## 命令行与开发

```bash
.venv/bin/python -m extractor_core.cli extract --input input.jpg --output output.png --method grabcut
# 自定义蒙版，尺寸需与工作图一致：
.venv/bin/python -m extractor_core.cli extract --input input.jpg --output output.png --mask mask.png --method manual --padding 12
```

```python
from extractor_core import extract
result = extract("input.jpg", "output.png", method="auto", options={"padding": 12})
```

CLI 与网页共用本地 `MaskProvider`，`auto` 仍是 GrabCut。CLI 输出 PNG、工作尺寸的 `.mask.png` 和 `.json`，不调用云端；输入不会被覆盖。更多参数见[API 文档](API.md)与[架构说明](ARCHITECTURE.md)。

```bash
.venv/bin/python -m pytest -q
npm run build --prefix frontend
.venv/bin/python -m tests.synthetic
# 先启动服务，浏览器测试使用独立 Chrome，无需登录账号
npm run test:e2e --prefix frontend
```

Windows 用 `.\.venv\Scripts\python.exe` 替换 Python 路径，可额外运行 `scripts/native_smoke.py` 检查原生启停。开发前端可运行 `npm run dev --prefix frontend`，Vite 在 127.0.0.1:5173 代理后端。服务仅支持单个 worker。

本轮验证记录见[测试与审查报告](VALIDATION_2026-10-15.md)。历史 Windows 验证见[原测试报告](TEST_REPORT.md)，后续工作见[开发计划](NEXT_STEPS.md)。

Python 测试统一在导入应用前关闭真实云端，并逐例使用临时 AI 配置；真实 HTTP transport 被测试守卫拒绝，只允许 Mock/ASGI transport。运行 pytest 不会借用开发者已保存的 Key，也不会发出模型调用。浏览器测试需要单独以 `PRINT_EXTRACTOR_CONFIG_PATH` 指向临时绝对路径后启动服务；不要使用真实用户配置或真实 Key 运行配置写入/清除场景。
