"""关键位识别: 大级别压力支撑 + 支撑阻力互换位 (用户核心手法)。"""
from ..config import DEFAULT_LEVEL, TRADE_LEVELS
from ..indicators import find_swings, find_close_swings, atr_wilder


def flip_levels(klines_by_tf, current, level=DEFAULT_LEVEL):
    """支撑阻力互换关键位 (贴合用户手法), 按交易级别自适应周期与距离。

    核心逻辑 (与常规相反):
      - 上方压力 = 现价上方的"收盘摆动低点"聚集带 (旧支撑跌破 → 变阻力)
      - 下方支撑 = 现价下方的"收盘摆动高点"聚集带 (旧阻力突破 → 变支撑)

    标准 (无魔数, 全部由 level 推导):
      - 关键位来源周期 = TRADE_LEVELS[level]["tfs"]  (日内=1h/4h, 波段=4h/日线, 趋势=日线/周线)
      - 聚类容差       = 各周期自身 ATR × 0.5         (跟数据颗粒度走)
      - 距离上限       = 锚定周期 ATR × dist_mult      (跟交易级别走)

    每个聚集带给三档止盈/止损参考 (保守/中庸/激进):
      - 上方压力: 下沿(保守,先触及) / 中心(中庸) / 上沿(激进)
      - 下方支撑: 上沿(保守) / 中心(中庸) / 下沿(激进)

    返回 {"resistance": [...], "support": [...], "unit_atr": float, "unit_tf": str},
      unit_atr/unit_tf = 距离归一化用的锚定周期 ATR (供显示"距现价 N×ATR")。
    """
    cfg = TRADE_LEVELS.get(level, TRADE_LEVELS[DEFAULT_LEVEL])
    tfs = cfg["tfs"]
    anchor_tf = cfg["anchor_tf"]

    anchor_kl = klines_by_tf.get(anchor_tf)
    anchor_atr = atr_wilder(anchor_kl, 14) if anchor_kl and len(anchor_kl) > 15 else None
    if not anchor_atr or anchor_atr <= 0:
        return {"resistance": [], "support": [], "unit_atr": None, "unit_tf": anchor_tf}
    max_dist = cfg["dist_mult"] * anchor_atr

    # 收集来源周期的收盘摆动点, 每个周期用自身 ATR 作聚类容差
    res_pts = []   # 上方: (price, tf, tol)
    sup_pts = []
    for tf in tfs:
        kl = klines_by_tf.get(tf)
        if not kl or len(kl) < 16:
            continue
        tf_atr = atr_wilder(kl, 14)
        if not tf_atr or tf_atr <= 0:
            continue
        tf_tol = 0.5 * tf_atr
        highs, lows = find_close_swings(kl, lookback=3)
        for _, p in lows:
            if p > current and (p - current) <= max_dist:
                res_pts.append((p, tf, tf_tol))
        for _, p in highs:
            if p < current and (current - p) <= max_dist:
                sup_pts.append((p, tf, tf_tol))

    def _cluster(points):
        """points: [(price, tf, tol), ...] → 聚类带。相邻价差 ≤ 两者容差均值则并簇。"""
        pts = sorted(points, key=lambda x: x[0])
        clusters = []
        for price, tf, tol in pts:
            if clusters and price - clusters[-1]["prices"][-1] <= max(tol, clusters[-1]["tol"]):
                clusters[-1]["prices"].append(price)
                clusters[-1]["tfs"].add(tf)
                clusters[-1]["tol"] = (clusters[-1]["tol"] + tol) / 2
            else:
                clusters.append({"prices": [price], "tfs": {tf}, "tol": tol})
        out = []
        for c in clusters:
            ps = c["prices"]
            # 标签取簇里最大周期
            if "1w" in c["tfs"]:
                tf_label = "周线"
            elif "1d" in c["tfs"]:
                tf_label = "日线"
            elif "4h" in c["tfs"]:
                tf_label = "4h"
            else:
                tf_label = "1h"
            out.append({"lower": min(ps), "mid": sum(ps) / len(ps),
                        "upper": max(ps), "count": len(ps), "tf": tf_label})
        return out

    resistance = []
    for c in _cluster(res_pts):
        resistance.append({
            "conservative": c["lower"], "mid": c["mid"], "aggressive": c["upper"],
            "count": c["count"], "tf": c["tf"],
            "dist_atr": (c["lower"] - current) / anchor_atr,
        })
    support = []
    for c in _cluster(sup_pts):
        support.append({
            "conservative": c["upper"], "mid": c["mid"], "aggressive": c["lower"],
            "count": c["count"], "tf": c["tf"],
            "dist_atr": (current - c["upper"]) / anchor_atr,
        })

    resistance.sort(key=lambda x: (-x["count"], x["dist_atr"]))
    support.sort(key=lambda x: (-x["count"], x["dist_atr"]))
    return {"resistance": resistance, "support": support,
            "unit_atr": anchor_atr, "unit_tf": anchor_tf}


def collect_key_levels(klines_by_tf, current, atr_1h, max_dist_atr=8.0, vp=None):
    """识别大级别 (4h + 日线) 的关键压力/支撑位, 用于反转判断和止盈锚定.

    只保留距现价 ≤ max_dist_atr × 1h ATR 的位置 (日线上有 4759 这种天量远点,
    对当前短线交易毫无意义, 必须过滤掉).

    近距离 (≤ 0.5×ATR) 的同类位置会被合并, 合并后 touches 记录被合并的原始点数
    (touches 越多 = 该价位被反复验证, 强度越高).

    参数:
      klines_by_tf: {"4h": [...], "1d": [...], ...} run() 里已拉好的 K 线
      current:      当前价 (1h 收盘代理)
      atr_1h:       1h ATR, 作为距离归一化单位
      max_dist_atr: 距离过滤上限 (默认 8×ATR)
      vp:           可选, volume_profile() 结果, 把 POC/HVN 也纳入压力位

    返回按距现价升序排序的 list:
      [{"price", "tf", "type": "high"/"low", "dist_atr", "touches"}, ...]
    """
    if atr_1h is None or atr_1h <= 0:
        return []

    raw = []  # (price, tf, type)
    for tf in ("4h", "1d"):
        kl = klines_by_tf.get(tf)
        if not kl or len(kl) < 12:
            continue
        highs, lows = find_swings(kl, lookback=5)
        for _, p in highs:
            raw.append((p, tf, "high"))
        for _, p in lows:
            raw.append((p, tf, "low"))

    # 纳入 Volume Profile 的 POC/HVN (成交密集区, 天然的强 S/R)
    if vp:
        if vp.get("poc"):
            raw.append((vp["poc"], "VP", "poc"))
        for h in vp.get("hvn", []):
            raw.append((h, "VP", "hvn"))

    # 距离过滤
    near = [
        (p, tf, t) for (p, tf, t) in raw
        if abs(p - current) <= max_dist_atr * atr_1h
    ]
    if not near:
        return []

    # 合并相近位置 (≤ 0.5×ATR 视为同一位置), 保留强度信息
    near.sort(key=lambda x: x[0])
    merge_gap = 0.5 * atr_1h
    clusters = []  # 每个: {"prices": [...], "tfs": set, "types": set}
    for p, tf, t in near:
        if clusters and p - clusters[-1]["prices"][-1] <= merge_gap:
            clusters[-1]["prices"].append(p)
            clusters[-1]["tfs"].add(tf)
            clusters[-1]["types"].add(t)
        else:
            clusters.append({"prices": [p], "tfs": {tf}, "types": {t}})

    out = []
    for c in clusters:
        price = sum(c["prices"]) / len(c["prices"])
        # 大级别标签优先级: 日线 > 4h > VP
        if "1d" in c["tfs"]:
            tf_label = "日线"
        elif "4h" in c["tfs"]:
            tf_label = "4h"
        else:
            tf_label = "VP"
        # type: 若簇里有 high 记为压力, 有 low 记为支撑; 混合时按多数
        n_high = sum(1 for t in c["types"] if t in ("high", "poc", "hvn"))
        lvl_type = "high" if price >= current else "low"
        out.append({
            "price": price,
            "tf": tf_label,
            "type": lvl_type,
            "dist_atr": abs(price - current) / atr_1h,
            "touches": len(c["prices"]),
        })

    out.sort(key=lambda x: x["dist_atr"])
    return out

