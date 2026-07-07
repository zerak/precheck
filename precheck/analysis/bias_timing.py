"""双轴判定: Bias(趋势方向) + Timing(入场时机/反转预警)。"""
from ..config import OVER_EXTENDED_ATR


def assess_bias_timing(ctx):
    """双轴判定: Bias(趋势方向) + Timing(入场时机).

    从 ctx 读取 rows/vol/oi_meaning/funding_meaning/key_levels/momentum/ema_dev。
    Bias 沿用 above_count(EMA200 结构). Timing 综合延伸度/动能/压力位, 并用
    "3 选 2" 判定是否触发反转预警.

    返回 {
      "bias": "long"/"short"/"neutral",
      "bias_desc": str,
      "aux_signals": [str],            # 辅助信号 (顺 bias 方向)
      "timing": "chase"/"pullback"/"wait"/"reversal_warning",
      "reversal_conditions": {"at_key_level": bool, "momentum_exhausted": bool, "over_extended": bool},
      "reversal_triggered": bool,
      "reversal_side": "long"/"short"/None,   # 反转后的方向
      "nearest_level": dict or None,   # 触发 at_key_level 的那个位置
      "narrative": [str],
    }
    """
    rows = ctx.rows
    vol = ctx.vol
    oi_meaning = ctx.oi_meaning
    funding_meaning = ctx.funding_meaning
    key_levels = ctx.key_levels
    momentum = ctx.momentum
    ema_dev = ctx.ema_dev
    above_count = sum(1 for r in rows if r["above"])
    if above_count == 3:
        bias, bias_desc = "long", "偏多 (3/3 在 EMA200 上方)"
    elif above_count == 0:
        bias, bias_desc = "short", "偏空 (3/3 在 EMA200 下方)"
    else:
        bias, bias_desc = "neutral", f"中性/分歧 ({above_count}/3 在 EMA200 上方)"

    # 顺势确认信号 (只用量价 + 结构, 不含 OI/费率 —— 后两者是实时接口, 无历史值,
    # 且回测证明放进 chase 门槛会导致顺势信号永远无法触发。降级为独立风险提示)。
    aux = []
    if bias == "long":
        if vol and "✓" in vol["meaning"] and "上涨" in vol["direction"]:
            aux.append("放量上涨")
        # 结构确认: 价格站在 1h EMA50 上方 (短期动能顺 bias)
        row_1h = next((r for r in rows if r["interval"] == "1h"), None)
        if row_1h and row_1h.get("ema50") and row_1h["close"] > row_1h["ema50"]:
            aux.append("站上 1h EMA50")
    elif bias == "short":
        if vol and (("缩量" in vol["tag"] and "上涨" in vol["direction"])
                    or (vol["tag"] == "放量" and vol["direction"] == "下跌")):
            aux.append("量价利空")
        row_1h = next((r for r in rows if r["interval"] == "1h"), None)
        if row_1h and row_1h.get("ema50") and row_1h["close"] < row_1h["ema50"]:
            aux.append("跌破 1h EMA50")

    # OI / 资金费率: 独立的风险提示 (不参与方向/开仓门槛, 仅实盘参考"别在拥挤时追单")
    risk_hints = []
    if "拥挤" in oi_meaning or "弱势" in oi_meaning:
        risk_hints.append(oi_meaning)
    if "拥挤" in funding_meaning or "过高" in funding_meaning:
        risk_hints.append(funding_meaning)

    # 反转方向: 与 bias 相反 (偏多→见顶反转看空; 偏空→见底反转看多)
    reversal_side = "short" if bias == "long" else ("long" if bias == "short" else None)

    # ── 反转条件 1: 过度延伸 (且延伸方向与 bias 一致, 即顺势方向已过热) ──
    over_extended = bool(
        ema_dev and ema_dev.get("over_extended")
        and ema_dev.get("extended_side") == bias
    )

    # ── 反转条件 2: 贴近逆势方向的大级别压力/支撑位 (≤1×ATR) ──
    # 偏多 → 看上方压力 (type=high); 偏空 → 看下方支撑 (type=low)
    at_key_level = False
    nearest_level = None
    if bias in ("long", "short") and key_levels:
        want = "high" if bias == "long" else "low"
        candidates = [lv for lv in key_levels if lv["type"] == want and lv["dist_atr"] <= 1.0]
        if candidates:
            at_key_level = True
            nearest_level = min(candidates, key=lambda x: x["dist_atr"])

    # ── 反转条件 3: 动能衰竭 (方向须与 bias 对立) ──
    momentum_exhausted = bool(
        momentum and momentum.get("exhausted")
        and ((bias == "long" and momentum["side"] == "top")
             or (bias == "short" and momentum["side"] == "bottom"))
    )

    conditions = {
        "at_key_level": at_key_level,
        "momentum_exhausted": momentum_exhausted,
        "over_extended": over_extended,
    }
    hit = sum(conditions.values())
    reversal_triggered = bias in ("long", "short") and hit >= 2

    # ── Timing 判定 ──
    narrative = []
    if bias == "neutral":
        timing = "wait"
        narrative.append("多周期分歧,胜率结构性偏低 → 等共振再入场")
    elif reversal_triggered:
        timing = "reversal_warning"
    elif over_extended:
        timing = "pullback"
        narrative.append(
            f"顺势方向已延伸 {ema_dev['ema200']['mult']:.1f}×ATR(过热)→ 不追,等回踩"
        )
    elif len(aux) >= 2:
        timing = "chase"
        narrative.append(f"{('多' if bias=='long' else '空')}头逻辑成立,辅助信号 {len(aux)}/3 → 顺势可入(回调更佳)")
    else:
        timing = "pullback"
        narrative.append(f"方向偏{('多' if bias=='long' else '空')}但辅助信号不足({len(aux)}/3),等回踩确认")

    return {
        "bias": bias,
        "bias_desc": bias_desc,
        "aux_signals": aux,
        "timing": timing,
        "reversal_conditions": conditions,
        "reversal_triggered": reversal_triggered,
        "reversal_side": reversal_side,
        "nearest_level": nearest_level,
        "risk_hints": risk_hints,
        "narrative": narrative,
    }

