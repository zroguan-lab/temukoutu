# Provider 扩展验证记录

本轮基于 `ec3fffa`，在独立本地分支验证。环境为 macOS arm64、Python 3.12.13、Node.js 26.0.0 与独立无登录 Chrome；Python/npm 使用仓库锁文件。下列记录不替代原有 Windows 测试，也不把模拟响应计作模型真实成功。

## 自动化结果

| 检查 | 命令 | 结果 |
|---|---|---|
| Python 功能、契约与预算回归 | `.venv/bin/python -m pytest -q` | 92 passed；1 项已知依赖弃用警告 |
| TypeScript 与生产构建 | `npm run build --prefix frontend` | 通过 |
| 浏览器全量回归 | `npm run test:e2e --prefix frontend` | 8 passed、1 skipped |
| Python 语法 | `python -m compileall`，针对本轮 Python 模块 | 通过 |
| 补丁空白检查 | `git diff --check` | 通过 |

浏览器跳过项是原有 Family Christmas 特定照片测试，未提供其 `PRINT_EXTRACTOR_REAL_IMAGE`，没有拿其他参考图冒充该素材。原有 5 个工作台场景通过，覆盖裁切、候选切换、200%/400% 画笔坐标、撤销/重做、透视、人工接管、删除、刷新恢复与透明 PNG 下载。

新增 3 个浏览器场景验证真实本地服务的默认云端关闭；临时假 Key 保存、刷新后恢复、密码框为空、响应/localStorage 无 Key、清除；以及明确 mock 的云端逐次确认、型号/费用、编辑冻结与独立下载。没有真实模型出图或费用。

新增 Python 检查覆盖千问 JSON 与 Base64 契约、单张数量、不转发下载鉴权、URL 白名单、HTTP 错误/超时不重试、错误信息不回显 Key、输入型号、假透明与无效图片、上传/费用确认、来源版本、请求去重、失败与中断记录、任务历史隔离、显式凭据开关，以及预算 dry-run、失败中止、结果复用和并发锁。

Starlette 的 TestClient 对当前 httpx 依赖有弃用提示；测试仍通过。本轮保持已有锁文件，未为消除警告升级或替换整个测试栈。

## 真实工作台与截图

实际启动 `uvicorn backend.app.main:app --host 127.0.0.1 --port 7860`，明确关闭云端；Playwright 操作真实上传、画笔、导出和下载后截屏。README 引用的 [workbench.png](images/workbench.png) 只包含 `tests.synthetic` 的自制 PRINT / 2026 图像，不含账号、密钥或私人素材，也没有拼造 UI。另有[云端关闭状态截图](images/cloud-disabled.png)。

首轮在受限沙箱中无法绑定本机端口或启动 Chrome，随后以获准的原生执行权限复测并通过。这是执行环境限制，未计入产品功能失败。

## 真实参考照片与质量

另有两张本地参考照片做了 CPU Lab/GrabCut 对照，未上传至模型服务，也未放入本仓库。四个本地候选均有实际 Alpha=0/255，RGB 与裁切源图一致。没有人工标注 Ground Truth，不报告 IoU 或准确率。

酒杯图主体文字、杯脚与飞溅大体保留，但边缘需检查。另一张黑色内部细节较多的图中，两种本地候选都丢失部分应保留的黑色与细节，不能作为自动提取质量通过。功能成功和文件透明门槛不等于人工质量通过。

## 代码审查

按本仓库架构与需求分别做单人审查，未使用额外子代理。仓库没有额外 AGENTS.md 或编码标准。标准轴检查核心无网络、已有 CLI/API 兼容、状态唯一来源、原子文件写入和单进程任务锁；需求轴检查真实 Alpha、原图 RGB、显式外传确认、费用边界及 mock/真实结果区分。

审查中已处理：生成文件避免被 revision 清理误删；任务锁内读取下载，避免删除竞态；云端生成时冻结本地编辑；超时提示先核对用量；预算脚本使用独占运行锁；不以第三方 URL 携带 API Key 下载。当前未发现需要阻止本地核验的已知代码缺陷。

## 尚未验证

- 千问真实 API 的账户权限、响应与输出质量。缺少本项目百炼 API Key，实际调用 0 次、费用 ¥0。计划两图各测 Turbo/Pro 一次，共 4 输出，预计 ¥0.70，预算不超过 ¥1；不将此计划写成成功记录。
- 官方 Codex 桥接未完成本人真实登录、图像工具调用或透明图质量验收；只有实际 CLI 空账号传输/线程配置与 mock 图像契约。用户另有本地 GPT OAuth 版本，未宣称迁移兼容。
- 新增 Windows .lnk 的原生创建、中文/空格路径、首次/重复打开、端口冲突与新配置的 ACL；目前只有平台分支/参数模拟及脚本静态检查，不挪用历史 Windows 结果。Linux 路径未实机验证。
- Grok、Claude、Seedream 的实际图像调用均未实施；能力与限制见 [PROVIDERS.md](PROVIDERS.md)。

当前只支持单进程，云端生成持有任务锁，尚无取消、后台持久队列或账户总预算硬限制。失败与中断请求需要人工核对服务用量；生成式输出仍须逐字、逐细节验收。

## 新增本机配置与官方桥接的检查

本机配置：临时假 Key 的文件 0600/目录 0700、API 不回显、进程重启恢复、启停和清除、格式/权限错误退回本地、Pydantic 错误不携带输入、Windows 当前 SID ACL 命令均通过。所有写入都在临时或测试目录，不写用户真实 Key。

Windows：跨平台辅助入口在 macOS/Linux 无命令和桌面副作用，Windows Unicode/空格路径以参数数组传递，缺少安装文件时拒绝创建，PowerShell 的平台守卫/启动互斥/端口冲突逻辑静态通过。没有原生 Windows，不能报告 .lnk 或启动实测通过。

官方 Codex：使用独立空 CODEX_HOME 和本机官方 CLI `0.162.0-alpha.17.2`，真实 stdio initialize、account/read(false)、ephemeral thread/start（profile=print_extractor、modelProvider=openai）通过，不含模型轮次。沙箱内首次创建线程受系统 sandbox_apply 限制，获准原生执行后通过；没关闭产品沙箱。实际发现内建 openai provider 不能被 model_providers 覆盖，已去掉不兼容的零重试配置，并如实说明 CLI 内部重试/额度边界。没有登录、图片上传、生成或额度消耗。

桥接 mock 覆盖必须主动同意额度、只接受 ChatGPT 账号、禁止 API-key 回退、权限 profile 失效时不发轮次、官方登录 URL 白名单及 loginId 匹配、只接受当前轮次图像事件、拒绝普通文本/不透明/空图/无效 Base64/越界路径/多张图、错误不泄漏上游细节、不自动重发；还覆盖 stdio 凭据环境过滤、拒绝客户端工具和初始化失败进程清理。mock 不能证明真实 GPT 图像输出。

新增 1600×1000 静态流程 PNG 和 SVG/JSON 源，真实页面 tokens 为样式依据，详见 [图像来源](images/README.md)。README 四步结构与相对图片链接已检查。当前没有发现需要阻止本地代码核验的未修复问题；模型质量、Windows 原生与跨平台行为仍须按上表单独验收。

测试隔离补强：根 conftest 在模块导入前使用空临时配置并关闭云端，每例重置配置路径与项目环境变量；真实 HTTP transport 被守卫拒绝。新增检查证明普通 pytest 无法向真实模型服务发请求，避免读到开发者已保存 Key 后误计费。最终计数 92 passed。
