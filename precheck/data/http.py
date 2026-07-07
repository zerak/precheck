"""HTTP 拉取 + SSL 处理 (公开只读数据)。"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

OKX_BASE = "https://www.okx.com"
BINANCE_BASE = "https://fapi.binance.com"
TIMEOUT = 10

# macOS 常见 SSL 证书问题 fallback. 仅用于公开只读数据.
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "precheck/1.0"})
    last_err = None
    for ctx in (_SSL_CTX, ssl._create_unverified_context()):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise SystemExit(f"HTTP {e.code} from {url}\n{body}")
        except urllib.error.URLError as e:
            last_err = e
            # SSL 错误才重试,其他直接 raise
            if "SSL" not in str(e.reason):
                raise SystemExit(f"网络错误: {e.reason} ({url})")
    raise SystemExit(f"网络错误: {last_err.reason if last_err else '未知'} ({url})")


def _build_url(base, path, params):
    # urlencode 处理非 ASCII（中文 base 等）和特殊字符的转义
    filtered = {k: v for k, v in params.items() if v is not None}
    if filtered:
        return f"{base}{path}?{urllib.parse.urlencode(filtered)}"
    return f"{base}{path}"


def okx_get(path, **params):
    url = _build_url(OKX_BASE, path, params)
    res = fetch(url)
    if str(res.get("code")) != "0":
        raise SystemExit(f"OKX 错误 {res.get('code')}: {res.get('msg')} ({url})")
    return res.get("data", [])


def binance_get(path, **params):
    url = _build_url(BINANCE_BASE, path, params)
    res = fetch(url)
    if isinstance(res, dict) and res.get("code") not in (None, 0, "0"):
        raise SystemExit(f"Binance 错误 {res.get('code')}: {res.get('msg')} ({url})")
    return res

