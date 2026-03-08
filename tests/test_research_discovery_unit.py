from __future__ import annotations

from app.research.discovery import discover_from_feed, discover_from_sitemap


def test_discover_from_feed_extracts_summary_and_title() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <guid>a1</guid>
      <title>Release Note</title>
      <link>https://example.com/post-1</link>
      <description><![CDATA[<p>New model release with faster latency.</p>]]></description>
    </item>
  </channel>
</rss>
"""
    items = discover_from_feed(raw, base_url="https://example.com/feed.xml", max_items=10)
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/post-1"
    assert items[0]["external_id"] == "a1"
    assert items[0]["title"] == "Release Note"
    assert "faster latency" in items[0]["summary"]


def test_discover_from_sitemap_supports_sitemapindex() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-news.xml</loc></sitemap>
</sitemapindex>
"""
    items = discover_from_sitemap(raw, base_url="https://example.com/sitemap.xml", max_items=10)
    urls = [item["url"] for item in items]
    assert "https://example.com/sitemap-blog.xml" in urls
    assert "https://example.com/sitemap-news.xml" in urls
