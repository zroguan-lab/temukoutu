# 架构与状态边界

版本 0.1.0，2026-10-15。可选云端适配新增说明见文末。

默认路径从原始照片中选择像素并赋予 Alpha，通过人工接管完成下载。生成式 provider 的结果独立保存，不能当作原像素的忠实恢复。

| 层 | 责任与唯一事实来源 | 验证 |
|---|---|---|
| extractor_core | 输入校验、检测、裁切、透视、可替换分割、边缘与 PNG 导出；没有网络调用 | 核心单元测试、RGB 不变测试、Ground Truth 指标 |
| Store | 每个 UUID 独立目录；meta.json 当前历史指针为权威状态 | 撤销/重做、分支截断、重启恢复、删除后 404 |
| FastAPI | 本地来源限制、参数验证、任务锁、API、静态前端 | API 集成、安全边界、下载 Alpha |
| React Canvas | 工作图像素坐标、当前工具与选区、蒙版笔划 | 浏览器 200%/400% 添加/擦除与回读坐标 |
| Windows 脚本 | 安装、桌面入口、单实例探测、启动/停止和健康状态 | 历史版本有原生报告；本轮新增桌面/启动锁/ACL 只有静态与模拟检查 |

## 引擎

- `io.py`：内容格式、25MB、16MP、EXIF、RGBA、原子文件替换。
- `detection.py`：Lab 对比、边缘密度、中心先验，只输出需确认的候选框，失败回退到参考框。
- `transforms.py`：矩形本质为四点多边形；裁切将选区外 Alpha 置零；四点凸四边形单应性变换。
- `segmentation.py`：边缘像素中位 Lab 估计布料色；颜色距离候选和 GrabCut 两条路径。最多 1000px 工作边长；蒙版回映射原工作尺寸，原图 RGB 不缩放。手动全保留随时可用。黑白确定种子支持引导 GrabCut。
- `masks.py`：L/8-bit 蒙版，形态学、平滑、羽化。
- `export.py`：原图 RGB + min(输入 Alpha, 蒙版)，紧贴有效 Alpha 包围盒裁切，加透明边距，Pillow 重新打开验证。
- `pipeline.py` / `cli.py`：统一可调用接口及 CLI 包装。网页复用相同核心组件。

不使用普通主体模型假装理解印花。默认路径不下载模型、不调用收费 API；可选云端路径见文末。所有自动结果和手动结果均保持 `needs_review`。背景残留标记仅基于工作边界是否有较多保留像素，属于提醒，不能检测所有残留或作为准确率。

## 数据和历史

```
data/tasks/<32位UUID>/
  original.png                 # EXIF 归一化后的不可变原图
  meta.json                    # 版本、历史索引、当前指针、导出元数据
  <revisionUUID>/
    work.png                   # 当前几何工作图 RGBA
    mask.png                   # L/8-bit Alpha
    color.png / grabcut.png / manual.png  # 生成候选时保留
  output.png                   # 当前导出；编辑后失效
```

保留规范化原图而不是复制用户路径，用户原始文件不会修改。任务不保留上传文件名用于路径构造。每次编辑写入新 revision 目录，文件用原子替换；完成后一次替换 meta.json 指向新版本。中途中断最多留下未引用的目录，不能把半写结果设为当前。新操作清除重做分支，最多保留 20 个版本。历史目录在提交后清理。候选在生成版本内同时保存；继续画笔后可通过撤销回到该版本重新切换。

单进程 uvicorn；按任务 RLock 串行修改，防止同一任务编辑、删除和导出相互覆盖。多进程 worker 不是 P0 支持模式。重启从磁盘 meta.json 恢复，不依赖内存图像、Base64 或前端缓存为事实来源。

## 请求与超时

只允许 `Host: 127.0.0.1`，浏览器 Origin 仅允许端口 7860/5173 的同机地址，跨站 Fetch 拒绝。没有开放 CORS，也没有外网绑定脚本。无 Origin 的本地 CLI 请求允许访问。

上传在 multipart 解析前限制总请求 26MB，支持分块请求计数；图片内容单独 25MB。接收总超时 30 秒。参数越界、无效几何、空蒙版均返回结构化错误。分割在线程池（最多两个）纯计算，45 秒超时返回 504；超时结果不会晚到写入任务。Python 无法强杀已开始的线程，超时计算会继续到 OpenCV 返回，这是 P0 已知边界。前端请求 100 秒中止并显示错误。

## 设计决策和回归

采用“新增实现”而非修改既有系统；三层各自拥有不同状态，前端只投影服务器已提交版本。对抗看似成功的假结果，验收同时检查交互操作、服务持久化、原图 RGB 和实际文件 Alpha。合成质量报告与功能测试分别记录；真实照片缺失不以合成替代。

源码和锁文件构成版本恢复依据；服务数据可在停止时复制整个任务目录备份。本轮只在隔离 clone 的本地分支修改，没有推送或外部发布。当前未实现跨进程锁、任务自动过期和中断 revision 的启动时垃圾回收。

实现参考：[FastAPI 文件上传](https://fastapi.tiangolo.com/tutorial/request-files/)、[OpenCV 几何变换接口](https://docs.opencv.org/4.12.0/javadoc/org/opencv/imgproc/Imgproc.html)。

## AI 生成与继续精修

核心的 `MaskProvider` 仍然只计算原工作尺寸的蒙版，不联网。官方登录及网络实现全部位于 `backend/providers/`；`CodexImageProvider`、`GrokImageProvider`、`QwenImageProvider` 提供 `generate`，返回经过格式、大小、像素和非空前景校验的 `GeneratedImage`。旧 `edit` 接口保留给既有 CLI；网页使用能区分不透明输出的生成接口。

`generated.py` 是生成文件接受规则的唯一来源。它保留服务原始字节、实际格式和解码图像。仅实际 PNG 含 Alpha、至少一个全透明像素且前景非空时，标记透明候选；JPG、无 Alpha PNG 或不透明图像仍可保存，但标为需去背景。透明判定不能证明文字或图案质量。

`app/cloud.py` 负责型号路由、单次上传/账号额度或费用确认、来源版本验证、请求去重和生成文件。请求在调用前原子写入 pending，成功写 completed，失败写 failed 与安全提示。同 ID 不重放失败或 pending 请求。相同账号的登录、检查和生成互斥；同任务沿用 Store 锁。没有持久后台队列，也不支持多个 uvicorn worker。

生成文件保存于任务根目录 `generation-<request_id>.png/jpg/webp`，同名 JSON 保存状态与来源 revision，不写入商品图或蒙版历史。格式由实际内容决定。任务编辑、撤销不会改写这些文件；删除源任务会一并删除其生成文件。

“继续精修”调用独立 `/refine` 接口，将生成文件重新校验后通过 `Store.create` 新建任务，保存来源 task、generation、provider、model。商品任务保持原版本。真正透明的候选可直接导出或继续画笔；不透明图起始 method=unprocessed，必须先生成蒙版或清理背景，导出前仍检查内容 Alpha，不能只靠透明 padding 通过。精修的商品图对照和返回入口引用源任务；源任务被用户删除后返回入口会报不存在，精修任务本身仍可用。

`App.tsx` 是当前本地任务的前端唯一状态，AI 生成记录由 `CloudEditor` 从服务读入。继续精修只通过父组件的 accept 切换任务，复用已有图像加载、画笔、撤销、导出流程。生成中冻结工作图编辑；账号登录与密码不进入 React 状态、localStorage 或任务 JSON。

## 官方账号与本机配置

`app/connections.py` 统一持有公开账号状态和每个账号的互斥锁。登录 POST 立即返回 waiting，后端限时等待官方流程，前端轮询公开状态。密码和新的 OAuth 授权由用户本人在官方页面完成；项目不复制 cookie、token 或其他应用的授权文件。检查只发公开认证请求，不创建模型轮次。响应不含邮箱、登录 URL、凭据或远端错误正文。

GPT 使用公开 Codex App Server JSON-RPC，凭据由官方 CLI 在本项目用户配置目录下的独立 codex/ 管理。模型任务只开放临时输入输出目录，禁用 shell、apps、浏览器、多代理、插件和 hooks，拒绝客户端工具与审批。仅接受当前 thread/turn 的单张 imageGeneration 完成事件，再验证文件内容；纯文本、空结果或失败事件不算成功。默认调度型号不等于底层图像型号。

Grok 使用官方 Build CLI OAuth 与 ACP cached_token 认证，凭据完全由官方 CLI 管理。生成调用受限的原生 image_edit，单轮、无搜索/子代理，仅允许图像编辑，不退回独立 API Key。只接受匹配 toolCallId 的单个 completed ImageEdit；验证路径必须位于本次显式 session UUID 与临时 cwd 对应的 images 目录。达到轮次上限后退出 1 但图像工具已完成的情形，以工具输出和文件为准；退出 0 或文字说成功不能代替图像。工具可能返回 JPG，不强行包装成透明图。

千问 Key 由 `app/settings.py` 独占读写，存在本机用户目录，原子保存，不回显。Unix 使用 0600/0700，Windows 设置当前用户和 SYSTEM ACL；这是权限保护，没有宣称加密。只向北京官方服务发请求，结果下载不携带授权头。千问真实服务仍未验证。

Windows 快捷方式复用项目 start.bat/start.ps1，使用命名互斥锁避免重复启动。原生 Windows 运行本轮未验证；保留静态与模拟结果，不将 macOS 验收当作 Windows 验收。

现场证据见 [工作台接入验收](VALIDATION_WORKBENCH_2026-10-16.md)，早先模型试验和质量复核见 [首次现场记录](VALIDATION_2026-10-16.md)。
