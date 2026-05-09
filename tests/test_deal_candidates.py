from pathlib import Path

_SQL_DIR = Path(__file__).parent.parent / "sql" / "views"


def _read_view(filename: str) -> str:
    return (_SQL_DIR / filename).read_text()


# --- deal_candidates: threshold enforcement ---

def test_deal_candidates_enforces_100_minimum():
    sql = _read_view("deal_candidates.sql")
    assert "current_price >= 100" in sql


def test_deal_candidates_enforces_active_filter():
    sql = _read_view("deal_candidates.sql")
    assert "p.active = TRUE" in sql


def test_deal_candidates_enforces_availability_filter():
    sql = _read_view("deal_candidates.sql")
    assert "cp.availability = TRUE" in sql


def test_deal_candidates_enforces_price_drop_condition():
    sql = _read_view("deal_candidates.sql")
    assert "m.max_price_30d > cp.current_price" in sql


def test_deal_candidates_enforces_25_minimum_drop():
    sql = _read_view("deal_candidates.sql")
    assert "(m.max_price_30d - cp.current_price) >= 25" in sql


# --- deal_candidates: category coverage ---

def test_deal_candidates_has_no_hardcoded_category_filter():
    # The view must serve all four categories — no hardcoded WHERE category = '...'
    sql = _read_view("deal_candidates.sql").lower()
    for cat in ("headphones", "earbuds", "speakers", "soundbars"):
        assert f"= '{cat}'" not in sql, (
            f"deal_candidates.sql contains a hardcoded category filter for '{cat}'"
        )


def test_deal_candidates_exposes_category_column():
    # Downstream consumers (e.g. frontend per-category deal pages) rely on p.category.
    sql = _read_view("deal_candidates.sql")
    assert "p.category" in sql


# --- downstream views: no category filtering ---

def test_topdeals_views_are_category_agnostic():
    for view_file in ("dealpage_topdeals.sql", "homepage_topdeals.sql"):
        sql = _read_view(view_file).lower()
        for cat in ("headphones", "earbuds", "speakers", "soundbars"):
            assert f"= '{cat}'" not in sql, (
                f"{view_file} contains a hardcoded category filter for '{cat}'"
            )
