# 工作台接入验收 · 2026-10-16

工程仍为 temukoutu，分支 improve/providers-and-onboarding。没有推送或创建 PR，没有子代理。以下区分软件流程通过与印花质量，README 不承载工程测试细节。

## 本轮真实调用

| 路径 | 新增模型调用 | 生成结果 | 工作台后续 |
|---|---:|---|---|
| GPT / 官方 Codex 登录 | 1 | PNG RGBA，1262×1246，Alpha 0–255 | 浏览器上传、登录检查、确认额度、生成、继续精修、导出并下载通过 |
| Grok / 官方 Build 登录 | 1 | JPEG RGB，880×1168，无 Alpha | 明确标记非透明，继续精修、颜色候选、导出并下载通过 |
| 千问 Turbo / Pro | 0 | 没有配置 Key | 只有适配契约与设置回归，不能宣称真实出图通过 |

GPT 的生成响应在上传/登录检查开始后约 69.8 秒取得；Grok 约 32.0 秒。这不是纯模型耗时测量。两个实际生成请求均完成，无模型重试，无独立 API Key 计费路径。官方账号额度仍可能消耗，不能宣称免费或零费用。

原先脚本等待上传完成的条件过早，两个 UI 预备尝试均未发出模型请求，记录为 ui-wait-*.json。Grok 一次生成 HTTP 请求被进行中的登录检查以 409 拒绝，也未进入模型轮次，见 grok-preflight-busy.json。改为等待登录检查响应后，才发生上表唯一一次 Grok 模型调用。没有重跑已成功的 GPT。

本轮以后累计：GPT 4 次模型轮次、2 张有效透明候选（鸭子两次失败保留）；Grok 2 次原生编辑均得到 RGB JPEG；千问 0 次。早先模型事件和质量证据见 VALIDATION_2026-10-16.md。

## 文件与质量

新结果、现场截图和安全记录位于 artifacts/live-workbench-2026-10-16/：

- gpt-attempt.json / grok-attempt.json：真实生成响应、来源与精修任务、原文件完整性。
- gpt-original.png / grok-original.jpg：服务原字节，下载前后 SHA-256 一致。
- gpt-refined.png：1268×1247 RGBA，Alpha 0–255。
- grok-refined.png：904×1192 RGBA，Alpha 0–255。
- gpt-generation.png / grok-generation.png：生成区实际截图。
- gpt-refined.png.ui.png / grok-refined.png.ui.png：继续精修和下载后的真实界面。
- file-verification.json / verification-summary.json：Pillow 复开、尺寸、模式、Alpha、SHA-256 与本轮调用计数。

已目检：GPT 文字和三杯轮廓可见，但生成式编辑有重绘，不能承诺原像素恢复或批量质量。新的 Grok JPG 画入了黑白棋盘格，本身无 Alpha；颜色候选又误删黑眼镜、暗部，保留白色格块，质量不合格。虽然下载 PNG 的 Alpha 为真，这张图仍需大量手工修正，不能把格式通过写成印花验收通过。

## 自动回归与浏览器

Python：109 passed，1 条现有 TestClient/httpx 弃用提示，见 artifacts/pytest-workbench-integration.xml。新增覆盖：官方登录异步等待、账号失效、无图、单次同意、失败去重、生成原文件保留、透明/不透明精修起始状态、禁止仅靠边距导出、独立历史、Grok 工具事件/会话路径约束。

前端 build 通过。浏览器：11 passed、1 skipped，见 artifacts/playwright-results.json。跳过的是旧 Family Christmas 场景，本轮没有提供该场景所需原图环境变量。已有实际 GPT/Grok 结果的 replay 场景完成预览、继续精修、画笔、撤销、三背景切换、下载、刷新恢复、返回原记录与原字节核对，这些 replay 不调用模型。此后又补做上表两次真实生成，不能混算为 mock 或 replay。

账号状态额外通过公开 account/read 与 ACP cached_token 认证确认，不读取凭据文件。Python 测试始终隔离配置、阻断真实 HTTP transport；配置写入的浏览器测试也使用独立配置，未动用户真实 Key。Windows 只保留脚本与模拟检查，没有原生实机验收。

## 文档和交付

README 已整体重写为用途、安装提示、AI 配置、上传/精修/下载和必要帮助。工作台截图是本轮真实界面的自制示例，不含用户账号或私有产品原图；流程图为 1600×1000 的可编辑 SVG 和 PNG。模型细节、架构、API、历史试验留在 docs/。Library README 沿用原身份并带版本并发检查更新；回执在当前委派工作区 deliverables/。
