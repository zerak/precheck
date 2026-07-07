"""数字格式化 (零依赖)。"""


def fmt_price(p):
    if p is None:
        return "-"
    if p >= 1:
        return f"{p:,.4f}"
    if p >= 0.01:
        return f"{p:.5f}"
    return f"{p:.7f}"


def fmt_pct(p):
    if p is None:
        return "-"
    sign = "+" if p > 0 else ""
    return f"{sign}{p:.2f}%"


def fmt_num(n):
    if n is None:
        return "-"
    a = abs(n)
    if a >= 1e9:
        return f"{n/1e9:.2f}B"
    if a >= 1e6:
        return f"{n/1e6:.2f}M"
    if a >= 1e3:
        return f"{n/1e3:.2f}K"
    return f"{n:.2f}"

