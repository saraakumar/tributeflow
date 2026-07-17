from tributeflow.config import Config, EmailConfig, WallConfig
from tributeflow.models import Entry
from tributeflow.publisher import build_wall_payloads


def make_config() -> Config:
    return Config(
        sheet_id="test",
        walls={
            "pets": WallConfig(
                tab="Pet",
                csv_header="In Honor/Memory Of:,Tribute Name,Donor Name,Image URL",
            ),
            "people": WallConfig(
                tab="People",
                csv_header="In Honor or Memory Of:,Tribute Name,Donor Name,Image URL",
            ),
        },
        columns={},
        email=EmailConfig(),
    )


def test_payloads_split_by_wall_and_sorted():
    entries = [
        Entry("people", 4, "John Doe", "Jane Doe", tribute_type="In memory of"),
        Entry("pets", 9, "Max", "Lee", tribute_type="In honor of"),
        Entry("pets", 2, "Bella", "Smith", tribute_type="In memory of"),
    ]
    payloads = build_wall_payloads(entries, make_config())

    pets = payloads["pets"].splitlines()
    assert pets[0] == "In Honor/Memory Of:,Tribute Name,Donor Name,Image URL"
    assert pets[1] == "In memory of,Bella,Smith,"  # sorted by row
    assert pets[2] == "In honor of,Max,Lee,"

    people = payloads["people"].splitlines()
    assert people[0] == "In Honor or Memory Of:,Tribute Name,Donor Name,Image URL"
    assert people[1] == "In memory of,John Doe,Jane Doe,"


def test_commas_in_fields_become_semicolons():
    # The site's app.js splits rows on "," with no quoting and renders ";" as
    # ", " — sanitization must keep the row intact and the display identical.
    entries = [
        Entry("pets", 2, "Fluffy, our beloved cat", "The Woods, Falls and Lee families",
              tribute_type="In memory of"),
    ]
    payloads = build_wall_payloads(entries, make_config())
    row = payloads["pets"].splitlines()[1]
    assert row == "In memory of,Fluffy; our beloved cat,The Woods; Falls and Lee families,"
    assert row.count(",") == 3  # still exactly 4 columns


def test_payload_is_deterministic():
    entries = [Entry("pets", 2, "Bella", "Smith", tribute_type="In memory of")]
    cfg = make_config()
    assert build_wall_payloads(entries, cfg) == build_wall_payloads(entries, cfg)
