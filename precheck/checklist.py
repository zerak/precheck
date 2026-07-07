"""交互式开仓 checklist。"""


def _ask(prompt, default=None, parse=str):
    """简单的输入工具,支持默认值和类型转换。"""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = str(default)
        if not raw:
            print("    ⚠ 不能为空")
            continue
        try:
            return parse(raw)
        except (ValueError, TypeError):
            print(f"    ⚠ 输入无效, 请重试")


def _ask_choice(prompt, choices, default=None):
    """让用户从有限选项中选,容忍模糊输入(只要包含关键字即可)。"""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {prompt} ({'/'.join(choices)}){suffix}: ").strip().lower()
        if not raw and default is not None:
            return default
        for c in choices:
            if c.lower() in raw or raw in c.lower():
                return c
        print(f"    ⚠ 必须从 {choices} 中选择")


def _ask_yn(prompt, default="n"):
    while True:
        raw = input(f"  {prompt} (y/n) [{default}]: ").strip().lower() or default
        if raw in ("y", "yes", "是"):
            return True
        if raw in ("n", "no", "否"):
            return False
        print("    ⚠ 输入 y 或 n")


def run_checklist(inst_id, rows, klines_by_tf):
    print()
    print("=" * 78)
    print(" 开仓 Checklist (5 项, 全过才下单)")
    print("=" * 78)
    print(" 提示: 直接 Ctrl+C 可中途退出,不保存任何状态")
    print()

    results = []  # [(label, passed: bool, note: str)]

    # ── [1/5] 多周期方向 vs 你的开仓方向 ──
    print("─" * 78)
    print(" [1/5] 多周期方向 (与你的开仓方向比对)")
    print("─" * 78)
    above_count = sum(1 for r in rows if r["above"])
    if above_count == 3:
        consensus = "long"
        print("   多周期状态: 3/3 在 EMA200 上方 → 共振多")
    elif above_count == 0:
        consensus = "short"
        print("   多周期状态: 3/3 在 EMA200 下方 → 共振空")
    else:
        consensus = None
        print(f"   多周期状态: {above_count}/3 在 EMA200 上方 → 分歧")

    direction = _ask_choice("你计划开", ["long", "short", "多", "空"])
    is_long = direction in ("long", "多")
    user_dir = "long" if is_long else "short"

    if consensus is None:
        print(f"   ✗ 多周期分歧期开 {user_dir} → 无明确顺势依据")
        print("     建议等共振后再开. 现在继续 = 你已主动接受较低胜率")
        cont = _ask_yn("仍然继续 checklist?", "n")
        if not cont:
            print("\n  → 已退出,等多周期共振再来。")
            return
        results.append(("多周期方向", False, f"分歧期开{user_dir}"))
    elif consensus == user_dir:
        print(f"   ✓ 多周期共振{('多' if is_long else '空')} 与你的方向一致 (顺势)")
        results.append(("多周期方向", True, f"顺势 {user_dir}"))
    else:
        print(f"   ✗ 多周期共振{('多' if not is_long else '空')} 但你计划做 {user_dir} (逆势!)")
        print("     逆势单胜率结构性更低. 强烈建议放弃这单, 找顺势机会.")
        cont = _ask_yn("仍然继续 checklist?", "n")
        if not cont:
            print("\n  → 已退出. 顺势是免费 alpha, 别浪费它。")
            return
        results.append(("多周期方向", False, f"逆势 {user_dir}"))
    print()

    # ── [2/5] S/R 评分 ──
    print("─" * 78)
    print(" [2/5] S/R 评分 (5 维度,目标 ≥ 6 分)")
    print("─" * 78)
    score = 0

    n_touch = _ask_choice("触碰次数", ["1次", "2-3次", "4-5次", "6+次"])
    delta = {"1次": 0, "2-3次": 2, "4-5次": 1, "6+次": -1}[n_touch]
    score += delta
    print(f"     → {n_touch} = {delta:+d} 分")

    if _ask_yn("时间跨度: 触碰间隔 ≥ 10 根 K 线 (避免把 1 次盘整误算成多次)?"):
        score += 1
        print("     → +1 分")
    else:
        print("     → 0 分")

    if _ask_yn("多周期可见: 5m 和 1h 都能看出这个 S/R?"):
        score += 2
        print("     → +2 分")
    else:
        print("     → 0 分")

    react = _ask_choice("反应强度", ["长wick反向", "普通", "仅缩量"])
    delta = {"长wick反向": 2, "普通": 0, "仅缩量": -1}[react]
    score += delta
    print(f"     → {react} = {delta:+d} 分")

    if _ask_yn("重合关键位: 与 EMA200 / 整数关口 / 前周期高低点重合?"):
        score += 1
        print("     → +1 分")
    else:
        print("     → 0 分")

    print(f"\n   总分: {score} 分")
    if score >= 6:
        print(f"   ✓ 强 S/R (≥ 6)")
        results.append(("S/R 评分", True, f"{score} 分"))
    else:
        print(f"   ✗ 不达标 (需要 ≥ 6)")
        results.append(("S/R 评分", False, f"{score} 分"))
    print()

    # ── [3/5] R/R ──
    print("─" * 78)
    print(f" [3/5] R/R 比 (方向: {user_dir})")
    print("─" * 78)
    entry = _ask("入场价", parse=float)
    stop = _ask("止损价", parse=float)
    tp = _ask("止盈价", parse=float)

    if is_long and (stop >= entry or tp <= entry):
        print("   ⚠ 做多时止损必须 < 入场, 止盈必须 > 入场")
        results.append(("R/R", False, "价位关系错误"))
    elif not is_long and (stop <= entry or tp >= entry):
        print("   ⚠ 做空时止损必须 > 入场, 止盈必须 < 入场")
        results.append(("R/R", False, "价位关系错误"))
    else:
        sl_dist = abs(entry - stop)
        tp_dist = abs(tp - entry)
        rr = tp_dist / sl_dist if sl_dist > 0 else 0
        sl_pct = sl_dist / entry * 100
        tp_pct = tp_dist / entry * 100
        print(f"   止损距离: {sl_dist:.4f} ({sl_pct:.3f}%)")
        print(f"   止盈距离: {tp_dist:.4f} ({tp_pct:.3f}%)")
        print(f"   R/R: {rr:.2f}")
        if rr >= 2:
            print(f"   ✓ 达 2R 标准")
            results.append(("R/R", True, f"{rr:.2f}"))
        else:
            print(f"   ✗ 不达标 (需要 ≥ 2)")
            results.append(("R/R", False, f"{rr:.2f}"))
    print()

    # ── [4/5] 仓位 (含手续费) ──
    print("─" * 78)
    print(" [4/5] 仓位 (含手续费)")
    print("─" * 78)
    account = _ask("账户 ($)", default=2000, parse=float)
    risk_pct = _ask("风险 %", default=2, parse=float)

    risk_budget = account * risk_pct / 100
    sl_dist = abs(entry - stop) if "entry" in dir() else None

    if sl_dist and sl_dist > 0:
        # 手续费按 0.04% × 2 (开+平 都市价) 估算最坏情况
        est_notional = (risk_budget * entry) / sl_dist
        fee_taker_2x = est_notional * 0.0008  # 0.08%
        actual_for_price = max(risk_budget - fee_taker_2x, 1)
        max_notional = actual_for_price / sl_dist * entry
        max_qty = max_notional / entry

        print(f"   风险预算:        ${risk_budget:.2f}")
        print(f"   止损距离:        {sl_dist:.4f}")
        print()
        print(f"   --- 含手续费场景 (开+平 0.08% 手续费) ---")
        print(f"   预留手续费:      ${fee_taker_2x:.2f}")
        print(f"   实际可承担价差:  ${actual_for_price:.2f}")
        print(f"   最大仓位 (USD):  ${max_notional:.0f}")
        print(f"   最大数量:        {max_qty:.4f}")
        print()
        print(f"   ✓ 仓位计算完成")
        results.append(("仓位计算", True, f"qty {max_qty:.4f}"))
    else:
        print("   ⚠ 跳过 (前一项 R/R 未通过)")
        results.append(("仓位计算", False, "前置项失败"))
    print()

    # ── [5/5] 止损 vs ATR ──
    print("─" * 78)
    print(" [5/5] 止损 vs ATR (≥ 0.7 × 持仓周期 ATR)")
    print("─" * 78)
    print("   速查: 持 30min-2h → 15m ATR / 持 2-8h → 1h ATR / 持 8h+ → 4h ATR")
    hold_tf = _ask_choice("持仓周期", ["15m", "1h", "4h"], default="1h")

    target_row = next((r for r in rows if r["interval"] == hold_tf), None)
    if target_row and target_row.get("atr") and sl_dist:
        atr = target_row["atr"]
        ratio = sl_dist / atr
        print(f"   {hold_tf} ATR(14):  {atr:.4f}")
        print(f"   止损距离:    {sl_dist:.4f}")
        print(f"   ATR 倍数:    {ratio:.2f}x")
        if ratio >= 1.0:
            print(f"   ✓ 安全 (≥ 1.0 × {hold_tf} ATR({atr:.4f}) = {atr:.4f})")
            results.append(("止损 vs ATR", True, f"{ratio:.2f}x"))
        elif ratio >= 0.7:
            print(f"   ✓ 可接受 (0.7-1.0 × {hold_tf} ATR({atr:.4f}) = {atr*0.7:.4f}-{atr:.4f}, 紧但合理)")
            results.append(("止损 vs ATR", True, f"{ratio:.2f}x"))
        else:
            need = atr * 0.7
            print(f"   ✗ 过紧 (< 0.7 × {hold_tf} ATR({atr:.4f}) = {need:.4f})")
            print(f"     建议止损至少放到距离 {need:.4f} 之外")
            results.append(("止损 vs ATR", False, f"{ratio:.2f}x"))
    else:
        print("   ⚠ 数据不足, 跳过")
        results.append(("止损 vs ATR", False, "数据缺失"))
    print()

    # ── 最终判定 ──
    print("=" * 78)
    print(" Checklist 最终判定")
    print("=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for label, ok, note in results:
        mark = "✓" if ok else "✗"
        print(f"   {mark} [{label}]  {note}")
    print()
    print(f" 通过: {passed}/{total}")
    print()
    if passed == total:
        print(" ━━━ ✓ 全部通过 — 可以按计划开仓 ━━━")
        print(" 提醒: 入场后立刻挂止损单和止盈单,然后离开盘面 4 小时不看")
    elif passed >= total - 1:
        print(" ━━━ ⚠ 1 项不达标 — 可酌情评估,但建议修正后再开 ━━━")
    else:
        print(f" ━━━ ✗ {total - passed} 项不达标 — 不建议开仓 ━━━")
        print(" 修正方向:")
        for label, ok, note in results:
            if not ok:
                print(f"   - {label}: {note}")
    print("=" * 78)

