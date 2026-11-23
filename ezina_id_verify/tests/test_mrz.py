"""MRZ parsing (ICAO Doc 9303), with no AWS involved."""
import pytest

from ezina_id_verify.name.mrz import extract_mrz_name, normalise_line, parse_name_field
from ezina_id_verify.name.ocr import OcrLine


def lines(*texts: str) -> list[OcrLine]:
    return [OcrLine(text=t, confidence=99.0, top=i * 0.06, left=0.08, height=0.04) for i, t in enumerate(texts)]


def td3(first: str, second: str = "A1234567<4IND9001019M3001017<<<<<<<<<<<<<<04") -> list[OcrLine]:
    return lines(first.ljust(44, "<"), second.ljust(44, "<"))


def test_indian_passport_surname_and_given_names():
    c = extract_mrz_name(td3("P<INDBEHERA<<CHITTA<RANJAN"))
    assert (c.surname, c.given_names, c.full_name, c.method) == ("BEHERA", "CHITTA RANJAN", "CHITTA RANJAN BEHERA", "mrz")


def test_german_passport_issuing_state_with_filler_characters():
    # "P<D<<": the issuing state is "D<<" (3 characters), so the name starts at the 6th character
    c = extract_mrz_name(td3("P<D<<MUSTERMANN<<ERIKA", "C01X00T478D<<6408125F2702283<<<<<<<"))
    assert (c.surname, c.given_names) == ("MUSTERMANN", "ERIKA")


@pytest.mark.parametrize("first,surname,given", [
    ("PDINDKUMAR<<ANITA<SHARMA", "KUMAR", "ANITA SHARMA"),  # document type "PD"
    ("POUTOERIKSSON<<ANNA<MARIA", "ERIKSSON", "ANNA MARIA"),  # document type "PO"
    ("PAUTOERIKSSON<<ANNA", "ERIKSSON", "ANNA"),  # any letter after "P"
])
def test_two_character_document_types(first, surname, given):
    c = extract_mrz_name(td3(first))
    assert (c.surname, c.given_names) == (surname, given)


def test_empty_surname_is_valid():
    c = extract_mrz_name(td3("P<UTO<<ERIKA"))
    assert c.surname is None and c.given_names == "ERIKA" and c.full_name == "ERIKA"


def test_a_name_with_only_a_surname():
    c = extract_mrz_name(td3("P<UTOERIKSSON"))
    assert c.surname == "ERIKSSON" and c.given_names is None and c.full_name == "ERIKSSON"


def test_ocr_slip_double_chevron_is_normalised():
    assert normalise_line("P<INDBEHERA«CHITTA<RANJAN") == "P<INDBEHERA<<CHITTA<RANJAN"
    raw = "P<INDBEHERA«CHITTA<RANJAN"
    c = extract_mrz_name(lines(raw + "<" * (43 - len(raw)), "A1234567<4IND9001019M3001017<<<<<<<<<<<<<<04"))
    assert c.full_name == "CHITTA RANJAN BEHERA"


def test_spaces_inside_the_mrz_line_are_removed():
    c = extract_mrz_name(lines("P< IND BEHERA << CHITTA < RANJAN <<<<<<<<<<<<<<<<<<<<<", "A1234567<4 IND 9001019 M 3001017<<<<<<<<<<<<<<04"))
    assert c.full_name == "CHITTA RANJAN BEHERA"


def test_padding_that_ocr_read_as_letters_is_dropped():
    c = extract_mrz_name(td3("P<INDBEHERA<<CHITTA<RANJAN" + "K" * 18))
    assert c.given_names == "CHITTA RANJAN"
    c = extract_mrz_name(td3("P<INDBEHERA<<CHITTA<RANJAN<<<KKKKKKKK"))
    assert c.given_names == "CHITTA RANJAN"


def test_a_name_ending_in_c_or_k_keeps_its_last_letter():
    c = extract_mrz_name(td3("P<UTOLENOIR<<ERIC"))
    assert c.given_names == "ERIC"
    c = extract_mrz_name(td3("P<UTOLENOIR<<MARK"))
    assert c.given_names == "MARK"


def test_digits_read_instead_of_letters_are_corrected():
    c = extract_mrz_name(td3("P<INDB3HERA<<CH1TTA<RANJAN"))  # 1 -> I; 3 is not a letter-like slip, so this is rejected
    assert c is None
    c = extract_mrz_name(td3("P<INDBEHERA<<CH1TTA<RANJAN"))
    assert c.given_names == "CHITTA RANJAN"


def test_td1_id_card_name_is_on_line_3():
    c = extract_mrz_name(lines("I<UTOD231458907<<<<<<<<<<<<<<<", "7408122F1204159UTO<<<<<<<<<<<6", "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"))
    assert (c.surname, c.given_names, c.full_name) == ("ERIKSSON", "ANNA MARIA", "ANNA MARIA ERIKSSON")


def test_td2_id_card():
    first = "I<UTOERIKSSON<<ANNA<MARIA".ljust(36, "<")
    second = "D231458907UTO7408122F1204159<<<<<<<6"
    assert len(first) == len(second) == 36
    c = extract_mrz_name(lines(first, second))
    assert c.full_name == "ANNA MARIA ERIKSSON"


def test_ordinary_text_is_not_an_mrz():
    assert extract_mrz_name(lines("REPUBLIC OF INDIA", "PASSPORT", "Surname", "BEHERA", "Given Name(s)", "CHITTA RANJAN")) is None


def test_a_single_mrz_line_is_used_only_when_the_name_is_complete_and_is_flagged():
    c = extract_mrz_name(lines("P<INDBEHERA<<CHITTA<RANJAN<<"))  # a real photo: line 2 missing, line 1 cut short
    assert c is not None and c.full_name == "CHITTA RANJAN BEHERA" and c.warnings == ("mrz_incomplete",)
    assert extract_mrz_name(lines("P<INDBEHERA<<CHITTA<RANJAN".ljust(44, "<"))).warnings == ("mrz_incomplete",)


def test_a_single_line_with_a_cut_off_name_is_not_used():
    c = extract_mrz_name(lines("P<INDBEHERA<<CHITTA<RANJ"))  # no closing "<<": the name may be cut, flagged for the caller
    assert c is not None and c.warnings == ("mrz_incomplete", "mrz_name_unclosed")
    assert extract_mrz_name(lines("IND<<SOMETHING<<LONGENOUGH<<")) is None  # not a passport line
    assert extract_mrz_name(lines("P<INDBEHERA")) is None


def test_other_mrz_fields_are_never_part_of_the_result():
    c = extract_mrz_name(td3("P<INDBEHERA<<CHITTA<RANJAN"))
    assert "A1234567" not in repr(c) and "9001019" not in repr(c)


@pytest.mark.parametrize("field", ["", "<<<<", "123<<456", "BE-HERA<<X"])
def test_garbage_name_fields_are_rejected(field):
    assert parse_name_field(field) is None
