# #003 Creator Experience / UI / UX 本地取证

**取证日期：**2026-10-09（Asia/Shanghai）  
**对象版本：**Git `98abd21dd744aa1eaed684982b91e48089f8bd55`，#003 已完成版本  
**网站：**`http://127.0.0.1:3000`；重点项目：`/projects/station-film/04`  
**方法：**真实 Chrome（Chromium 内核）浏览器，使用 Playwright DOM 定位和实际点击；截图由同一浏览器生成。Web 为本地 Next.js 生产构建，API 为本地 FastAPI。只创建本报告和截图；**没有修改产品代码、样式或业务逻辑**。本报告是供 Master Planner 独立验收的观察，不替代架构或影片验收。

## 数据隔离与证据边界

正式截图使用 `output/h3-002-2026-10-09/production.sqlite`。该库中真实 Take 数为 **0**，Clip A 保留原失败 Job，H3 显示“服务未启动”；没有点击生成或技术重试。交互演示短暂将同一网站的 API 指向独立 `output/e2e/studio-test.sqlite`，由现有测试脚本创建明确标记 `TEST ONLY` 的候选；测试媒体是不可播放的占位字节，不是生成影片。05 中输入的“实际结尾”也明确写着 **TEST ONLY / 没有真实视频可观察**，只为演示人工确认门槛。演示后 API 已恢复指向正式库。

正式库取证前后 SHA-256 均为 `207e4a030b9dead281a96afbe49da9f7af4335bfb47136b28edb7946f2adfeae`；真实 Take 数始终为 **0**。TEST ONLY 截图和状态不得用于 #002 Film PASS。

## 截图清单

截图目录：[`003-creator-experience-evidence/`](003-creator-experience-evidence/)。`SHA256SUMS` 提供每张原始 JPEG 的校验值。下表的尺寸为浏览器 **viewport**；标有“整页”的截图保留相同宽度，图片高度随页面增长。其余为当前 viewport 截图。所有截图均为真实浏览器画面，未改图、拼贴或加入假媒体。

### 1440 × 900 — 正式 station-film

| 截图 | 页面 / 状态 |
|---|---|
| [1440-00-home.jpg](003-creator-experience-evidence/1440-00-home.jpg) | Home；创建入口、项目卡片、搜索 |
| [1440-00-home-full.jpg](003-creator-experience-evidence/1440-00-home-full.jpg) | Home，**整页 1440 × 1178** |
| [1440-01-script.jpg](003-creator-experience-evidence/1440-01-script.jpg) | 01 剧本；原稿与 Scene |
| [1440-01-script-full.jpg](003-creator-experience-evidence/1440-01-script-full.jpg) | 01，**整页 1440 × 1018** |
| [1440-02-world.jpg](003-creator-experience-evidence/1440-02-world.jpg) | 02 人物与世界；身份、缺失视觉锚点、无真实资产 |
| [1440-02-world-full.jpg](003-creator-experience-evidence/1440-02-world-full.jpg) | 02，**整页 1440 × 1264** |
| [1440-03-shot-plan.jpg](003-creator-experience-evidence/1440-03-shot-plan.jpg) | 03 场次与分镜；Shot Card 默认层级 |
| [1440-03-shot-plan-full.jpg](003-creator-experience-evidence/1440-03-shot-plan-full.jpg) | 03，**整页 1440 × 2299**；五张 Shot Card 与添加入口 |
| [1440-03-shot-edit.jpg](003-creator-experience-evidence/1440-03-shot-edit.jpg) | 03 首张 Shot Card 展开编辑；未保存任何改动 |
| [1440-04-production-plan.jpg](003-creator-experience-evidence/1440-04-production-plan.jpg) | 04 Production Plan；Clip A–C2 与 H3 离线 |
| [1440-04-production-plan-full.jpg](003-creator-experience-evidence/1440-04-production-plan-full.jpg) | 同上，**整页 1440 × 1475**；可看完整 Clip 列表 |
| [1440-04-final-brief.jpg](003-creator-experience-evidence/1440-04-final-brief.jpg) | 04 Clip A 展开；三 Shot → 一个 Clip |
| [1440-04-final-brief-detail.jpg](003-creator-experience-evidence/1440-04-final-brief-detail.jpg) | 04 Final Brief 11 项正文，显示原始 ID/JSON |
| [1440-04-final-brief-full.jpg](003-creator-experience-evidence/1440-04-final-brief-full.jpg) | Clip A 展开，**整页 1440 × 2794**；映射、Brief、失败 Job |
| [1440-04-long-shot-c1.jpg](003-creator-experience-evidence/1440-04-long-shot-c1.jpg) | 04 长 Shot S05 0–12s → C1 |
| [1440-04-long-shot-c1-full.jpg](003-creator-experience-evidence/1440-04-long-shot-c1-full.jpg) | 同上，**整页 1440 × 4081** |
| [1440-04-long-shot-c2.jpg](003-creator-experience-evidence/1440-04-long-shot-c2.jpg) | 04 长 Shot S05 12–20s → C2，视频续接等待 Stable Tail |
| [1440-05-no-real-take.jpg](003-creator-experience-evidence/1440-05-no-real-take.jpg) | 05 无真实 Take；无假播放器或假视频 |
| [1440-05-no-real-take-full.jpg](003-creator-experience-evidence/1440-05-no-real-take-full.jpg) | 05，**整页 1440 × 900** |
| [1440-06-empty-timeline.jpg](003-creator-experience-evidence/1440-06-empty-timeline.jpg) | 06 正式项目空 Timeline |
| [1440-06-empty-timeline-full.jpg](003-creator-experience-evidence/1440-06-empty-timeline-full.jpg) | 06，**整页 1440 × 1141** |

### 1280 × 800 — 正式 station-film

| 截图 | 页面 / 状态 |
|---|---|
| [1280-03-shot-plan.jpg](003-creator-experience-evidence/1280-03-shot-plan.jpg) | 03 Shot Card |
| [1280-04-production-plan.jpg](003-creator-experience-evidence/1280-04-production-plan.jpg) | 04 Clip Plan、离线提示 |
| [1280-05-no-real-take.jpg](003-creator-experience-evidence/1280-05-no-real-take.jpg) | 05 无 Take 空状态 |

### 1024 × 768 — 正式 station-film

| 截图 | 页面 / 状态 |
|---|---|
| [1024-02-world.jpg](003-creator-experience-evidence/1024-02-world.jpg) | 02 视觉身份 / 无资产 |
| [1024-03-shot-plan.jpg](003-creator-experience-evidence/1024-03-shot-plan.jpg) | 03 Shot Card；导航折为仅图标 |
| [1024-04-production-plan.jpg](003-creator-experience-evidence/1024-04-production-plan.jpg) | 04 制作计划；导航折为仅图标 |
| [1024-06-empty-timeline.jpg](003-creator-experience-evidence/1024-06-empty-timeline.jpg) | 06 空 Timeline |

### 390 × 844 — 正式 station-film

| 截图 | 页面 / 状态 |
|---|---|
| [390-04-production-plan.jpg](003-creator-experience-evidence/390-04-production-plan.jpg) | 04 窄屏 Clip Plan；无横向溢出 |
| [390-04-navigation-open.jpg](003-creator-experience-evidence/390-04-navigation-open.jpg) | 打开导航后六个工作区均可见 |

### 1440 × 900 — **独立 TEST ONLY 数据库**

| 截图 | 页面 / 状态 |
|---|---|
| [1440-qa-05-test-only-before-selection.jpg](003-creator-experience-evidence/1440-qa-05-test-only-before-selection.jpg) | 05 有测试候选的 Player First 布局；明确不可播放 |
| [1440-qa-05-test-only-before-selection-full.jpg](003-creator-experience-evidence/1440-qa-05-test-only-before-selection-full.jpg) | 同上，**整页 1440 × 1046** |
| [1440-qa-05-test-only-selected.jpg](003-creator-experience-evidence/1440-qa-05-test-only-selected.jpg) | 点击“采用这条”后 Selected，Canonical 尚未确认 |
| [1440-qa-05-observed-needs-confirmation.jpg](003-creator-experience-evidence/1440-qa-05-observed-needs-confirmation.jpg) | 输入明确 TEST ONLY 的观察，出现人工确认框 |
| [1440-qa-05-canonical-confirmed.jpg](003-creator-experience-evidence/1440-qa-05-canonical-confirmed.jpg) | 点击“接受实际结果”后的测试 Canonical |
| [1440-qa-06-selected-before-add.jpg](003-creator-experience-evidence/1440-qa-06-selected-before-add.jpg) | 06 已采用 TEST ONLY Take，Timeline 尚空 |
| [1440-qa-06-test-only-timeline.jpg](003-creator-experience-evidence/1440-qa-06-test-only-timeline.jpg) | 06 测试 Take 已加入 Timeline；无可播放媒体 |
| [1440-qa-06-test-only-timeline-full.jpg](003-creator-experience-evidence/1440-qa-06-test-only-timeline-full.jpg) | 同上，**整页 1440 × 1156** |
| [1440-qa-06-test-only-export-rejected.jpg](003-creator-experience-evidence/1440-qa-06-test-only-export-rejected.jpg) | 点击可用的“导出预览”后，API 拒绝测试 Take |

## 交互事实

1. **03 Shot 编辑。** 首张 Shot Card 的“修改”能展开目的、时长、画面、动作、表演、摄影、声音字段。仅展开查看，未保存。默认卡片先显示镜头编号/时长/确认状态，再显示目的、描述、四项制作细节；视觉层级清楚。
2. **04 映射。** Clip A 展开后显示 S01 0–3s、S02 3–5s、S03 5–10s 的 Clip 内时间和 CUT；C1、C2 分别显示 S05 的 0–12s 与 12–20s，C2 提示等待上一条采用和 Stable Tail。证明“多 Shot → 一个 Clip”以及“长 Shot → 多 Clip”在真实页面可见。没有编辑映射或提交生成。
3. **04 离线。** 页面明确写“H3 视频服务器当前未启动”，同时告诉用户可以继续镜头和制作计划；Clip A 旧失败仍标“生成失败”，未出现成功假象。生成按钮被禁用。
4. **05 正式空状态。** Clip A 没有真实 Take，页面用文字与返回 04 的入口说明，不放大播放器或假缩略图。
5. **05 TEST ONLY。** 测试候选出现大审片框、候选列表、采用按钮，框内直写“测试结果或媒体不可播放”，候选 ID 旁标 `TEST ONLY`。点击采用后实际状态仍待填写；填写 `TEST ONLY：流程演示…没有真实视频可观察` 后才出现“接受实际结果”；接受后才显示已确认。该流程证明 UI 门槛，**不能证明真实视频 Player First 播放、审片质量或电影连续性**。
6. **06。** 正式项目是空 Timeline；测试库中已采用候选可加入时间线，显示 trim/转场/音量/字幕控件。测试媒体不播放；导出时后端拒绝，未产生成片或预览。
7. **响应式。** 1440/1280/1024/390 的 `documentElement.scrollWidth` 分别等于 viewport 宽度，所测页面没有横向溢出；390 的汉堡菜单能展开六工作区。

## 创作者体验观察

**整体视觉。** 深色、暖金、克制的卡片与清楚的六步导航，整体更像影视创作产品而非通用后台。04 先给计划、05 才给大审片框、06 保持轻量，符合媒体优先级。无真实资产时 02 用文字和空状态；本轮未看到假 Storyboard、假缩略图或假视频。Home 的电影图标是装饰性的项目卡片图形，不冒充作品画面。

**新用户理解。** 01→06 标签较直接，各页副标题说明用途。但 1024px 导航折成仅图标、英文小型眉题密集，首次进入的人需要猜图标；04 的 Shot/Clip、Stable Tail、READY 和生成策略仍要求一定内部概念。若没有真实媒体，05 的提示足够明确。H3 离线提示是本轮最清楚的状态说明之一。

**03 回答“这一场怎么拍”。** Shot Card 的框架覆盖目的、画面、动作、表演、摄影、声音；编辑字段也齐。雨夜车站现有五张卡却全部标“已确认”，目的和四项细节仍是“待补充”。因此真实项目页面目前主要是画面描述列表，尚不能凭卡片本身充分回答“怎么拍”。这是现有数据与确认门槛合在一起的体验问题，不能仅凭截图归咎于样式。

**04 回答“怎样生成最好”。** Scene、Clip、策略、时长、映射、离线/失败状态首先出现，信息顺序正确。Clip A 与 C1/C2 的映射比后台表格直观。展开后页面非常长，多个 Clip 可同时展开；在 1440px 下 A+C1+C2 会将主线拉到数千像素。Final Brief 的段落框架像制作方案，但部分关键内容仍原样输出机器字段。

**05 Player First。** 正式库无 Take，无法验收真实视频播放、A/B 切换或审片质量。TEST ONLY 状态验证了有候选时大播放器位置和人工决定流，但黑框不可播放且明确标为测试。不能据此宣称 Film PASS。

**06 轻量。** 空状态、候选加入、序列卡、trim、转场、音量、字幕都保持轻量；未验证真实媒体播放与 ffmpeg 输出。测试库的导出按钮/错误文案有明显体验缺口，见下。

## 观察到的问题（未修改代码）

| 优先级 | 观察与影响 | 证据 |
|---|---|---|
| 高 | **05 计划/实际对照失真。** 真实 Brief 有结构化 `planned_state_out`，但 TEST ONLY 审片页显示“未在最终制作方案中填写”，随后把人工输入一律判成与计划不同。用户无法据此准确决定下一片段承接什么。 | [04 Brief](003-creator-experience-evidence/1440-04-final-brief-detail.jpg)、[05 确认框](003-creator-experience-evidence/1440-qa-05-observed-needs-confirmation.jpg) |
| 高 | **03 已确认的 Shot 仍缺关键导演字段。** 雨夜车站五张 Shot Card 的目的、动作、表演、摄影、声音均“待补充”，但状态全为“已确认”。确认语义与实际完整度冲突。 | [03 默认](003-creator-experience-evidence/1440-03-shot-plan.jpg)、[03 编辑](003-creator-experience-evidence/1440-03-shot-edit.jpg) |
| 高 | **Final Brief 暴露机器真相。** 人物/场景显示 `linxia · old-station`，开始状态为 `scene_initial`，结束状态为 JSON 文本，直接破坏“最终制作方案”人话阅读。 | [Brief 正文](003-creator-experience-evidence/1440-04-final-brief-detail.jpg) |
| 中 | **06 导出按钮的可用性与实际限制矛盾。** TEST ONLY 时间线中“导出预览”可点，点击后才显示英文 `timeline contains non-current or test Take`。后端正确阻止了假成片，但前端未预先解释。 | [有内容时间线](003-creator-experience-evidence/1440-qa-06-test-only-timeline.jpg)、[拒绝](003-creator-experience-evidence/1440-qa-06-test-only-export-rejected.jpg) |
| 中 | **01 正式项目的原稿为空，却已有完整 Scene。** 新进入雨夜车站的人会看到 0 字和 1 个场次，缺少两者为何不同的解释；Home 项目卡也只能给泛化续写提示。 | [01](003-creator-experience-evidence/1440-01-script.jpg)、[Home](003-creator-experience-evidence/1440-00-home.jpg) |
| 中 | **04 “READY” 范围不清。** C1/C2 的 Brief 显示 READY，同时下方要求等待上游 Selection / Stable Tail，Clip 卡在离线状态。页面未直接说明 READY 只代表制作方案检查，容易被理解为可以生成。 | [C1](003-creator-experience-evidence/1440-04-long-shot-c1.jpg)、[C2](003-creator-experience-evidence/1440-04-long-shot-c2.jpg) |
| 中 | **1024px 导航只剩图标。** 页面没有可见 01–06 文字；虽然链接有无障碍名称，初次使用者需猜图标或悬停。 | [1024 03](003-creator-experience-evidence/1024-03-shot-plan.jpg)、[1024 06](003-creator-experience-evidence/1024-06-empty-timeline.jpg) |
| 低 | **信息密度局部偏高。** 02 的缺锚点说明压成一段小字；03 的四项细节、04 的映射控件和英文眉题字级偏小。大屏留白总体平衡，长页查找具体任务仍需多次滚动。 | [02](003-creator-experience-evidence/1440-02-world.jpg)、[04 整页](003-creator-experience-evidence/1440-04-final-brief-full.jpg) |
| 低 | **TEST ONLY Take 可重复“加入”。** 已在 06 序列里，右侧仍显示“加入”按钮；是否允许同一 Take 复用未在页面说明。 | [06 测试时间线](003-creator-experience-evidence/1440-qa-06-test-only-timeline.jpg) |

## 验收边界

本报告支持 Master Planner 对视觉、信息架构、响应式、离线体验和人工确认门槛做独立判断。它**不支持**对真实 H3 输出、视频播放、影片质量、C1→C2 连续性、真实成片导出作 PASS 结论。未进入 #004，也未修改 #003 产品实现。
