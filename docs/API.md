# 本地 API v0.1.0

基础地址 `http://127.0.0.1:7860`，OpenAPI 文档 `/docs`。仅本机请求。默认离线；可选云端编辑使用后端百炼 API Key，见文末。

成功直接返回 JSON 对象，图像返回 PNG；错误统一为：

```json
{"error":{"code":"invalid_input","message":"蒙版为空，请先添加需要保留的区域"}}
```

| 方法 / 路径 | 输入 | 返回 |
|---|---|---|
| GET /api/health | — | status、app、version、models、ai_used |
| POST /api/tasks | multipart `file` | 任务 id、rev、width、height、method、warnings |
| GET /api/tasks/{id} | — | 当前版本与导出元数据、撤销/重做状态 |
| DELETE /api/tasks/{id} | — | 删除任务全部文件 |
| POST /api/tasks/{id}/detect | — | box `[x0,y0,x1,y1]`、needs_review、warnings |
| POST /api/tasks/{id}/crop | `{"points":[[x,y],...]}` | 裁切新版本；最小 8×8 |
| POST /api/tasks/{id}/transform | 4 个按左上、右上、右下、左下排序的凸四边形点 | 透视后新版本，transformed=true |
| POST /api/tasks/{id}/segment | `{"method":"grabcut","tolerance":28,"use_seed":false}` | 新版本，同时包含 color/grabcut/manual 候选名 |
| POST /api/tasks/{id}/candidate | `{"name":"color"}` | 切换候选并保留其他候选 |
| PUT /api/tasks/{id}/mask | multipart `file`，工作尺寸的灰度 PNG，0 排除、255 保留 | 手动蒙版新版本 |
| POST /api/tasks/{id}/edges | `{"smooth":0,"feather":0,"expand":0}` | 调整边缘后的新版本 |
| POST /api/tasks/{id}/history/undo | — | 上个版本 |
| POST /api/tasks/{id}/history/redo | — | 下个版本 |
| POST /api/tasks/{id}/reset | — | 恢复原图的新版本（可撤销） |
| GET /api/tasks/{id}/preview | kind=result/work/original/mask | PNG；无 kind 默认 result |
| POST /api/tasks/{id}/export | `{"padding":12}` | 导出宽高、Alpha 范围、content_box、warnings、诊断提示 |
| GET /api/tasks/{id}/download | 必须已导出当前版本 | 附件 PNG RGBA |

分割方法 auto/color/grabcut/manual；颜色差异 2–150，平滑 0–10，羽化 0–20px，扩张 -20–20px，边距 0–200px。多边形 3–200 点，坐标属于当前工作图的像素空间，不是 CSS 显示坐标；不能越界或退化。透视后工作图和蒙版尺寸同步变更。

导出扩展参数：`scale` 为 1（默认）、2、4；`target_long_edge` 可指定最终长边（含边距），此时 scale 必须为 1。不允许小于原始导出长边；最多 8192px 长边、1600 万像素。保持纵横比，采用预乘 Alpha Lanczos 插值。返回 `native_width`、`native_height`、`resampled`、`scale`、`detail_note`，明确不增加原始细节。示例：`{"padding":12,"target_long_edge":1254}`。

上传或编辑响应举例：

```json
{"id":"32位十六进制UUID","rev":"版本UUID","width":360,"height":420,
 "method":"grabcut","version":"0.1.0","status":"needs_review","ai_used":false,
 "transformed":false,"can_undo":true,"can_redo":false,
 "candidates":["color","grabcut","manual"],"warnings":["需要人工检查"]}
```

404：任务或导出不存在/已删除；403：非本机来源；413：请求过大；408：上传接收超时；422：格式、几何或参数错误；504：分割计算超时；500：未知处理失败（查看本地日志）。所有路径由服务端构造，无按上传文件名读取任意文件的接口。编辑及撤销使旧导出失效，download 返回 404 直至重新导出。

不将图像 Base64 写入 JSON。数据目录可在启动前用 `PRINT_EXTRACTOR_DATA` 环境变量指定。不要使用多 uvicorn worker 同时写同一目录。

## AI 账号与生成图

`GET /api/providers` 返回本地能力、千问配置、GPT/Grok 安装与公开连接状态、实际可选型号。`cloud` 保留千问兼容字段；`models` 仅列 GPT/Grok 网页选项。千问代码以 `cloud.experimental=true`、`generation_verified=false` 保留兼容，不列为已支持模型。检查安装不读取账号文件，也不发起模型请求。

- `GET /api/connections/{gpt|grok}`：公开状态 unknown/signed_out/connected/waiting/error。
- `POST /api/connections/{name}/check`：通过官方协议检查已有登录，无模型轮次。
- `POST /api/connections/{name}/login`：启动官方登录，立即返回 waiting；用户在官方页面操作，之后 GET 轮询。不返回 cookie、token、邮箱或 OAuth URL。

`POST /api/tasks/{id}/generations` 示例：

```json
{"model":"gpt-image","request_id":"32位小写十六进制随机ID",
 "source_revision":"当前任务rev","allow_upload":true,"allow_account_usage":true}
```

GPT/Grok 型号分别为 `gpt-image`、`grok-native`，需显式确认上传与账号额度。千问 `qwen-image-2.1-turbo/pro` 需启用 Key，并传足够的 `max_estimated_cost_cny`，上限 1。预计费用不是账单硬限制；任何路径都不自动重试或回退其他 provider。调度模型标签不表示已获底层图像型号。

请求在调用前持久化。相同 ID 与相同来源/型号成功后返回原记录；失败、pending 或不同参数返回 409。来源已变或账号正在使用也返回 409。未同意上传、额度确认缺失、预算不足、无图、登录过期等返回安全错误。原商品任务、蒙版、历史和导出均不改变。

`GET /api/tasks/{id}/generations` 列出生成记录，包括状态、来源、实际格式、尺寸、透明判定和安全错误。`transparent=true` 只是 PNG/Alpha 文件门槛，质量始终 needs_review。

`GET /api/tasks/{id}/generations/{request_id}/image` 下载服务原始字节，实际 Content-Type 与扩展名对应，文件名为 `generated-original.<png|jpg|webp>`。不透明结果可下载原图，但不会被标成透明 PNG。不存在或未完成返回 404。

`POST /api/tasks/{id}/generations/{request_id}/refine`：校验已完成生成文件，新建独立本地任务并返回 Task，含 provenance。无用户指定路径参数，不覆盖原商品图或原生成文件。不透明任务需生成蒙版或画笔清理后才可通过原 `/export` 与 `/download`。

## 本机千问实验设置（未验证可用）

- `GET /api/settings`：返回 enabled、key_configured、workspace_id、provider 与安全错误提示，不返回 Key。
- `PUT /api/settings`：`{"enabled":true,"api_key":"用户本机输入","workspace_id":""}`。省略/null/空值保留已有 Key，启用但无 Key 返回 422。原子保存后即时生效。
- `DELETE /api/settings`：删除本项目千问配置；不删除 GPT/Grok 官方账号。显式进程环境配置仍按启动规则处理。

所有接口沿用本机 Host/Origin/Fetch 限制，验证错误不回显输入值。单进程运行，不支持多 worker 同时写同一目录。
