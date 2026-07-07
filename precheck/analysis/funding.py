"""资金费率分析。analyze_funding 接收已拉好的 cur/hist (不自己拉网络)。"""
from datetime import datetime, timezone


def annualize_funding(rate):
    return rate * 3 * 365 * 100  # 8h 一次,年化百分比


def analyze_funding(funding_now, funding_history):
    """接收已拉好的当前费率 dict 与历史 list。纯函数。"""
    cur = funding_now
    if cur is None:
        return None
    hist = funding_history or []
    avg = sum(hist) / len(hist) if hist else cur["funding_rate"]
    next_t = (
        datetime.fromtimestamp(cur["next_funding_time"] / 1000, tz=timezone.utc).astimezone()
        if cur["next_funding_time"]
        else None
    )
    return {
        "current": cur["funding_rate"],
        "current_annual_pct": annualize_funding(cur["funding_rate"]),
        "avg_8": avg,
        "avg_8_annual_pct": annualize_funding(avg),
        "next_time": next_t,
    }


def interpret_funding(f):
    if f is None:
        return "数据不足"
    r = f["current"]
    if r > 0.0005:
        return "⚠ 多头拥挤 (费率过高,有被砸盘风险)"
    if r > 0.0001:
        return "✓ 多头偏强但未过热"
    if r < -0.0005:
        return "⚠ 空头拥挤 (费率过低,有被轧空风险)"
    if r < -0.0001:
        return "✓ 空头偏强但未过热"
    return "中性 (费率接近 0)"
