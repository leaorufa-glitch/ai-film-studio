# Provider Simplification — Darl-Only H3 Routing

日期：2026-10-10。状态：代码与离线验收完成，修复分支提交后等待架构验收；不合并 main、不部署、不真实生成。

## 1. 基线与边界

- 仓库：`leaorufa-glitch/ai-film-studio`。
- 本地与远端 main 基线：`163ccd621691d13af1e6793a768b822a08bda226`，开工工作区 CLEAN。
- 分支：`refactor/darl-only-h3-routing`，从基线创建，未覆盖或重写 main 历史。
- Architecture Reset / v0.1；本次仅落实 D030 的单 Provider 路由与必要的当前树清理，不进入 #005。
- 没有生产 API / Runtime 重启，没有执行 Clip A 的真实 Technical Retry、Creative Regenerate 或真实生成；没有开始 B / C1 / C2。
- 没有修改或迁移正式数据库、Shot Plan、Clip A、`brief:A v1`、原 Compiled Task 或原失败 Job。

## 2. 实现

### 单 Provider、两个 execution models

- 唯一视频 Provider：`darl`。同一个 `DarlH3Adapter` 使用 `POST https://api.darl.cn/v1/videos`。
- 同一个 JSON 合同，`model` 分别为自建 `MiniMax-H3` 或云端备用 `runninghub-minimax-h3`，没有第二套视频 Adapter。
- 新生成按既有 `H3_SERVER_ON` 选择 execution model；不新增调度系统，不在提交失败后静默更换模型。
- API 只接受省略 Provider 或显式 `provider=darl`；其他 Provider 参数在创建任务前拒绝。
- Final Brief 不变。Compiler 只新增执行事实字段：`provider`（有 Profile 来源时）与 `execution_model`，不改变创意语义哈希或领域对象真相。
- Model Profile、Compiled Task、Job snapshot / provenance 记录实际 execution model。Runtime、Managed Media 与 Take provenance 同样保留执行模型。

### Technical Retry 与旧数据

- Creator / Admin Technical Retry 复用原 Compiled Task，不重新编译，不读取最新 Brief，不改变原 execution model、参数、引用或 continuation。
- 原自建任务在 `H3_SERVER_ON` 关闭时返回 `EXECUTION_MODEL_UNAVAILABLE`，不改用云端；云端任务不因自建恢复而改回自建。
- 修改 execution model 属于新的、有明确原因的 Creative Regenerate；可继续使用同一 Final Brief 版本。
- 旧 Darl Task 缺少新路由字段时，由原 `target_model` / Darl Profile 恢复模型，保留原 Task，不回写历史字段；重试成本快照记录原实际分辨率。
- 旧非 Darl Provider Job 只读保留，以 `LEGACY_PROVIDER_UNSUPPORTED` 拒绝执行或重试。Runtime 不恢复、轮询或下载旧直连任务；Job 与事件历史不迁移、不删除。
- 旧配置与 Profile 可保留在历史数据库中，但不再作为现行配置展示或使用。当前树不保留旧直连 Adapter、专属凭证、工作流、上传或查询实现。
- 历史垂直切片 CLI 的 submit / sync 入口也采用同一 Darl 模型路由及原 Task 重放，避免出现第二条会绕开冻结规则的执行路径；未运行真实 CLI 提交。

### Creator 与 Admin

- Creator 删除 Provider 选择，只显示“自建 H3”或“云端 H3 · 备用”。历史 Job 显示其实际路线，旧直连 Job 显示“旧 Provider · 只读”。
- Technical Retry 显示原冻结路线；原自建离线时禁用按钮，旧直连任务不显示重试按钮。
- Admin 仅保留一个 Darl 视频 Provider，在该 Provider 下展示两个 execution models。LLM / Image 的既有 Darl 服务不变。
- 独立 Admin 与 Creator 界面、人工 Selection / Observed / Canonical Gate 保持不变。

## 3. 修改文件

当前保留的新增 / 修改文件：

1. `film_core/h3_profile.py`：执行模型标识、标签、Profile 与既有 availability 选择。
2. `film_core/darl_h3.py`：单 Adapter 支持两个 model id，验证冻结模型一致性。
3. `film_core/core.py`：Compiler 新增执行事实快照字段；无 schema 迁移或业务真相层重构。
4. `apps/api/main.py`：Darl-only 新生成、原 Task 重试、可用性与 Admin 视图清理。
5. `apps/api/job_runtime.py`：Darl-only Runtime、冻结模型离线处理、跳过旧 Provider 历史。
6. `scripts/h3_slice.py`：既有 CLI 的同一路由、原 Compiled Task 重试及旧 Provider 拒绝。
7. `apps/web/src/lib/api.ts`：路由类型、标签与旧 Job 检测。
8. `apps/web/src/components/Workspace.tsx`：执行路线展示，取消 Provider 选择与旧工作流提示。
9. `apps/web/src/app/admin/page.tsx`：一个视频 Provider、两个模型、只读历史任务。
10. `apps/web/playwright.config.ts`：隔离 E2E 环境，清空视频 / AI 凭证，禁用生产 Runtime。
11. `apps/web/tests/creator.spec.ts`：Darl 路线、冻结重试、旧 Provider 只读的浏览器回归。
12. `tests/test_004_1_architecture_alignment.py`：保持原 Brief / Task / Reference / Job / Take 冻结测试，改为同一 Darl 下的两个执行模型。
13. `tests/test_creator_api.py`：更新自建关闭时云端备用可用的合同预期。
14. `tests/test_darl_only_h3_routing.py`：新路由、传输、快照、旧数据、Runtime、CLI 与当前树清理回归。
15. `README.md`：服务配置、执行路线、重试规则与安全验证命令。
16. `docs/MASTER-BLUEPRINT.md`：D030 当前执行路线。
17. `docs/PRODUCTION-RULES.md`：Provider / execution model 分离与冻结规则。
18. `docs/DECISIONS.md`：新增 D030 正式架构决定。
19. `docs/reports/004.1-architecture-alignment-hotfix-report.md`：标明历史验收语境，旧直连描述不再作为现行规格。
20. `docs/reports/darl-only-h3-routing-report.md`：本报告。

删除四项：旧备用直连 Adapter、两份专属直连测试、旧直连接入报告。旧文件仍保留在 Git 历史，不重写历史提交。

精确增删清单可用 `git diff --name-status 163ccd621691d13af1e6793a768b822a08bda226 HEAD` 查询。

## 4. 验证结果

- Python 全量：**83/83 PASS**，失败 0、错误 0。测试发现前禁用外部 HTTP，模块级 App 明确指向临时数据库，生成提交仅使用 TEST ONLY Mock。
- Playwright E2E：**12/12 PASS**。覆盖原 01–06 / Admin 流程、两条执行路线、请求无 Provider 选择、固定云端重试、离线自建重试禁用与旧 Provider 只读。
- Next.js production build：**PASS**。使用独立 `.next-build` 目录避免覆盖正在运行的站点构建；验证后清理本轮产物，并恢复 Next 自动改写的类型引用 / tsconfig，不提交无关生成配置。
- `git diff --check`：**PASS**。
- 当前代码、UI、配置、测试、文档文字检查：只保留 Darl 云端 execution model 标识，不保留任何旧直连 Provider 实现或配置字面量。
- 原正式记录只读核对：`job-12993b562313` 原快照与 `brief:A v1` 原 payload 的 SHA256 均与施工前一致；原 `task-f98261c1a4f8` 仍与 Job 的 task snapshot 相同。没有增加真实 Job 或 Take。

首次回归暴露两处旧测试预期：原备用 Profile 名与旧“自建关机即不可生成”状态；均按 D030 更新，不放宽冻结或历史保护规则。最终全量均通过。

Python 安全命令见 README。浏览器执行 `npm run test:e2e --prefix apps/web`；构建执行 `NEXT_TELEMETRY_DISABLED=1 NEXT_TEST_DIST_DIR=.next-build npm run build --prefix apps/web`。所有提交测试均为模拟，不构成真实视频成功证据。

## 5. 未覆盖风险与停止条件

- 两个 Darl 模型的真实账号可用性、云端计费、实际输出分辨率 / 时长 / 音频、参考素材和同一长镜头续接均未在本轮真实调用验证。
- Darl 公开传输 / H3 能力合同继续由 Profile 表达；离线测试证明请求模型选择和冻结语义，不证明云端模型的真实效果或所有参数 / reference 能力。
- `REAL_H3_FILM_VALIDATION` 仍未完成，仍为 Release Blocker；Admin 正式身份认证 / 授权也未完成。
- 未部署或重启正式 API / Runtime，正在运行的旧进程不会自动加载本分支；需要在架构验收、合并及另行运行授权后使用新路由。
- 本分支提交并 push 后立即停止，等待架构验收；不合并 main、不真实生成、不启动 #005。

修复 SHA 以本报告所属 Git commit 为准，使用 `git log -1 --format=%H -- docs/reports/darl-only-h3-routing-report.md` 查询。
