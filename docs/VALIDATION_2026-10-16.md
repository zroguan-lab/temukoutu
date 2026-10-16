# 2026-10-16 登录与真实图像测试

继续现有 `improve/providers-and-onboarding` 分支，复用 `backend/providers/codex.py` 与原有两张私有参考图。没有重建项目、开子 agent、推送或建 PR。本轮追加了官方图像事件解析修复及离线回归；此前 [92 项 Python 测试](VALIDATION_2026-10-15.md)保留为历史自动化记录，不重复计作真实模型成功。

## 已核验的登录

GPT：现有 `scripts/codex_bridge.py login` 打开 `auth.openai.com` 官方页，本人完成授权。脚本两轮曾返回通用失败提示，但随后同一项目独立配置目录的官方 `account/read(refreshToken=false)` 确认账号类型为 `chatgpt`，实际图像请求也成功执行；不把非零脚本退出当成最终账号状态。没有另行复制或导入其他应用的凭据。

Grok：本机官方 CLI `grok 1.0.46 (2765805b9442)` 的 `login --oauth` 打开 `auth.x.ai` / `accounts.x.ai` 官方授权页。本人同意后 CLI 报告登录成功；随后官方 ACP 声明 `cached_token`，以该方法 `authenticate` 成功。没有读取、复制或导出 token/cookie，没有重复要求同一授权。脱敏证据在 `artifacts/grok-auth-check-2026-10-16.json`。

## GPT 两图结果

仅通过本人 ChatGPT/Codex 额度测试，没有 API Key 回退。运行时权限仍为 `print_extractor`，未放开 shell、客户端工具或其他服务。

| 参考图 | 实际提交 | 结果 |
|---|---|---|
| 酒杯文字图 | 1 次模型轮次、1 个图像完成事件 | PNG 1237×1272，RGBA，Alpha 0–255，完全透明像素约 56.9856%，99.34 秒 |
| 鸭子文字图 | 先有 1 次账号预检拒绝，未发模型；只读确认登录后，提交该图首次模型轮次 | 1 个图像完成事件，但未取得有效图像字节，30.99 秒；保留失败记录，没有重发该模型轮次 |

此前实际提交 2 次模型轮次；本人随后明确授权原始鸭子图再跑一次，故本轮合计 **3 次模型轮次，1 张有效透明 PNG**。失败可能消耗 Codex 额度，不宣称额度为零；内建工具的内部次数不能由这段桥接换算成人民币硬上限。

对话调度模型：`gpt-6.1-sol`，官方 provider `openai`。鸭子轮次直接记录了 `thread/start` 返回；酒杯轮次未记录该字段，之后使用相同配置、无模型轮次的临时线程确认默认解析到同一型号。图像完成事件没有返回图像模型 ID；[官方说明](https://learn.chatgpt.com/docs/image-generation)称内建图像生成使用 `gpt-image-2`，此为文档信息，未从本次返回独立确认。

酒杯原图裁切为 355×365，结果经过重绘与放大，不是原图 RGB 的忠实提取。黑白底目视对照显示主要文字 “At my age / I need Glasses”、三个杯脚及装饰点保留，但细节和位置发生重绘，局部文字边缘仍有杂色与残留；保留 `needs_manual_review`，不作为印花质量全部通过。没有 Ground Truth，不报告准确率或 IoU。鸭子图无有效结果，未做质量通过判定。

本机私有产物（忽略 Git）：

- `artifacts/gpt-login-test-2026-10-16/glasses.png`：真实透明结果。
- 同目录 `glasses-white.png` / `glasses-black.png`：黑白底检查图。
- 同目录 `glasses.json`、`duck.json`、`duck-after-preflight.json`、`default-model.json`：脱敏结果、失败与型号证据。`duck.json` 只到账号预检，未提交模型。

## Grok 登录态真实图像调用

先前只核验了 ACP 登录和直接图像输入标志。续查[官方 image_edit 源码](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-tools/src/implementations/grok_build/image_edit/mod.rs)确认原生工具接受本地绝对图片路径并使用共享会话凭据，`promptCapabilities.image=false` 不代表没有图像工具。[共享客户端源码](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-tools/src/implementations/grok_build/image_gen/mod.rs)包含订阅等级、功能开关及模型覆盖，不能把源码能力当作本账号成功。

按本人追加授权，复用官方 CLI 登录测试已有鸭子图一次。仅允许 `image_edit`，禁止追加工具与子 agent，设一轮上限；日志确认实际只调用 1 次 `image_edit`，无其他工具调用。调度模型为 `grok-4.6`，图像工具未返回底层型号。官方源码的默认图像型号为 `grok-imagine-image-quality`，可被远端设置覆盖，未将其冒充本次实际返回。

工具在 32.77 秒内完成并保存实际图片，已复制为 `artifacts/grok-login-test-2026-10-16/duck-native.jpg`。Pillow 内容解码为 **JPEG、RGB、880×1168、无 Alpha**。鸭子、黑眼镜与文字仍在，但头发、眼镜和文字周围有明显条纹与底色残留，不能视为透明印花通过。未转换为假透明 PNG。

CLI 随后因本次设置的 `max-turns=1` 退出码为 1；完成事件和真实文件证明原生图像编辑成功，退出码并非图片生成失败。没有第二次 Grok 提交，未升级订阅、未提取或复制 token，也未使用独立 API Key 计费路径。官方 CLI 图像调用会使用账号额度，不宣称额度消耗为零。试验记录在同目录 `attempt.json`；原始事件只留本机，不上传账号或会话日志。

## 千问与预算

原有两张私有参考图都存在，SHA-256 与此前 `review/qwen-test-plan.json` 一致；不重复索取、不提交 Git。本机工作台已启动在 `http://127.0.0.1:7860`，其只读公开状态仍为 `enabled=false`、`key_configured=false`。

尚缺本人在工作台密码框保存的北京百炼 Key。两图各 Turbo/Pro 一次的授权仍为 4 次、预计 ¥0.70、上限 ¥1；没有发起千问调用，千问真实出图 0 次、千问 API 费用 ¥0。GPT/Grok 原生 CLI 会使用各自账号额度，未走独立 API Key 计费路径。不能写“千问实测通过”。用户配置后才能执行该四次计划；不得增加次数，失败/中断先核对用量。

## 文档与剩余阻塞

README 已按普通用户视角写明本地、千问 API、GPT/Grok 登录的实际状态，以及其他图像模型测试的 issue/PR 入口。DeepSeek 按 `deepseek-flash` 和 `deepseek-v4-pro` 区分图片理解与图像输出，不把整个品牌概括为单模态。

剩余：千问本机 Key；Grok JPEG 的真实透明输出与质量未通过，工作台 provider 未接入；GPT 鸭子图授权重跑也返回官方 failed/空结果，具体上游原因未提供，不能盲目再发。GPT/Grok 都已经登录，不再将“请重新授权”列为阻塞。


## 质量复核与可读对照

已逐字对照酒杯图 “At my age / I need Glasses”，主要文字一致，三个细杯脚连续，滴点仍在，但形状与位置重绘。已检查黑白底，以及文字边缘的 400% 像素局部；“Glasses” 上方可见不应保留的白块，黑底可见浅色或杂色边缘。结果保持 `needs_manual_review`，不视作忠实复刻或生产质量全部通过。

`artifacts/gpt-login-test-2026-10-16/glasses-quality-comparison.png`（2080×1540）同时展示原图、白底、黑底、杯脚局部与 400% 边缘。`quality-review.json` 保存不含账号信息的人工观察；没有 Ground Truth，未虚构准确率。

## 鸭子图离线诊断与代码修复

续查阶段先未提交模型。递归检查本项目官方 CLI 的 `generated_images`，只找到酒杯图；与交付 PNG 的像素完全一致，没有鸭子图。`sessions` 没有可回放的 JSONL。此前临时工作目录已随调用结束清理，测试记录只保留事件计数而非正文，无法从现有材料恢复鸭子结果，也不能确定它属于哪一种空结果原因。

用本机官方 CLI 重新生成公开 JSON schema，仅做本地协议检查，不登录或调用模型。图像事件字段为 `status`、`failure`、`result`、`savedPath` 等，没有发现需要猜测的新图像结果字段。

离线回归发现确定的问题：macOS 临时路径与 CLI 规范路径存在 `/var`、`/private/var` 等别名时，原先的目录包含判断可能误拒绝已授权文件。已将工作目录和验证根规范化，保留原有路径边界；增加真实临时文件路径的成功回归。另拒绝未完成的图像状态，将空结果、无效字段和不可读文件转为明确的 `ProviderError`，不回显上游细节，不自动重试。

修复前新增 9 个边界案例均失败；修复后桥接 30 passed，完整 Python 回归 **102 passed**，仍有 1 项已有依赖弃用警告。报告为 `artifacts/pytest-login-fixes.xml`。这些是假事件回归，不能冒充鸭子真实重测成功。

本人随后明确授权“鸭子图待会重跑一下看”，已执行且只执行一次。新尝试使用用户原始鸭子参考图（SHA-256 `5f15f8de58542effe06ce6fd0fdd89dfff10415d1576b4893bba0951ae0a2a6e`），前一次使用的是其裁切图，因此不把新结果当作仅修改解析逻辑的质量对照。

生成前已增加不含凭据的事件诊断及早期图像保存。新记录 `duck-user-rerun.json` 显示调度模型 `gpt-6.1-sol`，已提交 1 次模型轮次，31.16 秒收到同线程、同轮次图像完成事件：`status=failed`、`failure` 未提供、`result` 为空字符串、长度 0、无 `savedPath`。没有可恢复图片字节；官方没有提供更具体失败原因，不据此猜测额度、内容限制或账号故障，也不能追溯证明旧事件完全相同。没有继续重试。

旧 `duck.json`、`duck-after-preflight.json` 与新 `duck-user-rerun.json` 均保留，未覆盖原失败。本次没有有效 PNG，无法验收其 Alpha、黑眼镜或文字；不能把 Grok 的 JPEG 结果当作这次 GPT 成功。

## 后续工作台接入

本记录保留早先三次 GPT 与一次 Grok 试验。后续新增 GPT/Grok 工作台接入，并各一次实际生成，累计 GPT 4 次/2 张透明候选、Grok 2 次/2 张 RGB JPEG。完整 UI 与文件验收见 [工作台接入验收](VALIDATION_WORKBENCH_2026-10-16.md)。该后续验收不改变本文已记录的失败和质量问题。
