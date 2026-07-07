"""MarketContext: 贯穿 precheck 全流程的市场快照 + 运行参数。

engine 逐步填满它, 分析/展示函数只读它, 不再一个个传散参数。
纯工具函数(indicators/formatting/levels 算法/hit_probability 等)不依赖 ctx,
保持可独立复用与测试。
"""
from dataclasses import dataclass, field


@dataclass
class MarketContext:
    # ── 运行参数 ──
    inst_id: str = ""
    exchange: str = "okx"
    level: int = 1
    account: float = 10000
    risk_pct: float = 1
    with_check: bool = False

    # ── 多周期基础数据 ──
    klines_by_tf: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)      # 各周期 EMA/ATR 行
    direction_1h: str = None                       # "up"/"down"
    row_1h: dict = None
    current: float = None
    atr_1h: float = None

    # ── 量价 / OI / 资金费率 ──
    vol: dict = None
    oi: dict = None
    oi_meaning: str = ""
    funding: dict = None
    funding_meaning: str = ""

    # ── 关键位 / 动能 / 延伸度 ──
    vp: dict = None
    key_levels: list = field(default_factory=list)
    flip: dict = None
    momentum: dict = None
    ema_dev: dict = None

    # ── 判定结果 ──
    assessment: dict = None
