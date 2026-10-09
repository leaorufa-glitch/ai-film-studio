# #002 H3 Real Vertical Slice — 施工报告（当前未通过）

状态：**BLOCKED_AT_REAL_CREATE / System 未通过 / Film 未验收**。本报告记录 2026-10-09 实际施工证据；不得把离线合同测试当作真实影片结果。

## 1. 官方 H3 能力验证来源与日期

2026-10-09 阅读 [MiniMax H3 创建任务文档](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)、[任务查询文档](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)、[价格页](https://platform.minimax.io/docs/pricing/overview) 和 [MiniMax-H3 官方 Prompt Guide](https://github.com/MiniMax-AI/MiniMax-H3)。官方公开模型 `MiniMax-H3` 为 4–15 秒整数输出、768P/2K，支持文本、首尾帧与参考图片/视频/音频；首尾帧模式与参考模式互斥。另阅读用户提供的 [Darl MiniMax H3 API 使用说明](https://fwr0187eq6.apifox.cn/9352472m0)：本项目实际从 `https://api.darl.cn/v1/videos` 请求自建 H3 服务，公开任务状态为 queued/processing/succeeded/failed；代理可用 384P/480P/768P，1–100 步，支持 Data URI 与公开 URL。官方云端价格仅作估算参照，不是自建中转站的账单。

## 2. H3 Model Profile

新增版本化 `h3-darl` Profile，分开记录官方模型边界与 Darl 代理能力、来源和核对日期。当前版本 1 的阶段是 `DOCUMENTED_PENDING_REAL_REQUEST`，**尚未提升为 VERIFIED**：模型列表无费用查询确认公开模型名为 `MiniMax-H3`，但首个真实创建任务失败。未验证的真实生成可靠性没有写入 Hard Capability。

## 3. Real H3 Adapter

`film_core/darl_h3.py` 实现 Darl `POST /v1/videos`、`GET /v1/videos/{id}`、`GET /v1/videos/{id}/content` 和 DELETE 合同。请求将内部 Reference Role 映射为 `reference_image` / `reference_video` / `reference_audio` / 首尾帧，检查模式互斥、参考数量、文本长度和 Turbo/步数关系。Provider 错误被结构化分类；没有自动提交重试。创建任务已真实请求代理，但未得到公开任务 ID。

## 4. Credential / secret

使用用户明确授权的自建中转站 key。Runner 只从交互 stdin 读取后放入单次进程环境；源码、Fixture、报告、Git 与输出文件均不保存 key。`GET /v1/models` 成功列出 `MiniMax-H3`，因此本轮并非缺凭证。

## 5. Media persistence

已实现本地 managed media 目录、下载后的 SHA-256/文件大小/MIME/时长记录、Media Record 与真实 Take 的强制关联，留有对象存储替换边界。由于创建失败，**尚无真实媒体文件**。当前目录 `output/h3-002-2026-10-09/` 仅有执行数据库。

## 6. Clip A 实际任务与结果

来源：`station-scene`、S01/S02/S03、Clip A、Final Brief v1 → Brief QA READY → H3 Compiler `h3-compiler/0.1` → Compiled Task → Model Preflight READY。Project 决定 16:9；执行参数 10s、768P、20 步、Turbo=false、无参考素材的 T2VA。计划估算参照 MiniMax 公开 768P 单价约 US$0.80；自建服务实际价格/资源消耗未知。

真实 Compiled Task：`task-A-20261009T084845Z`；Job：`job-A-20261009T084845Z`。Darl 创建接口返回 HTTP 404，业务码 `fail_to_fetch_task`，错误消息为上游“页面未找到”的 HTML。没有返回公开任务 ID；Job 记录为 failed，未自动重提。推测是 Darl MiniMax-H3 渠道上游地址/服务路径不可达，需由渠道配置或服务日志确认；不能仅凭该错误断言一定没有上游任务产生。

## 7. Clip A Selection / Canonical State

无真实 Take，故无人工 Selection、Observed State 或 Canonical Snapshot。后续 Clip 按依赖规则保持不可执行。

## 8. Clip B 实际任务与结果

未提交。普通 CUT + Visual Anchor 的 Adapter 映射及 Selection 失效合同已通过离线测试；缺 A Selected Reality 与真实稳定帧。

## 9. Clip C1 实际任务与结果

未提交。缺 B Selected Reality。

## 10. Stable Tail

未提取。缺 C1 真实 Selected Take 和确认后的 Canonical State。

## 11. Clip C2 Video Continuation 实际任务与结果

未提交。真实 Stable Tail、上游 Selection 与 Canonical Snapshot 均缺失；没有以普通参考视频冒充真正续接。

## 12. 拼接预览路径

**不存在**。脚本只会在 A/B/C1/C2 四条真实 Take 均经人工 Selection 与 Canonical 确认后做简单顺序拼接。

## 13. Take 追溯

当前真实 Take 数为 **0**。Clip A 的 Brief v1、Profile v1、Compiler、Compiled Task、Job 和失败事件保存在 `output/h3-002-2026-10-09/production.sqlite`；无 provider task id、媒体、Selection、Observed 或 Canonical State。测试中的 `test-only://` 结果仅在临时内存数据库，不在真实执行数据库。

## 14. Technical Retry / Creative Regenerate

实际技术提交 1 次、失败 1 次、重试 0 次；创作性重生成 0 次。Runner 限制每 Clip 一次候选；再次提交 A 必须指明失败 Job、显式技术重试且确认渠道已修复。没有自动轮询或无限重试。

## 15. 测试结果

`python3 -m unittest discover -s tests -v`：**12 tests passed**，包含 #001 原有 6 项与 #002 离线 Adapter/Media/Dependency 合同 6 项。`python3 -m compileall -q film_core scripts tests` 通过。真实付费调用与普通单元测试分离。真实调用结果是 A 创建失败，**不计为端到端通过**。

## 16. 实际花费 / usage

Darl 未返回公开任务 ID、usage 或账单记录；实际资源消耗未知。用户说明 H3 为自建开源模型，不以货币费用作为阻断，但仍遵守单候选及明确技术重试保护。

## 17. 影片人工审片备注

无可审片视频；Film PASS **未验证**。不能评价多镜头节奏、不哭的表演、A→B CUT 或 C1→C2 连续性。

## 18. 已知问题

1. 自建 H3 渠道创建任务时收到上游 404，需检查 Base URL、端口、`/v2/video_generation` 路由以及服务日志。
2. 首次错误没有公开任务 ID，不能通过 New API 查询该请求是否创建了上游任务。
3. 自建代理实际输出与参考视频连续性的可靠性尚未经真实素材验证。
4. 本地人工 Selection 使用显式操作者输入；正式网站的身份/权限属后续工作。

## 19. Git commits

#001 已验收 HEAD：`7517ec08dceb18b8e0a94819dd661806ecca7a6e`；#002 施工单提交：`6aab6cf219908f1ccf9a9947942f7ba336830e04`。本报告与实现提交的最终哈希以提交后的 `git log -1 --format=%H` 为准。

## 20. 工作区状态

报告提交后以 `git status --porcelain` 实测为准。真实输出数据库/媒体位于忽略的 `output/`，不会进入 Git。

## 21. 范围

明确**没有进入 #003 正式网站**，也没有 Seedance、2K 批量候选、AI 总分或重后期。#002 需在 H3 渠道修复后继续执行四条真实 Clip 与人工影片验收，当前不能宣称 PASS。
