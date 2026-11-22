"""一次性探测：在 CI（美国节点）里测哪些线下渠道源/代理可用。

用法: python scripts/probe_urls.py
"""
from __future__ import annotations

import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}

TARGETS = [
    "http://news.winshang.com/list-12.html",
    "https://news.winshang.com/list-12.html",
    "https://www.winshang.com/",
    "http://www.linkshop.com/news/pp/",
    "https://www.linkshop.com/news/pp/",
    "https://www.linkshop.com/",
    "https://www.ebrun.com/retail/",
    "https://www.hzpgc.com/media/",
    "https://www.pinguan.com/media/",
    "http://www.ydzz.com/news.php?col=66",
    "https://www.cbndata.com/",
    "https://www.jiemian.com/",
]

PROXIES = {
    "allorigins": "https://api.allorigins.win/raw?url={}",
    "codetabs": "https://api.codetabs.com/v1/proxy?quest={}",
    "corsproxy": "https://corsproxy.io/?{}",
}


def probe(url: str, timeout: int = 12) -> tuple[str, int]:
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(400_000)
        return str(resp.status), len(body)


def main() -> None:
    print("=== 直连 ===")
    for u in TARGETS:
        try:
            code, size = probe(u)
            print(f"OK   {code} {size:>7}  {u}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {type(exc).__name__}: {str(exc)[:60]}  {u}")

    print("\n=== 代理（针对被墙的两个线下源）===")
    blocked = ["http://news.winshang.com/list-12.html", "http://www.linkshop.com/news/pp/"]
    for name, tpl in PROXIES.items():
        for u in blocked:
            wrapped = tpl.format(urllib.parse.quote(u, safe=""))
            try:
                code, size = probe(wrapped, timeout=20)
                head = "OK  "
                print(f"{head} {name:<10} {code} {size:>7}  {u}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name:<10} {type(exc).__name__}: {str(exc)[:50]}  {u}")


if __name__ == "__main__":
    main()
