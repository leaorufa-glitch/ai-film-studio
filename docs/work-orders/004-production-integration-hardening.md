# #004 — Production Integration & Hardening

> 状态：READY FOR CODEX  
> 前置条件：#001 CLOSED；#003 FULL PASS / CLOSED；#002 Real H3 Film Validation 仍因 H3 生产服务器按需关机而 DEFERRED。  
> 本轮性质：把“已经成形的网站”升级为“真正能稳定使用 AI / 图片 / 视频生产服务的创作平台”。  
> 本轮完成后停止，等待 Master Planner 验收；不得自行进入 #005 Release Candidate & Launch。

## 0. 省额度模式

本轮继续使用省 Codex 额度模式：

- 不重新通读全部历史文档。
- 不重新分析已冻结架构。
- 只读取与本轮任务直接相关的代码、测试、最近报告和必要权威文档。
- 施工中优先跑相关测试，Checkpoint 完成后再做一次全量回归。
- 不反复生成长篇解释。
- 不为已明确的问题重新做多套方案比较。
- 不重复做无价值的大规模截图。
- 如果现有实现可小改完成，禁止为了“更漂亮的架构”大面积重写。

稳定原则如已有 `AGENTS.md`，优先遵守；若尚无，可创建一个精简项目级 `AGENTS.md`，只收录长期冻结规则，不复制整套 Blueprint。

## 1. 本轮目标

把 #003 的 Creator Website 从“完整产品主体”推进为“真实生产可用”。

核心链必须变成：

```text
Creator UI
→ Contextual AI Proposal
→ Human Confirm
→ Formal State
→ Production Planning
→ Final Brief
→ Compiled Task
→ Generation Job
→ Provider
→ Media
→ Take
→ Review
→ Selection
→ Canonical State
→ Next Clip
```

本轮重点解决：

1. Contextual AI 接入。
2. 图片生成 / 视觉资产接入。
3. Generation Job 自动状态跟踪。
4. Provider / Media / Retry 生产化。
5. Admin / Ops Console。
6. 数据一致性、错误恢复与运行稳定性。
7. 为未来 Professional Library / Agent / Skill 扩展保留正确边界。
8. H3 开机时完成真实 A→B→C1→C2 网站端影片验证；若仍关机，不阻塞其它施工，但继续作为 #005 前 Release Blocker。

## 2. 不改变的冻结架构

必须保持：

- Production Core 是正式项目真相。
- UI 不直接写数据库。
- AI 输出先是 Proposal，不静默进入正式状态。
- Prompt 不是项目真相。
- Shot = 导演语言。
- Clip = 生成执行单元。
- Take immutable。
- Selection 与 Take 分离。
- Planned / Observed / Canonical 分离。
- No Silent Repair。
- 普通 CUT ≠ Video Continuation。
- Control Media ≠ 长期 Asset。
- 真实媒体才占大空间。
- 04 Production First。
- 05 Player First。
- 上游修改不删除历史，下游标影响。
- Provider 离线时仍可继续创作。

如果本轮实现要求破坏这些边界，停止并报告，不得 UI hack。

## 3. Checkpoint A — Contextual AI + Image Integration

### 3.1 Contextual AI

接入项目当前大语言模型渠道，但 AI 只在任务上下文中出现，不做永久聊天侧栏。

最低支持：

#### 01 剧本
- 整理为 Scene Proposal
- 改写选中段落
- 调整节奏 / 克制程度 / 情绪方向
- 检查故事事实冲突
- 输出结构化 diff / proposal

#### 03 场次与分镜
- 根据 Scene 提议 Shot Plan
- 补充动作过程
- 将抽象情绪改成可见表演
- 给出导演方案解释
- 检查 Shot 是否缺导演信息

#### 04 影片制作
- 提议 Clip Plan
- 解释为什么多 Shot 合并 / 长 Shot 拆分
- 提议 Final Brief
- 对 Brief 做模型无关 QA 建议
- 不得直接写 Raw Prompt 作为用户主要对象

#### 05 审片
本轮 AI 只做客观辅助：
- 记录用户输入的观察
- 可为未来视觉分析留接口
- 不做主观电影评分
- 不自动替用户选 Take

### 3.2 AI Proposal Contract

所有 AI Proposal 必须包含：

- source context
- proposal type
- structured proposed change
- human-readable explanation
- provenance
- model / provider metadata
- created_at
- accepted / rejected / superseded 状态

流程：

```text
Formal State
→ Context Assembly
→ LLM
→ Structured Output
→ Schema Validation
→ Authority Validation
→ Proposal
→ Human Accept
→ Formal Write
```

不能让 LLM 直接写正式数据库。

### 3.3 Context Assembly

只给任务相关上下文，不把整个项目全部 dump 给 LLM。

至少支持：
- 当前 Scene
- 必要 Story Facts
- 当前 Character / Look / Location / Prop
- 已确认 Shot
- 当前 Canonical State
- 当前 Creator Preference
- 任务需要的 Model Knowledge

每个 context item 应可追溯 source / authority。

未知信息允许返回 Unknown，不得自动编造。

## 4. 图片生成与视觉资产

如果当前中转站图片模型接口已可用，本轮正式接入。

### 4.1 用途

至少支持：
- Character Identity 候选
- Character Look 候选
- Location 候选
- Prop 候选

后续可扩展 Storyboard，但本轮不要把 Storyboard 变成强制步骤。

### 4.2 生成结果

生成结果先是 Candidate Asset Version。

必须由人：
- 采用
- 拒绝
- 再生成

只有采用后才成为当前 Asset Version。

禁止：
- 自动把图片生成结果当正式资产
- 自动把 Take 截图升级成 Character Master Asset
- 把控制帧和长期 Asset 混为一谈

### 4.3 上传与生成统一

上传图片与模型生成图片都进入同一个 Asset Version 体系，但 provenance 不同。

## 5. Checkpoint B — Generation Runtime Productionization

### 5.1 自动 Job 状态跟踪

#003 的人工“稍后同步”必须升级。

实现：
- create job
- provider task id
- 后台 polling
- backoff
- queued / running / succeeded / failed / cancelled
- 自动更新 Job Event
- 成功后下载并持久化媒体
- 创建 Take
- UI 实时或周期更新状态

前端不需要用户反复手动点刷新。

### 5.2 技术重试 vs 创作重生成

继续严格区分：

#### Technical Retry
- timeout
- 429
- transient provider error
- 临时网络错误

不得改变 Final Brief。

#### Creative Regenerate
- 表演不对
- 身份漂移
- 动作漏失
- 连续性不好
- 用户不喜欢

产生新的创作尝试 / Take。

UI 文案要不同。

### 5.3 Retry Guard

- 不自动无限重试
- 明确最大技术重试次数
- exponential/backoff 或合理策略
- 记录 retry_of
- 保留失败 Job
- 不覆盖历史

### 5.4 Provider Health

Creator App 只显示：
- 可用
- 未配置
- 服务未启动
- 暂时异常

详细 endpoint / raw error / task id 留给 Admin。

### 5.5 Provider Adapter Boundary

至少整理：
- LLM Adapter
- Image Adapter
- H3 Video Adapter

不得把 Darl 专有逻辑渗入 Production Core。

未来 Seedance 只能加：
- Model Profile
- Compiler
- Adapter

而不是重写 Shot / Clip / Brief。

## 6. Media Productionization

### 6.1 Media Record

所有真实媒体统一有 Media Record：

- id
- kind
- source
- mime
- size
- checksum
- duration
- width / height
- created_at
- provider source
- project ownership
- storage location
- test_only flag

### 6.2 Durable Boundary

本轮允许继续本地 managed media，但必须做到：

- provider URL 不是长期媒体真相
- provider 成功后尽快下载
- checksum
- 可验证文件存在
- 对象存储替换边界稳定

### 6.3 Derived Control Media

支持从 Selected Take 派生：
- stable frame
- stable tail clip
- continuation source

必须记录：
- derived_from_take
- selection version
- role
- extraction range
- checksum

不能自动升级为 Master Asset。

## 7. H3 Real Film Validation（条件执行）

H3 服务器如果本轮施工期间被用户开启，则继续 #002 延期验证。

必须通过网站完成：

```text
04 Clip A Generate
→ 自动 Job tracking
→ Real H3
→ Media
→ Take
→ 05 Review
→ Human Selection
→ Observed
→ Canonical
→ Clip B
→ C1
→ Stable Tail
→ C2 Video Continuation
→ 06 Timeline
→ A+B+C1+C2 Preview
```

重点验证：

- Clip A 多 Shot one-pass
- A→B 普通 CUT + state continuity
- B→C1 state continuity
- C1→C2 true video continuation
- H3 offline → online 恢复
- failure → technical retry
- media 回传
- Selection 改变导致 downstream stale

### 若 H3 仍关机

允许 #004 其它内容继续并通过。

但报告必须明确：

```text
REAL_H3_FILM_VALIDATION = DEFERRED
RELEASE_BLOCKER = TRUE
```

#005 上线前必须完成。

## 8. Checkpoint C — Admin / Ops Console

新增独立 Admin / Ops Console。

Creator App 和 Admin 必须逻辑分离。

建议路径：

```text
/admin
```

本轮不需要完整企业权限体系，但结构必须独立。

### 8.1 Admin 首页

至少展示：

- LLM 状态
- Image Provider 状态
- H3 状态
- 最近 Generation Jobs
- 失败 Job
- 媒体存储概况
- Model Profile 当前版本
- 最近错误

### 8.2 Provider 管理

至少可查看：
- Provider name
- model
- status
- base URL（隐藏敏感信息）
- last checked
- last error
- configured / unconfigured

Secrets：
- 不显示真实 API Key
- 不允许前端读取明文
- 只显示 configured / not configured

### 8.3 Generation Jobs

可筛选：
- queued
- running
- succeeded
- failed
- cancelled

可查看：
- project
- clip
- task
- provider task id
- retry chain
- timings
- error category
- media result

允许：
- 对合规失败 Job 发起 Technical Retry
- 不允许 Admin 随意改 Brief 真相

### 8.4 Media

查看：
- media kind
- project
- source
- size
- duration
- checksum
- missing / available
- test_only

本轮不做复杂 DAM。

### 8.5 Model Profiles

只读 + 版本查看优先。

允许管理员查看：
- verified/unverified
- source
- verified_at
- hard capabilities
- reliability knowledge

编辑能力如果实现，必须版本化，不能覆盖历史。

### 8.6 System Config

只做最小必要项：
- feature flags
- provider enable/disable
- polling settings
- retry settings

不要做巨型配置后台。

## 9. Professional Library 扩展边界

本轮不正式建设完整 Professional Library。

但需要为未来保留领域边界，不要让未来 Agent/Skill 只能靠硬编码。

至少设计可扩展概念，不必完整 UI：

```text
Capability Package
- type: agent | skill | style | format | technique | model_knowledge
- id
- name
- version
- status
- scope
- applicability
- dependencies
- provenance
- published_at
```

当前只做 schema/interface/registry 边界或最小 placeholder。

不要在本轮实现几十个 Agent / Skill。

未来目标是 Admin 管理能力包，Creator 前台只看自然语言选择/推荐。

## 10. Data Integrity / Hardening

本轮检查并强化：

- version conflict
- transaction boundaries
- duplicate job submission
- idempotency
- stale selection
- stale compiled task
- media missing
- provider success 但下载失败
- provider timeout
- app restart 后 polling 恢复
- user refresh 后状态恢复
- concurrent read/write 基础保护

不要为了“上线架构”过早大迁移。

如果 SQLite 仍能满足本地单人 + #004 测试：
- 继续使用
- 强化边界

如果明确成为阻断：
- 报告证据
- 再决定数据库迁移

不要仅因为“正式产品应该用 Postgres”就迁移。

## 11. Creator UX Hardening

重点补齐真实生产状态：

### 04
- 生成中进度状态
- 可离开页面
- 自动更新
- Technical Retry
- Creative Regenerate
- failure reason 人话化
- provider offline / online 恢复

### 05
- 真 Take 播放
- Take A/B 切换
- Selection
- Observed / Canonical
- continuation suitability
- 稳定帧/Stable Tail 选择入口（若真实 H3 验证执行）

### 06
- 真实媒体 timeline
- preview
- export
- missing media 防护
- current Selection 防护

## 12. 运行与恢复

本轮必须考虑服务重启：

- FastAPI 重启后历史 Job 不丢
- polling worker 可恢复未完成任务
- Next.js 重启不影响生产状态
- Provider 临时离线后可恢复
- 不因为前端关闭就丢任务

可以使用简单可靠的本地 worker / background task 方案。

不要求上分布式队列，除非现有结构真的需要。

## 13. Observability

不建复杂 APM，但至少：

- structured logs
- request id / job id
- error category
- provider latency
- job duration
- media download duration
- retry count

Admin 可查看关键失败信息。

Secrets 不进入日志。

## 14. Security

继续保证：

- Secrets server-only
- `.env*` ignored
- 前端无 API key
- Admin 不展示 secret
- 上传类型 / 文件签名检查
- 路径 traversal 防护
- 基础 request validation
- provider raw response 中的敏感字段不直接展示

本轮仍可保持本地开发无登录，但必须在报告标明：
- Admin 尚无正式 auth
- #005 上线前必须补登录/权限

## 15. 测试策略

### 施工中
只跑相关测试。

### Checkpoint 完成后
跑该 Checkpoint 集成测试。

### #004 完成后
统一全量回归一次。

最低新增覆盖：

#### Contextual AI
1. proposal 不直接写 formal state
2. accept 才写正式版本
3. reject 不改状态
4. context assembly 不注入无关全项目
5. malformed LLM output 被拒绝

#### Image
6. generated candidate asset 不自动采用
7. adopt 生成新当前 Asset Version
8. provenance 正确

#### Runtime
9. create → polling → succeeded → media → take
10. provider failed → structured Job failure
11. transient technical retry preserves Brief
12. duplicate submit guard
13. app restart resumes pending job
14. provider success but media download failure handled
15. stale Compiled Task cannot silently execute

#### Continuity
16. stable tail only from selected real Take
17. C1 Selection change invalidates C2
18. control media retains provenance

#### Admin
19. provider status visible without secret
20. failed jobs query
21. technical retry permission path
22. media missing state
23. model profile history

#### Creator
24. 04 auto status refresh
25. 05 real Take flow（自动化可使用 TEST ONLY adapter）
26. 06 invalid media export guard
27. provider offline → continue planning

### H3 real
真实 H3 测试单独运行，永远不进入普通 CI。

## 16. Browser QA

本轮不再做几十张截图。

关键取证即可：

- 01 AI proposal
- 02 generated asset candidate / adopt
- 03 AI Shot Plan proposal
- 04 generating / failed / retry / provider offline
- 05 Take review
- Admin provider status
- Admin failed job
- 06 real/test media state

约 8–12 张关键截图足够。

如果 H3 真开机，再额外提供：
- Clip A
- B
- C1
- C2
- Final preview

## 17. 本轮明确不做

不要做：

- 正式多用户团队协作
- 完整组织/角色权限
- 付费订阅
- 成本账单中心
- 完整 Professional Library 管理器
- 大量 Agent / Skill / Style Pack
- Seedance 正式接入
- 多模型智能路由
- Premiere 级 NLE
- AI 主观总评分
- 自动无限生成
- 全量线上部署
- 域名 / CDN / 正式 Release

这些属于后续。

## 18. #004 完成标准

### Creator
- AI Proposal 真能在 01/03/04 工作
- 图片生成/上传可进入统一资产体系
- Provider 离线不阻塞创作
- Generation Job 自动跟踪
- Take 回来后能审片/采用/确认 Canonical
- 06 能安全使用真实媒体

### Runtime
- Job 自动 polling
- restart 恢复
- retry 受控
- media durable
- idempotency
- 历史完整

### Admin
- 有独立 Admin Console
- Provider / Job / Media / Profile 可查看
- 技术错误不污染 Creator UI
- Secret 不泄露

### Architecture
- 无第二套真相
- AI 不静默写状态
- Provider-specific 逻辑不污染 Production Core
- Professional Library 有扩展边界

### H3
如果服务器开启：
- 完成 A→B→C1→C2 真实影片验收

如果未开启：
- 明确延期并保留为 Release Blocker

## 19. 施工报告

创建：

`docs/reports/004-production-integration-hardening-report.md`

保持比 #003 报告短，重点写结果。

包含：

1. 实际完成
2. Contextual AI
3. Image Integration
4. Generation Runtime
5. Retry / Idempotency
6. Media
7. Continuity
8. Admin Console
9. Data Hardening
10. Browser QA
11. 自动测试
12. H3 Real Film Validation 状态
13. 已知问题
14. Release Blockers
15. Git commits
16. workspace clean

不要写冗长过程复盘。

## 20. Git / Stop Condition

建议 Checkpoint A/B/C 各一到两个清晰 commit。

不要 push 到旧仓库。

完成后：

- 全量 tests
- E2E
- production build
- git diff --check
- workspace clean

然后停止。

不要自行进入：

> #005 Release Candidate & Launch

等待 Master Planner 验收。
