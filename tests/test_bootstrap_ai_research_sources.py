from scripts.bootstrap_ai_research_sources import CURATED_SOURCES, REPLACED_SOURCES


def test_non_productive_html_sources_stay_retired() -> None:
    curated = {(source["kind"], source["base_url"]) for source in CURATED_SOURCES}
    retired = {(source["kind"], source["base_url"]) for source in REPLACED_SOURCES}

    non_productive = {
        ("html_listing", "https://ai.meta.com/blog/"),
        ("html_listing", "https://developers.openai.com/resources"),
        ("html_listing", "https://www.llamaindex.ai/blog"),
    }

    assert curated.isdisjoint(non_productive)
    assert non_productive <= retired
