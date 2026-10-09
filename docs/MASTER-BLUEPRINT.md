# AI Film Studio — Master Blueprint v0.1

> 状态：Architecture Reset 后的项目最高蓝图  
> 适用范围：产品、AI Production Core、系统架构、Codex 施工、Work 设计与验收  
> 规则：若施工实现与本蓝图冲突，以本蓝图为准；需要改变已冻结原则时，必须先更新蓝图/决策记录，再施工。

---

## 0. 项目最高目标【已冻结】

AI Film Studio 不是 AI 工具集合，也不是传统影视项目管理软件。

项目目标是：

> 帮助创作者从故事和创作意图出发，由 AI 承担大量专业创作、生产规划和模型执行工作，持续生成真正能够进入最终影片的高质量视频，并自然组合成完整影片。

最高判断标准不是功能数量、Prompt 长度、模型数量或页面复杂度，而是最终影片质量。

核心优化目标：

- 画面更对：正确实现故事和导演意图。
- 表演和镜头更好：动作、表演、摄影、声音具有可信的电影表达。
- 前后更连续：人物、世界、道具、情绪、空间和剧情状态能够延续。
- 生成更聪明：正确决定一次生成、拆分、CUT、续接、首尾帧等策略。
- 返工更少：问题能够回到真正的责任层，而不是反复盲目重试。
- Clip 更接近成片：生成结果尽量可以直接进入最终影片，而不是松散素材。

项目总原则：

> Generate for the Final Film，而不是 Generate and Fix Later。

---

## 1. 三层产品模型【已冻结】

### 1.1 用户层

创作者直接看到和操作的内容：

- 剧本
- 人物与世界
- 场次与分镜
- 影片制作
- 审片
- 成片

用户主要负责：

> 创作意图、品味、重要决定、最终采用。

### 1.2 系统层

系统承担：

- 项目事实与版本
- 资产与媒体
- Continuity / Film State
- Context Assembly
- Production Planning
- Final Generation Brief
- QA
- Compiler
- Agent / Skill Runtime
- Generation Runtime
- 任务依赖
- 模型能力档案
- Take / Selection / Final Timeline

### 1.3 AI 模型层

实际执行能力：

- LLM
- 图片模型
- 视频模型
- 音频模型
- Vision / 理解模型

原则：

> 系统可以复杂，用户不应因此复杂。

---

## 2. 用户与 AI 的职责【已冻结】

用户主要负责：

- “我要什么”
- “这样拍对不对”
- “这种感觉对不对”
- “这条 Take 我要不要”
- “是否接受实际生成变化”

AI 主要负责：

- 故事理解与结构化
- Scene 理解
- Shot 设计
- 表演 / 摄影 / 声音深化
- 当前场次视觉准备判断
- Shot → Clip 制作规划
- Reference Planning
- Final Generation Brief 构建
- Model-aware 适配
- Prompt / Task 编译
- 生成前检查
- 客观/结构性审片辅助
- Continuity 状态观察与建议

系统主要负责：

- 记住正式事实
- 维护版本与依赖
- 防止下游静默改写上游
- 管理资产和媒体
- 管理模型任务、失败、重试与并行
- 维护 Selected Reality / Canonical State

原则：

> 人负责意图、品味和最终决定；AI 负责专业创作与生产推理；系统负责状态、执行和不把项目搞乱。

---

## 3. 创作者工作区【方向冻结】

项目工作区采用六个一级创作空间：

1. 01 剧本 — “发生什么？”
2. 02 人物与世界 — “重要的人和世界长什么样？”
3. 03 场次与分镜 — “这一场怎么拍？”
4. 04 影片制作 — “怎样让当前视频模型最好地生成？”
5. 05 审片 — “这条我要不要？”
6. 06 成片 — “组合以后这部片成立吗？”

这六个工作区不是硬关卡。用户可以回到上游修改，系统负责分析修改影响。

重要 UX 原则：

- 媒体只有真实存在时才占大空间。
- 03 没有真实 Storyboard 时不制造假的大预览图。
- 04 不做 Player First；核心是制作计划和最终制作方案。
- 05 因为已有真实视频，采用 Player First。
- Agent / Skill 不作为一级用户导航。
- 默认不让用户管理 Prompt、Asset ID、Reference 权重等内部参数。
- AI 不必长期占据半屏 Chat；AI 应融入当前工作区上下文。

---

## 4. 核心生产链【已冻结】

```text
创作意图
→ Story / World Truth
→ Scene
→ Director Shot Plan
→ Production Planning
→ Generation Clip Plan
→ Context Assembly
→ Final Generation Brief
→ Brief QA
→ Model Compiler
→ Compiled Generation Task
→ Model-specific Preflight
→ Generation Runtime
→ Video Model
→ Take
→ Human Review
→ Selection
→ Observed Reality
→ Canonical Film State
→ Next Clip Context
→ Final Timeline
→ Final Film
```

核心思想：

> AI Film Studio 的主要智能投入发生在视频生成之前。

---

## 5. Scene / Shot / Clip / Take【已冻结】

### Scene

叙事、时间与空间单位。

回答：

> 这一场发生什么，为什么发生。

### Shot

导演/电影语言单位。

回答：

> 这一镜为什么存在、观众看到什么、动作、表演、摄影、声音、节奏和与前后镜头的关系。

Shot 不受某个视频模型的单次时长限制支配。

### Generation Clip

AI 视频模型的一次计划执行单元。

回答：

> 当前 Shot Plan 在目标模型能力下，应该如何组织成一次实际视频生成。

Shot 与 Clip 不是 1:1：

- 多个 Shot 可以进入一个 Clip。
- 一个 Shot 可以拆成多个 Clip。

### Take

某次真实模型调用产生的视频候选。

同一 Clip 可拥有多个 Take。

### Selection

创作者当前采用哪一个 Take 的正式决定。

Take 是生成事实；Selection 是创作决定。

---

## 6. Near-Final Clip Generation【已冻结】

Clip 不只是“模型生成单位”，它应尽可能成为最终影片可直接使用的段落。

优先原则：

> 在模型可靠执行范围内，尽量减少不必要的 Clip 边界，让一次生成覆盖完整的电影节奏单位。

但：

- 15 秒等模型上限是容量，不是规划目标。
- 不是 Clip 越少越好。
- 可靠性优先。
- 不为了 One-pass 强塞过多动作、多人互动、复杂摄影和密集对白。

Production Planner 需要同时优化：

- 导演意图完整性
- 模型执行可靠性
- Continuity 成本
- 后期剪辑成本

---

## 7. Final Generation Brief｜最终制作方案【已冻结】

Prompt 不是项目真相。

模型无关的 Final Generation Brief 才是某个 Clip 的完整制作事实。

它至少表达：

- Intent / 目的
- Timeline / Shot 与 CUT 时间线
- Subjects & World / 人物、场景、道具
- State In
- Action Process
- Performance
- Camera
- Lighting / Physics / VFX（有需要时）
- Dialogue / Sound / Music
- References
- Constraints
- Planned State Out
- Handoff / Continuation candidacy

动作必须尽量描述成过程，而不是孤立标签：

> 初始状态 → 触发 → 开始 → 发展 → 接触/结果 → 反应 → 稳定结束。

抽象情绪应尽量翻译成可见/可听见的表演：

- 视线
- 表情
- 呼吸
- 姿态
- 手部
- 停顿
- 倾听
- 反应

---

## 8. Prompt / Compiler【已冻结】

正确关系：

```text
Final Generation Brief
→ H3 Compiler / Seedance Compiler / Future Compiler
→ Compiled Generation Task
→ Model
```

Compiler 是执行翻译层，不拥有创作权。

Compiler 可以：

- 重组表达
- 编号参考素材
- 转换模型专用结构
- 映射时长/参数
- 映射媒体绑定
- 生成模型所需 Prompt / Task representation

Compiler 不能：

- 改剧情
- 改导演意图
- 把“不哭”改成哭
- 新增关键动作
- 删除锁定限制
- 为了模型方便静默重写 Shot

如执行需要改变上游创作决定，必须返回上游提出 Revision Proposal。

---

## 9. Model Execution Profile【已冻结方向】

每个模型必须有版本化 Model Profile，不能依赖 LLM 记忆。

Profile 应表达：

- 模型身份与版本
- 数据来源
- verified_at
- 输入/任务模式
- 输出时长、画幅、分辨率等硬能力
- 多镜头能力
- Reference 能力
- First/Last frame 等时间控制
- Audio 能力
- Video reference / edit / extend / continuation 等不同任务语义
- 编译要求
- 可靠性经验

严格区分：

### Hard Capability

官方或实际验证的能力边界。

### Reliability Knowledge

内部测试与生产经验。

不能把经验说成官方硬限制。

### 当前 H3 执行路线：Darl-Only【已冻结 / D030】

- 唯一视频 Provider：`darl`；所有 H3 execution models 由 `https://api.darl.cn` 的 `POST /v1/videos` 执行。
- `H3_SERVER_ON=1` 时，新生成使用 `MiniMax-H3`（自建 H3）；否则使用 `runninghub-minimax-h3`（云端 H3 · 备用）。这是同一 Provider 下的 execution model 选择，不是 Provider 切换。
- Creator 只展示当前执行路线，Admin 在 Darl 下展示两个 execution models；不保留任何旧备用直连配置、Adapter、工作流或前台 Provider 选择。
- Final Brief 保持 model-independent；实际 Provider / execution model 写入 Compiled Task 与 Job 不可变快照。
- Technical Retry 使用原 Provider、原 Compiled Task、原 execution model、参数与引用。原自建模型关闭时安全拒绝，不能自动转云端；新路线需要明确的 Creative Regenerate。
- 历史非 Darl Provider Job 不删除或迁移，仅供查看；现行系统以 `LEGACY_PROVIDER_UNSUPPORTED` 拒绝继续执行和重试。
- 两个模型的真实输出、连续性与真实影片验证仍需要独立验收；离线合同测试不等于真实影片 PASS。

---

## 10. Reference Contract【已冻结】

Reference Source ≠ Reference Role。

同一素材在不同任务中可承担不同用途。

候选角色包括：

- character_identity
- character_look
- environment_identity
- prop_identity
- composition_reference
- motion_reference
- camera_reference
- audio_reference
- continuity_anchor
- first_frame
- last_frame
- continuation_source

Asset、Reference Binding、Control Media 必须分离。

特别是：

> 参考图不自动等于首帧。

---

## 11. World / Asset【已冻结】

### Character Identity ≠ Character Look ≠ Current State

- Character Identity：这个人是谁。
- Character Look：某阶段造型。
- Current State：当前故事时刻的动态状态。

### Location Identity ≠ Current Scene State

稳定空间身份与当前夜晚/雨/门开关/灯光状态分开。

### Prop

只有视觉漂移会影响剧情、连续性或生成的重要物品才需要稳定 Prop 身份。

### Just-in-Time Visual Preparation

不要求整部影片所有资产先完成。

当前即将制作的 Scene 只需补齐真正必要的视觉参考。

---

## 12. Project Knowledge & Memory【已冻结】

项目正式状态是唯一事实来源。

AI Film Studio 不只是“记住用户说过什么”，而是持续维护：

> 这部影片已经确定了什么，以及影片进行到现在真实发生了什么。

项目记忆至少分为：

- 创作意图
- Story Facts
- Character / World Facts
- Current / Canonical State
- Director Decisions
- Production Decisions
- Selected Generated Reality
- Project Preferences
- Version / Provenance

AI Proposal、Prompt、未采用 Take 都不能自动成为正式项目事实。

---

## 13. Continuity & Film Reality【已冻结】

连续性不是“上一帧长得一样”，而是下一次生成正确理解当前电影世界。

需要维护的内容包括：

- 人物身份与 Look
- 位置 / 朝向 / 视线
- 手部持物与接触
- 关键 Props
- 门窗/家具/环境状态
- 伤势、湿度等剧情相关状态
- Story knowledge
- Relationship facts
- Emotional residue
- 动作是否已完成

CUT 不重置世界状态。

严格区分：

- Planned State
- Observed Reality
- Canonical Film Reality

生成结果不会自动改写世界。

只有：

> Take + Selection + 必要的人类确认

才能形成新的 Canonical State。

---

## 14. Continuation / Handoff【已冻结】

State Continuity、Visual Anchor、Video Continuation 不是一回事。

正式支持的生成交接策略至少包括：

1. INDEPENDENT
2. MULTI_SHOT_ONE_PASS
3. STATE_CONTINUE_NEW_VIEW / 普通 CUT
4. VISUAL_ANCHOR
5. VIDEO_CONTINUATION
6. KEYFRAME_CONSTRAINED

VIDEO_CONTINUATION 适合：

- 同一连续 Shot 被模型时长拆分
- 未完成连续动作
- 精确身体/空间/接触关系需要连续
- 连续摄影机运动

通常不适合：

- 明确 CUT
- 反打/插入/新机位
- Scene Change / Time Jump
- 上一个 Take 尾部有明显错误
- 下一镜要求新构图

续接不能机械使用最后一帧。

应选择 Stable Tail，检查：

- 身份稳定
- 身体完整
- Prop 正确
- 空间清晰
- 运动模糊可接受
- 没有明显 artifact
- 与 Planned State Out 相符

依赖链：

```text
Clip A
→ Generate
→ Select Take
→ Confirm Actual State / Stable Tail
→ Clip B continuation becomes READY
```

---

## 15. Review【已冻结】

AI 审片只做辅助，不做最终审美裁判。

AI 适合辅助：

- 明显身份漂移
- 动作遗漏
- 道具异常
- 生成畸变
- 连续状态异常
- 计划结束与实际结束明显不同
- Stable Tail 可用性

主观视听判断，例如：

- 表演是否最有感染力
- 节奏是否高级
- 镜头是否“有味道”

最终由创作者决定。

不以“AI 89 分”作为核心产品机制。

---

## 16. 修改、版本和影响【已冻结】

上游修改不能删除下游历史。

系统应：

```text
修改
→ 自动分析影响范围
→ 保留所有历史
→ 标记真正受影响内容
→ 重新确认 / 重新规划 / 重新生成
```

影响可分：

- 不受影响
- Needs Reconfirmation
- Must Replan / Rebuild

已生成 Take 永远保留；变化的是其是否仍属于当前正式版本。

替换一个被后续 continuation 依赖的 Selection 时，后续依赖必须被识别为受影响。

---

## 17. Agent / Skill / Context【已冻结】

第一版只需要三个主要 AI 角色概念：

- 创作 / 导演 AI
- 制作 AI
- 审片辅助 AI

用户不需要管理 Agent。

Agent = 谁负责  
Skill = 用什么专业方法  
LLM = 推理引擎  
Tool = 能操作什么  
Model Profile = 模型真实能力  
Compiler = 模型执行翻译层

Skill 不是一段超长 Prompt，而应规定：

- 必需输入
- 判断步骤
- 输出合同
- 权限边界
- 停止条件
- QA

Context Assembly 根据当前任务只提供必要、权威、带来源/权限的信息。

重要信息应区分：

- LOCKED
- DERIVED
- PLANNED
- MODEL_SPECIFIC

优先级：

> 当前明确用户决定 > 已确认故事/导演事实 > Canonical Film State > 项目偏好 > AI 专业推导 > 模型经验建议。

---

## 18. System Architecture【方向冻结】

第一版采用模块化单体（Modular Monolith）思路：

- Project & Story
- World
- Directing
- Production
- AI Production Core
- Generation Runtime
- Film Reality
- Final Film

不优先建设微服务或“自主多 Agent 社会”。

核心生产对象应独立保存关系和版本，不再把整部电影只当成一个巨型 Project JSON。

所有重要对象应具有：

- Version
- Provenance / Source
- Status

AI 不直接写正式项目状态：

```text
Canonical State
→ Context Assembly
→ LLM
→ Structured Output
→ Schema Validation
→ Authority Validation
→ Proposal / Result
→ Necessary Human Approval
→ Canonical Write
```

---

## 19. Core Domain【方向冻结】

核心对象：

- Project
- Episode
- Scene
- Character
- Character Look
- Location
- Prop
- Story Fact
- Asset Version
- Shot
- Generation Clip
- Shot ↔ Clip Mapping
- Final Generation Brief
- Reference Binding
- Control Media
- Model Profile
- Compiled Generation Task
- Generation Job
- Take
- Selection
- Observed State
- Canonical Film State Snapshot
- Final Timeline

核心链：

```text
Scene
→ Shot
↔ Generation Clip
→ Final Generation Brief
→ Compiled Generation Task
→ Generation Job
→ Take
→ Selection
→ Canonical State Snapshot
→ Next Clip
```

---

## 20. Generation Runtime【方向冻结】

Generation Job 与 Clip / Brief 分开。

模型集成采用：

```text
Model Profile
+
Compiler
+
Adapter
```

增加新模型原则上只增加这三部分，不改 Scene/Shot/Clip 核心模型。

Generation Runtime 负责：

- queued / running / succeeded / failed / cancelled
- dependency waiting
- provider task tracking
- retry
- idempotency
- cost metadata
- parallel execution
- continuation dependencies

技术失败不能污染 Brief。

系统不能静默换模型。

---

## 21. Final Timeline【方向冻结】

Near-Final Clip Generation 不代表不需要后期。

Final Timeline 负责：

- 使用哪条 Selected Take
- trim
- 顺序
- 简单 transition
- 音量
- 音乐
- 字幕
- 最终导出

原则：

> Post-production 用于完成影片，不用于拯救错误的生成规划。

---

## 22. H3 Vertical Slice【已冻结】

大规模 UI 重建之前必须先跑通真实生产 Vertical Slice：

```text
Approved Shot Plan
→ Clip Plan
→ Final Brief
→ H3 Compiler
→ H3 Task
→ Generation
→ Take
→ Selection
→ Canonical State
→ Next Clip
```

测试 Scene：雨夜车站 / 林夏 / 旧信。

必须覆盖：

- 多 Shot → 一个 Clip
- 普通 CUT 但世界状态连续
- 一个长 Shot → 多 Clip
- 真正 VIDEO_CONTINUATION
- 上游 Selection 改变导致下游受影响

不允许用手工 Prompt 或假视频冒充端到端验证。

---

## 23. 施工顺序【方向冻结】

### Phase 1 — Production Core Foundation

建立：

- Domain
- Version / Dependency
- Final Brief
- H3 Profile / Compiler contract
- Generation Job
- Take / Selection
- Canonical State
- Fixture + Tests

### Phase 2 — H3 Vertical Slice

真实调用 H3 跑完整 Scene。

### Phase 3 — 03 / 04 Core Experience

重建核心创作和制作体验。

### Phase 4 — 01 / 02 / 05 / 06

补齐剧本、人物世界、审片与成片。

### Phase 5 — Full E2E

从故事到最终影片完整验证。

---

## 24. 项目治理【已冻结】

权威文件：

- `docs/MASTER-BLUEPRINT.md` — 项目宪法
- `docs/PRODUCTION-RULES.md` — 冻结生产规则
- `docs/DECISIONS.md` — 重大决策及原因
- `docs/work-orders/*.md` — Codex / Work 施工单
- `docs/reports/*.md` — 施工与验收报告

工作流：

```text
讨论 / 探索
→ 形成结论
→ 更新权威文档
→ 标记 已冻结 / 待验证 / 探索中
→ 发施工单
→ Codex / Work 执行
→ 验收
→ 更新正式版本
```

角色：

- Master Planner：产品、生产方法、系统架构、任务拆解、验收、决策收敛。
- Codex：正式工程实现、测试、迁移、Git。
- Work：视觉/交互设计、浏览器 QA、线上体验与部署验证。

施工者不能自行重新发明产品。

---

## 25. 当前仍待验证的内容

以下内容目前不作为不可改变的技术事实：

- 最终前端框架
- 后端运行环境
- D1 是否继续使用
- 旧 v12 哪些模块最终复用
- H3 当前所有 API 硬限制
- Seedance 完整能力档案
- Agent Runtime 的最终具体实现框架
- Final Timeline 第一版具体编辑能力

这些由实际工程验证后进入 Decision Log。

---

## 26. 项目参考

项目已提供 MiniMax H3 Singularity 视频提示词生产规范。H3 Compiler 与 Production Planning 的实现需要继续遵守其中关于：

- 主体与参考定义
- 参考角色
- 动作过程
- 表演可视化
- 摄影机
- 声音
- Shot 连续性
- 参考图不等于自动首帧

等原则。

该规范是 H3 专用执行知识，不替代本 Blueprint 的模型无关生产真相。
