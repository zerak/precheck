"""行情/OI/资金费率数据获取 (交易所适配)。"""
from ..config import KLINE_LIMIT, FUNDING_HISTORY_LIMIT
from .http import okx_get, binance_get


def get_klines(inst_id, bar, limit=KLINE_LIMIT, exchange="okx"):
    """返回旧→新的 K 线列表。"""
    if exchange == "binance":
        rows = binance_get(
            "/fapi/v1/klines",
            symbol=inst_id,
            interval=bar,
            limit=limit,
        )
        out = []
        for r in rows:
            # [open_time, open, high, low, close, volume, close_time, quote_asset_volume, ...]
            out.append({
                "ts": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            })
        return out

    rows = okx_get(
        "/api/v5/market/candles", instId=inst_id, bar=bar, limit=limit
    )
    rows = list(reversed(rows))
    out = []
    for r in rows:
        # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        out.append({
            "ts": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[6]),  # 用基础币种数量更稳(volCcy)
        })
    return out


def get_oi_now(inst_id, exchange="okx"):
    if exchange == "binance":
        r = binance_get("/fapi/v1/openInterest", symbol=inst_id)
        price = binance_mark_price(inst_id)
        oi_ccy = float(r.get("openInterest") or 0)
        return {
            "oi_ccy": oi_ccy,
            "oi_usd": oi_ccy * price,
        }

    rows = okx_get(
        "/api/v5/public/open-interest", instType="SWAP", instId=inst_id
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "oi_ccy": float(r.get("oiCcy") or 0),
        "oi_usd": float(r.get("oiUsd") or 0),
    }


def binance_mark_price(symbol):
    r = binance_get("/fapi/v1/premiumIndex", symbol=symbol)
    return float(r.get("markPrice") or r.get("indexPrice") or 0)


def get_oi_history(inst_id, period="1H", limit=24, exchange="okx"):
    """返回旧→新的 OI 历史 (USD 计价)。"""
    if exchange == "binance":
        rows = binance_get(
            "/futures/data/openInterestHist",
            symbol=inst_id,
            period=period,
            limit=limit,
        )
        return [
            {
                "ts": int(r["timestamp"]),
                "oi_usd": float(r.get("sumOpenInterestValue") or 0),
                "vol_usd": 0,
            }
            for r in rows
        ]

    rows = okx_get(
        "/api/v5/rubik/stat/contracts/open-interest-volume",
        ccy=inst_id,
        period=period,
    )
    rows = list(reversed(rows))[-limit:]
    return [
        {"ts": int(r[0]), "oi_usd": float(r[1]), "vol_usd": float(r[2])}
        for r in rows
    ]


def get_funding_now(inst_id, exchange="okx"):
    if exchange == "binance":
        r = binance_get("/fapi/v1/premiumIndex", symbol=inst_id)
        return {
            "funding_rate": float(r.get("lastFundingRate") or 0),
            "next_funding_time": int(r.get("nextFundingTime") or 0),
        }

    rows = okx_get("/api/v5/public/funding-rate", instId=inst_id)
    if not rows:
        return None
    r = rows[0]
    return {
        "funding_rate": float(r.get("fundingRate") or 0),
        "next_funding_time": int(r.get("fundingTime") or 0),
    }


def get_funding_history(inst_id, limit=FUNDING_HISTORY_LIMIT, exchange="okx"):
    if exchange == "binance":
        rows = binance_get(
            "/fapi/v1/fundingRate",
            symbol=inst_id,
            limit=limit,
        )
        return [float(r.get("fundingRate") or 0) for r in rows]

    rows = okx_get(
        "/api/v5/public/funding-rate-history", instId=inst_id, limit=limit
    )
    return [float(r.get("realizedRate") or r.get("fundingRate") or 0) for r in rows]

