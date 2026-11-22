"""回归测试（标准库 unittest，不需要 pytest）。

跑法: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect  # noqa: E402
import render  # noqa: E402
import score  # noqa: E402
from common import load_lexicon, load_profile  # noqa: E402

SRC = {"name": "测试源", "tier": "trade", "section": "product", "type": "x"}


class TestParsers(unittest.TestCase):
    def test_pinguan(self):
        html = ('<div class="cov-card" data-v-1><a href="/media/23125/" class="thumb"></a>'
                '<div class="body"><a href="/media/23125/"><h4>水杨酸面霜研发实验室探访</h4></a>'
                '<div class="meta"><span>2026-11-20</span><span class="dot">·</span><span>品牌</span></div>'
                '</div></div>')
        items = collect.parse_pinguan(SRC, html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published"], "2026-11-20")
        self.assertEqual(items[0]["tag"], "品牌")
        self.assertTrue(items[0]["url"].startswith("https://www.pinguan.com/media/"))

    def test_winshang(self):
        html = ('<div class="win-new-img"><span class="tag">开关店</span>'
                '<a href="http://news.winshang.com/html/074/2859.html"></a></div>'
                '<div class="win-new-txt"><h3><a href="http://news.winshang.com/html/074/2859.html">'
                '9700家门店大洗牌</a></h3><p class="win-new-info">开关店比1.10。</p>'
                '<p class="win-new-tab"><span>2026年10月28日</span></p></div>')
        items = collect.parse_winshang(SRC, html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["tag"], "开关店")
        self.assertEqual(items[0]["published"], "2026-10-28")

    def test_linkshop_absolute_url(self):
        html = ('<h2>\n<a href="http://www.linkshop.com/news/2026554169.shtml">'
                '珀莱雅收购花知晓</a>\n</h2>'
                '<p class="text_overflow">美妆并购潮。</p>'
                '<div class="labels"><span class="time">2026-11-19 23:19</span></div>')
        items = collect.parse_linkshop(SRC, html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published"], "2026-11-19")

    def test_rss_with_broken_entity(self):
        xml = ('<rss version="2.0"><channel><item><title>Beauty launch &nbsp; news</title>'
               '<link>https://example.com/a</link><pubDate>Sat, 21 Nov 2026 10:00:00 +0800</pubDate>'
               '</item></channel></rss>')
        items = collect.parse_rss(SRC, xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published"], "2026-11-21")

    def test_rss_bad_xml(self):
        self.assertEqual(collect.parse_rss(SRC, "<html>not xml"), [])


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.lex = load_lexicon()

    def _item(self, title, summary="", source="品观网", tier="trade", section="product"):
        return {"id": "x", "title": title, "summary": summary, "url": "https://e.com/1",
                "published": "2026-11-22", "source": source, "tier": tier,
                "section_hint": section, "tag": "", "type": "x"}

    def test_generic_retail_dropped(self):
        it = self._item("沃尔玛第三财季营收1888亿美元", source="联商网-品牌", tier="channel",
                        section="channel")
        blob = it["title"] + it["summary"]
        self.assertTrue(score.is_noise(it, self.profile, self.lex, blob))

    def test_beauty_retail_kept(self):
        it = self._item("美妆集合店话梅在成都开新店", source="联商网-品牌", tier="channel",
                        section="channel")
        blob = it["title"] + it["summary"]
        self.assertFalse(score.is_noise(it, self.profile, self.lex, blob))

    def test_bureaucratic_reg_news_dropped(self):
        it = self._item("某市药监局举办化妆品监管培训会", source="中国食品药品网-化妆品",
                        tier="reg", section="device")
        blob = it["title"] + it["summary"]
        self.assertTrue(score.is_noise(it, self.profile, self.lex, blob))

    def test_regulatory_goes_to_device(self):
        it = self._item("国家药监局通告32批次化妆品不合格")
        s = score.score_item(it, self.profile, self.lex)
        self.assertEqual(s["section"], "device")

    def test_generic_standard_not_regulatory(self):
        # "流程和标准"不是监管新闻，不能判进械字号与监管
        it = self._item("四千多项流程和标准：揭秘水羊工艺创新实验室的工艺科学体系")
        s = score.score_item(it, self.profile, self.lex)
        self.assertNotEqual(s["section"], "device")
        # 真监管新闻仍然进
        it2 = self._item("化妆品7项检验新标准发布，微生物检测体系重写")
        self.assertEqual(score.score_item(it2, self.profile, self.lex)["section"], "device")

    def test_title_fp_ignores_punctuation(self):
        from common import title_fp
        self.assertEqual(title_fp("山姆中国今年已新开10家门店，追平年度开店纪录"),
                         title_fp("山姆中国今年已新开10家门店 追平年度开店纪录！"))
        self.assertNotEqual(title_fp("山姆新开10家门店"), title_fp("珀莱雅收购花知晓"))

    def test_detail_link_uses_web_base(self):
        profile = load_profile()
        profile["delivery"]["web_base"] = "https://x.github.io/repo"
        href = render.detail_href({"url": "https://e.com/1"}, 3, "2026-11-22",
                                  profile["delivery"]["web_base"])
        self.assertEqual(href, "https://x.github.io/repo/2026-11-22/p3.html")
        href2 = render.detail_href({"url": "https://e.com/1"}, 3, "2026-11-22", "")
        self.assertEqual(href2, "https://e.com/1")

    def test_brand_match_false_positive(self):
        # "截至本公告日" 里含"至本"，不能算命中品牌
        self.assertFalse(score.brand_in("截至本公告日，公司完成发放", "至本"))
        self.assertTrue(score.brand_in("至本推出新面霜", "至本"))


class TestRender(unittest.TestCase):
    def test_email_contains_sections_and_escapes(self):
        brief = {
            "date": "2026-11-22", "title": "美妆情报",
            "scope": {"category": "大众护肤", "one_liner": "测试"},
            "today3": [{"headline": "测试 <script>", "why": "为什么"}],
            "close": "小结",
            "items": [{"id": "1", "section": "product", "section_label": "竞品动作",
                       "title": "标题 & 符号", "url": "https://e.com/1",
                       "so_what": "意味着什么", "source": "品观网", "published": "2026-11-22",
                       "brand": "", "price": "", "channel": ""}],
            "stats": {"candidates": 10},
        }
        html = render.render_email(brief, load_profile())
        self.assertIn("竞品动作", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("意味着什么", html)


if __name__ == "__main__":
    unittest.main()
