from tributeflow.sheets import rows_to_entries

COLUMNS = {
    "tribute_name": "Tribute Name",
    "donor_name": "Donor Name",
    "message": "Message",
    "image_url": "Image URL",
}


def test_rows_parsed_with_header_mapping():
    values = [
        ["Tribute Name", "Donor Name", "Message", "Image URL"],
        ["Bella", "Smith Family", "Forever loved", ""],
        ["Max", "Lee", "", "https://example.com/max.jpg"],
    ]
    entries = rows_to_entries("pets", values, COLUMNS)
    assert len(entries) == 2
    assert entries[0].row_number == 2  # header is row 1
    assert entries[0].tribute_name == "Bella"
    assert entries[1].image_url == "https://example.com/max.jpg"


def test_blank_rows_skipped():
    values = [
        ["Tribute Name", "Donor Name"],
        ["", ""],
        ["Bella", "Smith"],
    ]
    entries = rows_to_entries("pets", values, COLUMNS)
    assert len(entries) == 1
    assert entries[0].row_number == 3  # row numbering preserved past blanks


def test_short_rows_and_missing_columns_tolerated():
    # Sheet API omits trailing empty cells; optional columns may not exist at all.
    values = [["Tribute Name", "Donor Name"], ["Bella"]]
    entries = rows_to_entries("pets", values, COLUMNS)
    assert entries[0].donor_name == ""
    assert entries[0].image_url == ""


def test_whitespace_stripped():
    values = [["Tribute Name", "Donor Name"], ["  Bella ", " Smith "]]
    (entry,) = rows_to_entries("pets", values, COLUMNS)
    assert entry.tribute_name == "Bella"
    assert entry.donor_name == "Smith"
