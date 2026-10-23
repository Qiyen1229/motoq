import ssl
import urllib.request

_ctx = ssl.create_default_context()
# Python 3.13 起預設啟用 X.509 嚴格模式，會拒絕部分臺灣政府網站憑證鏈中缺少 Subject Key Identifier 的
# 根憑證（curl／瀏覽器皆可正常連線）。仍保留完整的憑證鏈與主機名稱驗證，只放寬這項嚴格檢查。
_ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT


def open_url(req: urllib.request.Request, timeout: int = 10):
    return urllib.request.urlopen(req, timeout=timeout, context=_ctx)  # noqa: S310 呼叫端只傳固定的 https 位址
