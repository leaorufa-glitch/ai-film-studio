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

H3 服务器关机是正常状态，04 会显示“服务未启动”，创作规划可继续。服务器真正开机后，服务端设置 `H3_SERVER_ON=1` 与 `DARL_API_KEY`，再重启 API；凭证不得写入前端环境变量或提交到 Git。生成按钮只提交一次明确的 Job，任务查询通过页面手动同步，不会自动轮询或重试。#002 的真实 A→B→C1→C2 影片验收仍待服务器开启和人工审片。用户偏好默认为 16:9、480P、20 步。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
python3 -m compileall -q film_core apps/api scripts tests
npm run build --prefix apps/web
npm run test:e2e --prefix apps/web
```

E2E 使用独立的 `output/e2e/` 数据库和明确标记 `TEST ONLY` 的候选结果。它不调用真实 H3，也不写入 #002 的真实执行数据库。浏览器测试使用本机 Chrome；若尚未安装，可执行 `npx playwright install chromium`。

施工规格与验收记录见 `docs/MASTER-BLUEPRINT.md`、`docs/PRODUCTION-RULES.md`、`docs/DECISIONS.md` 和 `docs/reports/`。
