# AI Film Studio

Architecture Reset 后的独立创作者网站。`film_core/` 保存 #001/#002 的正式 Project、Shot、Clip、Brief、Task、Job、Take 与影片状态；`apps/api/` 是 FastAPI 包装层；`apps/web/` 是 Next.js + TypeScript 六个工作区。项目媒体与本地数据库保存在 Git 忽略的 `output/`。

## 本地启动

要求 Python 3.9+、Node.js 20+、npm。导出预览还需要 `ffmpeg`。

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt
npm ci --prefix apps/web
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

另开终端，在项目根目录执行：

```bash
npm run dev --prefix apps/web
```

网站：<http://127.0.0.1:3000>；API 健康检查：<http://127.0.0.1:8000/api/health>。默认读取保留下来的 #002 雨夜车站数据库 `output/h3-002-2026-10-09/production.sqlite`；可用 `FILM_STUDIO_DB=/absolute/path/studio.sqlite` 指向另一份本地数据库，`FILM_STUDIO_MEDIA` 指定受管媒体目录。前端只通过 API 读写正式对象。空数据库可以从 Home 创建影片。

视频只维护 `provider=darl`，所有 H3 请求通过 `https://api.darl.cn/v1/videos`。服务端仅需配置 `DARL_API_KEY`；凭证不得写入前端环境变量或提交到 Git。`H3_SERVER_ON=1` 时新的生成使用 `MiniMax-H3`（自建 H3），否则使用 `runninghub-minimax-h3`（云端 H3 · 备用）。04 明确展示当前执行路线，不再选择 Provider。配置变更需按正式操作授权重启 API。

Final Brief 保持 model-independent。实际 execution model 与参数、引用、Brief 版本保存在不可变 Compiled Task / Job snapshot；Technical Retry 复用原任务，不跟随当前路线切换。原自建模型关闭时拒绝其技术重试；切换执行模型需要有原因的 Creative Regenerate。旧非 Darl Provider Job 保留为只读历史，返回 `LEGACY_PROVIDER_UNSUPPORTED`，不恢复查询或执行。

生成按钮仅提交一个明确候选，Runtime 最短每 180 秒查询原任务，不自动重提或 Creative Regenerate。真实 A→B→C1→C2 影片验收仍未完成，云端模型的实际输出与续接也尚待真实影片验证；本文不宣称验证 PASS。用户偏好默认为 16:9、480P、20 步。

## 验证

```bash
validation_dir=$(mktemp -d /tmp/ai-film-studio-tests.XXXXXX)
FILM_STUDIO_DB="$validation_dir/import.sqlite" FILM_STUDIO_MEDIA="$validation_dir/media" \
FILM_STUDIO_TEST_MODE=1 DARL_API_KEY= LLM_API_KEY= IMAGE_API_KEY= H3_SERVER_ON=0 .venv/bin/python - <<'PY'
import unittest
from unittest.mock import patch
with patch('urllib.request.urlopen', side_effect=AssertionError('external HTTP disabled')):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
raise SystemExit(not result.wasSuccessful())
PY
python3 -m compileall -q film_core apps/api scripts tests
npm run build --prefix apps/web
npm run test:e2e --prefix apps/web
```

E2E 使用独立的 `output/e2e/` 数据库和明确标记 `TEST ONLY` 的候选结果。它不调用真实 H3，也不写入 #002 的真实执行数据库。浏览器测试使用本机 Chrome；若尚未安装，可执行 `npx playwright install chromium`。

施工规格与验收记录见 `docs/MASTER-BLUEPRINT.md`、`docs/PRODUCTION-RULES.md`、`docs/DECISIONS.md` 和 `docs/reports/`。
