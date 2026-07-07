"""交易方案生成: 入场/止损/止盈/仓位/RR/触达概率。"""
from .config import DEFAULT_LEVEL, TRADE_LEVELS, REV_SL_BUFFER
from .indicators import find_swings, volume_profile
from .formatting import fmt_price


def collect_entry_candidates(direction, current, atr, ema50, ema200, recent_swings, vp):
    """收集所有入场候选, 标注来源类型. type 字段: 'volume' | 'ema' | 'swing'。

    LONG: 入场必须 < 当前价 (回踩支撑); SHORT: 必须 > 当前价 (反弹阻力).
    所有候选必须在距当前价 2 × ATR 之内 (太远的不算"近期可触发").
    """
    cands = []
    if direction == "long":
        in_range = lambda p: p < current and p >= current - 2 * atr
    else:
        in_range = lambda p: p > current and p <= current + 2 * atr

    # Volume-based (优先级最高)
    if vp.get("poc") and in_range(vp["poc"]):
        cands.append({"label": "Volume POC", "price": vp["poc"], "type": "volume",
                      "note": "近 100 根 1h 最大成交价位 (机构博弈最激烈处)"})
    for i, hvn in enumerate(vp.get("hvn", []), start=1):
        if in_range(hvn):
            cands.append({"label": f"Volume HVN #{i}", "price": hvn, "type": "volume",
                          "note": f"成交量分布的第 {i} 高峰 (强 S/R)"})

    # EMA-based
    if ema50 and in_range(ema50):
        cands.append({"label": "1h EMA50", "price": ema50, "type": "ema",
                      "note": "1 小时短中期均线 (动态支撑/阻力)"})
    if ema200 and in_range(ema200):
        cands.append({"label": "1h EMA200", "price": ema200, "type": "ema",
                      "note": "1 小时中长期均线 (主流资金成本线)"})

    # Swing-based
    if recent_swings:
        if direction == "long":
            nearest = max(p for _, p in recent_swings[-3:])
        else:
            nearest = min(p for _, p in recent_swings[-3:])
        if in_range(nearest):
            label = "近期 1h 摆动低点" if direction == "long" else "近期 1h 摆动高点"
            cands.append({"label": label, "price": nearest, "type": "swing",
                          "note": "最近 50 根 1h K 线的局部转折点"})

    # 排序: LONG 按价格降序 (最高 = 最近), SHORT 升序
    cands.sort(key=lambda c: -c["price"] if direction == "long" else c["price"])
    return cands


def select_entry(candidates, atr):
    """从候选中选最终入场点。规则:
       1. 默认选距当前价最近的 (cands 已按距离排好序, [0] 即最近)
       2. 但如果有 volume 类型候选在 0.5 ATR 范围内, 优先 volume (强 S/R)
    """
    if not candidates:
        return None
    closest = candidates[0]
    # 优先 volume 候选 (在 0.5 ATR 内可平替)
    for c in candidates:
        if c["type"] == "volume" and abs(c["price"] - closest["price"]) <= 0.5 * atr:
            return c
    return closest


def suggest_plan(ctx, direction, reversal=False):
    """生成给定方向的建议方案。reversal=True 时用更宽的止损缓冲(0.8×ATR vs 0.3×ATR)。

    从 ctx 读取 rows/klines_by_tf/account/risk_pct/key_levels。
    """
    rows = ctx.rows
    klines_by_tf = ctx.klines_by_tf
    account = ctx.account
    risk_pct = ctx.risk_pct
    key_levels = ctx.key_levels
    klines_1h = klines_by_tf.get("1h", [])
    if not klines_1h:
        return None
    row_1h = next((r for r in rows if r["interval"] == "1h"), None)
    if not row_1h or not row_1h.get("atr"):
        return None

    current = row_1h["close"]
    atr = row_1h["atr"]
    ema50 = row_1h["ema50"]
    ema200 = row_1h["ema200"]

    highs, lows = find_swings(klines_1h, lookback=5)
    n = len(klines_1h)
    recent_highs = [(i, p) for i, p in highs if i >= n - 50]
    recent_lows = [(i, p) for i, p in lows if i >= n - 50]

    # Volume Profile (近 100 根 1h ≈ 4 天)
    vp_window = klines_1h[-100:] if len(klines_1h) >= 100 else klines_1h
    vp = volume_profile(vp_window, n_bins=50, max_hvn=3)

    swings = recent_lows if direction == "long" else recent_highs
    candidates = collect_entry_candidates(
        direction, current, atr, ema50, ema200, swings, vp
    )

    if not candidates:
        if direction == "long":
            reason = "价格已在所有 EMA / Volume 节点 上方, 无近距离支撑 (趋势强多头, 不适合做多回踩)"
        else:
            reason = "价格已在所有 EMA / Volume 节点 下方, 无近距离阻力 (趋势强空头, 不适合做空反弹)"
        return {"_no_entry": True, "_reason": reason}

    chosen = select_entry(candidates, atr)
    entry = chosen["price"]
    entry_label = chosen["label"]
    entry_type = chosen["type"]
    entry_note = chosen["note"]

    # 选择理由
    if chosen is candidates[0]:
        select_reason = "距当前价最近的有效候选"
    else:
        select_reason = (
            f"距最近候选({fmt_price(candidates[0]['price'])})仅 "
            f"{abs(chosen['price'] - candidates[0]['price'])/atr:.2f}× 1h ATR"
            f"({atr:.4f}) = {abs(chosen['price'] - candidates[0]['price']):.4f}, "
            f"优先选 volume 类型 (S/R 强度更高)"
        )

    # 止损: 优先用近距离摆动锚 + 缓冲, 否则默认 1.0 × ATR
    # 反转单用更宽缓冲(0.8×ATR), 避免被趋势"最后一冲"扫损; 顺势单保持 0.3×ATR
    sl_buf = REV_SL_BUFFER if reversal else 0.3
    last_idx = n - 1  # 最新一根 1h K 线的索引
    if direction == "long":
        default_stop = entry - 1.0 * atr
        relevant_lows = [(i, p) for i, p in recent_lows[-5:] if entry - p <= 1.5 * atr] \
            if recent_lows else []
        if relevant_lows:
            anchor_i, anchor = min(relevant_lows, key=lambda x: x[1])
            anchor_bars_ago = last_idx - anchor_i
            stop = min(anchor - sl_buf * atr, default_stop)
            sl_type = "anchored"
            sl_anchor_value = anchor
            sl_meaning = (
                f"跌破近期摆动低点 {fmt_price(anchor)} ({anchor_bars_ago} 根 1h K 前) "
                f"- {sl_buf}× 1h ATR({atr:.4f}) = {sl_buf*atr:.4f} 缓冲 → "
                f"短期结构破坏, 入场依据失效"
            )
            sl_reason = (
                f"近期有摆动低点在 1.5× 1h ATR({atr:.4f}) = {1.5*atr:.4f} 内 "
                f"({fmt_price(anchor)}, {anchor_bars_ago} 根前), "
                f"锚定到该位置下方 {sl_buf}× 1h ATR({atr:.4f}) = {sl_buf*atr:.4f} 缓冲"
            )
        else:
            stop = default_stop
            sl_type = "default"
            sl_anchor_value = None
            sl_meaning = (
                f"跌破入场价 {fmt_price(entry)} 1× 1h ATR({atr:.4f}) = {atr:.4f} → "
                f"超出 1h K 线日常波动, 视为方向证伪"
            )
            sl_reason = (
                f"近 5 根摆动低点都在 1.5× 1h ATR({atr:.4f}) = {1.5*atr:.4f} 之外 (无近距离锚), "
                f"用默认 1.0× 1h ATR({atr:.4f}) = {atr:.4f} 保守止损"
            )
        sl_dist = entry - stop
        # 候选 swing 全表 (用于输出展示, 不影响选择)
        sl_swing_table = []
        for i, p in (recent_lows or []):
            dist = entry - p  # 正数: p 在入场下方
            in_range = (dist > 0) and (dist <= 1.5 * atr)
            sl_swing_table.append({
                "price": p,
                "bars_ago": last_idx - i,
                "dist": dist,
                "atr_mult": (abs(dist) / atr) if atr > 0 else 0,
                "side": "below" if dist > 0 else "above",
                "in_range": in_range,
                "selected": (sl_type == "anchored" and p == sl_anchor_value),
            })
    else:
        default_stop = entry + 1.0 * atr
        relevant_highs = [(i, p) for i, p in recent_highs[-5:] if p - entry <= 1.5 * atr] \
            if recent_highs else []
        if relevant_highs:
            anchor_i, anchor = max(relevant_highs, key=lambda x: x[1])
            anchor_bars_ago = last_idx - anchor_i
            stop = max(anchor + sl_buf * atr, default_stop)
            sl_type = "anchored"
            sl_anchor_value = anchor
            sl_meaning = (
                f"突破近期摆动高点 {fmt_price(anchor)} ({anchor_bars_ago} 根 1h K 前) "
                f"+ {sl_buf}× 1h ATR({atr:.4f}) = {sl_buf*atr:.4f} 缓冲 → "
                f"短期结构破坏, 入场依据失效"
            )
            sl_reason = (
                f"近期有摆动高点在 1.5× 1h ATR({atr:.4f}) = {1.5*atr:.4f} 内 "
                f"({fmt_price(anchor)}, {anchor_bars_ago} 根前), "
                f"锚定到该位置上方 {sl_buf}× 1h ATR({atr:.4f}) = {sl_buf*atr:.4f} 缓冲"
            )
        else:
            stop = default_stop
            sl_type = "default"
            sl_anchor_value = None
            sl_meaning = (
                f"突破入场价 {fmt_price(entry)} 1× 1h ATR({atr:.4f}) = {atr:.4f} → "
                f"超出 1h K 线日常波动, 视为方向证伪"
            )
            sl_reason = (
                f"近 5 根摆动高点都在 1.5× 1h ATR({atr:.4f}) = {1.5*atr:.4f} 之外 (无近距离锚), "
                f"用默认 1.0× 1h ATR({atr:.4f}) = {atr:.4f} 保守止损"
            )
        sl_dist = stop - entry
        # 候选 swing 全表 (用于输出展示, 不影响选择)
        sl_swing_table = []
        for i, p in (recent_highs or []):
            dist = p - entry  # 正数: p 在入场上方
            in_range = (dist > 0) and (dist <= 1.5 * atr)
            sl_swing_table.append({
                "price": p,
                "bars_ago": last_idx - i,
                "dist": dist,
                "atr_mult": (abs(dist) / atr) if atr > 0 else 0,
                "side": "above" if dist > 0 else "below",
                "in_range": in_range,
                "selected": (sl_type == "anchored" and p == sl_anchor_value),
            })

    # 止盈: 优先用"最近的摆动点" (= 最现实的目标), 不为了凑 R/R 跳到更远的点
    # 如果最近的摆动点导致 R/R < 2, 把更远的"凑 R/R"位作为备选展示, 但不替换主目标
    if direction == "long":
        # 价格升序排序, 最低 (最近触达) 排第一; 索引 last_idx-i = 距今根数
        swings_above = sorted([(i, p) for i, p in recent_highs if p > entry], key=lambda x: x[1])
        if swings_above:
            tp_i, tp = swings_above[0]   # 最近的, 最现实
            tp_bars_ago = last_idx - tp_i
            tp_label = "近期 1h 摆动高点 (最近)"
            tp_type = "swing"
            tp_meaning = (
                f"价格触及近期上一波反弹的高点 {fmt_price(tp)} ({tp_bars_ago} 根 1h K 前) → "
                f"短期阻力区, 大概率有反应 (机械止盈, 或考虑分批+移止损)"
            )
            tp_reason = (
                f"近期上方共 {len(swings_above)} 个摆动高点 "
                f"({', '.join(f'{fmt_price(p)}@{last_idx - i}根前' for i, p in swings_above[:3])}...), "
                f"取最近的 = 最可能被触及的目标"
            )
        else:
            tp = entry + 2.5 * sl_dist
            tp_label = "2.5R 几何目标"
            tp_type = "default"
            tp_meaning = (
                "近期上方无摆动高点 → 价格在新高区, 用 2.5R 几何位作目标"
            )
            tp_reason = "近 50 根 1h K 线内入场上方无任何摆动高点 (趋势强势)"
        tp_dist = tp - entry

        # 备选 TP (R/R < 2 时, 提示更远的"凑 R/R"位)
        tp_alts = []
        if tp_dist < 2.0 * sl_dist:
            further = [(i, p) for i, p in swings_above if p >= entry + 2.0 * sl_dist]
            if further:
                f_i, f_p = further[0]
                tp_alts.append({
                    "price": f_p,
                    "label": f"下一个 ≥ 2R 摆动高点 ({last_idx - f_i} 根前)",
                    "rr": (f_p - entry) / sl_dist,
                })
            geo_25r = entry + 2.5 * sl_dist
            tp_alts.append({
                "price": geo_25r,
                "label": "2.5R 几何目标",
                "rr": 2.5,
            })
        # 大级别压力位作为 TP 参考 (反转/趋势单的更靠谱目标)
        for lv in (key_levels or []):
            if lv["type"] == "high" and lv["price"] > entry:
                tp_alts.append({
                    "price": lv["price"],
                    "label": f"{lv['tf']}压力位",
                    "rr": (lv["price"] - entry) / sl_dist if sl_dist > 0 else 0,
                })

    else:
        # 价格降序: 最高 (最近触达) 排第一
        swings_below = sorted([(i, p) for i, p in recent_lows if p < entry], key=lambda x: -x[1])
        if swings_below:
            tp_i, tp = swings_below[0]
            tp_bars_ago = last_idx - tp_i
            tp_label = "近期 1h 摆动低点 (最近)"
            tp_type = "swing"
            tp_meaning = (
                f"价格触及近期上一波下跌的低点 {fmt_price(tp)} ({tp_bars_ago} 根 1h K 前) → "
                f"短期支撑区, 大概率有反应 (机械止盈, 或考虑分批+移止损)"
            )
            tp_reason = (
                f"近期下方共 {len(swings_below)} 个摆动低点 "
                f"({', '.join(f'{fmt_price(p)}@{last_idx - i}根前' for i, p in swings_below[:3])}...), "
                f"取最近的 = 最可能被触及的目标"
            )
        else:
            tp = entry - 2.5 * sl_dist
            tp_label = "2.5R 几何目标"
            tp_type = "default"
            tp_meaning = (
                "近期下方无摆动低点 → 价格在新低区, 用 2.5R 几何位作目标"
            )
            tp_reason = "近 50 根 1h K 线内入场下方无任何摆动低点 (趋势强势)"
        tp_dist = entry - tp

        tp_alts = []
        if tp_dist < 2.0 * sl_dist:
            further = [(i, p) for i, p in swings_below if p <= entry - 2.0 * sl_dist]
            if further:
                f_i, f_p = further[0]
                tp_alts.append({
                    "price": f_p,
                    "label": f"下一个 ≥ 2R 摆动低点 ({last_idx - f_i} 根前)",
                    "rr": (entry - f_p) / sl_dist,
                })
            geo_25r = entry - 2.5 * sl_dist
            tp_alts.append({
                "price": geo_25r,
                "label": "2.5R 几何目标",
                "rr": 2.5,
            })
        # 大级别支撑位作为 TP 参考 (反转/趋势单的更靠谱目标)
        for lv in (key_levels or []):
            if lv["type"] == "low" and lv["price"] < entry:
                tp_alts.append({
                    "price": lv["price"],
                    "label": f"{lv['tf']}支撑位",
                    "rr": (entry - lv["price"]) / sl_dist if sl_dist > 0 else 0,
                })

    # tp_alts 去重 (价格相近的合并) + 按距入场距离升序, 只留满足 ≥2R 的
    if tp_alts:
        seen = []
        deduped = []
        for alt in sorted(tp_alts, key=lambda a: abs(a["price"] - entry)):
            if alt["rr"] < 2.0:
                continue
            if any(abs(alt["price"] - s) <= 0.3 * atr for s in seen):
                continue
            seen.append(alt["price"])
            deduped.append(alt)
        tp_alts = deduped[:3]  # 最多展示 3 个, 避免刷屏

    rr = tp_dist / sl_dist if sl_dist > 0 else 0
    risk_budget = account * risk_pct / 100
    qty = risk_budget / sl_dist if sl_dist > 0 else 0
    dist_pct = abs(current - entry) / current * 100

    # 备选候选 (排除已选的)
    alts = [c for c in candidates if c["price"] != entry][:4]

    return {
        "direction": direction,
        "entry": entry,
        "entry_label": entry_label,
        "entry_type": entry_type,
        "entry_note": entry_note,
        "select_reason": select_reason,
        "alt_candidates": alts,
        "current": current,
        "dist_pct": dist_pct,
        "stop": stop,
        "sl_type": sl_type,
        "sl_anchor_value": sl_anchor_value,
        "sl_meaning": sl_meaning,
        "sl_reason": sl_reason,
        "sl_swing_table": sl_swing_table,
        "tp": tp,
        "tp_label": tp_label,
        "tp_type": tp_type,
        "tp_meaning": tp_meaning,
        "tp_reason": tp_reason,
        "tp_alts": tp_alts,
        "sl_dist": sl_dist,
        "tp_dist": tp_dist,
        "rr": rr,
        "qty": qty,
        "atr_1h": atr,
        "atr_ratio": sl_dist / atr if atr > 0 else 0,
        "vp": vp,
        "account": account,
    }


def hit_probability(distance_atr, structural=False, with_trend=None):
    """估计在典型持仓期 (4-8 小时) 内, 价格触及该距离价位的概率。

    启发式 (非精确值):
      - 距离越近越易触及 (按 ATR 距离衰减)
      - 结构位 (摆动点 / EMA / Volume) 有 +5% 溢价 (价格习惯反应)
      - 顺势方向 +7%, 逆势方向 -7%

    distance_atr: 距入场的距离, 以 1h ATR 为单位
    structural:   该位是否锚定在结构上 (True=摆动/EMA/POC, False=几何位)
    with_trend:   该位的方向是否与多周期趋势一致 (True/False/None=未知)
    """
    if distance_atr <= 0.3:
        base = 0.88
    elif distance_atr <= 0.5:
        base = 0.78
    elif distance_atr <= 1.0:
        base = 0.62
    elif distance_atr <= 1.5:
        base = 0.50
    elif distance_atr <= 2.0:
        base = 0.40
    elif distance_atr <= 3.0:
        base = 0.28
    elif distance_atr <= 5.0:
        base = 0.16
    else:
        base = 0.08

    if structural:
        base += 0.05
    if with_trend is True:
        base += 0.07
    elif with_trend is False:
        base -= 0.07

    return max(0.05, min(0.95, base))


def rr_verdict(rr, sl_loss_usd, tp_profit_usd):
    """根据 R/R 给分层判定 + 保本胜率。
    保本公式: W × tp_profit = (1-W) × sl_loss → W = sl_loss / (tp_profit + sl_loss)
    """
    if tp_profit_usd <= 0 or sl_loss_usd <= 0:
        return {"tier": "?", "breakeven_pct": 0, "min_wr_pct": 0, "comment": ""}

    breakeven = sl_loss_usd / (tp_profit_usd + sl_loss_usd) * 100

    if rr >= 2.5:
        return {
            "tier": "✓ 优秀",
            "breakeven_pct": breakeven,
            "min_wr_pct": breakeven + 5,
            "comment": "任何 30%+ 胜率都正期望, 抗误判能力强",
        }
    if rr >= 2.0:
        return {
            "tier": "✓ 标准",
            "breakeven_pct": breakeven,
            "min_wr_pct": breakeven + 7,
            "comment": "经典 2R 系统配置, 35-40% 胜率即正期望",
        }
    if rr >= 1.5:
        return {
            "tier": "⚠ 宽松",
            "breakeven_pct": breakeven,
            "min_wr_pct": breakeven + 8,
            "comment": "需要 50%+ 真实胜率才有可观期望, 适合撑压位 scalp",
        }
    if rr >= 1.0:
        return {
            "tier": "⚠ 紧",
            "breakeven_pct": breakeven,
            "min_wr_pct": breakeven + 8,
            "comment": "高胜率策略才行 (60%+), 一般情况下不建议",
        }
    return {
        "tier": "✗ 不利",
        "breakeven_pct": breakeven,
        "min_wr_pct": breakeven + 5,
        "comment": "数学上极度不利, 即使高胜率也难有期望",
    }

