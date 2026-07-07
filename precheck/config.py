"""precheck 全局常量与交易级别配置。"""

TIMEFRAMES = [
    ("15m", {"okx": "15m", "binance": "15m"}),
    ("1h", {"okx": "1H", "binance": "1h"}),
    ("4h", {"okx": "4H", "binance": "4h"}),
]
KLINE_LIMIT = 300  # 足够算 EMA200
VOL_AVG_WINDOW = 20
VREV_LOOKBACK = 60
FUNDING_HISTORY_LIMIT = 8

# ─── 交易级别 (决定关键位/止盈用哪些周期、多远还算数) ───
# 设计原则 (消除魔数):
#   - 聚类容差 = 该数据周期 ATR × 0.5      → 跟"数据颗粒度"走, 固定
#   - 距离上限 = 目标周期 ATR × dist_mult  → 跟"你的交易级别"走, 由 level 决定
# 持仓时间递增: 0 日内 < 1 波段 < 2 趋势
TRADE_LEVELS = {
    0: {
        "name": "日内",
        "tfs": ["1h", "4h"],       # 关键位来源周期
        "anchor_tf": "4h",          # 距离/容差的 ATR 锚定周期
        "dist_mult": 6.0,           # 距离上限 = 4h ATR × 6
        "hold": "几小时~1天",
        "bars": {"okx": {"1h": "1H", "4h": "4H"}, "binance": {"1h": "1h", "4h": "4h"}},
    },
    1: {
        "name": "波段",
        "tfs": ["4h", "1d"],
        "anchor_tf": "1d",          # 距离上限 = 日线 ATR × 6
        "dist_mult": 6.0,
        "hold": "几天~2周",
        "bars": {"okx": {"4h": "4H", "1d": "1D"}, "binance": {"4h": "4h", "1d": "1d"}},
    },
    2: {
        "name": "趋势",
        "tfs": ["1d", "1w"],
        "anchor_tf": "1d",          # 距离上限 = 日线 ATR × 10
        "dist_mult": 10.0,
        "hold": "数周以上",
        "bars": {"okx": {"1d": "1D", "1w": "1W"}, "binance": {"1d": "1d", "1w": "1w"}},
    },
}
DEFAULT_LEVEL = 0  # 默认日内


EMA_DEV_THRESHOLDS = {
    "EMA50":  (1.0, 2.0),   # ≤1: 正常; 1-2: 偏离; >2: 显著偏离
    "EMA200": (2.5, 5.0),
}
# 过度延伸判定阈值 (反转条件之一): 1h 距 EMA200 超过此 ATR 倍数视为过热
OVER_EXTENDED_ATR = 4.0

# 反转单止损缓冲 (ATR 倍数): 0.8 为验证最优 (避免被趋势"最后一冲"扫损)
# 顺势单保持 0.3 不变
REV_SL_BUFFER = 0.8


TIMING_LABELS = {
    "chase": "✓ 可顺势入场",
    "pullback": "⚠ 等回踩 (别追)",
    "wait": "⚠ 观望 (等共振)",
    "reversal_warning": "⛔ 反转预警",
}

