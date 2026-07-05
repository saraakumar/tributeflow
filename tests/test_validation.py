from tributeflow.models import Entry
from tributeflow.validation import drive_file_id, normalize_image_url, validate_entry


def make_entry(**overrides) -> Entry:
    defaults = dict(
        wall="pets", row_number=5, tribute_name="Bella", donor_name="The Smith Family"
    )
    defaults.update(overrides)
    return Entry(**defaults)


def url_ok(_url):
    return True


def url_broken(_url):
    return False


def test_valid_entry_without_image_passes():
    # Most CASPCA entries have no image — that must NOT be an error.
    assert validate_entry(make_entry(), url_checker=url_ok) == []


def test_missing_tribute_name_flagged():
    issues = validate_entry(make_entry(tribute_name=""), url_checker=url_ok)
    assert len(issues) == 1
    assert "tribute name" in issues[0].problem


def test_missing_donor_name_flagged():
    issues = validate_entry(make_entry(donor_name=""), url_checker=url_ok)
    assert len(issues) == 1
    assert "donor name" in issues[0].problem


def test_working_image_url_passes():
    entry = make_entry(image_url="https://example.com/photo.jpg")
    assert validate_entry(entry, url_checker=url_ok) == []


def test_broken_image_url_flagged():
    entry = make_entry(image_url="https://example.com/gone.jpg")
    issues = validate_entry(entry, url_checker=url_broken)
    assert len(issues) == 1
    assert "broken" in issues[0].problem


def test_non_url_image_flagged():
    issues = validate_entry(make_entry(image_url="photo.jpg"), url_checker=url_ok)
    assert len(issues) == 1
    assert "doesn't look like a URL" in issues[0].problem


def test_drive_file_id_extraction_variants():
    fid = "1AbC-xyz_123"
    assert drive_file_id(f"https://drive.google.com/file/d/{fid}/view?usp=sharing") == fid
    assert drive_file_id(f"https://drive.google.com/open?id={fid}") == fid
    assert drive_file_id(f"https://drive.google.com/uc?export=view&id={fid}") == fid
    assert drive_file_id("https://example.com/photo.jpg") is None


def test_drive_share_link_normalized_to_thumbnail():
    url = "https://drive.google.com/file/d/1AbC-xyz_123/view?usp=sharing"
    assert normalize_image_url(url) == "https://drive.google.com/thumbnail?id=1AbC-xyz_123&sz=w400"


def test_existing_thumbnail_link_untouched():
    url = "https://drive.google.com/thumbnail?id=1AbC&sz=w400"
    assert normalize_image_url(url) == url


def test_validation_normalizes_drive_link_in_place():
    entry = make_entry(image_url="https://drive.google.com/file/d/1AbC/view")
    validate_entry(entry, url_checker=url_ok)
    assert entry.image_url.startswith("https://drive.google.com/thumbnail?id=1AbC")
