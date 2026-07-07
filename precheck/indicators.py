"""纯数学指标: EMA / ATR / Volume Profile / 摆动点。无 IO 无副作用。"""


def ema_series(values, period):
    if len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    out = [None] * (period - 1)
    seed = sum(values[:period]) / period
    out.append(seed)
    e = seed
    for v in values[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def atr_wilder(klines, period=14):
    """Wilder 平滑的 ATR (业界标准)。返回最新一根的 ATR 值。"""
    if len(klines) < period + 1:
        return None
    trs = []
    for i in range(1, len(klines)):
        h, l = klines[i]["high"], klines[i]["low"]
        prev_c = klines[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    # 前 period 个用 SMA 作初始,之后 Wilder 递推
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def volume_profile(klines, n_bins=50, max_hvn=3, hvn_min_ratio=0.4, min_gap_bins=3):
    """近似的 Volume Profile (基于 K 线粒度).

    每根 K 线把它的 volume 均匀分配到它覆盖的价格桶 (low → high) 里.
    返回: {"poc": 最大成交价位, "hvn": [次高峰价位 list], "poc_vol": POC 桶的成交量}

    参数:
      n_bins: 价格区间分多少桶 (50 = 中等精度, 100 = 高精度但慢)
      max_hvn: 最多返回多少个 HVN
      hvn_min_ratio: HVN 桶的成交量必须 ≥ POC × 此比例 (默认 0.4 = 至少 40% POC 量)
      min_gap_bins: 相邻 HVN 之间最少间隔多少桶 (避免相邻桶被重复算成多个 HVN)
    """
    if len(klines) < 10:
        return {"poc": None, "hvn": [], "poc_vol": 0}

    all_high = max(k["high"] for k in klines)
    all_low = min(k["low"] for k in klines)
    if all_high <= all_low:
        return {"poc": None, "hvn": [], "poc_vol": 0}

    bin_size = (all_high - all_low) / n_bins
    bins = [0.0] * n_bins

    for k in klines:
        lo, hi, vol = k["low"], k["high"], k["volume"]
        i_lo = max(0, int((lo - all_low) / bin_size))
        i_hi = min(n_bins - 1, int((hi - all_low) / bin_size))
        n_cover = max(1, i_hi - i_lo + 1)
        per_bin = vol / n_cover
        for i in range(i_lo, i_hi + 1):
            bins[i] += per_bin

    # 按成交量降序
    sorted_bins = sorted(enumerate(bins), key=lambda x: -x[1])
    poc_idx, poc_vol = sorted_bins[0]
    poc_price = all_low + (poc_idx + 0.5) * bin_size

    # HVN: 次高峰, 与已选位置至少间隔 min_gap_bins, 且成交量 ≥ POC × hvn_min_ratio
    hvn_prices = []
    selected_idx = [poc_idx]
    for idx, vol in sorted_bins[1:]:
        if vol < hvn_min_ratio * poc_vol:
            break
        if all(abs(idx - s) >= min_gap_bins for s in selected_idx):
            hvn_prices.append(all_low + (idx + 0.5) * bin_size)
            selected_idx.append(idx)
            if len(hvn_prices) >= max_hvn:
                break

    return {"poc": poc_price, "hvn": hvn_prices, "poc_vol": poc_vol}


def find_swings(klines, lookback=5):
    """识别摆动高/低点。lookback=5 → 一根 K 线是其前后各 5 根中最高/最低才算摆动点。"""
    highs, lows = [], []
    for i in range(lookback, len(klines) - lookback):
        h = klines[i]["high"]
        l = klines[i]["low"]
        is_high = all(
            klines[j]["high"] <= h
            for j in range(i - lookback, i + lookback + 1)
            if j != i
        )
        is_low = all(
            klines[j]["low"] >= l
            for j in range(i - lookback, i + lookback + 1)
            if j != i
        )
        if is_high:
            highs.append((i, h))
        if is_low:
            lows.append((i, l))
    return highs, lows


def find_close_swings(klines, lookback=3):
    """摆动高/低点 —— 用收盘价实体判定 (不用影线极值)。

    与 find_swings (用 high/low 影线) 的区别: 这里用 close, 更贴合"实体收盘价
    定关键位"的手法。返回 (highs, lows), 每个元素 (idx, close_price)。
    """
    highs, lows = [], []
    for i in range(lookback, len(klines) - lookback):
        c = klines[i]["close"]
        if all(klines[j]["close"] <= c
               for j in range(i - lookback, i + lookback + 1) if j != i):
            highs.append((i, c))
        if all(klines[j]["close"] >= c
               for j in range(i - lookback, i + lookback + 1) if j != i):
            lows.append((i, c))
    return highs, lows

