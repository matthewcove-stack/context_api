from __future__ import annotations

from app.research.discovery import discover_from_feed, discover_from_html_listing, discover_from_sitemap


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


def test_discover_from_feed_uses_permalink_guid_when_link_is_missing() -> None:
    raw = """<rss><channel><item>
  <guid isPermaLink="true">https://example.com/post-from-guid</guid>
  <title>Post from GUID</title>
  <description>Useful details.</description>
</item></channel></rss>"""

    items = discover_from_feed(raw, base_url="https://example.com/feed.xml", max_items=10)

    assert items == [
        {
            "url": "https://example.com/post-from-guid",
            "external_id": "https://example.com/post-from-guid",
            "title": "Post from GUID",
            "summary": "Useful details.",
            "published_at": "",
        }
    ]


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


def test_html_listing_prioritizes_article_links_over_navigation() -> None:
    raw = """
    <nav><a href="/pricing">Pricing</a><a href="/docs">Docs</a></nav>
    <article><h2><a href="/blog/useful-agent-evals">How to build useful agent evaluations</a></h2></article>
    <a href="/">Home</a>
    """

    items = discover_from_html_listing(raw, base_url="https://example.com/blog", max_items=2)

    assert items[0]["url"] == "https://example.com/blog/useful-agent-evals"
    assert items[0]["title"] == "How to build useful agent evaluations"
    assert all(item["url"] != "https://example.com/" for item in items)
