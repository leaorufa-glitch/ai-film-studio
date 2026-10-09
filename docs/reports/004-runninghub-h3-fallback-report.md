# RunningHub H3 备用 Provider 接入报告

## 结果

- 首选仍为本地 Darl / Self-host H3；RunningHub 仅作为创作者明确选择的备用通道。04 在本地 H3 未启动时提示可选备用服务，不静默切换。每个 Generation Job、Runtime、Media 和 Take provenance 记录实际 Provider 与上游 task ID。
- RunningHub Adapter 从服务端 `RUNNINGHUB_API_KEY`、`RUNNINGHUB_WEBAPP_ID` 读取配置，支持图片 / 音频 / 视频参考文件上传、工作流提交、任务轮询、结构化失败和成功媒体下载。重启后按持久化 Provider 继续查询原任务。未改动 Production Core 的 Shot、Clip、Final Brief、Take、Selection、Canonical State 设计。
- Final Brief 仍经 Core 编译为 H3 Compiled Task，再由所选 Adapter 转成工作流节点。技术重试沿用原 Provider 与 Brief；切换 Provider 需明确以创作重生成提交。
- 已通过 RunningHub 的只读节点查询确认工作流节点存在。**没有提交真实生成任务，也没有真实 RunningHub 视频或 Take。** 用户提供的 API Key 未写入源码、文档、测试数据或 Git；前端仅获得配置状态。
- 备用工作流的视频参考节点仅按 motion/camera reference 使用。`VIDEO_CONTINUATION` 在 Profile、Adapter、API 和 UI 均被禁用。只有实际完成 C1 Stable Tail → C2 的同一长镜头连续性验证后，才能改变此状态。

## 验证

- Python 全量：**42/42 通过**；RunningHub 测试覆盖上传节点、鉴权差异、提交、查询、失败、下载、持久化 Provider、重启恢复、媒体 provenance、显式切换及续接拦截。外部生成链路使用 TEST ONLY Adapter。
- Chromium/Playwright E2E：**8/8 通过**，包括本地离线提示、备用显式选择和续接禁用。
- Next.js production build 与 `git diff --check`：**通过**。
- RunningHub 工作流映射采用约 0.4MP 与工作流内部步数；实际输出是否达到 480P / 20 步尚未由真实影片验证，界面已提示该限制。上线使用前需在服务端配置两个环境变量。

## 范围

H3 真实 A→B→C1→C2 影片验收仍延期。未进入 #005，未接 Seedance。目标 GitHub 仓库尚为公开且拥有者凭证失效，因此本次不推送；本地提交和工作区状态见交付回复。
