# AI Film Studio — Production Core Foundation (#001)

独立的新项目。这里只实现 #001 的生产内核，不包含 Creator UI 或真实 H3 调用。

- Python 3.9+，仅标准库；SQLite 持久化。
- `python3 -m unittest discover -s tests -v` 运行合同测试。
- `film_core.fixture.seed` 建立雨夜车站的规划数据；测试中的 provider URI 是显式的 `test_only` 模拟结果，不能用于生产验收。
- `h3-unverified` Profile 的真实能力保持 unknown；真实任务需在 #002 前验证资料并建立新的 Profile 版本。

权威规格位于 `docs/`，施工结论位于 `docs/reports/001-production-core-foundation-report.md`。
