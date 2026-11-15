"""Read-only source audit; preserve raw minute frames and daily volume comparisons."""
from datetime import date, timedelta
from pathlib import Path
import json


def main():
    import akshare as ak
    import pandas as pd
    from akshare.utils.context import config
    config.timeout = (5, 10)
    root = Path("output/minute-sina-010").resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for symbol in ("sh600000", "sh510300"):
        for period in ("1", "5"):
            entry = {"symbol": symbol, "period": period, "source": "akshare-sina", "synthetic": False}
            try:
                frame = ak.stock_zh_a_minute(symbol=symbol, period=period, adjust="")
                frame.to_json(root / f"{symbol}-{period}m.json", orient="records", force_ascii=False, indent=2)
                entry.update(count=len(frame), columns=list(frame.columns), first=frame.iloc[0].to_dict(),
                             last=frame.iloc[-1].to_dict())
                start = date.fromisoformat(str(frame.iloc[0]["day"])[:10]) - timedelta(days=10)
                daily = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start.isoformat(),
                                             end_date=date.today().isoformat(), adjust="")
                daily.to_json(root / f"{symbol}-{period}m-daily.json", orient="records", force_ascii=False, indent=2,
                              date_format="iso")
                frame["volume"] = pd.to_numeric(frame["volume"])
                sums = frame.groupby(frame["day"].str[:10])["volume"].agg(["sum", "count"])
                values = {str(row["date"])[:10]: row for row in daily.to_dict("records")}
                entry["daily_comparison"] = [{"date": day, "bars": int(row["count"]),
                                              "minute_volume": float(row["sum"]),
                                              "daily_volume": float(values[day]["volume"]),
                                              "ratio": float(row["sum"]) / float(values[day]["volume"])}
                                             for day, row in sums.iterrows() if day in values]
                entry["passed"] = True
            except Exception as error:
                entry.update(passed=False, error=str(error))
            results.append(entry)
            print(json.dumps(entry, ensure_ascii=False, default=str), flush=True)
            (root / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
