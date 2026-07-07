"""持仓量分析。analyze_oi 接收已拉好的 oi_history (不自己拉网络)。"""


def analyze_oi(oi_history):
    """接收已拉好的 OI 历史 (get_oi_history 的返回), 计算变化率。纯函数。"""
    hist = oi_history
    if not hist or len(hist) < 2:
        return None
    oi_now = hist[-1]["oi_usd"]
    oi_1h_ago = hist[-2]["oi_usd"]
    oi_24h_ago = hist[0]["oi_usd"]
    return {
        "now_usd": oi_now,
        "change_1h_pct": (oi_now - oi_1h_ago) / oi_1h_ago * 100 if oi_1h_ago else 0,
        "change_24h_pct": (oi_now - oi_24h_ago) / oi_24h_ago * 100 if oi_24h_ago else 0,
    }


def interpret_oi(oi, price_dir_1h):
    if oi is None or price_dir_1h is None:
        return "数据不足"
    up = oi["change_1h_pct"] > 0.3
    down = oi["change_1h_pct"] < -0.3
    if price_dir_1h == "up":
        if up:
            return "✓ 价涨 + OI 增 → 多头开新仓推涨(强势)"
        if down:
            return "⚠ 价涨 + OI 减 → 空头平仓推涨(弱势,动能不足)"
        return "中性 (OI 几乎无变化)"
    else:
        if up:
            return "✓ 价跌 + OI 增 → 空头开新仓推跌(强势)"
        if down:
            return "⚠ 价跌 + OI 减 → 多头平仓推跌(可能反弹)"
        return "中性 (OI 几乎无变化)"
