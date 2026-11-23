"""extract_name end to end with saved (synthetic) DetectText responses. Rekognition is stubbed; AWS is never called."""
import logging

import pytest
from conftest import jpeg_bytes, make_settings

from ezina_id_verify import UnsupportedDocType, extract_name
from ezina_id_verify.config import set_settings


async def read(aws, doc_type: str, fixture, **settings):
    if settings:
        set_settings(make_settings(**settings))
    aws.detect_text(fixture)
    result = await extract_name(doc_type, jpeg_bytes())
    aws.done()
    return result


# ---------------------------------------------------------------------------------------------- MRZ
async def test_passport_mrz_gives_surname_and_given_names_separately(aws):
    r = await read(aws, "passport", "passport_ind_mrz")
    assert r.found and r.method == "mrz" and r.confidence == 0.95 and r.warnings == []
    assert (r.given_names, r.surname, r.full_name) == ("CHITTA RANJAN", "BEHERA", "CHITTA RANJAN BEHERA")
    assert r.name == r.full_name and r.doc_type == "passport"


@pytest.mark.parametrize("fixture,full", [
    ("passport_deu_mrz", "ERIKA MUSTERMANN"),
    ("passport_pd_mrz", "ANITA SHARMA KUMAR"),
    ("passport_po_mrz", "ANNA MARIA ERIKSSON"),
    ("passport_no_surname_mrz", "ERIKA"),
])
async def test_passport_mrz_variants(aws, fixture, full):
    r = await read(aws, "passport", fixture)
    assert r.found and r.method == "mrz" and r.full_name == full


async def test_empty_mrz_surname_returns_only_given_names(aws):
    r = await read(aws, "passport", "passport_no_surname_mrz")
    assert r.surname is None and r.given_names == "ERIKA"


async def test_td1_id_card_mrz_name_is_on_line_3(aws):
    r = await read(aws, "generic_id", "id_td1_mrz")
    assert r.method == "mrz" and (r.given_names, r.surname) == ("ANNA MARIA", "ERIKSSON")


async def test_passport_without_a_readable_mrz_falls_back_to_the_printed_labels(aws):
    r = await read(aws, "passport", "passport_labels_only")
    assert r.method == "label" and r.confidence == 0.85
    assert (r.given_names, r.surname, r.full_name) == ("ARJUN VIKRAM", "NAIR", "ARJUN VIKRAM NAIR")


async def test_a_low_ocr_confidence_lowers_a_label_result(aws):
    r = await read(aws, "passport", "low_ocr_label")
    assert r.found and r.method == "label" and r.confidence == 0.75


# ---------------------------------------------------------------------------------------------- India
async def test_aadhaar_name_above_the_dob_line_skipping_hindi_and_relative_lines(aws):
    r = await read(aws, "aadhaar", "aadhaar_front")
    assert r.found and r.method == "layout" and r.confidence == 0.7
    assert r.full_name == "ASHA DEVI PATEL" and r.given_names is None and r.surname is None
    dumped = r.model_dump_json()
    for forbidden in ("4321", "8765", "1098", "14/03/1990", "RAMAN", "S/O", "भारत", "Government"):
        assert forbidden.lower() not in dumped.lower()


async def test_aadhaar_aliases_are_accepted_and_the_canonical_type_is_returned(aws):
    r = await read(aws, "Aadhaar_Masked", "aadhaar_front")
    assert r.doc_type == "aadhaar" and r.full_name == "ASHA DEVI PATEL"


async def test_aadhaar_without_a_dob_line_falls_back_to_the_first_name_like_line(aws):
    r = await read(aws, "aadhaar", ["Government of India", "आशा देवी पटेल", "Asha Devi Patel", "Female", "4321 8765 1098"])
    assert r.full_name == "ASHA DEVI PATEL"


async def test_aadhaar_name_on_the_same_line_as_the_dob_marker(aws):
    r = await read(aws, "aadhaar", ["Government of India", "Asha Devi Patel DOB: 14/03/1990", "Female"])
    assert r.full_name == "ASHA DEVI PATEL"


async def test_pan_new_format_returns_the_cardholder_never_the_father(aws):
    r = await read(aws, "pan", "pan_new")
    assert r.found and r.method == "label" and r.full_name == "SUNITA RAO"
    assert "RAMESH" not in r.model_dump_json()


async def test_pan_old_format_uses_the_line_below_the_header_never_the_father(aws):
    r = await read(aws, "pan", "pan_old")
    assert r.found and r.method == "layout" and r.full_name == "SUNITA RAO"
    assert "RAMESH" not in r.model_dump_json() and "ABCDE" not in r.model_dump_json()


async def test_voter_id_electors_name_label(aws):
    r = await read(aws, "voter_id", "voter_id")
    assert r.method == "label" and r.full_name == "VIKRAM SINGH"
    assert "MOHAN" not in r.model_dump_json()


async def test_voter_id_name_label_with_a_hindi_line_in_between_and_husbands_name_skipped(aws):
    r = await read(aws, "voter_id", "voter_id_name_label")
    assert r.full_name == "VIKRAM SINGH" and "MOHAN" not in r.model_dump_json()


async def test_driving_licence_name_and_relative_label_skipped(aws):
    r = await read(aws, "driving_licence", "driving_licence")
    assert r.method == "label" and r.full_name == "MEERA NAIR" and "GOPAL" not in r.model_dump_json()


async def test_driving_license_alias(aws):
    r = await read(aws, "driving_license", "driving_licence")
    assert r.doc_type == "driving_licence"


# ---------------------------------------------------------------------------------------------- Africa
@pytest.mark.parametrize("doc_type,fixture,given,surname,full", [
    ("botswana_omang", "omang", "KEABETSWE THATO", "MOTSWANA", "KEABETSWE THATO MOTSWANA"),
    ("botswana_omang", "omang_same_line", "KEABETSWE THATO", "MOTSWANA", "KEABETSWE THATO MOTSWANA"),
    ("kenya_id", "kenya_new", "WANJIKU MUTHONI", "KAMAU", "WANJIKU MUTHONI KAMAU"),
    ("south_africa_id", "south_africa_id", "SIPHO THABO", "NKOSI", "SIPHO THABO NKOSI"),
    ("nigeria_nin", "nigeria_nin", "OLUWASEUN TEMITOPE", "ADEYEMI", "OLUWASEUN TEMITOPE ADEYEMI"),
    ("ghana_card", "ghana_card", "KWAME KOFI", "MENSAH", "KWAME KOFI MENSAH"),
])
async def test_surname_and_given_names_are_returned_separately_and_combined(aws, doc_type, fixture, given, surname, full):
    r = await read(aws, doc_type, fixture)
    assert r.found and r.method == "label" and r.confidence == 0.85
    assert (r.given_names, r.surname, r.full_name) == (given, surname, full)


async def test_kenya_old_card_has_one_full_names_field(aws):
    r = await read(aws, "kenya_id", "kenya_old")
    assert r.full_name == "WANJIKU MUTHONI KAMAU" and r.given_names is None and r.surname is None


async def test_ghana_previous_names_are_not_returned(aws):
    r = await read(aws, "ghana_card", "ghana_card")
    assert "ASARE" not in r.model_dump_json()


async def test_generic_id_takes_the_first_name_like_line(aws):
    r = await read(aws, "generic_id", "generic_id")
    assert r.method == "layout" and r.full_name == "CHINEDU OKAFOR"


# ---------------------------------------------------------------------------------------------- not found, quality
async def test_name_not_found_is_a_result_not_an_exception(aws):
    r = await read(aws, "voter_id", "no_name")
    assert r.found is False and r.full_name is None and r.name is None and r.method is None and r.confidence == 0.0
    assert r.warnings == ["name_not_found"]


async def test_a_nearly_empty_ocr_result_adds_low_image_quality(aws):
    r = await read(aws, "voter_id", "unreadable")
    assert r.found is False and r.warnings == ["name_not_found", "low_image_quality"]


# ---------------------------------------------------------------------------------------------- cleanup, case
async def test_titles_and_label_punctuation_are_removed(aws):
    r = await read(aws, "voter_id", ["Elector's Name : Shri. Vikram Singh |"])
    assert r.full_name == "VIKRAM SINGH"
    r = await read(aws, "pan", ["Name", "Smt Sunita Rao"])
    assert r.full_name == "SUNITA RAO"


async def test_label_variants_with_ocr_noise_are_matched(aws):
    r = await read(aws, "voter_id", ["Electors Name: Vikram Singh"])  # no apostrophe
    assert r.full_name == "VIKRAM SINGH"
    r = await read(aws, "voter_id", ["ELECTOR'S NAME VIKRAM SINGH"])  # no colon
    assert r.full_name == "VIKRAM SINGH"


async def test_a_real_name_that_looks_like_a_label_word_is_kept_after_a_label(aws):
    r = await read(aws, "south_africa_id", ["Surname / Van", "MKHIZE", "Names / Voorname", "Given Thabo"])
    assert r.full_name == "GIVEN THABO MKHIZE"


async def test_a_relative_label_is_never_taken_as_the_value(aws):
    r = await read(aws, "voter_id", ["Elector's Name", "Father's Name : Mohan Singh"])
    assert r.found is False


@pytest.mark.parametrize("case,expected", [("upper", "ASHA DEVI PATEL"), ("title", "Asha Devi Patel"), ("original", "Asha Devi Patel")])
async def test_name_case_setting(aws, case, expected):
    r = await read(aws, "aadhaar", "aadhaar_front", name_case=case)
    assert r.full_name == expected


async def test_name_case_applies_to_every_part(aws):
    r = await read(aws, "passport", "passport_ind_mrz", name_case="title")
    assert (r.given_names, r.surname, r.full_name) == ("Chitta Ranjan", "Behera", "Chitta Ranjan Behera")


# ---------------------------------------------------------------------------------------------- doc types
async def test_unsupported_doc_type_is_an_exception_and_makes_no_aws_call(aws):
    with pytest.raises(UnsupportedDocType, match="library_card"):
        await extract_name("library_card", jpeg_bytes())
    assert aws.calls == []


async def test_doc_type_spelling_is_normalised(aws):
    r = await read(aws, " Voter-ID ", "voter_id")
    assert r.doc_type == "voter_id"


async def test_image_is_checked_before_any_aws_call(aws):
    from ezina_id_verify import UnsupportedFile

    with pytest.raises(UnsupportedFile, match="Only JPEG and PNG"):
        await extract_name("passport", b"%PDF-1.7 not an image")
    assert aws.calls == []


async def test_only_detect_text_is_called_with_the_image_bytes(aws):
    data = jpeg_bytes()
    aws.detect_text("voter_id")
    await extract_name("voter_id", data)
    assert aws.operations() == ["detect_text"]
    assert aws.params("detect_text")["Image"]["Bytes"] == data


async def test_a_png_is_accepted(aws, png):
    aws.detect_text("voter_id")
    assert (await extract_name("voter_id", png)).found


async def test_exif_rotated_image_is_corrected_before_ocr(aws):
    aws.detect_text("voter_id")
    await extract_name("voter_id", jpeg_bytes((1200, 800), orientation=6))
    sent = aws.params("detect_text")["Image"]["Bytes"]
    import io

    from PIL import Image

    assert Image.open(io.BytesIO(sent)).size == (800, 1200)


# ---------------------------------------------------------------------------------------------- privacy
async def test_logs_never_contain_names_numbers_ocr_text_or_image_data(aws, caplog):
    data = jpeg_bytes()
    with caplog.at_level(logging.DEBUG, logger="ezina_id_verify"):
        for doc_type, fixture in [("aadhaar", "aadhaar_front"), ("passport", "passport_ind_mrz"), ("pan", "pan_new"),
                                  ("voter_id", "no_name")]:
            aws.detect_text(fixture)
            await extract_name(doc_type, data)
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records if r.name.startswith("ezina_id_verify"))
    assert "name extraction" in text and "outcome=found" in text and "outcome=not_found" in text
    for secret in ("asha", "patel", "chitta", "ranjan", "behera", "sunita", "rao", "4321", "a1234567", "abcde1234f", "1990",
                   "government", "ffd8", "\\xff\\xd8"):
        assert secret not in text.lower()


# ---------------------------------------------------------------------------------------------- OCR provider interface
class FakeOcr:
    """Any object with `async read_lines(image)` can replace Rekognition OCR (for example Amazon Textract later)."""

    def __init__(self, *texts: str):
        from ezina_id_verify.name.ocr import OcrLine

        self.lines = [OcrLine(text=t, confidence=99.0, top=i * 0.06, left=0.08, height=0.04) for i, t in enumerate(texts)]
        self.images: list[bytes] = []

    async def read_lines(self, image: bytes):
        self.images.append(image)
        return self.lines


async def test_another_ocr_provider_can_replace_rekognition_without_touching_the_extractors(aws):
    ocr = FakeOcr("Elector's Name : Vikram Singh")
    r = await extract_name("voter_id", jpeg_bytes(), ocr=ocr)
    assert r.found and r.full_name == "VIKRAM SINGH" and len(ocr.images) == 1
    assert aws.calls == []  # Rekognition was not used


async def test_junk_ocr_text_never_crashes_any_document_type():
    import random

    from ezina_id_verify.config import load_documents

    rnd = random.Random(1234)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 <<:'’-./|()«‹éüñ  अआइक中文العربية\t"
    words = ["Name", "Surname", "Father's", "S/O", "DOB", "Given", "Names", "P<IND", "Elector's", "of", "Government", "India"]
    image = jpeg_bytes((400, 300))
    for doc_type in load_documents().doc_types:
        for _ in range(60):
            lines = []
            for _ in range(rnd.randint(0, 12)):
                parts = [rnd.choice(words) if rnd.random() < 0.4 else "".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 20)))
                         for _ in range(rnd.randint(1, 4))]
                lines.append(" ".join(parts))
            r = await extract_name(doc_type, image, ocr=FakeOcr(*lines))
            assert r.found in (True, False) and (r.found or r.full_name is None)
            if r.found:
                assert r.full_name and not any(ch.isdigit() for ch in r.full_name)


@pytest.mark.parametrize("label", ["Name of Holder", "Name of the Holder", "Name of Licence Holder", "Holder's Name", "Name"])
async def test_driving_licence_name_label_variants_do_not_leak_into_the_name(label):
    r = await extract_name("driving_licence", jpeg_bytes(), ocr=FakeOcr(f"{label} RAJESH KUMAR", "S/D/W of RAMESH KUMAR"))
    assert r.found and r.full_name == "RAJESH KUMAR"


@pytest.mark.parametrize("relative", ["S/D/W of", "S/DW of", "SDW of", "S D W of", "S/ DW of", "SIDIW of", "S/D/W", "S/DWof"])
async def test_a_misread_relative_label_is_never_returned_as_the_name(relative):
    for rows in ([ "Name", relative ], ["Name", relative, "RAMESH KUMAR"]):
        r = await extract_name("driving_licence", jpeg_bytes(), ocr=FakeOcr(*rows))
        assert not r.found or "SDW" not in (r.full_name or "").replace(" ", "").replace("I", "").replace("/", "")
        assert not r.found or r.full_name == "RAMESH KUMAR" or r.full_name is None


async def test_a_misread_relative_label_does_not_hide_the_real_name_on_the_same_line():
    r = await extract_name("driving_licence", jpeg_bytes(), ocr=FakeOcr("Name RAJESH KUMAR", "SDW of RAMESH KUMAR"))
    assert r.full_name == "RAJESH KUMAR"


@pytest.mark.parametrize("relative", ["S-D-W of", "S_D_W of", "S:D:W of", "S/D/W of", "Ramesh of"])
async def test_label_lookalikes_and_names_ending_in_of_are_rejected(relative):
    r = await extract_name("driving_licence", jpeg_bytes(), ocr=FakeOcr("Name", relative))
    assert not r.found


# ---------------------------------------------------------------------------------------------- tilted two-column card
def _tilted_card_response(width: int, height: int, degrees: float, items: list[tuple[str, float, float]]) -> dict:
    """A DetectText response for text boxes (text, centre x, centre y; both 0-1) rotated about the image centre."""
    import math

    a = math.radians(degrees)
    cx0, cy0 = width / 2, height / 2
    half_w, half_h = 0.06 * width, 0.017 * height
    dets = []
    for text, fx, fy in items:
        x, y = fx * width, fy * height
        pts = []
        for ox, oy in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)):
            px, py = x + ox, y + oy  # the box, then the whole page turned about its centre
            rx = cx0 + (px - cx0) * math.cos(a) - (py - cy0) * math.sin(a)
            ry = cy0 + (px - cx0) * math.sin(a) + (py - cy0) * math.cos(a)
            pts.append((rx / width, ry / height))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        dets.append({"DetectedText": text, "Type": "LINE", "Confidence": 98.0, "Geometry": {
            "BoundingBox": {"Left": min(xs), "Top": min(ys), "Width": max(xs) - min(xs), "Height": max(ys) - min(ys)},
            "Polygon": [{"X": px, "Y": py} for px, py in pts]}})
    return {"TextDetections": dets}


class TiltedCard:
    def __init__(self, degrees: float):
        from ezina_id_verify.name.ocr import lines_from_response

        self.degrees = degrees
        # labels in the left column, values in the right; the first value is level with its label ("Name" row)
        rows = [("Licence No", "DL01 20240001", 0.30), ("Name", "ASHA MWANGI", 0.38), ("S/D/W of", "JOSEPH MWANGI", 0.46),
                ("Address", "PLOT TWELVE NAIROBI", 0.54), ("DoB", "01-01-1990", 0.62)]
        items = [(label, 0.28, y) for label, _, y in rows] + [(value, 0.58, y) for _, value, y in rows]
        self.lines = lines_from_response(_tilted_card_response(1000, 800, degrees, items), (1000, 800))

    async def read_lines(self, image: bytes):
        return self.lines


@pytest.mark.parametrize("degrees", [0, 5, -11, 11, 20])
async def test_a_tilted_two_column_card_returns_the_holder_not_the_relative(degrees):
    r = await extract_name("driving_licence", jpeg_bytes(), ocr=TiltedCard(degrees))
    assert r.found and r.full_name == "ASHA MWANGI", (degrees, r.full_name)


def test_straightened_positions_line_a_value_up_with_its_label_whatever_the_tilt():
    for degrees in (-11, 0, 15):
        by_text = {l.text: l for l in TiltedCard(degrees).lines}
        for label, value in (("Name", "ASHA MWANGI"), ("S/D/W of", "JOSEPH MWANGI")):
            assert abs(by_text[label].dy - by_text[value].dy) < 0.005
        assert abs(by_text["Name"].dy - by_text["JOSEPH MWANGI"].dy) > 0.05


def test_without_outlines_or_an_image_size_lines_have_no_straightened_position():
    from ezina_id_verify.name.ocr import lines_from_response

    resp = _tilted_card_response(1000, 800, -11, [("Name", 0.3, 0.4), ("ASHA", 0.6, 0.4), ("Other", 0.3, 0.5)])
    assert all(l.dy is None for l in lines_from_response(resp))
    for det in resp["TextDetections"]:
        del det["Geometry"]["Polygon"]
    assert all(l.dy is None for l in lines_from_response(resp, (1000, 800)))
