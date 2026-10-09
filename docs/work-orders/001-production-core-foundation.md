# #001 — Production Core Foundation

> 状态：READY FOR CODEX  
> 类型：Architecture Reset 后第一张正式施工单  
> 目标：建立新的 Production Core 基础，不重做完整网站。  
> 完成后必须停止，提交施工报告，等待 #002。

---

## 1. 本轮施工权威来源

施工前必须阅读：

1. `docs/MASTER-BLUEPRINT.md`
2. `docs/PRODUCTION-RULES.md`
3. `docs/DECISIONS.md`
4. 本施工单

如果旧 v12 代码、旧 Schema、旧 UI 逻辑与上述文件冲突：

> 以新文档为准。

禁止为了复用旧代码而修改新 Domain Model 的核心边界。

---

## 2. 施工目标

在当前 AI Film Studio 仓库中建立 Architecture Reset 后的新 Production Core，使以下链路在代码和测试中真实成立：

```text
Scene
→ Approved Shot Plan
→ Generation Clip Plan
→ Final Generation Brief
→ H3 Compiler
→ Compiled Generation Task
→ Generation Job
→ Take
→ Selection
→ Canonical Film State Snapshot
→ Next Clip Context
```

本轮不以完整 UI 为目标。

可以建立最小内部 Inspector / Test Harness，用于验证核心对象和链路。

---

## 3. 开工前 Repo Audit

先扫描现有代码，把与本轮相关内容分类：

### REUSE
可以原样或轻微修改复用。

### ADAPT
基础能力可保留，但接口/职责需要适配新架构。

### REPLACE
与新蓝图业务边界冲突，需要新实现。

### LEAVE ALONE
本轮无关，不动。

至少检查：

- 数据访问基础
- 当前数据库与 ORM
- 媒体存储
- 上传能力
- H3 / 视频模型 Adapter
- 服务端密钥处理
- Generation 任务基础
- 测试框架
- 当前项目/Revision 机制

Audit 结论必须进入 #001 施工报告。

---

## 4. 必须建立的核心对象

至少建立以下领域对象或等价稳定模型：

### Story / World

- Project
- Episode
- Scene
- Character
- Character Look
- Location
- Prop
- Story Fact
- Asset Version

### Directing / Production

- Shot
- Generation Clip
- Shot ↔ Clip Mapping
- Final Generation Brief
- Reference Binding
- Control Media

### Model / Runtime

- Model Profile
- Compiled Generation Task
- Generation Job

### Reality

- Take
- Selection
- Observed State
- Canonical Film State Snapshot

命名可以根据项目语言规范微调，但语义和边界不能改变。

---

## 5. 硬性 Domain Invariants

### 5.1 Shot ↔ Clip 多对多

必须支持：

```text
S01 + S02 + S03
→ Clip A
```

同时支持：

```text
S05
→ Clip C1 + Clip C2
```

禁止设计成 Shot 只有一个 `clipId` 或 Clip 只能属于一个 Shot。

### 5.2 Final Generation Brief 是一等对象

必须：

- 独立持久化
- 有版本
- 有 source/provenance
- 有 status
- 可重新编译
- 不依赖某一模型 Prompt 才能存在

禁止把 `clip.prompt` 当成生产真相。

### 5.3 Take 与 Selection 分离

同一 Clip 可有多个 Take。

Selection 指向当前采用 Take。

切换 Selection 不删除旧 Take。

### 5.4 State 分层

必须区分：

- Planned State
- Observed State
- Canonical Film State

未采用 Take 不得更新 Canonical State。

禁止只使用一个全局 `currentState` 代表整部影片。

### 5.5 Identity / Look / State 分开

Character Identity、Character Look、Current State 不能揉成一个对象。

### 5.6 Asset / Binding / Control 分开

- Asset = 长期稳定视觉媒体/版本
- Reference Binding = 某次生成中该 Asset 的具体用途
- Control Media = 首帧、尾帧、稳定尾部、临时构图图等执行控制媒体

### 5.7 历史不可破坏

Brief 修改、Selection 修改、上游重规划都不能删除旧 Take / Job / Brief version。

---

## 6. Final Generation Brief v0.1 最低合同

第一版 Brief 至少能够结构化表达：

- purpose / intent
- source Scene / Shots
- target duration
- shot timeline / CUT timeline
- subjects
- environment
- props
- state_in
- action_process
- performance
- camera
- sound
- references
- constraints
- planned_state_out
- handoff / continuation intent
- provenance / authority metadata

建议对关键字段支持权限/来源标签：

- LOCKED
- DERIVED
- PLANNED
- MODEL_SPECIFIC（主要出现在编译侧）

---

## 7. Brief QA

实现模型无关 Brief QA。

至少检查：

- purpose 存在
- source Shot timeline 完整
- duration 存在且合理
- state_in 可重建
- 核心 subject 可解析
- 关键 action 不是只有动作标签
- performance 不只有抽象情绪
- camera execution 足够明确
- sound 关系明确（如适用）
- 每个 reference 有 role
- continuity 无明显冲突
- planned_state_out 存在
- LOCKED 内容没有被下游改写

QA 失败应返回结构化 reason，不直接“补写”上游真相。

---

## 8. H3 Model Layer

第一版建立：

```text
H3 Model Profile
H3 Compiler
H3 Adapter Contract
```

已有 H3 Adapter 若可复用，可归类 REUSE/ADAPT。

但新 Production Core 不得迁就旧 Adapter 的数据形状。

### 8.1 H3 Profile

至少提供：

- model id / version
- source
- verified_at
- supported task modes
- duration envelope
- media/reference capability
- temporal controls
- audio capability
- compilation requirements

本轮不允许凭 LLM 记忆硬编码未经验证的能力。

如当前官方/API 资料不足：

> 显式标记 unknown / unverified。

### 8.2 H3 Compiler

输入：

> Final Generation Brief + Reference Bindings + H3 Model Profile

输出：

> Compiled Generation Task

至少包括：

- target model
- task/generation mode
- compiled prompt
- media bindings
- duration
- aspect ratio
- continuation source（如有）
- generation parameters
- source brief version
- compiler version
- model profile version

第一版 H3 Full-Reference Prompt 可以采用项目 H3 生产规范中的稳定结构：

- subject_definitions
- summary
- retention_analysis
- detailed_description
- overall_soundscape
- non_diegetic_music

Compiler 只能翻译和映射，不得重新导演。

---

## 9. Compilation Fidelity

必须建立最小检查，保证 Compiler 没有：

- 删除 LOCKED 约束
- 改变关键动作意义
- 改变表演方向
- 新增上游不存在的关键剧情
- 把“不哭”等明确约束反向改写

如不能忠实编译：

> 返回 compilation failure / upstream revision request。

禁止 Silent Repair。

---

## 10. Model Preflight

Brief QA 通过后，编译完成后再做 H3-specific Preflight。

至少检查：

- task mode 合法
- duration 符合当前已验证 Profile
- reference count/type 符合 Profile
- required media 存在
- continuation source 存在且来自已选择的有效 Take / Control Media
- 必要参数合法
- compiled structure 完整

最终状态：

- READY
- NOT_READY + structured reasons

---

## 11. Generation Job

真实模型请求必须成为独立 Generation Job。

Job 至少支持：

- queued
- running
- succeeded
- failed
- cancelled

Production/Dependency 层可另有：

- waiting_for_dependency

Generation Job 必须记录执行快照，能够追踪：

- Compiled Task
- Provider/Model
- Model version/Profile
- Brief version
- Compiler version
- Reference bindings
- Control Media
- generation params
- provider task id / response metadata
- error
- timing
- cost metadata（有则记录，不要求本轮做完整成本中心）

技术失败不能删除或修改 Brief。

---

## 12. Dependency / Continuation

本轮至少支持以下依赖：

```text
Clip C2
depends on
Clip C1 Selection
```

在 C1 没有 Selected Take 之前：

- C2 的导演/生产计划可以存在
- 但 continuation-specific execution task 不能最终 READY

当 C1 Selection 改变：

- 基于旧 Selection/Stable Tail 的 C2 task 应被标记 stale / needs reprepare
- 不删除历史 task/job/take

普通 CUT 不应错误要求 video continuation。

---

## 13. Take / Selection / State

### Take

真实生成结果，不可被后续修改覆盖。

派生编辑/延长应产生新 Take 或新结果对象。

### Selection

当前创作者采用决定。

Selection 改变不删除任何 Take。

### Observed State

可以由人工/AI 辅助记录 Take 实际结束状态。

### Canonical State

只有 Selected Take + 必要确认才能产生新的 Canonical Film State Snapshot。

下一 Clip Context 从 Canonical State 读取。

---

## 14. 固定 Fixture：雨夜车站

建立正式 Fixture / Seed Test，验证 Domain 表达能力。

### Scene

雨夜旧车站候车厅。林夏打开旧信，认出失踪多年的母亲的字迹。她没有哭。远处列车进站，她收起信，起身走向站台门口。

### Shot Plan

- S01 · 3s：中近景，林夏坐着展开旧信。
- S02 · 2s：信件特写，出现可识别的关键字迹/署名信息。
- S03 · 5s：回人物。认出字迹，停顿，不哭，呼吸变浅，手指压住纸边，慢慢抬眼。
- S04 · 6s：CUT 到新的过肩/侧后机位，看向站台，远处列车灯出现。
- S05 · 20s：一个连续长镜头。折信 → 起身 → 穿过候车厅 → 走向站台门口 → 稳定停住。

### Expected Clip Plan

#### Clip A
- S01 + S02 + S03
- 约 10s
- MULTI_SHOT_ONE_PASS

#### Clip B
- S04
- 约 6s
- 普通 CUT / 新机位
- State Continuity
- 不做 Video Continuation

#### Clip C1
- S05 前半段
- 约 12s
- 同一长 Shot 第一段

#### Clip C2
- S05 后半段
- 约 8s
- VIDEO_CONTINUATION
- 依赖 C1 Selection + Stable Tail / continuation source

Fixture 用于验证模型，不代表产品硬编码该规划。

---

## 15. 自动测试最低清单

必须覆盖：

1. 多 Shot → 一个 Clip。
2. 一个 Shot → 多 Clip。
3. Shot ↔ Clip 映射顺序/范围可表达。
4. Brief 可创建新版本，旧版本保留。
5. 修改 Brief 不删除旧 Take。
6. 同 Clip 可拥有多个 Take。
7. Selection 可 A → B 切换，A 仍保留。
8. 未采用 Take 不能更新 Canonical State。
9. Selected Take + confirmed observed state 可形成新 State Snapshot。
10. 普通 CUT 不要求 video continuation。
11. continuation Clip 无上游 Selection 时不能 READY。
12. 上游 Selection 改变后，旧 continuation task 被识别为 stale/needs reprepare。
13. Generation Job failed 不破坏 Brief。
14. Retry 产生新的 Job 或安全复用 provider task，不污染创作层。
15. 重新编译不能修改 Shot / Final Brief。
16. Compiler 不能丢失 LOCKED 约束。
17. Historical execution snapshot 能追溯 Brief/Compiler/Profile/References。
18. Fixture 可以表达完整 A/B/C1/C2 关系。

---

## 16. 本轮不做

禁止扩大范围到：

- 完整 01–06 页面重做
- 大规模 UI/视觉设计
- Seedance 完整接入
- 自主多 Agent 社会
- AI 审片总评分
- 完整 NLE/剪辑器
- 全项目旧数据迁移
- 多用户复杂权限
- 完整成本中心
- Storyboard 自动生成系统
- 为测试 UI 制造假 Storyboard/假生成视频

可以做最小 Inspector/Test Harness，但它不是正式 Creator UI。

---

## 17. 数据库/基础设施原则

不要因为本轮重建就自动更换数据库/云基础设施。

先验证现有关系型基础能否支持：

- 独立核心对象
- 多对多
- versioning
- dependency
- state snapshots
- job tracking
- impact analysis

如果当前基础存在真正阻断：

> 写入施工报告，提出迁移建议。

不要自行启动大范围基础设施迁移。

---

## 18. 完成验收

#001 不能以“Schema 已建”作为完成。

必须证明 Fixture 可以完成：

```text
Scene
→ 5 Shots
→ 4 Generation Clips
→ 4 Final Briefs
→ H3 Compiled Tasks
→ Generation Jobs
→ Takes
→ Selection
→ Canonical State
→ Next Clip Context
```

真实 H3 成片调用不是 #001 的强制完成条件；真实端到端视频生成属于 #002。

但：

- 不能用假视频冒充真实 H3 生成验收。
- 如果当前环境可以安全调用 H3，可以做辅助验证，并在报告中明确标注。

---

## 19. #001 施工报告格式

完成后创建/返回：

`docs/reports/001-production-core-foundation-report.md`

必须包含：

1. 实际完成内容
2. Repo Audit：REUSE / ADAPT / REPLACE / LEAVE ALONE
3. 新增核心对象
4. Shot ↔ Clip 实现
5. Final Brief 结构与版本机制
6. H3 Model Profile
7. H3 Compiler
8. Brief QA / Model Preflight
9. Generation Job
10. Take / Selection / State
11. Dependency / Continuation
12. 自动测试结果
13. 雨夜车站 Fixture 验证结果
14. 已知技术债 / 风险
15. 明确没有做的内容
16. 数据库/基础设施是否存在阻断
17. Git commit
18. 当前工作区是否 clean

---

## 20. Stop Condition

完成 #001 后必须停止。

不要自行进入：

- #002 H3 Vertical Slice
- UI 重建
- Seedance
- 旧数据全迁移

等待 Master Planner 验收。

验收结果只会是：

- PASS → 发 #002
- PARTIAL → 发修正单
- FAIL → 返回架构层纠正
