# #003 Full Creator Website Build — 施工报告

日期：2026-10-09。状态：**网站施工完成，待 Architecture / Creator Experience / Browser 验收；真实 H3 Film Validation 继续 DEFERRED / EXPECTED_INFRASTRUCTURE_OFFLINE**。本轮没有执行真实视频生成，也没有伪造 Take 或成片。

## 1. 实际完成范围

按 Checkpoint A/B/C 连续完成正式本地创作者网站、六个工作区、FastAPI、Production Core 集成、生成任务与人工影片状态流、轻量成片时间线、测试和浏览器 QA。施工前 HEAD 为 `a8e0b0dbfa81130b5aa81d132de47560ad93a388`，`git status --porcelain` 为空。#002 的 `output/h3-002-2026-10-09/production.sqlite` 及失败 Job `job-A-20261009T084845Z` 完整保留，网站直接读取它；没有再次提交 Clip A。

## 2. 技术结构

`apps/web/` 为 Next.js 15 App Router、React、TypeScript；`apps/api/` 为 FastAPI；`film_core/` 仍是唯一正式领域写入入口。API 添加页面读取模型和少量附属存储：影响事件、当前素材指针、时间线片段及字幕。Shot↔Clip 映射增加修订历史；没有新建第二套 Project / Shot / Clip / Take 真相。SQLite 与媒体留在 `output/`，该目录被 Git 忽略。服务端与前端分开运行，前端只请求 API。

## 3. Web/API 启动方式

在仓库根目录：

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt
npm ci --prefix apps/web
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

另开终端运行 `npm run dev --prefix apps/web`；网站为 `http://127.0.0.1:3000`，API 健康检查为 `http://127.0.0.1:8000/api/health`。本轮结束时本地生产构建以 `npm run start --prefix apps/web` 运行。可用 `FILM_STUDIO_DB` / `FILM_STUDIO_MEDIA` 选择独立本地数据库及受管媒体目录。`H3_SERVER_ON=1` 和服务端 `DARL_API_KEY` 只在自建 H3 真正启动后配置；前端不接收密钥。

## 4. 01 剧本

Home 可建项目、搜索最近项目、从一句想法/文本进入；01 可编辑原稿并保存版本、添加/改写/排序/归档 Scene、标记场次可进入导演设计。归档前提醒下游影响，旧版本与下游对象保留。

## 5. 02 人物与世界

分开展示人物、造型、场景、道具身份；上传真实 PNG/JPEG/WebP，检查声明类型、文件签名和 10 MB 上限；显示资产版本并由人指定当前版本。按后续 Brief 中出现的人物、造型及场景显示缺失视觉锚点。没有素材时使用文字身份，素材不自动变成首帧或长期 Master Asset。图片生成尚未接入。

## 6. 03 场次与分镜

Scene 导航和 Shot Card 展示镜头目的、画面、动作、表演、摄影、声音、时长。支持新增、修改、确认、排序、拆分与归档；长镜头可保持一个 Shot，再由 04 分到不同 Clip。无真实 Storyboard 时不显示虚构画面。

## 7. 04 影片制作

首先显示 Production Plan 与 Clip Plan：镜头映射、区间、时长、策略、上游依赖、Ready/Not Ready/失败/服务离线状态及 Take 数量。展开 Clip 可编辑映射和最终制作方案。已有 Clip A 的旧失败 Job 以“生成失败”呈现，其余规划不被离线服务阻塞。没有真实视频时不设大播放器。

## 8. 05 审片

仅有实际 Take 时展示 Player First、候选切换、采用决定；没有真实 Take 时显示清楚的空状态。测试数据标注 `TEST ONLY` 且不作为真实媒体播放。采用后，页面并列展示计划结尾与人工填写的实际结尾；如两者不同，使用普通语言要求明确接受，再更新 Canonical。切换候选时不能把另一条 Take 的观察误记到已采用 Take。

## 9. 06 成片

时间线引用已采用的受管 Take，支持加入、排序、裁切、用当前已采用 Take 替换、连续播放、直接 CUT/简单淡入、基础音量、字幕轨及本地预览导出。导出依赖 `ffmpeg`，字幕另存 `.srt`；不修改原始 Take。真实视频缺失时预览不存在，空时间线不显示假播放器。

## 10. Production Core 接入方式

API 调用既有 `Core` 完成版本化对象、Brief QA、H3 编译、Model Preflight、Job 事件、Take、Selection、Observed 与 Canonical。正式生成链为 Final Brief → H3 Compiler → Compiled Task → Job → Darl H3 Adapter；UI 不接受手工 Raw Prompt 绕过。API 合同测试验证 Job 快照仍指向 Brief 版本。模型 Profile 在需要时以已记录的 `h3-darl` 文档化 Profile 建立，未把其真实可靠性伪称 VERIFIED。

## 11. Shot↔Clip UI

04 显示多镜头进入同一 Clip（A：S01/S02/S03）及长镜头区间进入不同 Clip（C1：S05 0–12s，C2：S05 12–20s）。映射编辑写入 Core 的修订历史，旧记录不删。

## 12. Final Brief UI

按目的、时间线、人物/世界/道具、开始状态、动作过程、表演、摄影、声音、真实参考素材、计划结束状态与衔接展示和编辑。保存新 Brief 版本，生成前显示 QA 原因；高级执行信息折叠。真实上传资产可以按角色及固定版本绑定 Reference；参考图片不静默升级为首帧。

## 13. Provider offline / error UX

H3 服务器按需开关机。默认显示“服务未启动”，04 解释可继续做镜头与制作计划；服务端生成 API 返回 `PROVIDER_UNAVAILABLE`，不创建伪 Job。若已实际提交且 Darl 返回 `fail_to_fetch_task`/404，失败 Job 和错误事件保留、页面显示失败。LLM/Image 显示未配置或可用状态；本轮不验证其生成合同。

## 14. Generation Job UX

一个明确点击提交一个候选，参数默认为 16:9、480P、20 步；既有失败 Job 只能在显式 `retry_of` 下重新提交。没有自动轮询、无限重试或批量候选。成功提交后提示预计约 3 分钟，用户可稍后手动同步。当前 H3 离线，网站端没有实际提交。

## 15. Take / Selection / Canonical

Take 仍由真实 Job 与 Media Record 产生；API 拒绝跨 Clip Selection。Selection、Observed Reality、人工 Canonical 确认分开，05 不能静默把计划或 AI 提案写成实际事实。自动化中使用独立数据库、显式 `TEST ONLY` 候选验证流程；真实项目数据库仍为 0 条真实 Take。

## 16. Continuity / Impact

故事、Scene、Shot、Brief、世界身份/素材版本改变会生成下游影响提示或触发既有 Core 的版本失效。C1 更换 Selection 后，C2 旧 continuation 准备被标记 `Must Replan / Rebuild`。UI 用自然语言展示影响，不删除旧对象。Stable Tail 仍须来自已采用真实 Take，不以普通参考视频冒充。

## 17. Final Timeline

API 保证只加入当前采用的受管媒体，替换操作再次验证当前 Selection；导出拒绝 test-only、过期 Selection 或丢失媒体。时间线保存引用与 trim/transition/volume，预览是新文件，原 Take 不可变。

## 18. Browser QA

实际 Chrome 查看 Home、01–06 导航和主要页面；在 1440px 检查 05 无 Take、06 空时间线，在 1280px 检查 03 Shot Cards，在 1024px 检查 02 真实身份/锚点提示及 04 离线 Clip Plan，在 390px 检查 04 窄屏导航与卡片。问题修正：1024px 收窄导航仍保留可访问名称，06 空时间线移除无内容的大面板。04 的旧 Clip A 明确显示失败，不出现伪视频。05/06 的人工状态流另有浏览器 E2E 验证。窄屏只保证可访问与不崩坏，完整移动端剪辑体验未实现。

## 19. 自动测试

`.venv/bin/python -m unittest discover -s tests -v`：**20/20 通过**（#001 6、#002 6、#003 API 8）。`python3 -m compileall -q film_core apps/api scripts tests`、`npm run build --prefix apps/web`、`git diff --check` 均通过。API 测试覆盖版本冲突、映射历史、Brief 版本、Compiled Task 快照、离线/失败 Job、Selection/Canonical、C1→C2 失效、上传校验与时间线引用。

## 20. E2E 测试

`npm run test:e2e --prefix apps/web`：**3/3 通过**。覆盖新项目→剧本→Scene→身份→Shot→Clip→READY Brief 且 H3 离线；雨夜车站真实 Brief 与无假媒体；独立测试库中 `TEST ONLY` Take 的采用→实际观察→人工确认→时间线。测试专用 `output/e2e/` 不污染 #002 数据库；CI/浏览器测试不调用真实 H3。

## 21. 真实 H3 是否执行

**没有**。生产服务器仍按已确认事实处于关机状态，本轮只读取并保留 #002 失败 Job。A+B+C1+C2 真实网站端生成、审片、Stable Tail、续接和拼接预览均未发生，仍是 Beta Release 前的验收阻断项。当前没有真实生成产物或拼接路径。

## 22. 已知问题 / 技术债

- 本地单人开发模式尚无登录、权限与线上数据库/对象存储迁移；不是 Beta 部署配置。
- Contextual AI 提案、LLM/Image 生成未接入：接口可靠性尚未验证；本轮没有假提案或静默写入。
- 05 尚无自动客观镜头质检标注；人工可审片和决定。06 仅提供轻量顺序播放器和简单淡入，浏览器预览与 `ffmpeg` 导出效果仍待真实媒体验证。
- H3 Profile 的真实表现、媒体返回、A→B→C1→C2 连续性均待服务器开机后的真实影片验收。

## 23. 明确未做内容

没有多人协作、计费、重型 NLE、多模型路由、AI 主观总分、假 Storyboard/缩略图/视频、自动批量生成、Seedance、Beta Hardening、Release 或旧项目改动。

## 24. Git commits

- `b0c39c3` — Checkpoint A: boot creator website and core-backed API
- `5b1dd8f` — Checkpoint B: connect production planning, generation and film reality
- `79b4c10` — Checkpoint C: finish creator flow and browser verification
- 本报告所在提交：见提交记录最新一项。

所有提交仅在本地；无 Git remote，未 push。

## 25. 工作区是否 clean

本报告提交后执行 `git status --porcelain` 核对，预期为空。`output/`、`node_modules/`、`.venv/`、`.next/`、`.next-e2e/` 与 `.env*` 被忽略；旧失败证据仍在本地。

## 26. 本地网站地址

<http://127.0.0.1:3000>；雨夜车站生产计划：<http://127.0.0.1:3000/projects/station-film/04>。API：<http://127.0.0.1:8000/api/health>。

## 27. 部署 / 测试站

未部署；没有测试站地址。本轮完成后停止，等待 Architecture Review、Creator Experience Review、Browser Review；H3 上线后再做 Film Review。不进入 Beta Hardening / Release。
