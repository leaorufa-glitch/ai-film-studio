# #002 — H3 Real Vertical Slice

> 状态：READY FOR CODEX  
> 前置条件：#001 Production Core Foundation 已通过架构验收  
> 目标：用真实 MiniMax H3 API 跑通“雨夜车站”端到端生产链，并验证普通 CUT、视觉锚点和真正 Video Continuation。  
> 本轮完成后必须停止，提交报告与真实产物清单，等待架构/影片验收。  
> 本轮仍不是正式网站 UI 施工；#002 PASS 后立即进入正式网站 #003。

---

## 1. 本轮唯一目标

证明 #001 建立的 Production Core 不只是数据合同，而能驱动真实 H3 完成：

```text
Approved Shot Plan
→ Clip Plan
→ Final Generation Brief
→ H3 Compiler
→ Model Preflight
→ Real H3 API
→ Real Generation Job
→ Real Take
→ Human Selection
→ Observed / Canonical State
→ Next Clip Context
→ Stable Tail
→ Video Continuation
```

最终必须得到 A + B + C1 + C2 四个真实视频片段，并可按顺序播放/简单拼接进行人工审片。

---

## 2. 开工前先验证当前 H3 官方 API

不要继承 #001 的 `h3-unverified` 为真实能力。

先阅读并记录当前官方 MiniMax H3 文档，建立 VERIFIED Model Profile。

至少核对：

- 官方 model id
- API base / endpoint
- async task create/query
- output duration
- resolution
- ratio
- text/image/video/audio content schema
- reference_image / reference_video / reference_audio
- first_frame / last_frame
- 各媒体数量、大小、时长、格式限制
- image-to-video 与 reference-to-video 是否可混用
- callback/task status
- error codes
- 当前 pricing（只用于运行前预算，不写死为产品真相）

当前官方文档（2026-10-09 施工单编制时）显示：
- Model：`MiniMax-H3`
- Create：`POST /v2/video_generation`
- 输出时长：4–15 秒整数
- 输出：768P / 2K
- 支持 text / image_url / video_url / audio_url
- reference images ≤ 9
- reference videos ≤ 3；每段 2–15s；总时长 ≤ 15s
- reference audios ≤ 3；每段 2–15s；总时长 ≤ 15s
- first/last-frame 模式与 reference-to-video 模式互斥
- Create 返回 task_id，后续 query
- 状态包含 queued / running / succeeded / failed / cancelled

这些必须由 Codex 在施工当天重新对照官方文档确认后再写 VERIFIED Profile。

官方来源：
- https://platform.minimax.io/docs/api-reference/video-generation-v2-create
- https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir
- https://github.com/MiniMax-AI/MiniMax-H3

---

## 3. 关于 H3-Context-IR 的决定

本轮不把官方 `H3-Context-IR` 直接放进 Canonical Production Path。

原因：
- 官方说明它会对上下文做语义增强，并可能补充欠描述信息。
- 我们的架构要求 No Silent Repair，Compiler 不能静默增加或改变导演事实。

因此本轮：

### Canonical Path
```text
Final Brief
→ 我们自己的 H3 Compiler
→ /v2/video_generation
```

### Optional Diagnostic
可以把同一输入送入 `/v2/h3_context_ir` 进行对照研究，但：
- 不能自动覆盖 Final Brief；
- 不能自动覆盖我们编译后的 Prompt；
- 必须保存官方增强结果为 diagnostic artifact；
- 如发现有价值的增强，只能作为后续 Compiler/Skill 改进证据。

---

## 4. Project Aspect Ratio

修正 #001 的一个边界：

> 16:9 不能是 Compiler 私自决定的默认创作选择。

本 Fixture 明确把 Project / Production aspect ratio 设置为：

```text
16:9
```

Compiler 只读取并映射这个决定。

未来其他项目可使用其他画幅。

---

## 5. Fixture 继续使用“雨夜车站”

### Scene

雨夜旧车站候车厅。林夏打开旧信，认出失踪多年的母亲的字迹。她没有哭。远处列车进站，她收起信，起身走向站台门口。

### Shot Plan

- S01 · 3s：中近景，林夏坐着展开旧信。
- S02 · 2s：信件特写，表现熟悉字迹/署名信息，不要求生成长篇准确可读文字。
- S03 · 5s：回人物。认出字迹，停顿，不哭，呼吸变浅，手指压住纸边，慢慢抬眼。
- S04 · 6s：CUT 到新的过肩/侧后机位，看向站台，远处列车灯出现。
- S05 · 20s：同一连续长镜头。折信 → 起身 → 穿过候车厅 → 走向站台门口 → 稳定停住。

### Clip Plan

- Clip A：S01 + S02 + S03，10s，MULTI_SHOT_ONE_PASS
- Clip B：S04，6s，普通 CUT / STATE_CONTINUE_NEW_VIEW
- Clip C1：S05 前半段，12s
- Clip C2：S05 后半段，8s，VIDEO_CONTINUATION，依赖 C1 Selected Take

---

## 6. 第一次真实生成策略

为减少外部资产依赖，本轮允许 Clip A 使用 T2VA 建立“这场戏第一次真实视觉现实”。

Clip A 被人工采用后：

- 从 Selected Take 记录实际人物/Look/空间/道具状态；
- 选择或提取一个稳定视觉帧作为 Control Media；
- 该帧可用于 Clip B 的 `reference_image` / VISUAL_ANCHOR；
- 它不是自动成为 Character Master Asset。

这样本轮能验证：

```text
Text creates first reality
→ Selection makes it canonical
→ actual reality controls next generation
```

这是 Vertical Slice 的测试策略，不代表正式产品永远从文字开始。

---

## 7. Clip A — Real Multi-Shot One-Pass

目标：

- 真实调用 H3
- 10s
- 16:9
- 768P 优先（本轮先控制成本和迭代速度）
- S01 → CUT → S02 → CUT → S03
- 原生声音：雨声、纸张声、站台环境
- 明确 `林夏不哭`

必须使用 #001 的：

```text
Final Brief
→ Brief QA
→ H3 Compiler
→ Model Preflight
→ H3 Adapter
→ Job
→ Take
```

禁止开发者手工改最终 Prompt 才让结果成功。

如果 Prompt 必须人工修正：
- 先定位是 Brief / Compiler / Model Strategy 哪层问题；
- 写成新正式版本；
- 再生成。

---

## 8. Clip A 人工选择门

真实生成完成后必须暂停自动生产。

至少由人完成：

```text
Review Take
→ Select / Reject
```

只有 Selected Take 可以进入 Observed State。

至少确认：

- 人物是否稳定可用
- 信件是否存在
- 是否违背“不哭”
- 关键动作是否基本完成
- 最终坐姿/持信/视线
- 是否存在可用 Stable Visual Frame

如果 Take 不可用：
- 允许重新生成新 Take；
- 不能让 AI 自动无限循环；
- 任何 Creative Regenerate 与 Technical Retry 必须分开记录。

---

## 9. Clip B — 普通 CUT + Visual Anchor

Clip B 是新的机位。

必须证明：

> 世界连续，但不是 Video Continuation。

生产策略：

```text
State Continuity
+
Visual Anchor（来自 Clip A Selected Take 的稳定帧，如质量足够）
+
new camera/view
```

不得把 Clip A 视频作为“连续上一段”来强行延长。

可根据 H3 当前 VERIFIED Profile，把稳定帧作为 Ref2VA 的 `reference_image`。

必须明确 Reference Role：
- internal role：continuity_anchor / character_identity / current_look（按实际绑定）
- H3 adapter role：映射到当前官方 API 支持的 role

禁止将该控制帧自动写回 Character Master Asset。

---

## 10. Clip C1 — Long Shot Part 1

C1 是 S05 的前 12s。

目标：
- 折信
- 起身
- 开始穿过候车厅
- 保持同一人物、Look、信件和空间

根据 B 的 Selected Reality 组装 State In。

可以使用：
- Selected B stable frame / visual anchor
- 已存在的 continuity control media
- 但不能做假 continuation

C1 生成后同样进入人工选择门。

---

## 11. Clip C2 — Real Video Continuation

这是 #002 最关键的单项测试。

只有 C1 已经：

```text
Real Take
→ Selected
→ Observed State confirmed
→ Canonical Snapshot
→ Stable Tail selected
```

之后，C2 才能 READY。

### Stable Tail

不要机械使用 C1 最后一帧。

从 Selected C1 的尾部选择/提取真实 Control Media：

- 至少满足 H3 当前 reference video 最小时长；
- 人物身份稳定；
- 身体与持物关系正确；
- 没有明显运动模糊/畸变；
- 空间关系清楚；
- 与 C1 Canonical State 相符。

当前官方 H3 文档要求 reference video 每段 2–15 秒，因此本轮建议从 C1 尾部提取约 2–4 秒稳定片段作为 continuation source；具体长度以真实素材和官方限制为准。

### H3 Mapping

内部语义仍然是：

```text
VIDEO_CONTINUATION
continuation_source = Stable Tail from Selected C1
```

H3 Adapter 如何映射到官方 `reference_video` 与 Prompt 的 `[video continuation]` 语义，由本轮根据官方 H3 Prompt Guide 验证。

不要把“reference_video 存在”自动等同于 continuation；只有 Production Plan 明确为 VIDEO_CONTINUATION 才使用 continuation 语义。

---

## 12. Real H3 Adapter

实现真实 H3 Adapter，不只 Protocol。

必须支持：

- server-side API key
- create task
- task query（callback 可选，不作为本轮必需）
- provider task id
- polling/backoff
- success result
- provider error mapping
- rate limit / transient retry classification
- cancellation（若官方支持且本轮合理）
- download/persist returned media
- usage metadata
- real Job Event history

API key：
- 只允许环境变量/服务端 secret；
- 禁止写入 repo、fixture、report；
- 报告中禁止打印 key。

如果环境没有 key：
- 停止在 `NEEDS_CREDENTIALS`；
- 不伪造真实调用；
- 明确告诉用户只需要配置哪个环境变量；
- 不进入模拟 PASS。

---

## 13. Media Persistence

Provider 返回的 URL 不是项目长期媒体真相。

真实 Take 完成后：
- 立即把视频保存到项目管理的 durable media location；
- 保存 checksum / size / mime / duration 等基础 metadata；
- Take 指向项目自己的 Media record；
- provider URL 只作为 execution metadata/history。

本轮如果还没有云存储，可以先使用明确的本地 managed media directory，但接口必须为后续对象存储留出边界。

---

## 14. Cost Guard

本轮是真实付费生成，不允许自动无限重试/多候选轰炸。

策略：

- 默认每个 Clip 一次生成一个候选；
- 技术性 transient error 可按受控策略重试；
- 创作结果不好必须由人决定是否再生成；
- 每次提交前记录预估成本；
- 每个 Job 记录实际 usage/cost 能拿到的字段。

本施工单编制时 MiniMax 官方价格页面显示：
- H3 768P：$0.08 / 输出秒
- H3 2K：$0.13 / 输出秒
- reference video 还会按输入时长计费

实际施工当天必须重新读取官方价格；不要把上述数字长期硬编码为产品事实。

本轮优先 768P，先验证生产方法，不为测试盲目付 2K 成本。

---

## 15. Technical Retry vs Creative Regenerate

必须区分：

### Technical Retry
例如：
- timeout
- 429
- temporary provider error

不改变 Final Brief。

### Creative Regenerate
例如：
- 表演不对
- 动作漏掉
- 人物漂移
- continuity 不满意

创建新 Generation Job / Take，但必须记录这是新的创作尝试。

禁止把两者都叫“retry”。

---

## 16. H3 Profile Promotion

只有通过真实官方文档验证 + 最小真实请求验证的能力，才从：

```text
unknown/unverified
```

提升为：

```text
verified
```

Profile 每个关键字段尽量带：

- source
- verified_at
- confidence / evidence

历史 Compiled Task 继续 pin 当时的 Profile version。

---

## 17. 影片验收产物

本轮最终必须产出：

```text
Clip A selected take
Clip B selected take
Clip C1 selected take
Clip C2 selected take
```

并生成一个仅用于验收的：

```text
A → B → C1 → C2
```

简单拼接预览。

允许：
- 基础 trim
- 不改变内容的拼接
- 简单音量归一（如必要）

不允许：
- 用复杂后期掩盖 generation continuity 问题
- 用传统剪辑“救”掉模型没有完成的关键动作
- 替换人物/修脸等重后期

---

## 18. 人工影片验收标准

不要用 AI 总分。

人工检查：

### Clip A
- 多 Shot 是否真的像一个完成的电影段落
- CUT 节奏是否自然
- “不哭”是否保留
- 动作/表演是否可信

### A → B
- 是同一个人/Look/世界
- 新机位像正常 CUT，而不是错误 continuation
- 信件和人物状态延续

### B → C1
- State In 正确
- 起身前后的故事/空间关系可信

### C1 → C2
- 真正像同一长 Shot 被拆开继续
- 身体、方向、速度、持物、摄影机运动没有明显重置
- 没有“重新生成一条相似视频”的强烈断裂感

### 全段
最终 30–40 秒只需要轻量 trim 即可作为影片片段使用。

---

## 19. 必须保存的证据

每一个 Selected Take 必须能够追溯：

- Scene / Shot
- Clip
- Final Brief version
- Reference Bindings
- Control Media
- H3 Profile version
- Compiler version
- Compiled Task
- Generation Job
- provider task id
- actual H3 response metadata
- local/durable media
- Selection
- Observed State
- Canonical State

C2 必须额外证明：
- continuation source 来自哪个 C1 Selected Take
- Stable Tail 的具体媒体
- 上游 Selection version

---

## 20. 本轮不做

不要进入：

- 正式 01–06 网站 UI
- Seedance 接入
- 多模型路由
- 多 Agent 自治
- AI 审片总评分
- 完整 Final Timeline 编辑器
- 大规模数据库迁移
- 多用户系统
- 2K 作为默认生成策略
- 自动批量生成很多候选

#002 的唯一任务是：

> 证明我们的 Production Core 可以真实驱动 H3 生成连续、接近成片的 Scene。

---

## 21. 自动测试

保留 #001 全部测试。

新增至少覆盖：

- VERIFIED Profile 由官方能力记录构建
- unverified 字段仍不会被误当 hard fact
- API request payload 正确映射各种 role
- first/last-frame 与 reference mode 互斥
- real adapter response → Job/Take
- provider errors → structured failure
- technical retry 不改 Brief
- media persistence
- Clip B 不使用 video continuation
- C2 在 C1 Selection / Canonical / Stable Tail 缺一时不 READY
- C1 Selection 替换后 C2 execution stale
- Project ratio 来源正确，不由 Compiler 擅自决定

真实 H3 调用测试必须和普通 unit tests 分离，避免 CI 每次运行产生费用。

---

## 22. #002 PASS 条件

必须同时满足：

### System PASS
- 真实 H3 API 调通
- VERIFIED H3 Profile 成立
- Real Adapter 成立
- A/B/C1/C2 都来自真实 H3
- Job/Take/Selection/State/Dependency 全链真实工作
- C2 使用真实 Selected C1 的 Stable Tail
- 没有手工 Prompt bypass
- 没有假媒体冒充真实结果

### Film PASS
- 人工审片认为整体至少达到“可作为真实影片片段继续开发”的水平
- 普通 CUT 和 continuation 行为符合预期
- C1→C2 连续性测试成立

如果 System PASS 但 Film FAIL：

> 不进入正式网站大规模施工；定位 Production Planning / Brief / Compiler / Continuation 策略并修正。

---

## 23. #002 施工报告

创建：

`docs/reports/002-h3-real-vertical-slice-report.md`

必须包含：

1. 官方 H3 能力验证来源与日期
2. VERIFIED H3 Model Profile
3. Real H3 Adapter 实现
4. Credential / secret 处理
5. Media persistence
6. Clip A 实际任务与结果
7. Clip A Selection / Canonical State
8. Clip B 实际任务与结果
9. Clip C1 实际任务与结果
10. Stable Tail 选择
11. Clip C2 video continuation 实际任务与结果
12. A+B+C1+C2 拼接预览路径
13. 每条 Take 的追溯信息
14. Technical Retry / Creative Regenerate 记录
15. 实际测试结果
16. 实际花费/usage（能获得多少写多少）
17. 影片人工审片备注
18. 已知问题
19. Git commits
20. 工作区是否 clean
21. 明确确认没有进入 #003

禁止在报告中输出 API key。

---

## 24. Stop Condition

完成 #002 后必须停止。

不要自行开始建网站。

等待 Master Planner 做：

```text
System Review
+
Film Review
```

只有 #002 PASS 后才发：

> #003 — Website Foundation + 03/04 Core Experience
