# 已核验改动清单

本地分支 improve/providers-and-onboarding。用户已核验并授权将现有工作台功能、脚本和审核版 README 一并从本人 fork 提交 PR；不直接修改上游 main，不合并。最新状态见 [PR 验收](VALIDATION_PR_2026-10-17.md)。

## 行为变化

上传商品图后可选择 GPT 官方 Codex 登录、Grok 官方 Build 登录；千问仅保留未验证可用的实验代码。GPT/Grok 本轮各一次真实出图。生成原文件单独保留，点击继续精修创建独立本地任务，不再下载后重新上传。Grok JPG 和其他不透明结果明确提示去背景，内容没有真实透明像素时不能靠导出 padding 冒充已提取。

## 主要改动

- backend/providers/generated.py：原始字节、实际格式、Alpha 与非空前景的统一验证。
- backend/providers/grok.py、codex.py、qwen.py：官方登录生成适配及兼容旧 edit 接口；不提取凭据、不切换到其他计费方式。
- backend/app/connections.py：公开连接状态、异步本人登录、账号检查/生成互斥。
- backend/app/cloud.py、storage.py、main.py：统一生成路由、逐次同意、去重、原图下载、独立精修与来源。
- frontend/src/AccountConnections.tsx、AISettings.tsx、CloudEditor.tsx、services/ai.ts：连接、模型选择、透明状态和继续精修。
- frontend/src/App.tsx、style.css：精修任务接管、返回商品图、原图对照、完整适应预览，AI 入口置顶。
- backend/tests/test_account_workflow.py、frontend/tests/generated-refine.spec.ts 与更新的云端场景：关键状态和 UI 回归。
- README 与 docs/images：普通用户说明、真实截图、16:10 流程；架构/API/配置/验收详情在 docs。

## 验证与边界

109 项 Python、11 项浏览器通过，1 项旧素材场景跳过；前端构建通过。真实 GPT/Grok 生成→精修→下载通过，原字节保留。千问独立实测返回 403，没有图片，不列为可用提供商。Grok 的生成与自动颜色候选质量未通过，仍需手工处理；文件 Alpha 不是质量评分。Windows 原生运行未验证，CLI 与账号需官方图像权限，单进程服务，无全局账户硬预算。

凭据留在本人本机，图像只按本次确认发所选官方服务，没有读取或导出 cookie/token。提交状态以 GitHub PR 为准，不合并。
