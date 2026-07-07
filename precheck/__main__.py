#!/usr/bin/env python3
"""
开仓前四维体检 + 自动建议交易方案

数据来源: 默认 Binance USDⓈ-M Futures；可用 --okx 切到 OKX 公开 REST API (无需认证)

用法:
  python -m precheck <SYMBOL>                       # 默认 Binance + 日内级别: 诊断 + 自动方案
  python -m precheck <SYMBOL> --okx                 # 指定 OKX 数据源
  python -m precheck <SYMBOL> --exchange okx        # 同上,完整写法
  python -m precheck <SYMBOL> --account 2000 --risk 2  # 自定义账户/风险
  python -m precheck <SYMBOL> -l 1                  # 交易级别 (见下), --level 或 -l, 也可 -l swing
  python -m precheck <SYMBOL> --check               # 交互式 5 项 checklist (验证你自己的方案)

交易级别 --level / -l (决定关键位/止盈用哪些周期、多远还算数; 持仓时间随数字递增):
  0 / intraday / 日内   持仓几小时~1天   关键位周期 1h+4h    距离按 4h ATR × 6    (默认)
  1 / swing    / 波段   持仓几天~2周     关键位周期 4h+日线  距离按 日线 ATR × 6
  2 / trend    / 趋势   持仓数周以上     关键位周期 日线+周线 距离按 日线 ATR × 10
  说明: 聚类容差 = 各周期自身 ATR × 0.5 (跟数据颗粒度走);
        距离上限 = 锚定周期 ATR × 倍数  (跟你的交易级别走)。无魔数, 全部由级别推导。

支持的输入格式:
  OKX:     ETHUSDT / ETH-USDT-SWAP / ETHUSDC / PUMPUSDT → ETH-USDT-SWAP 等
  Binance: ETHUSDT / ETHUSDC / ETH-USDT-SWAP / ETH/USDT → ETHUSDT 等

默认输出:
  [诊断]  多周期 EMA + ATR / 量价 / OI / Funding
  [5]     大级别压力/支撑位 (4h + 日线摆动点 + 成交密集区)
  [5b]    支撑阻力互换位 (收盘价实体; 前低聚集→上方压力, 前高聚集→下方支撑;
          每带给保守/中庸/激进三档止盈止损)
  [6]     近端动能衰竭
  [方案]  系统基于客观数据自动给出 LONG 和 SHORT 两个方案
          - 入场点 (基于 EMA50 / EMA200 / 1h 摆动高低点)
          - 止损位 (基于 0.7-1.0 × 1h ATR; 反转单用更宽缓冲)
          - 止盈位 (基于 2.5R 或下一个摆动高低点)
          - 仓位数量 (基于风险预算)
          - 标记哪个方向"顺势 / 推荐", 哪个"逆势 / 不推荐"
"""
import sys

from .config import DEFAULT_LEVEL, TRADE_LEVELS
from .data.symbols import normalize_symbol
from .engine import run


def _extract_flag_value(args, name, default):
    """从 args 中拿 --name VALUE,返回 (value, remaining_args)。"""
    out = []
    value = default
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            try:
                value = float(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            out.append(args[i])
            i += 1
    return value, out


def _extract_exchange(args):
    out = []
    exchange = "binance"
    i = 0
    while i < len(args):
        if args[i] == "--binance":
            exchange = "binance"
            i += 1
        elif args[i] == "--okx":
            exchange = "okx"
            i += 1
        elif args[i] == "--exchange" and i + 1 < len(args):
            value = args[i + 1].lower()
            if value not in ("okx", "binance"):
                raise SystemExit("--exchange 只支持 okx 或 binance")
            exchange = value
            i += 2
        else:
            out.append(args[i])
            i += 1
    return exchange, out


def _extract_level(args):
    """解析 --level / -l: 支持数字 0/1/2 或名称 intraday/swing/trend/日内/波段/趋势。"""
    name_map = {
        "0": 0, "intraday": 0, "日内": 0, "scalp": 0,
        "1": 1, "swing": 1, "波段": 1,
        "2": 2, "trend": 2, "position": 2, "趋势": 2,
    }
    out = []
    level = DEFAULT_LEVEL
    i = 0
    while i < len(args):
        if args[i] in ("--level", "-l") and i + 1 < len(args):
            v = args[i + 1].lower()
            if v not in name_map:
                raise SystemExit("--level/-l 只支持 0/1/2 或 intraday/swing/trend (日内/波段/趋势)")
            level = name_map[v]
            i += 2
        else:
            out.append(args[i])
            i += 1
    return level, out


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    args = sys.argv[1:]
    with_check = "--check" in args
    args = [a for a in args if a != "--check"]
    account, args = _extract_flag_value(args, "--account", 2000)
    risk_pct, args = _extract_flag_value(args, "--risk", 2)
    level, args = _extract_level(args)
    exchange, args = _extract_exchange(args)

    if not args:
        print(__doc__)
        sys.exit(1)
    inst_id = normalize_symbol(args[0], exchange=exchange)
    lv = TRADE_LEVELS[level]
    print(f"  交易级别: {level} {lv['name']} (持仓 {lv['hold']}, 关键位周期 {'+'.join(lv['tfs'])})")
    try:
        run(inst_id, exchange=exchange, with_check=with_check, account=account,
            risk_pct=risk_pct, level=level)
    except (KeyboardInterrupt, EOFError):
        print("\n\n  → 已中断,未保存任何状态")
        sys.exit(0)


if __name__ == "__main__":
    main()
