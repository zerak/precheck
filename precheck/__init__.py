"""precheck: 开仓前体检 + 关键位识别 + 交易方案 (分层包)。

向后兼容: re-export 回测脚本/外部调用依赖的公共函数,
使 `from precheck import ...` 与旧单文件版本行为一致。
"""
from .indicators import (
    ema_series, atr_wilder, volume_profile, find_swings, find_close_swings,
)
from .analysis.structure import analyze_structure, compute_ema_deviation
from .analysis.momentum import analyze_volume, detect_momentum_exhaustion
from .analysis.levels import collect_key_levels, flip_levels
from .analysis.openinterest import analyze_oi, interpret_oi
from .analysis.funding import analyze_funding, interpret_funding, annualize_funding
from .analysis.bias_timing import assess_bias_timing
from .plan import (
    collect_entry_candidates, select_entry, suggest_plan,
    hit_probability, rr_verdict,
)
from .data.symbols import normalize_symbol, base_ccy
from .data.client import (
    get_klines, get_oi_now, get_oi_history,
    get_funding_now, get_funding_history,
)
from .config import (
    TRADE_LEVELS, DEFAULT_LEVEL, TIMEFRAMES, KLINE_LIMIT,
    VOL_AVG_WINDOW, VREV_LOOKBACK, FUNDING_HISTORY_LIMIT,
    EMA_DEV_THRESHOLDS, OVER_EXTENDED_ATR, REV_SL_BUFFER, TIMING_LABELS,
)
from .engine import run

__all__ = [
    "ema_series", "atr_wilder", "volume_profile", "find_swings", "find_close_swings",
    "analyze_structure", "compute_ema_deviation",
    "analyze_volume", "detect_momentum_exhaustion",
    "collect_key_levels", "flip_levels",
    "analyze_oi", "interpret_oi",
    "analyze_funding", "interpret_funding", "annualize_funding",
    "assess_bias_timing",
    "collect_entry_candidates", "select_entry", "suggest_plan",
    "hit_probability", "rr_verdict",
    "normalize_symbol", "base_ccy",
    "get_klines", "get_oi_now", "get_oi_history",
    "get_funding_now", "get_funding_history",
    "run",
]
