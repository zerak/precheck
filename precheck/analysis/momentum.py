"""量价 + 动能衰竭。"""
from ..config import VOL_AVG_WINDOW


def analyze_volume(klines):
    # 币安/OKX 返回的最后一根是"进行中"的未收盘 K 线, 其成交量残缺 (只累计了已走
    # 过的时间), 直接用会系统性低估当前量能. 因此改用倒数第二根 (最后一根已收盘)
    # 做量价判断, 均量窗口也相应对齐到已收盘区间.
    if len(klines) < VOL_AVG_WINDOW + 2:
        return None
    cur = klines[-2]  # 最后一根已收盘 K 线
    window = klines[-VOL_AVG_WINDOW - 2 : -2]
    avg = sum(k["volume"] for k in window) / VOL_AVG_WINDOW
    if avg <= 0:
        return None
    ratio = cur["volume"] / avg
    cur_up = cur["close"] >= cur["open"]
    if ratio >= 1.5:
        tag = "放量"
    elif ratio <= 0.6:
        tag = "缩量"
    else:
        tag = "正常"
    direction = "上涨" if cur_up else "下跌"
    if tag == "放量" and cur_up:
        meaning = "✓ 放量上涨 = 真涨(买盘真实进场)"
    elif tag == "放量" and not cur_up:
        meaning = "✓ 放量下跌 = 真跌(卖盘真实出货)"
    elif tag == "缩量" and cur_up:
        meaning = "⚠ 缩量上涨 = 假涨/弱势(看位置判方向)"
    elif tag == "缩量" and not cur_up:
        meaning = "✓ 缩量下跌 = 惜售信号(可能止跌)"
    else:
        meaning = "中性"
    return {"ratio": ratio, "tag": tag, "direction": direction, "meaning": meaning}


def detect_momentum_exhaustion(klines, lookback=4):
    """检测近端动能衰竭 (顶部见顶 / 底部见底的雏形).

    只看已收盘 K 线 (排除最后一根进行中的), 组合三类信号:
      1. 放量反向: 近 lookback 根里出现放量阴线 (顶部) / 放量阳线 (底部), 量 ≥ 1.5× 均量
      2. 长上/下影: 最近 1-2 根 wick 占全幅比例高 (顶部长上影 = 拒绝上涨, 底部长下影 = 拒绝下跌)
      3. 缩量滞涨/滞跌: 价格创近端新高但量能递减 (顶背离雏形), 反之为底

    返回 {"exhausted": bool, "side": "top"/"bottom"/None, "signals": [str, ...]}
      side 表示衰竭指向的反转方向: "top"=见顶(利空), "bottom"=见底(利多)
    """
    # 需要足够样本: lookback 根观察 + 20 根均量窗口 + 1 根进行中
    if len(klines) < VOL_AVG_WINDOW + lookback + 1:
        return {"exhausted": False, "side": None, "signals": []}

    closed = klines[:-1]  # 排除进行中的最后一根
    recent = closed[-lookback:]
    # 均量基准: 观察窗口之前的 20 根
    base_window = closed[-VOL_AVG_WINDOW - lookback : -lookback]
    avg_vol = sum(k["volume"] for k in base_window) / len(base_window)
    if avg_vol <= 0:
        return {"exhausted": False, "side": None, "signals": []}

    top_signals = []
    bottom_signals = []

    # ── 信号 1: 放量反向 ──
    for k in recent:
        vol_ratio = k["volume"] / avg_vol
        if vol_ratio < 1.5:
            continue
        is_down = k["close"] < k["open"]
        if is_down:
            top_signals.append(f"放量阴线 (量 {vol_ratio:.1f}×)")
        else:
            bottom_signals.append(f"放量阳线 (量 {vol_ratio:.1f}×)")

    # ── 信号 2: 长上/下影 (看最近 2 根) ──
    for k in recent[-2:]:
        rng = k["high"] - k["low"]
        if rng <= 0:
            continue
        upper_wick = k["high"] - max(k["open"], k["close"])
        lower_wick = min(k["open"], k["close"]) - k["low"]
        if upper_wick / rng >= 0.5:
            top_signals.append(f"长上影 (上影占 {upper_wick/rng*100:.0f}%)")
        if lower_wick / rng >= 0.5:
            bottom_signals.append(f"长下影 (下影占 {lower_wick/rng*100:.0f}%)")

    # ── 信号 3: 缩量滞涨 / 滞跌 (价格创近端新高但量递减) ──
    if len(recent) >= 3:
        highs = [k["high"] for k in recent]
        lows = [k["low"] for k in recent]
        vols = [k["volume"] for k in recent]
        # 价格阶梯新高 + 量能阶梯下降 → 顶背离
        price_higher = highs[-1] >= max(highs[:-1])
        vol_fading = vols[-1] < vols[0] and vols[-1] < avg_vol
        if price_higher and vol_fading:
            top_signals.append("缩量新高 (顶背离雏形)")
        price_lower = lows[-1] <= min(lows[:-1])
        if price_lower and vol_fading:
            bottom_signals.append("缩量新低 (底背离雏形)")

    # 取占优的一侧 (信号更多的方向); 至少 1 个信号才算衰竭迹象
    if len(top_signals) >= len(bottom_signals) and top_signals:
        return {"exhausted": True, "side": "top", "signals": top_signals}
    if bottom_signals:
        return {"exhausted": True, "side": "bottom", "signals": bottom_signals}
    return {"exhausted": False, "side": None, "signals": []}

