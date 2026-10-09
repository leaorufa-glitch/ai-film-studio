# #004 Production Integration & Hardening 施工报告

## 完成内容

- **Checkpoint A**：01/03/04/05 接入任务上下文 AI Proposal；上下文带来源与权限标签，校验结构和版本，人明确接受后才写入 Production Core。01 可整理场次与改写，03 可提议镜头，04 可提议 Clip/Brief 并检查方案，05 仅整理人工观察。图片生成接入 `gpt-image-2`，单张结果先成为 Candidate；人工采用后才成为 Asset Version。上传与生成资产共用版本体系，保留不同 provenance。
- **Checkpoint B**：独立 H3 worker 自动轮询、退避、重启恢复，生产轮询最短 180 秒；提交 request id 幂等，同 Clip 活跃任务互斥。技术重试只限暂时性错误、最多两次且需明确操作；创作重生成另走新尝试。成功后下载到本地受管媒体、校验并登记 Media Record，再创建 immutable Take。04 自动刷新并区分生成中、失败、离线；05 保持 Player First；06 继续拦截不可导出媒体。Selected Take 派生 Stable Frame / Stable Tail 时记录来源 Take、Selection、提取区间和 checksum，不升级为长期 Asset。
- **Checkpoint C**：独立 `/admin` 显示 Provider、Job、Media、Model Profile 历史、最小系统设置及 Capability Package 边界；不返回密钥。补充结构化请求与任务日志、错误分类、运行耗时及媒体缺失状态。Production Core 领域边界未修改。

## 真实渠道与数据边界

- 在独立 `output/qa-004/studio-test.sqlite` 中，真实调用 `deepseek-v4.1-flash` 生成待确认场次提案 `proposal-1a98605a01be`；正式 Scene 数未因此改变。
- 同一 **TEST ONLY QA** 数据库中，真实调用 `gpt-image-2` 生成候选 `candidate-e73255c8a55a`，媒体在 `output/qa-004/media/candidate-e73255c8a55a.png`；未自动采用。浏览器截图 01/02 展示这两项真实渠道结果。其他截图使用独立 `output/e2e/studio-test.sqlite`，其中 Job、Take、红色占位候选均明确标记 **TEST ONLY**，绝非真实 H3 影片。
- H3 生产服务器未启动，未提交真实 H3 请求，也没有 A+B+C1+C2 预览。

## 测试与浏览器取证

- Python 全量：**35/35 通过**，包含 #001/#002 既有测试与 #004 AI、图片、Runtime、Admin 新测试。
- Chromium/Playwright E2E：**7/7 通过**；覆盖 Proposal 人工确认、Candidate 采用、离线创作、TEST ONLY Take 审片与 06 导出保护、Admin 密钥隐藏。
- Next.js production build：**通过**。`git diff --check`：**通过**。
- 浏览器：真实 Chrome/Playwright，视口 **1440 × 900**，本地 `http://127.0.0.1:3001`，API `http://127.0.0.1:8001`；服务在取证后关闭。正常开发默认网站地址为 `http://127.0.0.1:3000`。

| 截图 | 页面 / 状态 |
| --- | --- |
| [01-ai-scene-proposal.png](evidence-004/01-ai-scene-proposal.png) | 01 真实 LLM 场次 Proposal，待人确认 |
| [02-image-candidate-pending.png](evidence-004/02-image-candidate-pending.png) | 02 真实图片候选，尚未采用 |
| [03-ai-shot-plan-proposal.png](evidence-004/03-ai-shot-plan-proposal.png) | 03 TEST ONLY Shot Plan Proposal |
| [04-production-offline.png](evidence-004/04-production-offline.png) | 04 制作计划与 H3 未启动 |
| [05-job-history-and-brief.png](evidence-004/05-job-history-and-brief.png) | 04 Final Brief、TEST ONLY 运行/失败记录与重试入口 |
| [06-review-test-only-take.png](evidence-004/06-review-test-only-take.png) | 05 Player First、人工观察及客观 AI 提案入口 |
| [07-timeline-empty.png](evidence-004/07-timeline-empty.png) | 06 空时间线 |
| [08-admin-overview.png](evidence-004/08-admin-overview.png) | Admin Provider、Job、Media、Profile、设置 |
| [09-admin-failed-job.png](evidence-004/09-admin-failed-job.png) | Admin 失败 Job 筛选和合规技术重试 |
| [10-timeline-test-only-export-guard.png](evidence-004/10-timeline-test-only-export-guard.png) | 06 TEST ONLY 时间线，导出禁用及中文原因 |

## 状态与剩余门槛

- `REAL_H3_FILM_VALIDATION = DEFERRED`
- `RELEASE_BLOCKER = TRUE`：H3 开机后仍需通过网站完成真实 A→B→C1→C2、连续性及最终拼接验收。现有 TEST ONLY Job/Take 不替代该验收。
- Admin 目前仅供本地单人开发使用，**尚无正式登录与权限控制**；上线前必须补齐。媒体目前为本地受管存储。此轮没有进入 #005，也没有接 Seedance。

## Git

- 实现 commit：`d78bb708045d98bfe2d86a55f37f071ac950bdeb`
- 报告与截图单独提交；提交后工作区应为 clean。
