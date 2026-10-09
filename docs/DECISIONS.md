# AI Film Studio — Decision Log v0.1

> 用于记录重大架构/产品决定及其原因。  
> 状态含义：Frozen = 可直接作为施工依据；Validate = 方向接受但需真实模型/工程验证；Explore = 仅探索。

| ID | 决策 | 状态 | 原因 |
|---|---|---|---|
| D001 | Architecture Reset：旧 v12 是实验和经验，不是新产品约束 | Frozen | 旧页面和数据模型已证明会把产品带向错误方向 |
| D002 | 最高目标改为“稳定产生更好的 AI 影视成片” | Frozen | 所有功能必须服务最终影片质量、连续性、可控性和返工效率 |
| D003 | Pre-generation First | Frozen | AI 对主观视听的事后审片能力有限；应把智能集中在生成前 |
| D004 | Near-Final Clip Generation | Frozen | 目标是 Clip 拼接后已经接近成片，而不是先生成松散素材再救 |
| D005 | 六工作区：剧本 / 人物与世界 / 场次与分镜 / 影片制作 / 审片 / 成片 | Frozen direction | 与新的生产内核职责自然对应 |
| D006 | Shot 是导演语言；Generation Clip 是模型执行语言 | Frozen | 避免用模型限制污染导演设计 |
| D007 | Shot ↔ Clip 多对多 | Frozen | 主流模型可一次多 Shot，也可能需要拆长 Shot |
| D008 | Final Generation Brief 为模型无关一等对象 | Frozen | 支持模型切换、可追溯、可 QA，并把 Prompt 降为执行表示 |
| D009 | Prompt 不是项目真相 | Frozen | 避免模型切换或 Prompt 重编译破坏创作层 |
| D010 | Compiler 无创作权 | Frozen | 防止下游为了模型方便静默改写剧情、表演和镜头 |
| D011 | No Silent Repair | Frozen | 每个层级只拥有自己的决策权；越权变化必须返回上游 |
| D012 | AI 审片只做辅助，人是最终审片者 | Frozen | 表演、节奏、视听感受存在强主观性 |
| D013 | Planned / Observed / Canonical Reality 分离 | Frozen | 生成结果不能自动污染后续影片事实 |
| D014 | State Continuity 与 Video Continuation 分离 | Frozen | 普通 CUT 仍要继承世界状态，但不应强行续视频 |
| D015 | Stable Tail，而不是机械最后一帧 | Frozen | 避免把尾部畸变、模糊、错误继续传播 |
| D016 | Character Identity / Look / Current State 分离 | Frozen | 防止临时状态污染人物长期身份 |
| D017 | Asset / Reference Binding / Control Media 分离 | Frozen | 素材本身与本次生成用途必须解耦 |
| D018 | Project Memory = 正式项目事实，不是聊天记忆 | Frozen | AI 必须知道“影片真实是什么”，不是只记用户说过什么 |
| D019 | 旧下游内容不因上游修改而删除 | Frozen | 保留创作历史，做精确 Impact Analysis |
| D020 | 第一版只保留少量专业 AI 角色，不做自主多 Agent 社会 | Frozen | 优先上下文、权限、方法和可追溯性，而不是 Agent 数量 |
| D021 | 模型通过 Profile + Compiler + Adapter 接入 | Frozen direction | 避免产品业务层绑定 H3 或某单一供应商 |
| D022 | Hard Capability 与 Reliability Knowledge 分离 | Frozen | 避免把内部经验误当官方能力 |
| D023 | 系统架构优先模块化单体 | Frozen direction | 第一版降低复杂度，保留清晰模块边界和未来拆分空间 |
| D024 | 核心生产对象不再只保存在巨型 Project JSON | Frozen direction | Scene/Shot/Clip/Brief/Take/State 都有独立版本和依赖 |
| D025 | 大规模 UI 重建前先跑 H3 Vertical Slice | Frozen | 先验证生产发动机，再投入页面重建 |
| D026 | D1 / 当前前后端基础是否保留由工程验证决定 | Validate | 不为技术“升级”而升级，也不被旧实现绑架 |
| D027 | H3 / Seedance 的硬限制必须按当前官方/真实 API 再验证 | Validate | 模型能力会变化，不能靠记忆 |
| D028 | 自建 H3 生产服务器按需开关机；在已确认关机时，`fail_to_fetch_task` / HTTP 404 归类为预期的 `provider unavailable`，保留失败 Job 与执行证据 | Frozen | 停机节省资源是既定运行方式；不能把本次预期离线误判为未知路由故障或伪造成成功 |
| D029 | #002 Real H3 Film Validation 标记为 `DEFERRED / EXPECTED_INFRASTRUCTURE_OFFLINE`；不重试现有 Clip A；A+B+C1+C2 真实影片验收延期到正式网站 Generation Flow 接通之后 | Frozen | 先完成正式网站中的生成流程，再按需启动 H3 服务器执行影片验收；这是本次对 D025 顺序的明确例外，#002 未获 System/Film PASS |
