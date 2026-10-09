# AI Film Studio — Production Rules v0.1

> 本文件只记录可直接作为施工约束的冻结规则。  
> 若与临时讨论、旧 v12 实现或旧 UI 冲突，以本文件和 Master Blueprint 为准。

## A. 产品目标

1. 系统最高目标是稳定产生更好的 AI 影视成片，而不是展示更多 AI 功能。
2. Pre-generation First：主要智能投入在生成之前。
3. Near-Final Generation：Clip 应尽可能接近最终影片可直接使用的段落。
4. Human Taste, AI Assistance：AI 审片是辅助，主观视听判断和最终采用属于创作者。
5. Post-production 用于完成影片，不用于拯救错误的生成规划。

## B. Scene / Shot / Clip / Take

6. Scene = 叙事/时空单位。
7. Shot = 导演/电影语言单位。
8. Clip = 视频模型执行单位。
9. Take = 一次真实生成结果。
10. Selection = 创作者采用决定。
11. Shot ↔ Clip 不是 1:1，必须支持多对多。
12. 多个 Shot 可进入一个 Clip。
13. 一个 Shot 可拆成多个 Clip。
14. 模型单次最大时长是容量，不是规划目标。
15. 03 负责“怎么拍”；04 负责“怎么生成”。
16. 04 可以改变生成方式，不能静默改变导演设计。

## C. Final Brief / Prompt / Compiler

17. Final Generation Brief 是模型无关的一等生产对象。
18. Prompt 不是项目真相。
19. 正确链路：Final Brief → Compiler → Compiled Task → Model。
20. Compiler 只做模型执行翻译，没有创作权。
21. 下游不得 Silent Repair 上游事实。
22. 如模型执行要求改变导演设计，必须返回上游 Revision Proposal。
23. Final Brief 需要独立版本化。
24. Brief QA 与 Model Preflight 必须分开。

## D. References / Assets

25. Reference Source ≠ Reference Role。
26. Asset ≠ Reference Binding ≠ Control Media。
27. Character Identity ≠ Character Look ≠ Current State。
28. Location Identity ≠ Current Scene State。
29. Take 不能自动变成 Canonical Asset。
30. 从 Take 提取的稳定尾帧可作为 Control Media，但不自动覆盖主人物/场景资产。
31. 参考图不自动等于首帧。
32. 采用 Just-in-Time Visual Preparation，不要求整片所有资产先完成。

## E. Continuity / Film Reality

33. CUT 不重置世界状态。
34. Planned State ≠ Observed Reality ≠ Canonical Film Reality。
35. 未采用 Take 不能更新 Canonical State。
36. AI 可以辅助观察实际状态，但不能自动宣布项目真相。
37. 下一 Clip 继承 Canonical Film Reality，而不是旧 Planned State。
38. Continuity 服务下一次生成，不做成独立行政负担。
39. 重要连续信息包括人物、Look、位置、朝向、视线、持物、道具、环境、剧情知识和情绪余韵。
40. 时间跳跃需要重新判断哪些状态保留，不能机械复制全部状态。

## F. Handoff / Continuation

41. State Continuity、Visual Anchor、Video Continuation 必须分开。
42. Video Continuation 不是默认策略。
43. 明确 CUT、反打、新机位、Scene Change、Time Jump 通常不做 Video Continuation。
44. 同一长 Shot 拆分、未完成连续动作、连续摄影机运动等可考虑 Video Continuation。
45. Video Continuation 必须依赖上一 Clip 已采用的真实 Take。
46. 续接优先使用 Stable Tail，不机械使用最后一帧。
47. 上游 Selection 被替换后，依赖其视觉/视频延续的下游必须标记受影响。

## G. Review

48. AI Review 不作为最终审美裁判。
49. 不使用单一 AI 总分作为 Take 的核心质量判定。
50. 用户可以采用、换 Take、重做、修改制作方案、接受实际变化。
51. “接受实际变化”后才可进入 Canonical Film Reality。

## H. Version / Dependency

52. 上游修改不删除下游历史。
53. 已生成 Take 永久保留历史。
54. 系统自动做 Impact Analysis。
55. 下游状态至少区分：仍有效 / Needs Reconfirmation / Must Replan。
56. 每个重要对象必须可追溯版本、来源和状态。
57. 一个 Take 必须能追溯到当时的 Brief、Compiler、Model Profile、Reference、Generation Job。

## I. Model Layer

58. 模型能力来自版本化 Model Profile，不来自 LLM 记忆。
59. Hard Capability 与 Reliability Knowledge 分开。
60. 新模型通过 Model Profile + Compiler + Adapter 接入。
61. 不静默换模型。
62. Generation Job 技术失败不能破坏 Final Brief。
63. 同一 Clip 可拥有多个 Generation Job 和多个 Take。

## J. Agent / Skill

64. 第一版不做自主多 Agent 社会。
65. 用户不需要管理 Agent / Skill。
66. 第一版主要 AI 角色：创作/导演 AI、制作 AI、审片辅助 AI。
67. Skill 必须定义输入、步骤、输出、权限、停止条件和 QA，而不是只有一段长 Prompt。
68. AI 不直接写正式项目状态；重要输出先经过结构校验、权限校验和必要的人类确认。
69. 当前明确用户决定优先级最高。

## K. UX

70. 媒体只有真实存在时才占大空间。
71. 不为 UI 制造虚假 Storyboard 或假视频。
72. 03 以 Shot Plan 为核心，不做假 Player。
73. 04 以 Production Plan / Final Brief 为核心，不做“大画面 Player First”。
74. 05 因为已有真实视频，采用 Player First。
75. 前台尽量用自然创作语言，不暴露无必要的系统术语。
76. 用户不需要手动管理 Prompt、Asset ID、Dependency Graph、Compiler Version 等内部信息。
