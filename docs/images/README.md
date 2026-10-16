# README 图像来源

- `workbench.png`：真实本地工作台，独立无登录 Chrome，2026-10-16 经 Playwright 上传自制 PRINT / 2026 素材、生成候选并导出后的当前界面截图。AI 入口已在右侧顶部。没有拼造 UI，不含用户私有参考照片或账号。
- `cloud-disabled.png`：2026-10-17 当前工作台真实截图，展开 GPT/Grok 连接与模型选择，使用自制 PRINT / 2026 示例和独立临时配置；没有登录或生成请求，不展示密钥及私人参考图。千问仅标为未验证的实验配置，不在可用模型选项。
- `workflow.png`：1600 × 1000（16:10）静态用户流程图。可编辑源为 `workflow.svg` 与 `workflow.graph.json`，不是工作台截图。主流程：上传 → 提取 → 预览 → 满意直接下载；需调整或结果带背景时，继续精修后下载。安装/可选 AI 配置仅为首次准备。

仓库窄范围检查没有找到 `design.md`。流程图颜色直接读取实际 `frontend/src/style.css`：背景 #111315、面板 #191c1f、边框 #34393e、正文 #e4e6eb、次要文字 #a1aab2、强调 #b5ed7c、深色文字 #172011。结构参考已读取的 su-diagram 和 su-black-purple-gif Skill 的 graph-first 原则；用户要求静态产物，因此没有 GIF、动画或视频，也没有套用黑紫色配色。SVG 已检查文字完整、箭头方向、分支和重叠，并用 Chrome 实际渲染后查看 PNG。
