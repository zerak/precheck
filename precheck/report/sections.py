"""各输出段落打印。"""
from datetime import datetime
from ..config import EMA_DEV_THRESHOLDS, TIMING_LABELS
from ..indicators import volume_profile
from ..analysis.structure import compute_ema_deviation
from ..plan import suggest_plan, hit_probability, rr_verdict
from ..formatting import fmt_price, fmt_pct, fmt_num


def print_header(ctx):
    inst_id = ctx.inst_id
    exchange = ctx.exchange
    print("=" * 78)
    print(f" 开仓前四维体检 — {inst_id}")
    print(f" 数据源: {exchange.upper()}")
    print("=" * 78)
    print(f" 时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()


def print_timeframes(ctx):
    rows = ctx.rows
    print("─" * 78)
    print(" [1] 多周期 K 线 + EMA + ATR")
    print("─" * 78)
    print(
        f" {'周期':<6} {'收盘':>11} {'EMA50':>11} {'EMA200':>11} "
        f"{'vs EMA200':>14} {'ATR(14)':>10}"
    )
    for r in rows:
        pos = (
            f"{'上' if r['above'] else '下'}方 {fmt_pct(r['pct_vs_ema200'])}"
            if r["above"] is not None
            else "-"
        )
        atr_str = fmt_price(r["atr"]) if r.get("atr") else "-"
        print(
            f" {r['interval']:<6} {fmt_price(r['close']):>11} "
            f"{fmt_price(r['ema50']):>11} {fmt_price(r['ema200']):>11} "
            f"{pos:>14} {atr_str:>10}"
        )
    print()
    print(" 结构识别:")
    for r in rows:
        print(f"   {r['interval']:<5} → {r['structure']}")
    print()
    print_ema_deviation(rows)


# EMA50 紧贴价格,1-2 ATR 已是延伸; EMA200 在趋势中天然离得更远,阈值更宽


def print_ema_deviation(rows):
    """基于 1h 数据,显示价格距 EMA50/EMA200 的 ATR 倍数偏离,提示追单风险。"""
    row_1h = next((r for r in rows if r["interval"] == "1h"), None)
    dev = compute_ema_deviation(row_1h)
    if not dev:
        return
    ema50 = row_1h.get("ema50")
    ema50_extended_side = None  # 'long' / 'short' / None

    lines = []
    for label, key in (("EMA50", "ema50"), ("EMA200", "ema200")):
        d = dev.get(key)
        if d is None:
            continue
        side = "上方" if d["diff"] >= 0 else "下方"
        if label == "EMA50" and d["mult"] > EMA_DEV_THRESHOLDS["EMA50"][1]:
            ema50_extended_side = d["side"]
        lines.append(
            f"   距 1h {label:<6} {side} {abs(d['pct']):>4.2f}%  "
            f"({d['mult']:.2f} × 1h ATR)  → {d['tag']}"
        )

    if not lines:
        return
    print(" EMA 偏离 (1h):")
    for ln in lines:
        print(ln)
    if ema50_extended_side == "long":
        print(f"   ↳ 价格已超 EMA50 上方 > 2×ATR,现价做多大概率买在均值回归反向")
        print(f"     建议: 挂限价单到 EMA50 ≈ {ema50:,.4g} 附近等回踩,或仓位减半")
    elif ema50_extended_side == "short":
        print(f"   ↳ 价格已超 EMA50 下方 > 2×ATR,现价做空大概率卖在均值回归反向")
        print(f"     建议: 挂限价单到 EMA50 ≈ {ema50:,.4g} 附近等反弹,或仓位减半")
    print()


def print_volume(ctx):
    v = ctx.vol
    print("─" * 78)
    print(" [2] 量价关系 (1H 最后一根已收盘 K 线 vs 之前 20 根均量)")
    print("─" * 78)
    if v is None:
        print(" 数据不足")
        print()
        return
    print(f" 倍数:  {v['ratio']:.2f}x   状态: {v['tag']}{v['direction']}")
    print(f" 含义:  {v['meaning']}")
    print()


def print_oi(ctx):
    oi = ctx.oi
    meaning = ctx.oi_meaning
    print("─" * 78)
    print(" [3] 持仓量 (Open Interest)")
    print("─" * 78)
    if oi is None:
        print(" 数据不足")
        print()
        return
    print(f" 当前 OI:    ${fmt_num(oi['now_usd'])}")
    print(f" 1h  变化:   {fmt_pct(oi['change_1h_pct'])}")
    print(f" 24h 变化:   {fmt_pct(oi['change_24h_pct'])}")
    print(f" 含义:       {meaning}")
    print()


def print_funding(ctx):
    f = ctx.funding
    meaning = ctx.funding_meaning
    print("─" * 78)
    print(" [4] 资金费率 (Funding Rate)")
    print("─" * 78)
    if f is None:
        print(" 数据不足")
        print()
        return
    print(
        f" 当前:       {f['current']*100:+.4f}%  (年化 {fmt_pct(f['current_annual_pct'])})"
    )
    print(
        f" 近8期均:    {f['avg_8']*100:+.4f}%  (年化 {fmt_pct(f['avg_8_annual_pct'])})"
    )
    if f["next_time"]:
        print(f" 下次结算:   {f['next_time'].strftime('%Y-%m-%d %H:%M %Z')}")
    print(f" 含义:       {meaning}")
    print()


def _print_reversion_evidence(ctx):
    """反转预警下, 打印"反向回撤到 EMA 的历史概率依据"(查 reversion 缓存)。"""
    ev = ctx.reversion
    if not ev:
        return
    status = ev.get("status")
    if status == "missing":
        print("   ℹ 反向回撤依据: 无缓存 → 加 --fr / --force-reversion 现算 (需拉历史约几十秒)")
        return
    if status == "stale":
        print(f"   ℹ 反向回撤依据: 缓存已过期 (生成于 {ev.get('generated_at')}) "
              f"→ 加 --fr 刷新")
        return
    if status in ("nodata", "skip"):
        return
    # status == ok
    side_zh = "回调" if ev["side"] == "up" else "反弹"
    move_zh = "跌回" if ev["side"] == "up" else "涨回"
    cur = ctx.current
    print(f"   ─ 反向回撤依据 (历史统计, 缓存 {ev.get('generated_at')}):")
    if cur:
        print(f"     现价 {fmt_price(cur)}")
    for period, dev_atr, by_window, ref, diff, pct in ev["rows"]:
        parts = []
        for W in sorted(by_window):
            st = by_window[W]
            parts.append(f"未来{W}根触及{st['reach']*100:.0f}% (缺口中位{st['cov50']*100:.0f}%)")
        tgt = f"目标 EMA{period}={fmt_price(ref)}" if ref is not None else f"EMA{period}"
        if diff is not None and pct is not None:
            gap = f" (距现价 {fmt_price(abs(diff))} / {abs(pct):.1f}%)"
        elif pct is not None:
            gap = f" (距现价 {abs(pct):.1f}%)"
        else:
            gap = ""
        print(f"     {tgt}{gap}, 偏离 {dev_atr:.1f}×ATR → {move_zh}概率: "
              + " / ".join(parts))
    print(f"     读法: 触及%=历史上同偏离度{side_zh}到该EMA的占比; "
          f"缺口中位=没到位时通常{side_zh}到缺口的几成 (可作分批止盈参考)")


def print_summary(ctx):
    vol = ctx.vol
    oi_meaning = ctx.oi_meaning
    funding_meaning = ctx.funding_meaning
    assessment = ctx.assessment
    print("=" * 78)
    print(" 综合评分")
    print("=" * 78)

    if vol:
        print(f" 量价关系:   {vol['meaning']}")
    print(f" OI 信号:    {oi_meaning}")
    print(f" 资金费率:   {funding_meaning}")
    print()

    a = assessment
    print(f" Bias(趋势方向):   {a['bias_desc']}")
    if a["aux_signals"]:
        print(f"                   辅助信号 {len(a['aux_signals'])}/3: {a['aux_signals']}")
    print(f" Timing(入场时机): {TIMING_LABELS.get(a['timing'], a['timing'])}", end="")

    if a["reversal_triggered"]:
        cond = a["reversal_conditions"]
        hit = sum(cond.values())
        print(f" — 满足 {hit}/3 反转条件:")
        # 过度延伸
        if cond["over_extended"]:
            print("                    ✓ 顺势方向已过度延伸(过热)")
        else:
            print("                    ✗ 过度延伸(未触发)")
        # 压力位
        if cond["at_key_level"] and a["nearest_level"]:
            lv = a["nearest_level"]
            print(f"                    ✓ 贴近{lv['tf']}{'压力' if lv['type']=='high' else '支撑'}位 "
                  f"{fmt_price(lv['price'])}(距现价 {lv['dist_atr']:.2f}×ATR)")
        else:
            print("                    ✗ 贴近大级别压力/支撑位(未触发)")
        # 动能衰竭
        if cond["momentum_exhausted"]:
            print("                    ✓ 动能衰竭迹象出现")
        else:
            print("                    ✗ 动能衰竭(暂未出现)")
        rev_zh = "做空" if a["reversal_side"] == "short" else "做多"
        bias_zh = "多" if a["bias"] == "long" else "空"
        print(f" → 结论: 趋势偏{bias_zh}, 但高位满足反转条件 → 不追{bias_zh}, 警惕反转. "
              f"若确认见{'顶' if a['bias']=='long' else '底'}可考虑{rev_zh}")
        _print_reversion_evidence(ctx)
    else:
        print()
        for line in a["narrative"]:
            print(f" → {line}")

    print()
    print("=" * 78)


def print_key_levels_and_momentum(ctx):
    """打印大级别压力/支撑位 + 近端动能衰竭明细 (双轴判定的支撑证据)。"""
    key_levels = ctx.key_levels
    momentum = ctx.momentum
    flip = ctx.flip
    print()
    print("─" * 78)
    print(" [5] 大级别压力/支撑位 (4h + 日线摆动点 + 成交密集区, 距现价 ≤8×ATR)")
    print("─" * 78)
    if key_levels:
        for lv in key_levels[:8]:
            kind = "压力" if lv["type"] == "high" else "支撑"
            strength = f"×{lv['touches']}" if lv["touches"] > 1 else ""
            print(
                f"   {lv['tf']:<4} {kind}位  {fmt_price(lv['price'])}  "
                f"(距现价 {lv['dist_atr']:.2f}×1h ATR){(' 强度' + strength) if strength else ''}"
            )
    else:
        print("   近距离内无显著大级别压力/支撑位")

    # 支撑阻力互换位 (贴合用户手法: 前低聚集→上方压力, 前高聚集→下方支撑)
    if flip and (flip.get("resistance") or flip.get("support")):
        unit_tf = flip.get("unit_tf", "?")
        print()
        print("─" * 78)
        print(f" [5b] 支撑阻力互换位 (收盘价实体; 保守/中庸/激进三档止盈止损)")
        print(f"      上方压力=前低聚集(旧支撑变阻力)  下方支撑=前高聚集(旧阻力变支撑)")
        print(f"      距离以 {unit_tf} ATR 为单位")
        print("─" * 78)
        if flip.get("resistance"):
            print("   上方压力 (做多止盈 / 做空入场参考):")
            for c in flip["resistance"][:3]:
                st = f"×{c['count']}" if c["count"] > 1 else ""
                print(
                    f"     {c['tf']:<4} 保守 {fmt_price(c['conservative'])} | "
                    f"中庸 {fmt_price(c['mid'])} | 激进 {fmt_price(c['aggressive'])}  "
                    f"(前低聚集{st}, 距现价 {c['dist_atr']:.2f}×{unit_tf}ATR)"
                )
        if flip.get("support"):
            print("   下方支撑 (做空止盈 / 做多入场参考):")
            for c in flip["support"][:3]:
                st = f"×{c['count']}" if c["count"] > 1 else ""
                print(
                    f"     {c['tf']:<4} 保守 {fmt_price(c['conservative'])} | "
                    f"中庸 {fmt_price(c['mid'])} | 激进 {fmt_price(c['aggressive'])}  "
                    f"(前高聚集{st}, 距现价 {c['dist_atr']:.2f}×{unit_tf}ATR)"
                )

    print()
    print("─" * 78)
    print(" [6] 近端动能衰竭 (基于已收盘 1h)")
    print("─" * 78)
    if momentum and momentum.get("exhausted"):
        side_zh = "见顶(利空)" if momentum["side"] == "top" else "见底(利多)"
        print(f"   ⚠ 检出{side_zh}衰竭迹象:")
        for s in momentum["signals"]:
            print(f"      - {s}")
    else:
        print("   近端无明显动能衰竭迹象")
    print()


# ─────────────── 主流程 ───────────────


# ─────────────── 自动方案生成 ───────────────


def print_suggestions(ctx):
    rows = ctx.rows
    account = ctx.account
    risk_pct = ctx.risk_pct
    assessment = ctx.assessment
    above = sum(1 for r in rows if r["above"])
    if above == 3:
        recommended = "long"
        consensus = "多周期共振多 (3/3)"
    elif above == 0:
        recommended = "short"
        consensus = "多周期共振空 (3/3)"
    else:
        recommended = None
        consensus = f"多周期分歧 ({above}/3 在 EMA200 上方)"

    # 反转预警时: 顺势方向被"降级", 逆势(反转)方向被"提升"为反转候选
    reversal = bool(assessment and assessment.get("reversal_triggered"))
    reversal_side = assessment.get("reversal_side") if assessment else None

    # 拿当前价 (用 1h 收盘当作 spot 代理)
    row_1h = next((r for r in rows if r["interval"] == "1h"), None)
    current_price = row_1h["close"] if row_1h else None

    print()
    print("=" * 78)
    print(" 系统建议交易方案 (基于客观数据自动生成)")
    print("=" * 78)
    if current_price:
        print(f" 当前价:     {fmt_price(current_price)}")
    print(f" 多周期判断: {consensus}")
    if reversal:
        rec_zh = "做多" if recommended == "long" else "做空"
        rev_zh = "做空" if reversal_side == "short" else "做多"
        print(f" 趋势方向:   {rec_zh} (顺势) — ⛔ 但已触发反转预警, 不建议追顺势")
        print(f" 推荐动作:   观望 / 等反转确认; 若见{'顶' if recommended=='long' else '底'}成立可考虑{rev_zh}(反转候选)")
    elif recommended:
        rec_zh = "做多" if recommended == "long" else "做空"
        timing = assessment.get("timing") if assessment else None
        if timing == "pullback":
            print(f" 推荐方向:   {rec_zh} (顺势) — ⚠ 高位/信号不足, 等回踩不追")
        else:
            print(f" 推荐方向:   {rec_zh} (顺势)")
    else:
        print(" 推荐方向:   等共振 (任何方向都缺顺势依据)")
    print(f" 仓位计算:   账户 ${account}, 单笔风险 {risk_pct}%")
    print()

    rev = assessment.get("reversal_triggered") if assessment else False
    rev_side = assessment.get("reversal_side") if assessment else None
    long_plan = suggest_plan(ctx, "long", reversal=(rev and rev_side == "long"))
    short_plan = suggest_plan(ctx, "short", reversal=(rev and rev_side == "short"))

    for plan, label in ((long_plan, "做多 LONG"), (short_plan, "做空 SHORT")):
        if not plan:
            print("─" * 78)
            print(f" {label}  [数据不足]")
            print()
            continue
        if plan.get("_no_entry"):
            print("─" * 78)
            print(f" {label}  [无合理入场点]")
            print(f"   原因: {plan['_reason']}")
            print()
            continue

        is_rec = plan["direction"] == recommended
        if reversal:
            # 反转预警下: 反转方向 = 反转候选(提升), 顺势方向 = 已过热不追(降级)
            if plan["direction"] == reversal_side:
                tag = "🔄 反转候选 (需确认见顶/底)"
            else:
                tag = "⛔ 顺势但已过热, 不追"
        elif recommended is None:
            tag = "⚠ 分歧期, 谨慎"
        elif is_rec:
            tag = "✓ 顺势, 推荐"
        else:
            tag = "✗ 逆势, 不推荐"

        print("─" * 78)
        print(f" {label}  [{tag}]")
        print("─" * 78)

        # 入场动作描述
        cur = plan["current"]
        entry_diff_abs = abs(plan["entry"] - cur)
        is_long = plan["direction"] == "long"

        if abs(plan["dist_pct"]) < 0.1:
            entry_action = "可立即入场 (当前价已在入场区)"
            entry_pos = "几乎贴当前价"
        elif is_long:
            entry_action = f"挂限价单, 等价格回落到 {fmt_price(plan['entry'])} 触发"
            entry_pos = f"当前价下方 {fmt_price(entry_diff_abs)} ({plan['dist_pct']:.2f}%)"
        else:
            entry_action = f"挂限价单, 等价格反弹到 {fmt_price(plan['entry'])} 触发"
            entry_pos = f"当前价上方 {fmt_price(entry_diff_abs)} ({plan['dist_pct']:.2f}%)"

        # 类型 emoji
        type_tag = {
            "volume": "⭐ Volume",  # 优先级最高
            "ema": "📊 EMA",
            "swing": "🔀 Swing",
        }.get(plan.get("entry_type"), "?")

        # 止损 / 止盈的方向描述
        sl_dir = "下方" if is_long else "上方"
        tp_dir = "上方" if is_long else "下方"
        sl_pct = plan["sl_dist"] / plan["entry"] * 100
        tp_pct = plan["tp_dist"] / plan["entry"] * 100

        print(f"   入场:    {fmt_price(plan['entry'])}  [{type_tag}] {plan['entry_label']}")
        print(f"            含义:  {plan.get('entry_note', '')}")
        print(f"            选取:  {plan.get('select_reason', '')}")
        print(f"            位置:  {entry_pos}")
        print(f"            → {entry_action}")

        # 备选候选(供比对)
        alts = plan.get("alt_candidates") or []
        if alts:
            print(f"   备选入场点 (供参考, 当前选择以上⭐为准):")
            for c in alts:
                diff = c["price"] - plan["entry"]
                diff_pct = diff / plan["entry"] * 100
                tag = {"volume": "⭐", "ema": "📊", "swing": "🔀"}.get(c["type"], "?")
                print(
                    f"            {tag} {c['label']:<20} @ {fmt_price(c['price'])}  "
                    f"(距首选 {diff:+.4f} / {diff_pct:+.2f}%)"
                )

        # 金额计算 (qty × dist 即美元盈亏, sl_loss 应等于风险预算)
        sl_loss_usd = plan["qty"] * plan["sl_dist"]
        tp_profit_usd = plan["qty"] * plan["tp_dist"]
        sl_pct_account = sl_loss_usd / account * 100
        tp_pct_account = tp_profit_usd / account * 100

        # 止损 — 详细展开
        sl_type_tag = {
            "anchored": "🔗 锚定摆动点",
            "default": "⚖️ ATR 默认",
        }.get(plan.get("sl_type"), "?")
        print(f"   止损:    {fmt_price(plan['stop'])}  [{sl_type_tag}]")
        print(f"            含义:  {plan.get('sl_meaning', '')}")
        print(f"            选取:  {plan.get('sl_reason', '')}")
        print(
            f"            位置:  入场{sl_dir} {fmt_price(plan['sl_dist'])} / "
            f"{sl_pct:.2f}% ({plan['atr_ratio']:.2f}× 1h ATR({plan['atr_1h']:.4f}) = {plan['sl_dist']:.4f})"
        )
        print(f"            金额:  -${sl_loss_usd:.2f} (账户 -{sl_pct_account:.2f}%)")
        print(f"            → 触发后平仓")

        # 所有摆动点候选 (近 50 根 1h 内, 含被过滤掉的, 让用户自己看清楚为什么选这个)
        sl_swings = plan.get("sl_swing_table") or []
        if sl_swings:
            # 按 bars_ago 升序 (最近在上)
            sl_swings_sorted = sorted(sl_swings, key=lambda x: x["bars_ago"])
            print(f"            所有候选 swing (★=本次锚定, 近 50 根 1h):")
            for s in sl_swings_sorted:
                marker = "★" if s["selected"] else " "
                if s["in_range"]:
                    status = f"✓ 在 1.5×ATR 内 ({s['atr_mult']:.2f}×ATR)"
                else:
                    side_tag = "上方" if s["side"] == "above" else "下方"
                    status = f"✗ 超出 1.5×ATR ({side_tag} {s['atr_mult']:.2f}×ATR)"
                print(
                    f"              {marker} {fmt_price(s['price'])}  "
                    f"({s['bars_ago']:>2} 根前)  {status}"
                )

        # 止盈 — 详细展开
        tp_type_tag = {
            "swing": "🎯 摆动锚定",
            "default": "⚖️ R 倍数默认",
        }.get(plan.get("tp_type"), "?")
        print(f"   止盈:    {fmt_price(plan['tp'])}  [{tp_type_tag}] {plan['tp_label']}")
        print(f"            含义:  {plan.get('tp_meaning', '')}")
        print(f"            选取:  {plan.get('tp_reason', '')}")
        print(
            f"            位置:  入场{tp_dir} {fmt_price(plan['tp_dist'])} / "
            f"{tp_pct:.2f}%"
        )
        print(
            f"            金额:  +${tp_profit_usd:.2f} "
            f"(R/R {plan['rr']:.2f}, 账户 +{tp_pct_account:.2f}%)"
        )
        print(f"            → 挂限价平仓, 或考虑分批 + 移动止损吃趋势")

        # 备选止盈 (仅当主目标 R/R < 2 时展示, 让用户看到"凑 R/R"的更远位)
        tp_alts = plan.get("tp_alts") or []
        if tp_alts:
            print(f"   备选止盈 (主目标 R/R < 2, 这些位距离更远但满足 ≥ 2R):")
            for alt in tp_alts:
                alt_dist = abs(alt["price"] - plan["entry"])
                alt_profit = plan["qty"] * alt_dist
                alt_pct = alt_profit / account * 100
                print(
                    f"            🎯 {alt['label']:<22} @ {fmt_price(alt['price'])}  "
                    f"R/R {alt['rr']:.2f}  +${alt_profit:.2f} (+{alt_pct:.2f}%)"
                )
            print(f"            ⚠ 这些位虽然 R/R 更优, 但更远 = 更难触及")
        # R/R 分层判定
        # 注: 输的实际损失 = 风险预算 + 市价止损手续费 (~ 0.04% × 名义)
        actual_loss = sl_loss_usd + plan["qty"] * plan["entry"] * 0.0004
        rr_v = rr_verdict(plan["rr"], actual_loss, tp_profit_usd)
        print(f"   R/R:     {plan['rr']:.2f}  [{rr_v['tier']}]")
        print(
            f"            保本胜率:  {rr_v['breakeven_pct']:.1f}%  "
            f"(赢 +${tp_profit_usd:.2f}, 输 -${actual_loss:.2f})"
        )
        print(f"            含义:      {rr_v['comment']}")

        # ─── 触达概率估算 (启发式) ───
        # 趋势方向匹配: 对当前 trade 而言, TP 是顺势位、SL 是逆势位 (顺势单)
        # 逆势单则相反
        if recommended is None:
            tp_with_trend = None
            sl_with_trend = None
        else:
            tp_with_trend = is_rec  # 顺势单的 TP = 顺势, 逆势单的 TP = 逆势
            sl_with_trend = not is_rec  # 顺势单的 SL = 逆势, 逆势单的 SL = 顺势

        sl_atr = plan["sl_dist"] / plan["atr_1h"]
        tp_atr = plan["tp_dist"] / plan["atr_1h"]
        p_tp = hit_probability(
            tp_atr,
            structural=(plan.get("tp_type") == "swing"),
            with_trend=tp_with_trend,
        )
        p_sl = hit_probability(
            sl_atr,
            structural=(plan.get("sl_type") == "anchored"),
            with_trend=sl_with_trend,
        )
        # 隐含胜率: 假设两者互斥, P(TP 先到) ≈ P_tp / (P_tp + P_sl)
        implied_wr = p_tp / (p_tp + p_sl) if (p_tp + p_sl) > 0 else 0
        # 单笔期望(以 R 为单位): WR × R - (1-WR) × 1
        single_ev_r = implied_wr * plan["rr"] - (1 - implied_wr)
        single_ev_usd = (
            implied_wr * tp_profit_usd - (1 - implied_wr) * actual_loss
        )
        breakeven_decimal = rr_v["breakeven_pct"] / 100
        ev_gap = (implied_wr - breakeven_decimal) * 100  # 百分点

        print()
        print(f"            触达概率估算 (基于距离+结构+趋势的启发式):")
        tp_struct = "swing 锚定" if plan.get("tp_type") == "swing" else "几何位"
        sl_struct = "摆动锚定" if plan.get("sl_type") == "anchored" else "ATR 默认"
        tp_trend = "顺势" if tp_with_trend else ("逆势" if tp_with_trend is False else "中性")
        sl_trend = "顺势" if sl_with_trend else ("逆势" if sl_with_trend is False else "中性")
        print(
            f"              ⊕ P(止盈触达):  {p_tp*100:.0f}%  "
            f"(距入场 {tp_atr:.2f}× 1h ATR({plan['atr_1h']:.4f}) = {plan['tp_dist']:.4f}, {tp_struct} + {tp_trend})"
        )
        print(
            f"              ⊖ P(止损触达):  {p_sl*100:.0f}%  "
            f"(距入场 {sl_atr:.2f}× 1h ATR({plan['atr_1h']:.4f}) = {plan['sl_dist']:.4f}, {sl_struct} + {sl_trend})"
        )
        print(
            f"              隐含胜率:      {implied_wr*100:.0f}%  "
            f"(P_tp / (P_tp + P_sl))"
        )
        gap_sign = "+" if ev_gap >= 0 else ""
        print(
            f"              vs 保本胜率:   {gap_sign}{ev_gap:.1f} 个百分点  "
            f"({'高于保本 → 正期望' if ev_gap > 0 else '低于保本 → 负期望'})"
        )
        ev_sign = "+" if single_ev_usd >= 0 else ""
        print(
            f"              单笔期望值:    {ev_sign}{single_ev_r:.2f} R "
            f"= {ev_sign}${single_ev_usd:.2f}"
        )

        print(f"   仓位:    {plan['qty']:.4f} 张  (风险预算 ${account * risk_pct/100:.2f})")
        # 把估算值塞回 plan 给 verdict_lines 用
        plan["_implied_wr"] = implied_wr
        plan["_breakeven"] = breakeven_decimal
        plan["_single_ev_r"] = single_ev_r

        # Volume Profile 数据简显 (含"是否在候选范围内"标注)
        vp = plan.get("vp")
        if vp and vp.get("poc"):
            atr = plan["atr_1h"]

            def _vp_node_status(p):
                """返回该节点相对当前/入场的状态标签。"""
                # 相对当前价的距离 (ATR 倍数)
                dist_atr = abs(p - cur) / atr if atr > 0 else 0
                # 是否在入场方向上 + 2 ATR 内 (即被纳入候选的范围)
                if is_long:
                    in_range = (p < cur and p >= cur - 2 * atr)
                else:
                    in_range = (p > cur and p <= cur + 2 * atr)
                if in_range:
                    return "✓候选"
                if (is_long and p > cur) or (not is_long and p < cur):
                    return f"逆向 ({dist_atr:.1f}×ATR)"
                return f"过远 ({dist_atr:.1f}×ATR)"

            poc_tag = _vp_node_status(vp["poc"])
            print(f"   📊 VP:   POC={fmt_price(vp['poc'])} [{poc_tag}]  (近 100 根 1h)")
            for i, h in enumerate(vp["hvn"], start=1):
                print(f"            HVN#{i}={fmt_price(h)} [{_vp_node_status(h)}]")

        # 综合判定: 基于"估算单笔期望值"作主判, R/R + ATR + 方向作辅助
        verdict_lines = []
        ev_r = plan.get("_single_ev_r", 0)
        implied_wr = plan.get("_implied_wr", 0) * 100
        breakeven_pct = plan.get("_breakeven", 0) * 100

        # 主判: 单笔期望值
        if ev_r > 0.2:
            verdict_lines.append(
                f"   ✓ 估算单笔期望 +{ev_r:.2f}R (隐含胜率 {implied_wr:.0f}% "
                f"vs 保本 {breakeven_pct:.0f}%) → 几何上正期望"
            )
        elif ev_r > 0:
            verdict_lines.append(
                f"   ⚠ 估算单笔期望 +{ev_r:.2f}R (隐含胜率 {implied_wr:.0f}% "
                f"vs 保本 {breakeven_pct:.0f}%) → 期望微正, 边缘单"
            )
        else:
            verdict_lines.append(
                f"   ✗ 估算单笔期望 {ev_r:.2f}R (隐含胜率 {implied_wr:.0f}% "
                f"vs 保本 {breakeven_pct:.0f}%) → 几何上负期望, 不建议"
            )

        # 辅助警告
        if plan["atr_ratio"] < 0.7:
            verdict_lines.append(
                f"   ⚠ 止损 {plan['atr_ratio']:.2f}× 1h ATR({plan['atr_1h']:.4f}) = {plan['sl_dist']:.4f} < 0.7 → 易被噪音扫损 "
                f"(P_sl 估算偏低, 实际可能更高)"
            )
        if not is_rec and recommended:
            verdict_lines.append(
                f"   ⚠ 多周期共振{('多' if recommended=='long' else '空')} → 此方向逆势 "
                f"(P_tp 已扣分 7%)"
            )

        # 提醒估算的局限
        verdict_lines.append(
            "   ℹ️ 注: 触达概率为启发式估算, 实战需用你自己的复盘数据校准"
        )

        for line in verdict_lines:
            print(line)
        print()

    print("=" * 78)
    print(" 提醒: 本工具只提供四维数据快照 + 自动方案, 不替代交易决策与你对 K 线形态的眼睛确认。")
    print("       入场前还需独立确认: 入场点 / 止损位 / 仓位规模 (含手续费 0.08%)。")
    print(" 如要修改账户/风险:  --account <数字> / -a   --risk <数字> / -r")
    print(" 如要交互验证你自己的方案:  加 --check / -c")
    print("=" * 78)

