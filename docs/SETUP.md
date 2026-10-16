# 安装、配置与排错

以下命令均在项目根目录执行。首次使用入口见 [README](../README.md)。

## 手工安装备用

准备 64 位 Python 3.11 或 3.12，以及 Node.js 20.19+。首次安装需要联网下载依赖，默认本地流程安装后可以离线使用，不会自动下载模型。

**Windows：** 下载或克隆仓库，双击 `install.bat`，安装成功后会由项目脚本创建桌面快捷方式，之后可双击桌面的 Print Extractor AI 或项目 `start.bat`。打开 **http://127.0.0.1:7860**，停止时双击 `stop.bat`。关闭浏览器不会停止服务。


Windows 需要手工执行时，可在项目文件夹的 PowerShell 中运行（以下以 Python 3.12 为例；3.11 请改用 `requirements-lock311.txt`）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.\start.bat
```

**macOS / Linux：** 在项目根目录运行以下命令。此路径已在 macOS、Python 3.12 验证；Linux 仍待验证。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 7860
```

打开同一地址，按 `Ctrl+C` 停止。服务同时托管网页，无需另开 Vite。Python 3.11 请使用 `backend/requirements-lock311.txt`；Windows 安装脚本会按版本选择锁文件。不要把别的电脑上的虚拟环境直接复制过来。

## Windows 桌面入口

`install.bat` 完成依赖和构建后，会运行项目 `scripts/post_install.py`，再由 `scripts/create_shortcut.ps1` 在当前用户的真实桌面目录创建 Print Extractor AI.lnk。目标是项目 `start.bat`，工作目录为实际安装路径。移动项目后请重新运行安装后辅助入口。其他系统会直接跳过，不写桌面、不调用 Windows COM。

快捷方式调用的 `start.ps1` 用启动互斥锁避免同时双击产生多个服务。它先探测本应用健康标识：已运行则直接打开；未运行则使用项目虚拟环境启动单进程服务，等待就绪后打开浏览器；端口被其他程序占用则报错。没有常驻监控、开机自启或快捷方式内的 Key。关闭浏览器不会结束服务，Windows 用 `stop.bat` 停止。

本轮没有 Windows 原生环境，已做路径参数、平台分支、互斥与冲突处理的静态/模拟检查；真实 .lnk、中文路径和首次/重复打开仍待 Windows 实机验收。没有在用户当前 Mac 桌面创建入口。

## 本机千问实验配置（未验证可用）

GPT/Grok 请使用下方的官方账号登录步骤。以下仅说明保留的千问实验设置，尚未成功完成端到端出图，不列入网页可用模型。高级测试者可在“配置 AI”中展开“千问实验配置（未验证可用）”，用密码框保存实验 Key。无需在终端配置，也无需重启。下次从快捷方式启动时，后端从同一用户配置文件恢复。已有有效 Key 可以直接使用；程序不会去其他软件或项目寻找 Key。

| 系统 | 用户配置文件 |
|---|---|
| Windows | `%LOCALAPPDATA%/PrintExtractorAI/print-extractor.local.json` |
| macOS | `~/Library/Application Support/PrintExtractorAI/print-extractor.local.json` |
| Linux | `$XDG_CONFIG_HOME/PrintExtractorAI/print-extractor.local.json`，默认 `~/.config/PrintExtractorAI/` |

这是用户专属的本地文件，**没有加密**：Unix 目录 0700、文件 0600；Windows 写入前通过 ACL 限制为当前用户与系统。Key 不写入仓库、任务图像、快捷方式、日志、浏览器 localStorage 或接口响应。密码框在保存后清空；服务器只返回“是否已配置”。同一台电脑上具有本人或系统权限的软件仍可能读取该文件。

Key 仅用于所选的阿里云官方固定接口，图片只在主动生成时上传处理，不发送给项目作者。可在同处关闭云端处理（保留 Key）或清除本机 Key。默认没有 Key、云端关闭，本地提取照常可用。测试只用临时目录与假值，没有为用户写入真实 Key。

高级兼容方式仍支持 `PRINT_EXTRACTOR_CLOUD_ENABLED=1` 与 `PRINT_EXTRACTOR_DASHSCOPE_API_KEY`，但它们只作用于当前进程；显式环境开关 `0` 强制禁用，`1` 且提供项目变量 Key 时优先于文件。普通使用请用界面保存，避免快捷方式重启后丢失配置。`.env.example` 仅供参考，不自动读取 `.env`。

## 千问实验接口的限制

保留 `qwen-image-2.1-turbo/pro` 请求代码和设置 API 供继续排查，只有模拟契约测试通过。用户指定端点的真实测试返回 403，没有图片，根因未知；不列为工作台可用模型，也不建议为本项目另购额度。具体端点、型号与结果见[最新验收记录](VALIDATION_PR_2026-10-17.md)。

已有实验调用记录、原文件和继续精修 API 保留，网页模型选择只展示 GPT/Grok。预计价格不是服务端账单硬上限，失败或超时不要盲目重发。

## 遇到问题

| 现象 | 可以先做什么 |
|---|---|
| 缺少 Python 环境或前端文件 | Windows 重新运行 `install.bat`；其他系统按启动命令安装并构建 |
| 7860 被占用 | 停止占用程序，再启动；不要同时启动两份服务 |
| Windows 启动失败 | 查看 `artifacts/server.err.log`，确认使用 Python 3.11/3.12 |
| 访问被拒绝 | 使用 `http://127.0.0.1:7860`，不要换成 localhost 或局域网地址 |
| 候选全空、选到整件衣服 | 先裁切到印花，调整颜色差异，切换算法或人工修正 |
| 黑描边或细线缺失 | 用原图对照并补蒙版；同色区域可能无法自动分辨 |
| 分割超时或画笔慢 | 缩小选区；16 MP 图片仍可能较慢 |
| 云端按钮不可用 | 展开“配置 AI”检查官方 CLI 安装与账号状态；本地功能仍可使用 |
| 云端报错或超时 | 记录错误并检查服务状态与用量；失败记录不自动重发，不据此推断是 Key 问题 |
| 生成图没有透明背景 | 不透明原图会明确标记需去背景，可继续精修；不要把棋盘格图片当成透明 PNG |

本工具没有超分辨率、SVG、批处理、OCR 或商业级自动提取保证。真实照片的功能跑通、生成图有透明通道和人工认可的可用质量，需要分别验证。

已获授权的固定对比流程可以用 `scripts/benchmark_qwen.py`：先传入两次 `--input` 查看计划，再加 `--execute` 执行整轮；执行时可使用界面已保存的本机 Key。默认比较 Turbo/Pro、每图每模型 1 次，使用同一输出目录复用结果；整轮只需一次执行授权，无需逐张勾选。脚本不自动重试失败或中断的请求。

## GPT 与 Grok 官方登录

按各自官方说明安装 [Codex CLI](https://learn.chatgpt.com/docs/cli) 或 [Grok Build CLI](https://github.com/xai-org/grok-build#installing-the-released-binary)。工作台不自动安装 CLI。安装后展开 AI 提取 → 配置 AI，点击连接，密码和 OAuth 授权由本人完成。已有登录点击检查；失效时重新登录。

Codex 可从 PATH、macOS ChatGPT 内置 CLI 或 PRINT_EXTRACTOR_CODEX_BIN 定位可执行文件；使用本项目用户配置目录下独立 codex/ 账号，不复用其他 Codex 缓存。Grok 从 PATH、官方 ~/.grok/bin 或 PRINT_EXTRACTOR_GROK_BIN 定位，通过官方 CLI 管理登录，不复制其凭据到项目。环境覆盖仅接受实际可执行文件，不启动 .bat/.cmd 包装。

登录检查不产生图像模型调用。每次生成仍需同意上传与账号额度；账号需要图像权限和可用额度，订阅不等于独立 Images API Key。Windows 原生登录、出图和快捷方式本轮尚未实机验证。
