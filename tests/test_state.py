from tributeflow.models import Entry
from tributeflow.state import diff_entries, load_state, save_state


def make_entry(row=2, name="Bella", **overrides) -> Entry:
    defaults = dict(wall="pets", row_number=row, tribute_name=name, donor_name="Smith")
    defaults.update(overrides)
    return Entry(**defaults)


def test_hash_is_stable():
    assert make_entry().content_hash() == make_entry().content_hash()


def test_hash_changes_when_content_changes():
    assert make_entry().content_hash() != make_entry(message="We miss you").content_hash()


def test_diff_all_new_with_empty_state():
    diff = diff_entries([make_entry(2), make_entry(3, "Max")], {})
    assert len(diff.new) == 2
    assert diff.changed == [] and diff.unchanged == []


def test_diff_detects_changed_and_unchanged():
    unchanged, changed = make_entry(2), make_entry(3, "Max")
    state = {unchanged.key: unchanged.content_hash(), changed.key: "old-hash"}
    diff = diff_entries([unchanged, changed], state)
    assert diff.unchanged == [unchanged]
    assert diff.changed == [changed]
    assert diff.new == []


def test_state_round_trip(tmp_path):
    path = tmp_path / "state" / "published.json"
    entries = [make_entry(2), make_entry(3, "Max")]
    save_state(path, entries)
    state = load_state(path)
    diff = diff_entries(entries, state)
    assert len(diff.unchanged) == 2


def test_missing_state_file_is_empty():
    assert load_state("/nonexistent/state.json") == {}
