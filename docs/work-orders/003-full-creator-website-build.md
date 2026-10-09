# #003 — Full Creator Website Build

> 状态：READY FOR CODEX  
> 前置条件：#001 Production Core Foundation 已通过；#002 H3 Integration/Contracts 已完成，真实 H3 Film Validation 因生产服务器按需关机而延期，不阻塞本轮。  
> 本轮性质：**正式网站施工开始**。  
> 本轮目标：把 Architecture Reset 后的 Production Core 做成真正可使用的 AI Film Studio 创作者网站，完成 01→06 的主体体验，并把 03→04→05 做成核心生产链。

## 1. 总目标

这不是“做几个页面”，而是第一次把系统做成完整创作者产品：

```text
创作者进入真实项目
→ 剧本 / Scene
→ 人物与世界
→ Shot Plan
→ Generation Clip Plan
→ Final Generation Brief
→ Generation Job
→ Take / Selection
→ Canonical Film Reality
→ Final Timeline
```

网站必须直接建立在 #001/#002 的正式领域模型上，禁止为了 UI 再造第二套 Project / Shot / Clip / Take 真相。

## 2. 产品原则

最高目标：**稳定地产生更好的 AI 影视视频，并让每个 Clip 尽量接近可直接进入成片的电影片段。**

冻结原则：
- Prompt 不是项目真相。
- Shot = 导演语言；Generation Clip = 模型执行单元。
- Take 是真实候选，Selection 是采用决定。
- Planned / Observed / Canonical 必须分开。
- No Silent Repair。
- AI 主要价值在生成前，主观审片由人决定。
- 媒体只有真实存在时才占大空间。
- Storyboard 只有真实存在时才显示。
- 后端越专业，前端越简单。

## 3. 六个工作区

项目内固定为：

```text
01 剧本
02 人物与世界
03 场次与分镜
04 影片制作
05 审片
06 成片
```

它们是 Workspaces，不是强制向导。用户可以返回上游修改，但系统必须说明下游影响。

核心问题：
- 01：发生什么？这个故事对不对？
- 02：重要的人和世界长什么样？
- 03：这一场怎么拍？
- 04：已经决定这样拍了，当前模型怎样生成最好？
- 05：这条我要吗？
- 06：组合以后整部片成立吗？

## 4. 技术架构决定

继续采用 **Modular Monolith**，不拆微服务。

推荐目录：

```text
ai-film-studio/
  apps/
    web/      # Next.js + TypeScript
    api/      # FastAPI，包装现有 Python film_core
  film_core/  # #001/#002 已有 Production Core
  tests/
  docs/
  output/     # ignored managed local media
```

### Frontend
- Next.js
- React
- TypeScript
- App Router

### Backend
- FastAPI
- 直接调用已有 `film_core`
- 前端不得绕过 API 直接写 SQLite

### Persistence
- #003 本地开发继续允许 SQLite
- 保留 Repository / Data Access 边界
- 不把 SQLite 冻结为最终线上数据库
- 本轮不为了“企业级”虚构数据库迁移

### Media
- 开发阶段允许 managed local media
- Take 必须指向正式 Media Record
- 未来对象存储替换边界保留

## 5. Home + Project Shell

### Home
支持：
- 新建影片
- 最近项目
- 继续创作
- 搜索项目
- “今天想拍什么？”快速入口

新建项目至少支持：
- 项目名
- 一句话想法 / 粘贴剧本
- 画幅
- 基础偏好

AI 服务未配置时仍可创建空项目。

### Project Shell
进入项目后提供：
- 项目名
- 当前 Episode / Scene 上下文
- 01–06 导航
- 保存状态
- 轻量 Provider 状态
- 全局生成任务状态入口

禁止永久占大面积的 AI Chat。

## 6. 01 剧本

主界面以可编辑剧本为核心，不做表单后台。

必须支持：
- 手工创建 / 编辑剧本
- Scene 切分
- Scene 重排
- Scene 删除前影响提醒
- 保存版本
- 从纯文本开始
- Scene 标记为可进入导演设计

如果 LLM Adapter 可可靠接入，可提供：
- 整理为 Scene
- 改写这段
- 更克制 / 更紧张 / 更快
- 故事事实冲突检查

AI 输出只能是 proposal，用户确认后才能写正式状态。

01 不决定镜头语言、Clip 切分和模型 Prompt。

## 7. 02 人物与世界

目标不是资产仓库，而是回答：**这场戏真正需要稳定的视觉身份是什么？**

分开：
- Character Identity / Look / Current State
- Location Identity / Current Scene State
- Prop Identity / Current Prop State

必须支持：
- 上传真实资产
- 查看 Asset Version
- 指定当前版本
- 保留历史版本
- 标注用途
- 提示 upcoming Scene 缺少哪些必要视觉锚点

JIT Visual Prep：只准备接下来真正需要的内容，不要求一开始生成整部片所有资产。

如果图片模型接口明确且可可靠接入，可以接入生成；否则上传流程必须完整，图片生成不作为 #003 blocker。

禁止：
- Take 截图自动升级成 Character Master Asset
- Control Media 当长期资产
- 没有真实图时放假缩略图

## 8. 03 场次与分镜

这是本轮第一个核心页面。

页面回答：**这一场怎么拍？**

建议结构：
- 左：Scene 导航
- 中：当前 Scene Shot Plan
- 右/抽屉：Shot 详情与 contextual AI（不可永久挤压主区）

Shot Card 优先显示：
- Shot 编号
- 镜头目的
- 观众看到什么
- 动作过程
- 表演
- 摄影
- 声音
- 预计时长

已有真实人物/场景/道具资产时显示小缩略图；没有就显示文字身份。

Storyboard 只有真实存在才显示，不为布局制造假图。

支持：
- 新增
- 删除
- 排序
- 拆分
- 修改
- 确认 Shot Plan
- 查看上游变化影响

长 Shot 不能因为模型时长被 03 强拆。例如 22s Shot 仍是一个 Shot，04 再决定如何拆成 Clips。

AI 可提议 Shot Plan 和表演可见化，但不得自动确认或静默改导演意图。

## 9. 04 影片制作

这是本轮最核心页面。

页面回答：**已经决定这样拍了，当前模型怎样生成最好？**

### 关键 UX
没有真实媒体时，不做巨大播放器。第一层先展示当前 Scene 的 **制作计划**。

每个 Clip 至少显示：
- Clip 名称 / 编号
- 包含哪些 Shot
- 目标时长
- 生成策略
- 普通 CUT / State Continuity / Visual Anchor / Video Continuation
- 独立生成 / 等待上游
- READY 状态
- 当前模型
- 参考媒体摘要
- 上游影响状态
- 是否已有 Take

### Shot ↔ Clip 可视化
必须能直观看见：

```text
S01 ┐
S02 ├→ Clip A
S03 ┘

S05 0–12s → Clip C1
S05 12–20s → Clip C2
```

不要做复杂工程图。

## 10. Final Generation Brief UI

用户侧名称：**最终制作方案**。

不要把 Raw Prompt 当主编辑器。

展开 Clip 后按人话展示：
1. 这一段的目的
2. 时间线
3. 人物 / 世界 / 道具
4. 开始状态
5. 动作过程
6. 表演
7. 摄影
8. 声音
9. 参考素材
10. 结束状态
11. 与下一段的衔接

用户可以修改允许修改的 Production / Brief 内容、重新生成 proposal、确认 Brief、查看为何当前不能生成。

高级信息默认折叠：compiler version / profile version / raw prompt / provider payload。

## 11. Generation 状态

按钮/状态至少包括：
- 可以生成
- 等待上一片段确认
- 缺少必要素材
- 需要重新确认
- 模型服务未启动
- 生成中
- 已生成候选
- 生成失败

### H3 服务器离线
本项目 H3 服务器按需开关机。

当中转站可访问、但 H3 上游关闭时，用户应看到类似：

> H3 视频服务器当前未启动。你可以继续完成镜头和制作计划，启动视频服务器后再生成。

不要显示未知错误或无限 spinner。底层保留真实 provider error / Job Event。

## 12. 05 审片

这是第二个核心页面。

页面回答：**这条我要吗？**

到 05 才 Player First。

至少支持：
- 当前 Clip
- 大播放器
- Take 列表
- Selected Take
- Take A/B 切换
- 基础 metadata
- 重新生成
- 修改制作方案
- 采用这条

AI Review Assist 可以标记：
- 身份明显漂移
- 关键动作缺失
- 道具错误
- 明显 artifact
- 连续性差异
- continuation suitability

禁止 AI 给电影感总分或替用户选 Take。

## 13. Selection → Observed → Canonical

采用 Take 后必须真实走：

```text
Selected Take
→ Observed Reality
→ 人工确认
→ Canonical Film Reality
```

若实际结尾和 Planned State 不同，用户看到普通语言，例如：

> 这条最终是左手拿信，与原计划右手不同。是否接受这个实际结果并让下一片段按左手继续？

选择：
- 接受实际结果
- 重新生成
- 修改计划

系统不能静默更新 Canonical State。

## 14. Continuity UI

连续性不能做成复杂后台面板。

用户只需要看到：
- 与上一片段是否连续
- 当前承接哪些重要状态
- 下一片段在等什么
- 使用哪个稳定帧 / Stable Tail
- 上游 Selection 改变后哪些片段要重新准备

例如：

> Clip C2 等待 Clip C1 采用一条候选片段后才能生成。

或：

> Clip C1 已更换采用版本。Clip C2 的旧生成准备已失效，需要重新准备。

不要展示 DAG 图。

## 15. 06 成片

定位为轻量 Final Timeline，不是 Premiere。

必须支持：
- Selected Take 进入时间线
- 顺序排列
- 基础 trim in/out
- 替换 Take
- 播放整个序列
- 简单转场
- 基础音量
- 字幕轨 / 简单字幕
- 导出/生成预览

Final Timeline 不修改原 Take。Take immutable，时间线只引用 Take + range。

## 16. 上游修改与影响

必须实现跨页面影响逻辑。

例：
- 01 改故事事实：旧 Shot / Clip / Take 不删除，但显示需要重新确认/重新制作。
- 03 改 Shot：04 对应 Clip / Brief 需要重新准备。
- C1 更换 Selection：C2 旧 continuation 失效。
- Character Look 切换：相关后续 Clips 显示连续性风险。

用户看到自然语言，不暴露 revision hash。

## 17. Provider / Model 状态

网站提供轻量状态入口：
- LLM
- Image
- H3 Video

仅显示：可用 / 未配置 / 服务离线 / 最近失败。

不要变成运维控制台。

Provider 离线时，所有不依赖真实生成的创作工作仍可继续。

## 18. Contextual AI

不要做永久 AI 聊天栏。

AI 应出现在任务里：
- 01：整理 Scene / 改写
- 03：提议 Shot Plan / 表演可见化
- 04：重新规划 Clip / 解释为什么拆分
- 05：检查客观连续性问题

输出为 proposal + explanation + structured diff，用户确认后才正式写入。

## 19. 视觉与交互方向

- 专业
- 克制
- 有电影制作感
- 信息密度可控
- 不像企业后台
- 不像参数实验室
- 不像聊天机器人外壳

核心原则：**媒体只有真实存在时才占大空间。**

- 没视频：重点是计划 / Shot / Brief
- 有视频：05 Player First
- 有资产：显示真实缩略图
- 无资产：干净文字，不放假图

## 20. Empty / Loading / Error States

至少覆盖：
- 新项目无剧本
- 有剧本无 Scene
- 有 Scene 无 Shot
- Shot Plan 未确认
- Clip Plan 未生成
- Brief NOT_READY
- Provider 离线
- Generation failed
- Clip 无 Take
- 有 Take 未 Selection
- Selection 未确认 Canonical
- Final Timeline 为空

不能出现一片空白或假卡片。

## 21. API Contract

Frontend 必须通过 Backend API 操作正式对象。

资源边界至少包括：
- projects
- episodes
- scenes
- shots
- shot_clip mappings
- clips
- briefs
- model profiles
- references
- control media
- generation jobs
- takes
- selections
- observed state
- canonical snapshots
- timeline

可为页面提供 read model，但写操作仍遵守领域规则。

## 22. #002 延期的真实 H3 影片验收

网站建立后，当需要验收真实 04→05 Generation Flow 时，继续使用“雨夜车站”。

如果用户开启 H3：

```text
网站 04
→ Clip A Generate
→ H3 Adapter
→ 中转站
→ H3
→ Take 回到网站
→ 05 审片
→ Selection
→ Canonical
→ B
→ C1
→ Stable Tail
→ C2
→ 06 拼接
```

如果 H3 仍关闭：
- #003 其他施工继续
- 真实影片验收保持 Deferred
- 禁止伪造视频结果

## 23. 内部施工检查点

本轮是一张大施工单，不拆新 Work Order，但内部必须保留三个 Checkpoint。

### Checkpoint A — Foundation
完成：
- Web/API 启动
- Home
- Project Shell
- 01–06 导航
- 正式 API 层
- 真实项目读取/保存
- Provider status
- 基础 Empty/Error states

验证后继续，不等待新施工单。

### Checkpoint B — Production Core UI
完成：
- 03
- 04
- 05
- Shot↔Clip
- Final Brief
- Generation Job
- Take / Selection
- Canonical
- Continuity

如果发现必须修改 #001 核心领域边界：停止并报告 blocker，不用 UI hack 绕过。

### Checkpoint C — Full Creator Flow
完成：
- 01
- 02
- 06
- 跨页面 impact
- polish
- 浏览器 E2E
- 基础性能与稳定性

## 24. Browser / Responsive QA

至少测试：
- Desktop 1440px
- Laptop 1280px
- 较窄桌面 1024px

移动端本轮不要求完整生产能力，但不能完全崩坏。

重点验证：导航、长文本、Shot cards、Clip Plan、Brief、Player、Timeline、空状态、错误状态。

## 25. 自动测试最低要求

保留 #001/#002 全部测试。

新增至少覆盖：

### API
1. Project create/read/update
2. Scene/Shot update obeys versioning
3. Shot↔Clip read/write
4. Brief versions preserved
5. Generation Job uses Compiled Task
6. failed provider job surfaced without corrupting state
7. Selection only from valid Take
8. Canonical requires confirmation
9. upstream change marks downstream impact
10. C1 Selection change invalidates C2 continuation prep
11. offline H3 becomes provider unavailable state
12. Final Timeline references immutable Take

### Frontend
13. Home create project
14. 01 save script
15. 03 edit/approve Shot Plan
16. 04 render Clip Plan
17. 04 NOT_READY explanation
18. 04 offline provider explanation
19. 05 Take selection
20. 05 actual-state confirmation
21. 06 timeline assembly
22. no fake storyboard/media on empty state

### E2E
23. project → script → scene → shot → clip → brief flow
24. mock/test provider 只允许用于自动化 UI 测试，并必须明确 test-only
25. real H3 path 与 CI 分离，避免误生成

## 26. 安全

- API key 仅 server environment
- 前端 bundle 不含 key
- raw secret 不进日志
- 上传校验类型/大小
- 防路径 traversal
- API 输入验证
- 报告不输出密钥
- `.env*` 正确 ignore

## 27. 性能底线

- 大列表避免全量重渲染
- 视频懒加载
- 缩略图合理尺寸
- generation polling 使用 backoff
- 页面切换不要重复加载整个项目巨型 JSON
- API 使用 Workspace read model

## 28. 明确不做

本轮不扩张到：
- 多人实时协作
- 复杂权限组织
- 计费中心
- Premiere/Resolve 级 NLE
- 大规模模型市场
- 多模型智能路由
- 自主多 Agent 社会
- AI 主观总评分
- 假 Storyboard
- 自动无限生成
- Prompt-first 产品设计

## 29. #003 完成标准

### Product
- 网站可运行
- 01–06 全部可进入
- 03/04/05 为真正可用核心链
- 01/02/06 有完整基础体验
- 用户无需理解数据库/编译器才能操作

### System
- UI 真正连接 Production Core
- 没有第二套前端真相
- 版本/影响/Selection/Canonical 工作
- Provider 离线不破坏创作
- 历史对象不因修改被删除
- Take immutable

### Visual
- 没有假媒体
- 04 无媒体时不 Player First
- 05 有媒体时 Player First
- 视觉层级清楚
- 核心页面不像后台管理系统

### Workflow
至少完整演示：

```text
新建项目
→ 01 输入故事
→ Scene
→ 02 准备必要身份
→ 03 Shot Plan
→ 04 Clip Plan / Final Brief
→ Generation 状态
→ 05 Take / Selection（真实或明确 test-only）
→ Canonical
→ 06 Timeline
```

## 30. 真实 H3 特殊 PASS 规则

H3 生产服务器按需关机，因此：
- #003 Website PASS 不要求服务器长期在线。
- 但 Beta Release 前必须完成一次真实 A→B→C1→C2 网站端到端影片验收。
- 如果 #003 验收时用户方便开启 H3，则本轮直接完成真实影片验收。
- 如果仍不开机，网站可通过 #003，但真实影片验收继续作为 release blocker。

## 31. 施工报告

创建：

`docs/reports/003-full-creator-website-build-report.md`

必须包含：
1. 实际完成范围
2. 技术结构
3. Web/API 启动方式
4. 01 页面
5. 02 页面
6. 03 页面
7. 04 页面
8. 05 页面
9. 06 页面
10. Production Core 接入方式
11. Shot↔Clip UI
12. Final Brief UI
13. Provider offline / error UX
14. Generation Job UX
15. Take / Selection / Canonical
16. Continuity / Impact
17. Final Timeline
18. Browser QA
19. 自动测试
20. E2E 测试
21. 真实 H3 是否执行
22. 已知问题 / 技术债
23. 明确未做内容
24. Git commits
25. 工作区是否 clean
26. 本地网站地址
27. 如有部署，测试站地址

## 32. Git / Commits

至少在 Checkpoint A/B/C 保留清晰 commit。

不要提交 output media、secret、node_modules、build cache。

完成时：
- `git status` clean
- 无 remote 可以
- 不擅自 push 到旧仓库

## 33. Stop Condition

完成 #003 后停止。

不要自行进入 Beta Hardening / Release。

等待 Master Planner 做：

```text
Architecture Review
+
Creator Experience Review
+
Browser Review
+
（如 H3 在线）Film Review
```

下一阶段根据 #003 验收结果决定是否进入 Beta Hardening & Release。
