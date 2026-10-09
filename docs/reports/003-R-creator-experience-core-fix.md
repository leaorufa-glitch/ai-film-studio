# #003-R Creator Experience Core Fix

## 修复

- 03：Shot 确认必须具备镜头目的、画面、动作、表演、摄影、声音和有效时长。旧的不完整确认记录在读取时显示“需要重新确认”，保留历史，不补造导演内容；API 同样拒绝不完整确认。
- 04：最终制作方案把人物、场景、道具、开始与计划结束状态转为中文制作语言；内部标识和结构化数据只放在折叠的技术详情。制作方案、生成依赖、H3 服务分开显示，服务离线时仍可继续规划。
- 05：从 Final Brief 的结构化 `planned_state_out` 读取计划结尾，与人工记录的实际结尾对照；只有点击“接受实际结果”才确认 Canonical State。
- 06：导出前读取 API 可用性检查。TEST ONLY、缺失媒体、过期 Selection 等情况禁用按钮并显示中文原因，后端拒绝保护保留。
- 1024px：保留工作区名称、01–06 含义和项目名称。01：空原稿但有 Scene 时解释结构化场次来源。

## 测试与浏览器取证

- Python 全量：21 项通过；Chromium Playwright E2E：4 项通过；Next.js production build：通过；`git diff --check`：通过。
- 浏览器：真实 Chromium，截图均为 1440×900，导航图为 1024×900。使用隔离的 `output/e2e/studio-test.sqlite`，没有改动正式 `station-film` 数据。05/06 的 Take 和媒体是明确标注的 TEST ONLY；没有真实 H3 请求。

| 证据 | 页面与状态 | 截图 |
| --- | --- | --- |
| 1 | 03，不完整 Shot 禁止确认 | [01-03-shot-confirmation-1440.png](evidence-003-r/01-03-shot-confirmation-1440.png) |
| 2 | 04，人话化 Final Brief | [02-04-final-brief-1440.png](evidence-003-r/02-04-final-brief-1440.png) |
| 3 | 04，方案、依赖、服务三类状态 | [03-04-three-statuses-1440.png](evidence-003-r/03-04-three-statuses-1440.png) |
| 4 | 05，Planned vs Observed，TEST ONLY | [04-05-planned-observed-1440-TEST-ONLY.png](evidence-003-r/04-05-planned-observed-1440-TEST-ONLY.png) |
| 5 | 06，禁用导出与中文原因，TEST ONLY | [05-06-disabled-export-1440-TEST-ONLY.png](evidence-003-r/05-06-disabled-export-1440-TEST-ONLY.png) |
| 6 | 03，1024px 工作区导航 | [06-1024-navigation.png](evidence-003-r/06-1024-navigation.png) |
| 7 | 01，空原稿与结构化 Scene 说明 | [07-01-empty-script-1440.png](evidence-003-r/07-01-empty-script-1440.png) |

实现提交：`cec6b3fc8a17aab692d99419f6af92f2462eff6b`。本报告和截图另行提交；完成后 workspace clean。未进入 #004。
