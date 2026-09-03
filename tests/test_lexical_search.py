from app.retrieval.lexical_search import BM25Index, reciprocal_rank_fusion


def test_bm25_ranks_the_matching_document_first():
    index = BM25Index(
        chunk_ids=["a", "b", "c"],
        texts=[
            "Additional users are billed per month per user.",
            "The Atlas Professional subscription plan costs SAR 5,200 per month.",
            "Travel booking rules require line manager approval.",
        ],
    )
    results = index.search("current price of the Atlas Professional plan", top_k=3)
    assert results[0][0] == "b"


def test_bm25_returns_empty_when_no_query_terms_match():
    index = BM25Index(chunk_ids=["a"], texts=["Completely unrelated content about travel."])
    results = index.search("zzzznonexistentterm", top_k=5)
    assert results == []


def test_bm25_handles_empty_index():
    index = BM25Index(chunk_ids=[], texts=[])
    assert index.search("anything", top_k=5) == []


def test_reciprocal_rank_fusion_favours_items_ranked_high_in_both_lists():
    fused = reciprocal_rank_fusion([
        ["x", "y", "z"],
        ["y", "x", "z"],
    ])
    assert fused[0] in ("x", "y")
    assert fused[-1] == "z"


def test_reciprocal_rank_fusion_boosts_an_item_agreed_on_by_both_rankings():
    # "b" is #2 in the first ranking and #1 in the second - agreement across
    # both signals should let it outrank "a", which only appears in one.
    fused = reciprocal_rank_fusion([
        ["a", "b"],
        ["b"],
    ])
    assert fused[0] == "b"
