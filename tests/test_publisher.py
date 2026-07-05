import json

from tributeflow.models import Entry
from tributeflow.publisher import build_wall_payloads


def test_payloads_split_by_wall_and_sorted():
    entries = [
        Entry("people", 4, "John Doe", "Jane Doe"),
        Entry("pets", 9, "Max", "Lee"),
        Entry("pets", 2, "Bella", "Smith", message="Forever loved"),
    ]
    payloads = build_wall_payloads(entries, ["pets", "people"])

    pets = json.loads(payloads["pets.json"])
    assert [p["tribute_name"] for p in pets] == ["Bella", "Max"]  # sorted by row
    people = json.loads(payloads["people.json"])
    assert people == [{"tribute_name": "John Doe", "donor_name": "Jane Doe"}]


def test_empty_optional_fields_omitted_from_public_data():
    payloads = build_wall_payloads([Entry("pets", 2, "Bella", "Smith")], ["pets"])
    (record,) = json.loads(payloads["pets.json"])
    assert "image_url" not in record and "message" not in record


def test_payload_is_deterministic():
    entries = [Entry("pets", 2, "Bella", "Smith")]
    assert build_wall_payloads(entries, ["pets"]) == build_wall_payloads(entries, ["pets"])
