"""趋势结构 + EMA 偏离度。"""
from ..config import VREV_LOOKBACK, EMA_DEV_THRESHOLDS, OVER_EXTENDED_ATR


def analyze_structure(closes, ema200, lookback=VREV_LOOKBACK):
    n = len(closes)
    if ema200[-1] is None:
        return "数据不足"
    cur_above = closes[-1] > ema200[-1]
    start = max(1, n - lookback)
    last_breakdown = None
    last_reclaim = None
    for i in range(start, n):
        if ema200[i] is None or ema200[i - 1] is None:
            continue
        prev_above = closes[i - 1] > ema200[i - 1]
        cur = closes[i] > ema200[i]
        if prev_above and not cur:
            last_breakdown = i
            last_reclaim = None
        elif (not prev_above) and cur:
            last_reclaim = i

    if last_breakdown is None and cur_above:
        return "稳态在 EMA200 上方(趋势偏多)"
    if last_breakdown is None and not cur_above:
        return "稳态在 EMA200 下方(趋势偏空)"
    if last_breakdown is not None and last_reclaim is None:
        return "反弹被压 EMA200 下方(空头结构延续 ✗ 慎做空陷阱: 是否在阻力区拒绝)"
    if (last_breakdown and last_reclaim and last_reclaim > last_breakdown
            and cur_above):
        return "V 反 — 跌破后重夺并站稳(看多 ✓)"
    if last_breakdown and last_reclaim and not cur_above:
        return "假突破未守住(再次跌破,空头结构)"
    return "震荡(反复穿越 EMA200)"


def compute_ema_deviation(row_1h):
    """纯计算: 返回 1h 价格距 EMA50/EMA200 的偏离数据 (供输出和反转判定共用)。

    返回 {"ema50": {...}, "ema200": {...}, "over_extended": bool, "extended_side": ...}
      每个 ema 项: {"ref", "diff", "mult"(ATR 倍数), "side"("long"/"short"), "pct", "tag"}
      over_extended: 1h 距 EMA200 > OVER_EXTENDED_ATR × ATR
      extended_side: 过度延伸的方向 "long"(价在上方过热)/"short"(下方过冷)/None
    """
    if not row_1h or not row_1h.get("atr"):
        return None
    close = row_1h["close"]
    atr = row_1h["atr"]
    if not atr:
        return None

    def _tag(label, mult, near, far):
        if mult <= near:
            return "正常"
        if mult <= far:
            return "偏离 (建议等回踩)"
        return {
            "EMA50": "⚠ 显著偏离 (现价追单胜率低,优先等回踩)",
            "EMA200": "⚠ 显著延伸",
        }[label]

    out = {"over_extended": False, "extended_side": None}
    for label, key in (("EMA50", "ema50"), ("EMA200", "ema200")):
        ref = row_1h.get(key)
        if ref is None:
            out[key] = None
            continue
        near, far = EMA_DEV_THRESHOLDS[label]
        diff = close - ref
        mult = abs(diff) / atr
        out[key] = {
            "ref": ref,
            "diff": diff,
            "mult": mult,
            "side": "long" if diff >= 0 else "short",
            "pct": diff / ref * 100 if ref else 0,
            "tag": _tag(label, mult, near, far),
        }

    ema200 = out.get("ema200")
    if ema200 and ema200["mult"] > OVER_EXTENDED_ATR:
        out["over_extended"] = True
        out["extended_side"] = ema200["side"]
    return out

