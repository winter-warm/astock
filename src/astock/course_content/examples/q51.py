"""人工财报：按公告可知时点匹配，不能按报告期提前使用。"""
import pandas as pd


reports = pd.DataFrame({
    "report_period": ["2025-12-31", "2026-03-31", "2026-03-31"],
    "known_at": pd.to_datetime(["2026-03-10 18:00", "2026-04-25 18:00", "2026-06-01 18:00"]),
    "eps": [1.0, .4, .3],
    "version": ["annual-first", "quarter-first", "quarter-correction"],
}).sort_values("known_at")
decisions = pd.DataFrame({
    "decision_at": pd.to_datetime(["2026-03-10 15:00", "2026-03-11 15:00",
                                   "2026-04-24 15:00", "2026-04-27 15:00",
                                   "2026-06-02 15:00"]),
    "price": [10., 10., 11., 11., 10.5],
})
matched = pd.merge_asof(decisions.sort_values("decision_at"), reports,
                       left_on="decision_at", right_on="known_at", direction="backward")
print(matched.to_string(index=False))
assert pd.isna(matched.iloc[0].eps)
assert matched.iloc[2].eps == 1.0
assert matched.iloc[3].eps == .4
assert matched.iloc[4].eps == .3
assert (matched.known_at.dropna() <= matched.loc[matched.known_at.notna(), "decision_at"]).all()
# 仅演示年度EPS与价格的PE；不能把单季EPS直接叫作TTM。
annual = matched[matched.version == "annual-first"].copy()
annual["illustrative_pe"] = annual.price / annual.eps
print("年度口径演示 PE：", annual.illustrative_pe.tolist())

