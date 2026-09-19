# assembler

Fill deal data: read the `os_fill_*` PostgreSQL reporting views and perform the
resulting writes against the shared [`china_model`](../china_model) Peewee
models.

This package is the new home of the fill logic that used to live in
`flow/dags/datasource/fill_data_fun.py` (>1500 lines). It does **not** run any
LLM extraction and does **not** orchestrate the pipeline — it only consumes the
records already materialised in the `os_fill_*` views (plus
`os_llm_deal_waterfall`) and updates deals, bonds, payments, ratings, clear
reports and trading prices.

## Steps

Each exposed function corresponds to one view and one write target. Running the
full pass (`python -m assembler.main run`) executes them in the same order as
the legacy `flow/dags/fill_data.py::fill_deal_data_obj`:

| Function | View / source | Write target |
|---|---|---|
| `toFillPricing` | `os_fill_pricing_data` | `Deal.data['pricing']` |
| `toFillBond` | `os_fill_bond` | `Bond`, `BondID` |
| `IssuePlansInit` | `os_fill_issue_plan` | `Deal.data['issuePlan']`, `PreClosingBond` |
| `preClosingDealsDataInit` | `os_fill_init_rating_data` | `Deal.data['preClosing']` |
| `initClearRpt` | `os_fill_clear` | `Deal.data['clear']`, `Deal.endDate` |
| `fillTrusteePeriod` | `os_fill_trusteereport_period` | `TrusteeReport.period` |
| `processTrusteeReports` | `os_fill_trustee_report` | `BondPayments`, `Bond.curBalance`, `Deal.period` |
| `fixPoolType` | `os_fill_npl_subpooltype` | `Deal.poolSubType` |
| `fillWaterfall` | `os_llm_deal_waterfall` | `Deal.data['waterfall']` |
| `fillInitView` | `os_fill_rating_init_view` | `Deal.data['preClosing']['view']` |
| `fillSeqView` | `os_fill_rating_seq_view` | `Deal.data['seqViews']` |
| `fillDealEndDate` | `os_fill_deal_enddate` | `Deal.endDate` |
| `tieoutBalanceForBalance` | `os_fill_bond_curbalance` | `BondPayments`, `Bond.curBalance` |
| `fillPoolPerfNPL` | `os_fill_trusteereport_pool_data_npl` | `Deal.data['current']['trustee']` |
| `fillIsin` | `os_fill_isin_code` | `BondID` (ISIN) |
| `fill_trading_price` | `os_fill_trading_price` | `TradingPrice` |

## Usage

```bash
# from the repo root, after `uv sync --all-packages`
uv run python -m assembler.main list      # list steps
uv run python -m assembler.main run       # run every step
uv run python -m assembler.main run fill_isin to_fill_bond
```

The database is configured through `china_model.configure()`, which reads
`DATABASE_URI` (or the `DATABASE_*` variables). `fillWaterfall` and
`calibrateTheName` need an OpenAI-compatible endpoint and the optional `llm`
extra (`uv sync --package assembler --extra llm`); everything else is pure
database work.
