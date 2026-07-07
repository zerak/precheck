"""编排: 拉数据 → 分析 → 方案 → 展示。所有市场状态收敛到 MarketContext。"""
from .config import DEFAULT_LEVEL, TRADE_LEVELS, TIMEFRAMES, FUNDING_HISTORY_LIMIT
from .context import MarketContext
from .data.symbols import base_ccy
from .data.client import (
    get_klines, get_oi_history, get_funding_now, get_funding_history,
)
from .indicators import ema_series, atr_wilder, volume_profile
from .analysis.structure import analyze_structure, compute_ema_deviation
from .analysis.momentum import analyze_volume, detect_momentum_exhaustion
from .analysis.levels import collect_key_levels, flip_levels
from .analysis.openinterest import analyze_oi, interpret_oi
from .analysis.funding import analyze_funding, interpret_funding
from .analysis.bias_timing import assess_bias_timing
from .report.sections import (
    print_header, print_timeframes, print_volume, print_oi, print_funding,
    print_summary, print_key_levels_and_momentum, print_suggestions,
)
from .checklist import run_checklist


def run(inst_id, exchange="okx", with_check=False, account=10000, risk_pct=1,
        level=DEFAULT_LEVEL):
    ctx = MarketContext(
        inst_id=inst_id, exchange=exchange, level=level,
        account=account, risk_pct=risk_pct, with_check=with_check,
    )
    print_header(ctx)

    rows = []
    klines_by_tf = {}
    direction_1h = None
    for label, bars in TIMEFRAMES:
        kl = get_klines(inst_id, bars[exchange], exchange=exchange)
        closes = [k["close"] for k in kl]
        e50 = ema_series(closes, 50)
        e200 = ema_series(closes, 200)
        atr14 = atr_wilder(kl, period=14)
        last = kl[-1]
        ema200_last = e200[-1]
        above = last["close"] > ema200_last if ema200_last else None
        pct = (last["close"] - ema200_last) / ema200_last * 100 if ema200_last else None
        rows.append({
            "interval": label,
            "close": last["close"],
            "ema50": e50[-1],
            "ema200": ema200_last,
            "above": above,
            "pct_vs_ema200": pct,
            "structure": analyze_structure(closes, e200) if ema200_last else "数据不足",
            "atr": atr14,
        })
        klines_by_tf[label] = kl
        if label == "1h":
            direction_1h = "up" if last["close"] >= last["open"] else "down"

    # 按交易级别额外拉取关键位所需周期 (日线/周线), 不参与多周期方向打分
    cfg = TRADE_LEVELS.get(level, TRADE_LEVELS[DEFAULT_LEVEL])
    extra_bars = {
        "1d": {"okx": "1D", "binance": "1d"},
        "1w": {"okx": "1W", "binance": "1w"},
    }
    for tf in cfg["tfs"]:
        if tf in klines_by_tf:
            continue  # 1h/4h 已在 TIMEFRAMES 拉过
        if tf in extra_bars:
            try:
                klines_by_tf[tf] = get_klines(inst_id, extra_bars[tf][exchange], exchange=exchange)
            except SystemExit:
                pass  # 拉取失败不阻断主流程
    # collect_key_levels 仍需日线 (它的大级别位固定看 4h+日线), 确保已拉
    if "1d" not in klines_by_tf:
        try:
            klines_by_tf["1d"] = get_klines(inst_id, extra_bars["1d"][exchange], exchange=exchange)
        except SystemExit:
            pass

    ctx.rows = rows
    ctx.klines_by_tf = klines_by_tf
    ctx.direction_1h = direction_1h
    print_timeframes(ctx)

    klines_1h = klines_by_tf.get("1h")
    ctx.vol = analyze_volume(klines_1h) if klines_1h else None
    print_volume(ctx)

    # OI: 数据层先拉, 再喂给纯分析函数 (解耦网络)
    oi_key = inst_id if exchange == "binance" else base_ccy(inst_id)
    oi_history = get_oi_history(
        oi_key, period="1h" if exchange == "binance" else "1H", limit=24, exchange=exchange
    )
    ctx.oi = analyze_oi(oi_history)
    ctx.oi_meaning = interpret_oi(ctx.oi, direction_1h)
    print_oi(ctx)

    # 资金费率: 同样先拉后算
    funding_now = get_funding_now(inst_id, exchange=exchange)
    funding_history = get_funding_history(inst_id, limit=FUNDING_HISTORY_LIMIT, exchange=exchange)
    ctx.funding = analyze_funding(funding_now, funding_history)
    ctx.funding_meaning = interpret_funding(ctx.funding)
    print_funding(ctx)

    # 双轴判定所需的新维度
    row_1h = next((r for r in rows if r["interval"] == "1h"), None)
    current = row_1h["close"] if row_1h else None
    atr_1h = row_1h["atr"] if row_1h else None
    ctx.row_1h = row_1h
    ctx.current = current
    ctx.atr_1h = atr_1h
    if klines_1h and current and atr_1h:
        vp_window = klines_1h[-100:] if len(klines_1h) >= 100 else klines_1h
        ctx.vp = volume_profile(vp_window, n_bins=50, max_hvn=3)
        ctx.key_levels = collect_key_levels(klines_by_tf, current, atr_1h, vp=ctx.vp)
        ctx.flip = flip_levels(klines_by_tf, current, level=level)
    ctx.momentum = detect_momentum_exhaustion(klines_1h) if klines_1h else None
    ctx.ema_dev = compute_ema_deviation(row_1h)
    ctx.assessment = assess_bias_timing(ctx)

    print_summary(ctx)

    # 大级别压力位 / 支撑阻力互换位 / 动能衰竭 明细
    print_key_levels_and_momentum(ctx)

    # 默认输出: 自动建议交易方案
    print_suggestions(ctx)

    # 可选: 交互式 5 项 checklist (用于验证你自己的方案)
    if with_check:
        run_checklist(inst_id, rows, klines_by_tf)
