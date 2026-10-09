# AI Film Studio — Production Core Foundation (#001)

独立的新项目。这里只实现 #001 的生产内核，不包含 Creator UI 或真实 H3 调用。

- Python 3.9+，仅标准库；SQLite 持久化。
- `python3 -m unittest discover -s tests -v` 运行合同测试。
- `film_core.fixture.seed` 建立雨夜车站的规划数据；测试中的 provider URI 是显式的 `test_only` 模拟结果，不能用于生产验收。
- `h3-unverified` Profile 的真实能力保持 unknown；真实任务需在 #002 前验证资料并建立新的 Profile 版本。

权威规格位于 `docs/`，施工结论位于 `docs/reports/001-production-core-foundation-report.md`。

## #002 H3 real vertical slice

`scripts/h3_slice.py` is the explicit single-job runner for the Darl MiniMax-H3
transport. It reads the bearer credential from stdin into the process only and
does not store it. `prepare` creates `output/h3-002-2026-10-09/production.sqlite`;
`models`, `submit --clip A --submit-one`, and `sync --job-id ...` handle the real
task. Later `accept`, `anchor`, `tail`, and `preview` commands are gated by real
Take, human Selection, and Canonical State. The `output/` folder is local managed
media and is excluded from Git. Offline contract tests never make paid requests.

The proxy's actual H3 route and limits are recorded separately from MiniMax's
official public API. #002 remains incomplete until four real Takes and the
human film review exist; see `docs/reports/002-h3-real-vertical-slice-report.md`.
