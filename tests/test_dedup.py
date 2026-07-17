"""Deterministic dedup: consolidate only same-honoree + same-donor rows."""

from tributeflow.dedup import find_duplicates
from tributeflow.models import Entry


def entry(wall="people", row=2, name="Robert Finelsen", donor="Libbi Finelsen", **kw):
    return Entry(wall=wall, row_number=row, tribute_name=name, donor_name=donor,
                 tribute_type="In memory of", **kw)


def test_exact_duplicate_keeps_first_row():
    notices, keys = find_duplicates([entry(row=2), entry(row=5), entry(row=9)])
    assert keys == {"people:5", "people:9"}
    assert len(notices) == 2
    assert all("row 2" in n.problem for n in notices)
    assert all(n.source == "dedup" for n in notices)


def test_match_ignores_case_and_whitespace():
    notices, keys = find_duplicates([
        entry(row=2, name="Robert Finelsen", donor="Libbi Finelsen"),
        entry(row=3, name="  robert   FINELSEN ", donor="LIBBI FINELSEN"),
    ])
    assert keys == {"people:3"}


def test_same_honoree_different_donor_is_not_a_duplicate():
    notices, keys = find_duplicates([
        entry(row=2, donor="Libbi Finelsen"),
        entry(row=3, donor="The Hess Family"),
    ])
    assert keys == set()
    assert notices == []


def test_same_donor_different_honoree_is_not_a_duplicate():
    notices, keys = find_duplicates([
        entry(row=2, name="Bella"),
        entry(row=3, name="Whiskers"),
    ])
    assert keys == set()


def test_same_names_on_different_walls_are_not_duplicates():
    notices, keys = find_duplicates([
        entry(wall="pets", row=2, name="Charlie", donor="The Smiths"),
        entry(wall="people", row=2, name="Charlie", donor="The Smiths"),
    ])
    assert keys == set()


def test_blank_names_are_never_consolidated():
    notices, keys = find_duplicates([
        entry(row=2, name="", donor="Libbi Finelsen"),
        entry(row=3, name="", donor="Libbi Finelsen"),
        entry(row=4, name="Robert Finelsen", donor=""),
        entry(row=5, name="Robert Finelsen", donor=""),
    ])
    assert keys == set()
    assert notices == []


def test_differing_image_or_type_still_consolidates():
    # The client's rule is honoree + donor only — other fields don't matter.
    notices, keys = find_duplicates([
        entry(row=2, image_url="https://example.com/a.jpg"),
        entry(row=3, image_url=""),
    ])
    assert keys == {"people:3"}
