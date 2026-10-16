# PR 验收与模型实测 · 2026-10-17

日期按 Asia/Shanghai。用户已核验现有功能并授权从本人 fork 提交到上游仓库的单个 PR，不直接修改上游 main，不合并。本次提交准备没有新增图像模型调用。

## 工作台实际范围

| 用户操作 | 实现位置 | 验证 |
|---|---|---|
| 配置 AI、连接与检查 GPT/Grok 官方登录 | `frontend/src/AccountConnections.tsx`、`AISettings.tsx`、`backend/app/connections.py` | 本人 OAuth、账号状态及异步等待流程已有实际验收；本次自动回归不登录 |
| 上传工作图、确认上传与额度后调用图像工具 | `frontend/src/CloudEditor.tsx`、`backend/app/cloud.py`、`backend/providers/codex.py`、`grok.py` | GPT/Grok 已各在工作台真实出图；不是只有命令行脚本 |
| 保存生成原文件、预览和下载 | `backend/providers/generated.py`、`backend/app/cloud.py`、`frontend/src/CloudEditor.tsx` | 实际格式/Alpha 验证；原件字节保留 |
| 继续精修、返回源任务、保留独立编辑历史 | `backend/app/storage.py`、`main.py`、`frontend/src/App.tsx`、`services/ai.ts` | 已有 GPT/Grok 结果离线重放通过，不重新上传或生成 |
| 非透明结果提示、失败状态、重复请求保护 | `backend/app/cloud.py`、`backend/providers/generated.py`、`frontend/src/CloudEditor.tsx` | 不把 JPG 或棋盘格当真透明；不能靠导出留白冒充抠图；失败不自动重试 |
| Windows 安装、桌面入口、重复启动复用 | `scripts/install.ps1`、`start.ps1`、`create_shortcut.ps1`、`post_install.py` | 仅静态与模拟回归，未在 Windows 原生电脑验收 |

## 模型实测与限制

- GPT：官方 Codex 登录已接工作台。先前酒杯透明结果与后续原始鸭子图透明结果均已交付；鸭子原生 PNG 为 1199×1312、RGBA、Alpha 0–255，完全透明像素约 42.9154%。保留英文、眼镜等主体，但生成式编辑仍有重绘，需对照原图。早先失败轮次保留在历史记录中。
- Grok：官方 Build 登录、真实出图和继续精修流程已跑通；两次原生图像编辑均为 880×1168 RGB JPEG，无 Alpha，其中一张还生成了棋盘格。透明印花质量未通过，暂不推荐。精修能导出带 Alpha 的 PNG，不等于自动提取质量通过。
- 豆包：`doubao-seedream-5-0-pro-260628` 仅做独立 API 实测，得到 1840×2448 RGBA PNG、Alpha 0–255，完全透明像素约 48.0288%。输入原始 RGB 照片外加 1px 透明边框以满足该接口要求，照片内部像素未改；服务输出原字节未做本地去背景。尚未集成工作台。
- 千问：没有成功出图记录，不列为已支持模型，不出现在网页模型选择。保留的北京百炼代码与设置 API 仅为实验兼容，标记 `experimental=true`、`generation_verified=false`，模拟测试不能证明端到端可用。

用户指定 `maas.qianwenaiapi.com` 的独立测试：

| 请求路径 | 模型 | HTTP 与服务错误 | 图片 |
|---|---|---|---:|
| `/compatible-mode/v1/images/generations` | `qwen-image-2.1-pro` | 403 / `access_denied` / `Model access denied`；旧密钥与新的一次性密钥各一次 | 0 |
| `/api/v1/services/aigc/multimodal-generation/generation` | `qwen-image-3.0-pro` | 403 / `Model.AccessDenied` / `Model access denied`；按用户追加示例一次 | 0 |

403 根因未知，不归咎于用户 Key，不据此断言平台身份。该独立测试端点不同于保留代码的默认 `dashscope.aliyuncs.com`，不能将它写成工作台接口验证成功。返回没有账单扣费信息。原始响应和请求记录仅留本机，密钥未写入项目配置或提交。

## 本次离线回归

- Python：109 passed，1 条现有 TestClient/httpx 弃用提示。测试逐例隔离配置，阻断真实 HTTP transport。
- 前端：TypeScript 与 Vite 生产构建通过。
- 浏览器：11 passed、1 skipped。跳过旧 Family Christmas 原图场景；已重放现有 GPT/Grok 输出，覆盖预览、继续精修、画笔、撤销、黑白/棋盘背景、透明导出、刷新恢复与返回源记录。
- 新增回归断言确保网页模型列表仅含 GPT/Grok；实验 Key 保存、刷新、清除不泄露到接口响应或浏览器存储。
- 当前工作台截图使用自制 PRINT / 2026 示例、独立临时配置和 Chrome。没有调用模型、检查真实账号或展示私人参考图。

本地证据为忽略 Git 的 `artifacts/pytest-pr-2026-10-17.xml`、`artifacts/playwright-results.json` 及历史生成验收记录。公开提交只保留脱敏文字记录与自制示例界面，不提交私人原图、生成图、OAuth 日志或本机配置。

历史记录：[自动化基线](VALIDATION_2026-10-15.md)、[官方登录与早期失败](VALIDATION_2026-10-16.md)、[工作台真实生成与精修](VALIDATION_WORKBENCH_2026-10-16.md)。历史文件中的“尚未测试”“未创建 PR”等语句描述当时阶段，最新状态以本记录和 GitHub PR 为准。
