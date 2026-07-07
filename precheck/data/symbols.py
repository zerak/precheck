"""交易对写法归一。"""
import re


def normalize_symbol(raw, exchange="okx"):
    """将多种写法转成交易所永续合约 symbol。"""
    s = raw.upper().replace("/", "-").replace("_", "-")
    if s.endswith("-SWAP"):
        if exchange == "okx":
            return s
        s = s[:-5]

    if "-" in s:
        parts = s.split("-")
        if len(parts) != 2:
            raise SystemExit(f"无法解析交易对: {raw}")
        base, quote = parts
    else:
        # base 允许任意非空字符（含中文等非 ASCII），quote 仍然限定主流计价币
        m = re.match(r"^(.+?)(USDT|USDC|USD|BTC|ETH)$", s)
        if m:
            base, quote = m.group(1), m.group(2)
        else:
            # 没有显式 quote 后缀 → 默认 USDT (例: btc → BTCUSDT, pepe → PEPEUSDT)
            base, quote = s, "USDT"

    if exchange == "binance":
        return f"{base}{quote}"

    return f"{base}-{quote}-SWAP"


def base_ccy(inst_id):
    if "-" in inst_id:
        return inst_id.split("-", 1)[0]
    m = re.match(r"^(.+?)(USDT|USDC|USD|BTC|ETH)$", inst_id)
    return m.group(1) if m else inst_id

