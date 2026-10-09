# #001 Production Core Foundation — 施工报告

状态：完成，等待架构验收。工作区：`/Users/lvy/Documents/ChatGPT/ai-film-studio`（新建独立目录；未在旧项目施工）。

## 1. 实际完成内容

建立了 Python 标准库 + SQLite 的模块化生产内核：独立版本化创作对象、Shot↔Clip 关系、模型无关 Brief、Brief QA、H3 编译合同、模型预检、不可变执行快照、Job 状态事件、Take/Selection、Observed/Canonical State，以及依赖和影响判断。没有创建 Creator UI。`README.md` 给出测试入口。

## 2. Repo Audit

开工时新目录只有规划包中的四份权威文档和 `CODEX_START_001.txt`，没有旧代码、数据库、ORM、媒体存储、上传服务、H3 Adapter、服务端密钥处理、任务基础、测试框架或 Project/Revision 机制。逐项结论：

| 检查项 | 分类 | 处理 |
|---|---|---|
| 权威规划文档 | REUSE | 原样保留并纳入本地 Git |
| 数据访问、数据库、ORM | REPLACE（新建） | 无现存实现；建立 SQLite 关系表及版本记录，不引入外部 ORM |
| Generation 任务、Project/Revision、测试框架 | REPLACE（新建） | 无现存实现；建立 Job 事件、独立版本和 `unittest` |
| 媒体存储、上传、H3 Adapter、服务端密钥处理 | LEAVE ALONE | 新仓库不存在；本轮仅建立 Adapter Protocol 和媒体元数据合同，没有真实接入或密钥落盘 |
| ADAPT | 无 | 无可适配的既有模块 |

没有扫描或修改旧 AI-shot-drama、ai-film-video 或其他已有项目。

## 3. 新增核心对象

`objects` 表按 `kind + id + version` 保存 Project、Episode、Scene、Character、Character Look、Location、Prop、Story Fact、Asset Version、Shot、Generation Clip、Final Generation Brief、Reference Binding、Control Media、Model Profile；每一版本保存 source、status、payload、created_at。关系/执行表分别保存 Shot↔Clip、dependency、Compiled Task、Job、Job Event、Take、Selection Event、Observed State、Canonical Snapshot。Character Identity、Look、当前状态分离；Asset、Binding、Control Media 分离。

## 4. Shot ↔ Clip

`shot_clip` 是独立多对多表，保存顺序、Shot 内区间、Clip 内区间和 CUT 标记。Fixture 中 A 映射 S01/S02/S03；S05 分别映射 C1 的 0–12s 和 C2 的 12–20s。Brief QA 核对批准的 Shot 描述、映射顺序、时间线无空隙或重叠。Shot 自身不绑定单个 Clip。

## 5. Final Brief 与版本

Brief 独立保存为 `brief:<clip>` 的不可变版本，包含目的、Scene/Shot 时间线、时长、主体/环境/道具、state_in、动作过程、表演、摄影、声音、参考、约束、planned_state_out、handoff、provenance/authority。新版本追加，不覆盖旧版本。上游 Canonical State 注入会显式产生新 Brief 版本；旧 Task/Job/Take 保留。Prompt 只存在于 Compiled Task。

## 6. H3 Model Profile

建立 `h3-unverified` Profile：model id 为 `new-h3-video`，版本、时长、参考数量/类型、时间控制、音频、参数和画幅能力均显式 unknown/unverified，`verified_at` 为空。预检会阻止以此 Profile 发起生产 Job。测试另用明确标记 `TEST-ONLY` 的合成 Profile 验证合同；这些测试数值不代表真实 H3 能力。Hard Capability 与 Reliability Knowledge 字段分离。

## 7. H3 Compiler

确定性编译 Brief + Reference Bindings + Profile 为 Compiled Task。产物包含 H3 六段结构（subject_definitions、summary、retention_analysis、detailed_description、overall_soundscape、non_diegetic_music）、Prompt、媒体绑定、时长、16:9 默认画幅、参数、续接来源、Brief/Compiler/Profile 版本，以及完整引用和控制媒体快照。编译器只序列化已有制作事实，不能重写 Shot/Brief；LOCKED 约束逐项保留并做语义载荷哈希检查。若 Brief QA 不通过则编译失败。只定义 H3 Adapter Protocol，没有真实网络实现。

## 8. Brief QA / Model Preflight

Brief QA 返回 `READY` 或 `NOT_READY + structured reasons`，检查目的、批准 Shot 时间线和描述、覆盖范围、时长、可重建 state_in、主体解析、动作过程、可见表演、摄影、声音、Reference role/Asset、planned_state_out 和基本连续性冲突。模型预检另外检查 Profile 支持的模式、已验证时长、媒体数/类型、参数、画幅、结构完整性、音频/续接能力、版本过期、上游 Canonical State，以及续接的当前 Selection/Stable Tail。QA 不自动补写创作内容。

## 9. Generation Job

Job 独立于 Brief，保存完整 Compiled Task 执行快照。状态事件支持 queued → running → succeeded/failed/cancelled；重试建立新 Job，保留原失败记录。快照可追溯 Brief、Compiler、Profile、Reference/Control Media、参数；事件可记录 provider task id、响应、错误、时间和成本元数据。技术失败不改 Brief。

## 10. Take / Selection / State

Take 指向成功 Job 并保留媒体 URI/供应商元数据，Selection 为独立追加事件；更换 Selection 不删除旧 Take。Observed State 独立于 Planned State。只有当前选中 Take 的观察结果加显式人工确认，才能写 Canonical Snapshot；下一 Clip 从 Snapshot 读取，Selection 变化后旧 Snapshot 不能继续作为当前 Context。测试 Take 带 `test_only` 标志，且只能在测试模式写入。

## 11. Dependency / Continuation

B←A、C1←B 为状态连续依赖；B 是普通 CUT，无视频续接媒体。C2←C1 是 VIDEO_CONTINUATION。C2 规划/Brief 可提前存在；缺上游 Selection、Canonical State 或 Stable Tail 时不能 READY。C1 Selection 切换后，旧 C2 Task 动态判为 `Must Replan / Rebuild`，历史 Task/Job/Take 不删除。Brief/Profile/Reference 版本变化也会在预检中暴露；旧 Brief Task 不能继续新建 Job。

## 12. 自动测试结果

命令：`python3 -m unittest discover -s tests -v`；结果：**6 tests passed**。`python3 -m compileall -q film_core tests` 通过。测试覆盖施工单的 18 项最低清单：多对多及区间、Brief 版本和旧 Take 保留、多 Take/Selection 切换、Canonical 写入门禁、普通 CUT、续接阻塞和旧 Selection 影响、Job 失败/重试、编译不改上游、LOCKED 保留、执行快照追溯，以及完整 Fixture。另验证 SQLite 文件关闭重开后版本仍在、未验证真实 Profile 被预检阻止、未知参数被拒绝。

## 13. 雨夜车站 Fixture

建立 1 Scene、5 approved Shots、4 Clips、4 初始 Brief。合同测试按 A→B→C1→C2 顺序得到 4 Compiled Tasks、4 成功 Jobs、4 测试 Take、4 Selection、4 confirmed Canonical Snapshots；B/C1/C2 执行前各自显式产生引用上游 Snapshot 的 Brief 新版本。另有 C2 未就绪草稿 Task、C1 替代 Take 用于依赖变更测试。所有 `test-only://` URI 均为合成供应商结果，没有假冒真实 H3 视频，也未调用 API。

## 14. 已知技术债 / 风险

- 真实 H3 API 能力和媒体上传/Adapter 未验证；生产 Profile 维持 NOT_READY。这是 #002 前的明确验证项，本轮没有凭记忆填参数。
- SQLite 的通用 `objects.payload` 为 JSON；对象间部分外键及字段级 Schema 由服务层验证。正式多用户服务需要进一步强化数据库约束、迁移与并发事务边界。
- 人工确认接口记录 actor 字符串；实际身份认证/授权由未来应用层接入。测试证明观察本身不会自动进入 Canonical State。
- 编译忠实性通过确定性结构复制、LOCKED 保留和哈希保证；自然语言内部矛盾和表演质量仍需后续人工/专业 QA。Stable Tail 的画面质量目前由显式 assessment 输入，不执行视频视觉分析。
- 外部媒体 URI 的实际可达性和供应商返回物真实性须由真实 Adapter/媒体层确认；本轮仅核对引用资产与元数据存在。

## 15. 明确没有做的内容

没有进入 #002；没有真实 H3 视频请求、Seedance、01–06 UI、Storyboard/假视频、全项目旧数据迁移、自主多 Agent、AI 总评分、完整剪辑器、多用户权限或成本中心。没有配置 Git 远程，也没有推送。

## 16. 数据库/基础设施阻断

本轮为全新仓库，无现有数据库可评估或迁移。SQLite 关系表已经证明 #001 的多对多、版本、依赖、状态快照和 Job 跟踪可表达；#001 无基础设施阻断。SQLite 是否作为线上数据库不是本报告的架构决定。

## 17. Git commit

- `1c8eca41e191a9277d46f15464ca6bc6808dd387` — 核心实现、Fixture、测试和权威文档。
- `e9e3eb6c8808e61dfaccbe29c109797470f562c2` — 时间线完整性校验及 Shot 意图进入 Brief。
- 本报告所在提交：用 `git log -1 --format=%H` 查询（报告提交后哈希才生成）。

## 18. 当前工作区

报告提交并验证后应为 clean；最终状态以交付消息中的 `git status --short` 实测为准。已停在 #001，等待架构验收。
