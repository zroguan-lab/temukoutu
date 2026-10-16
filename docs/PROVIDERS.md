# 模型能力与接入边界

当前工作台可使用本地蒙版、GPT 官方 Codex 登录和 Grok 官方 Build 登录。GPT/Grok 生成原文件可直接“继续精修”。千问实验代码保留兼容接口，但未成功完成端到端出图，不列为可用提供商，也不出现在网页模型选项。早先两图试验与后续网页现场验收分开记录，不能用文件有 Alpha 代替印花质量通过。

最新状态：[PR 验收与模型实测](VALIDATION_PR_2026-10-17.md)；历史证据：[工作台接入验收](VALIDATION_WORKBENCH_2026-10-16.md)；早先失败轮次与质量复核：[现场记录](VALIDATION_2026-10-16.md)。官方文档只说明能力，不代替项目实测。

## 先分清要得到什么

| 能力 | 输出 | 对本项目的意义 |
|---|---|---|
| 视觉理解 | 描述、文字、解释 | 可以辅助检查，不能直接下载成透明印花 |
| 定位 | 框、点或区域 | 帮用户圈定印花，不等于像素级蒙版 |
| 分割 | 与工作图对齐的蒙版 | 用本地原图 RGB 与蒙版合成 PNG，保留照片已有像素 |
| 图像编辑 | 新的图像像素 | 可能改字或重画，只作为独立候选 |
| 透明输出 | 实际 Alpha 通道 | 需要解码验证；PNG 后缀与棋盘格都不能证明透明 |

本项目要取出衣服上的设计，普通整件衣服去背景的效果不能代替验收。原图缺失、遮挡或与衣物完全同色的信息不能保证恢复。

## 官方能力矩阵

| 服务与型号 | 官方能力及接口 | 透明输出证据 | 本项目状态 |
|---|---|---|---|
| Qwen Image 2.1 Turbo / Pro | 图生图，最多 10 张参考图；本适配只传当前工作图 1 张 | 官方说明可按提示输出带透明通道的图像 | 实验代码，仅模拟契约验证；真实测试未出图，不列为支持 |
| GPT / 官方 Codex CLI | 公开 app-server JSON-RPC，本人 ChatGPT 登录；内建 image_generation | CLI schema 有 imageGeneration、savedPath、transparentBackground；仍须解码 Alpha | 已接入工作台；本人登录、真实透明候选及继续精修均有实测，部分输入曾失败，质量需复核 |
| Grok Build `image_edit` / Imagine | 官方 CLI 原生工具共用受管理会话凭据；另有独立图像 API | 本次真实结果为 RGB JPEG，无 Alpha | 已接入工作台与继续精修；本人登录态有实际出图，原结果无 Alpha，独立 API 未适配 |
| Claude 原生视觉 | 理解图片；官方明确不原生生成或编辑图像 | 无原生图像输出契约 | 不适合作为直接透明图 provider |
| Seedream 5.0 Pro / Flash | 图像编辑及图层拆分；Pro `doubao-seedream-5-0-pro-260628`、Flash `doubao-seedream-5-0-flash-260915` | 拆层可输出 1 张底图与最多 16 张透明图层 | Pro 独立 API 实测得到透明 PNG，尚未集成工作台；Flash 未调用 |
| DeepSeek `deepseek-flash` / `deepseek-v4-pro` | 官方表中 Flash 支持视觉输入，Pro 不支持；Flash 的图片理解返回文本 | 本轮未核实二者原生图像生成/编辑输出契约 | 未适配，不能直接作为透明印花生成 provider |
| Doubao Seed2.0 / Qwen3.8 等名称 | 不能用理解/文本系列名称代替图像模型 ID | 未以这两个名称核实可直接调用的印花 RGBA 契约 | 不列为支持型号 |

来源：[千问接口](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference)、[千问图像编辑指南](https://help.aliyun.com/zh/model-studio/qwen-image-edit-guide)、[Grok 图像编辑](https://docs.x.ai/developers/model-capabilities/images/editing)、[Claude 视觉问答](https://platform.claude.com/docs/en/build-with-claude/vision)、[Seedream 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)。

Seedream 的 `background=transparent` 路径要求输入已带透明通道，不能据此直接宣称支持普通 JPG T 恤抠图。独立实测为原始 RGB 照片外加 1px 透明边框后，使用 Pro 的 `background=transparent` 返回原生透明 PNG；未改动照片内部像素，也未做输出去背景。此试验没有集成工作台，仍须验证细节和实际印花质量。

## 保留的千问实验契约（未验证可用）

实验代码固定使用下述百炼域名；后续用户指定 `maas.qianwenaiapi.com` 的独立测试返回 403，没有出图，根因未知，不能作为该代码端到端成功的证明。详见最新验收记录。

本实现使用北京地域 `POST /compatible-mode/v1/images/generations`，JSON 中传入 `model`、`prompt`、Base64 `image`、`n=1`，关闭提示词改写。不使用 `/images/edits` 或 multipart，也不传没有文档依据的 `mask`、`background` 参数。`response_format=b64_json` 会被该兼容接口忽略，因此解析 `data[0].url` 后下载图像。

API Key 只发给北京官方固定域名或用户配置的北京业务空间域名。结果下载只接受 HTTPS 的 `*.aliyuncs.com`，不转发 Authorization、不跟随重定向、不使用环境代理，不记录上游错误正文或签名 URL。如果官方后续改变下载域名，需要核实来源后再调整适配。

输入 PNG 最多 10 MB，长边最多 8000px，宽高比不超过 10:1。结果限制 25 MB、1600 万像素，校验实际格式与非空前景，保存服务原字节。仅 PNG 具有 Alpha 且含全透明像素时才标透明候选；不透明结果需继续精修。透明比例是文件状态，不是质量评分。

每个请求在发出前写入本地记录，包含请求 ID、来源 revision、型号、预计价格和状态。同一 ID 成功时返回已有记录，失败或中断时拒绝再次计费提交。新请求 ID 代表新的一次可能付费调用，前端不自动重试。该去重只支持本项目单进程模式；价格估算不是云端账单硬限制。

## 成本与验收

北京地域公开单价：Turbo ¥0.10/输出张、Pro ¥0.25/输出张。两张参考图各测两种模型、每次输出 1 张，预计 ¥0.70。免费额度需要逐账户核对；这些价格仅描述保留代码的估算，不表示接口已经可用。后续独立测试失败及其端点记录见最新验收。[价格来源](https://help.aliyun.com/zh/model-studio/model-pricing)。

Seedream 拆层需要按输出张数累加，包括底图；不能把一次请求价格当作一张透明印花价格。具体分辨率、图层数和当期价格要在适配前重新核对，工作台没有集成该独立实测路径，详见最新验收记录。

对每张图检查：英文逐字及标点一致，酒杯脚不断裂，飞溅和装饰点齐全，黑眼镜和内部黑色保留，毛发细线未丢，衣物黑底与印花间隙已透明。黑、白底 200%–400% 检查后，另记人工是否通过。实际单张可用成本应为本轮总费用除以通过张数；没有通过结果时不能报告可用单价。

## 官方 GPT 登录桥接

不等待朋友的本地 OAuth 源码，也不转用任何现有凭据。本分支新增独立的官方 Codex App Server 桥接：由官方 CLI 发起 `account/login/start` 的 `chatgpt` 浏览器流程，官方进程管理回调与登录缓存，再用公开 `thread/start`、`turn/start` 发送一张本地图像。普通聊天订阅不是 OpenAI Images API Key；这条路径使用 Codex 自身支持的登录与工具权限，没有把订阅 token 发给图像 API。

依据：[Codex 登录](https://learn.chatgpt.com/docs/auth)、[官方 App Server 客户端协议](https://learn.chatgpt.com/docs/app-server)、[Codex 内建图像生成](https://learn.chatgpt.com/docs/image-generation)、[SDK 与权限配置](https://learn.chatgpt.com/docs/codex-sdk)。这些说明支持官方客户端接入路线，不等于已证明本项目能恢复印花或输出透明图。

本机官方 CLI `0.162.0-alpha.17.2` 的 `features list` 显示 image_generation 可用；用其 `app-server generate-json-schema` 生成的 schema 核对了 imageGeneration 事件、savedPath、result 与 transparentBackground。真实 stdio 初始化、空账号 `account/read(refreshToken=false)`、隔离权限的 ephemeral 线程创建通过；这些是 2026-10-15 的历史预检，彼时没有登录或模型轮次。2026-10-16 已完成本人登录并提交两图，结果分别记录于现场复核，不能继续把本桥接整体称为仅 mock。

实现位于 `backend/providers/codex.py`，现已接入工作台的账号连接、生成与继续精修。保留独立 CLI 入口（Windows 请换成 `.venv/Scripts/python.exe`）：

```bash
# 只发起本人官方登录；不要复制其他应用的 auth.json 或浏览器凭据
.venv/bin/python scripts/codex_bridge.py login
# 会上传图片并消耗 Codex 额度；单独确认预算/额度后才执行
.venv/bin/python scripts/codex_bridge.py extract --input product.png --output candidate.png --allow-usage
```

凭据由官方 CLI 写入本项目用户配置目录下的独立 `codex/`，与用户已有 `~/.codex` 隔离。CLI 文件可通过 PATH 或 `PRINT_EXTRACTOR_CODEX_BIN` 指定；不会下载安装或复制账号缓存。未登录、API Key 账号、权限 profile 未生效时，桥接在发送模型任务前拒绝；不回退到 API 付费路径。

桥接禁用 shell、其他应用、多代理、插件与 hooks，拒绝客户端工具/审批请求；文件访问仅临时输入输出目录。它只接收同线程/轮次的单个 imageGeneration 完成事件，文字回复不算成功；本地输出路径与 PNG/Alpha 仍需验证。原图 RGB 不承诺保持，产物独立保存，继续标为 needs_review。

应用不自动重发轮次，并关闭 CLI 的无限连接重试特性；当前官方 CLI 禁止覆盖内建 OpenAI provider，不能以通用 request_max_retries 配置承诺其底层零重试，参见[官方配置契约](https://learn.chatgpt.com/docs/config-file/config-reference)。内建工具的实际次数、内部重试和 Codex 额度不能由这段桥接换算成人民币硬上限；提示只生成一张也不是服务端费用上限。2026-10-16 已完成真实登录、图像工具事件和单张透明结果验证；两张参考图原先共两次轮次，另按本人追加授权对原始鸭子图重跑一次，仍未取得有效图像；没有继续重发。Codex 额度可能已消耗，不能宣称费用或额度为零；没有使用独立 API Key 计费路径。这是早先试验的记录；后续已开放网页按钮，并新增一次酒杯图真实生成与继续精修，累计 4 次模型轮次、2 张透明候选。质量仍需人工复核。

用户已有的本地 GPT OAuth 版本确实存在；公开仓库基线 `ec3fffa` 的两次提交和公开引用未包含它。本桥接不声称兼容或替代该实现。日后接回时仍按蒙版/新图输出选对应 provider，凭据留在原授权持有层。

## Grok 与 Claude

[Grok Build](https://docs.x.ai/build/overview) 的官方 CLI 包含原生 `image_edit`，不是只能通过独立 API Key 接图像。[官方源码](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-tools/src/implementations/grok_build/image_edit/mod.rs)说明该工具可读取绝对图片路径，并复用 `image_gen` 的受管理会话凭据；[共享客户端与门槛](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-tools/src/implementations/grok_build/image_gen/mod.rs)还包含独立功能开关、订阅等级检查与模型覆盖配置。能力存在不代表每个账号都可用，也不保证透明输出。

2026-10-16 本机 CLI 1.0.46 已由本人完成 OAuth，官方 ACP 的 `cached_token` 认证成功。此前 `promptCapabilities.image=false` 只描述直接图像 prompt 输入，不能据此否定工具通过本地路径编辑图片。模型目录读取虽曾超时，随后受限 CLI 轮次确实调用了 **1 次 `image_edit`**，32.77 秒内返回 880×1168 的 RGB JPEG。`grok-4.6` 是本次调度模型；工具返回未提供底层图像型号。源码默认图像型号可被设置覆盖，不能用默认值冒充实测返回。

该 JPEG 没有 Alpha，边缘可见大面积条纹与底色残留，未通过透明印花验收；没有把它转换为假透明 PNG。CLI 因设置的一轮上限在工具完成后退出，文件与完成事件证明图像调用成功，非零退出不能反推工具失败。未重试、未调用其他工具，也未使用 API Key 计费路径。这是早先试验的记录；后续已实现 Grok 工作台 provider，新增一次原生编辑得到 JPG，继续精修与下载通过。累计两次原生编辑均无 Alpha，自动去背景质量仍未通过。

[Imagine 编辑 API](https://docs.x.ai/developers/model-capabilities/images/editing)及 [Responses 图像工具](https://docs.x.ai/developers/tools/image-generation)是另两种公开 API 接口；本轮未自行抽取或转发登录 token 去调用它们。官方 CLI 持有并使用其自身凭据，与应用手动搬用凭据是不同接入方式。

Claude 的原生视觉理解不能直接生成/编辑可下载图像。官方第三方凭据限制见[凭据使用说明](https://code.claude.com/docs/en/legal-and-compliance)；不把 Claude.ai Free/Pro/Max 登录态接作本项目图像 API。普通视觉理解、坐标定位、蒙版分割、生成式编辑与透明输出是独立验收项。

## DeepSeek 的具体型号

不把整个品牌概括成单模态。2026-10-16 官方[型号表](https://api-docs.deepseek.com/quick_start/pricing/)列出 `deepseek-flash`（DeepSeek-V4.1-Flash）支持视觉输入，`deepseek-v4-pro`（DeepSeek-V4-Pro-0813）不支持视觉输入；[Vision 指南](https://api-docs.deepseek.com/guides/vision/)展示 Flash 读取图片并回答文字。视觉输入与图像像素输出是不同能力，本轮未核实这两个型号的原生图像生成/编辑接口，因此未将其作为透明印花生成 provider。若引入其他具体图像型号，应另行核实公开协议与 Alpha，并记录真实结果。
