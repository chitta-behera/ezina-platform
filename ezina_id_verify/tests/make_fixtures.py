"""Builds the saved Rekognition responses in tests/fixtures/ (SYNTHETIC documents only: invented names and numbers,
ICAO specimen MRZ lines; never a real person's ID or face). Run:  python tests/make_fixtures.py

The JSON files have the real response shape (they are validated by botocore's Stubber when the tests use them).
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"


def _poly(left: float, top: float, width: float, height: float) -> list[dict]:
    return [{"X": left, "Y": top}, {"X": left + width, "Y": top}, {"X": left + width, "Y": top + height},
            {"X": left, "Y": top + height}]


def detect_text(lines: list) -> dict:
    """A DetectText response: each entry is a text or (text, confidence); one LINE plus its WORDs per entry."""
    detections = []
    for i, item in enumerate(lines):
        text, confidence = item if isinstance(item, tuple) else (item, 98.6)
        box = {"Width": round(min(0.9, 0.012 * len(text) + 0.05), 4), "Height": 0.04, "Left": 0.08, "Top": round(0.05 + i * 0.06, 4)}
        geometry = {"BoundingBox": box, "Polygon": _poly(box["Left"], box["Top"], box["Width"], box["Height"])}
        detections.append({"DetectedText": text, "Type": "LINE", "Id": i, "Confidence": confidence, "Geometry": geometry})
        for j, word in enumerate(text.split()):
            detections.append({"DetectedText": word, "Type": "WORD", "Id": 1000 + i * 100 + j, "ParentId": i,
                                "Confidence": confidence, "Geometry": geometry})
    return {"TextDetections": detections, "TextModelVersion": "3.0"}


def mrz(first: str, second: str, width: int = 44) -> list[str]:
    return [first.ljust(width, "<"), second.ljust(width, "<")]


DOCUMENTS: dict[str, list] = {
    # passports: a TD3 MRZ (the spec's example name), a German one ("P<D<<" country code), "PD" / "PO" types, empty surname
    "passport_ind_mrz": ["REPUBLIC OF INDIA", "PASSPORT", "Type P Country Code IND", "Passport No. A1234567",
                         *mrz("P<INDBEHERA<<CHITTA<RANJAN", "A1234567<4IND9001019M3001017")],
    "passport_deu_mrz": ["BUNDESREPUBLIK DEUTSCHLAND", "REISEPASS", *mrz("P<D<<MUSTERMANN<<ERIKA", "C01X00T478D<<6408125F2702283<<<<<<<")],
    "passport_pd_mrz": [*mrz("PDINDKUMAR<<ANITA<SHARMA", "B7654321<1IND8505055F2905051<<<<<<<<<<<<<<04")],
    "passport_po_mrz": [*mrz("POUTOERIKSSON<<ANNA<MARIA", "L898902C36UTO7408122F1204159ZE184226B<<<<<10")],
    "passport_no_surname_mrz": [*mrz("P<UTO<<ERIKA", "L898902C36UTO7408122F1204159ZE184226B<<<<<10")],
    "passport_labels_only": ["PASSPORT", "Surname", "NAIR", "Given Name(s)", "ARJUN VIKRAM", "Nationality", "INDIAN"],
    # an ID card with a TD1 MRZ (ICAO specimen lines, 3 x 30)
    "id_td1_mrz": ["IDENTITY CARD", "I<UTOD231458907<<<<<<<<<<<<<<<", "7408122F1204159UTO<<<<<<<<<<<6",
                   "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"],
    # India
    "aadhaar_front": ["भारत सरकार", "Government of India", "आशा देवी पटेल", "Asha Devi Patel", "S/O Raman Patel",
                      "जन्म तिथि / DOB: 14/03/1990", "महिला / Female", "4321 8765 1098", "मेरा आधार, मेरी पहचान"],
    "pan_new": ["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "Permanent Account Number Card", "ABCDE1234F",
                "नाम / Name", "SUNITA RAO", "पिता का नाम / Father's Name", "RAMESH RAO",
                "जन्म की तारीख / Date of Birth", "12/08/1985", "हस्ताक्षर / Signature"],
    "pan_old": ["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "Permanent Account Number", "ABCDE1234F", "SUNITA RAO", "RAMESH RAO",
                "12/08/1985", "Signature"],
    "voter_id": ["ELECTION COMMISSION OF INDIA", "IDENTITY CARD", "ABC1234567", "Elector's Name : Vikram Singh",
                 "Father's Name : Mohan Singh", "Sex / Gender : Male", "Date of Birth : 01/01/1980"],
    "voter_id_name_label": ["ELECTION COMMISSION OF INDIA", "ELECTOR PHOTO IDENTITY CARD", "XYZ7654321", "नाम / Name", "विक्रम सिंह",
                            "Vikram Singh", "Husband's Name", "MOHAN SINGH"],
    "driving_licence": ["DRIVING LICENCE", "DL No. KL0120190001234", "Name : MEERA NAIR", "S/D/W of : GOPAL NAIR",
                        "DOB : 03/04/1992", "Blood Group : B+"],
    # Africa
    "omang": ["REPUBLIC OF BOTSWANA", "OMANG", "Surname", "MOTSWANA", "Forenames", "KEABETSWE THATO", "ID No 123456789"],
    "omang_same_line": ["REPUBLIC OF BOTSWANA", "Surname: MOTSWANA", "Forenames: KEABETSWE THATO", "Date of Birth 01 01 1990"],
    "kenya_old": ["REPUBLIC OF KENYA", "JAMHURI YA KENYA", "ID NUMBER 12345678", "FULL NAMES", "WANJIKU MUTHONI KAMAU",
                  "DATE OF BIRTH", "01.01.1985", "SEX", "FEMALE"],
    "kenya_new": ["REPUBLIC OF KENYA", "Surname", "KAMAU", "Given Name", "WANJIKU MUTHONI", "Date of Birth", "01.01.1985"],
    "south_africa_id": ["REPUBLIC OF SOUTH AFRICA", "IDENTITY CARD", "Surname / Van", "NKOSI", "Names / Voorname", "SIPHO THABO",
                        "Nationality / Nasionaliteit", "RSA"],
    "nigeria_nin": ["FEDERAL REPUBLIC OF NIGERIA", "NATIONAL IDENTIFICATION NUMBER", "Surname", "ADEYEMI", "First Name", "OLUWASEUN",
                    "Middle Name", "TEMITOPE", "Date of Birth", "01 JAN 1990"],
    "ghana_card": ["REPUBLIC OF GHANA", "ECOWAS IDENTITY CARD", "Surname", "MENSAH", "Firstnames", "KWAME KOFI", "Previous Names",
                   "ASARE", "Personal ID Number", "GHA-000000000-0"],
    # generic / failure cases
    "generic_id": ["NATIONAL ID CARD", "ID 0012345", "Chinedu Okafor", "Date of Birth 01/02/1990"],
    "no_name": ["ELECTION COMMISSION OF INDIA", "IDENTITY CARD", "ABC1234567", "Date of Birth : 01/01/1980"],
    "unreadable": ["xk"],
    "low_ocr_label": ["PASSPORT", ("Surname", 60.0), ("NAIR", 62.0), "Given Name(s)", ("ARJUN VIKRAM", 65.0)],
}


def _face(width=0.4, height=0.5, left=0.3, top=0.2, sharpness=80.0, brightness=70.0, sunglasses=False, eyes_open=True) -> dict:
    return {
        "BoundingBox": {"Width": width, "Height": height, "Left": left, "Top": top},
        "Confidence": 99.9,
        "Quality": {"Brightness": brightness, "Sharpness": sharpness},
        "Sunglasses": {"Value": sunglasses, "Confidence": 99.0},
        "EyesOpen": {"Value": eyes_open, "Confidence": 99.0},
        "Smile": {"Value": False, "Confidence": 90.0},
        "Pose": {"Roll": 1.2, "Yaw": -2.0, "Pitch": 3.1},
    }


def detect_faces(*faces: dict) -> dict:
    return {"FaceDetails": list(faces), "OrientationCorrection": "ROTATE_0"}


def compare(similarities: list[float], source_width: float = 0.2) -> dict:
    source = {"BoundingBox": {"Width": source_width, "Height": 0.3, "Left": 0.1, "Top": 0.3}, "Confidence": 99.8}
    matches = [{"Similarity": s, "Face": {"BoundingBox": {"Width": 0.4, "Height": 0.5, "Left": 0.3, "Top": 0.2}, "Confidence": 99.9}}
               for s in similarities]
    return {"SourceImageFace": source, "FaceMatches": matches, "UnmatchedFaces": []}


FACES: dict[str, dict] = {
    "faces_good": detect_faces(_face()),
    "faces_none": detect_faces(),
    "faces_two": detect_faces(_face(width=0.1, height=0.12, left=0.7, top=0.6, sharpness=10.0), _face()),
    "faces_blurry": detect_faces(_face(sharpness=5.0)),
    "faces_dark": detect_faces(_face(brightness=8.0)),
    "faces_sunglasses": detect_faces(_face(sunglasses=True)),
    "faces_eyes_closed": detect_faces(_face(eyes_open=False)),
    "compare_96": compare([96.4]),
    "compare_80": compare([80.2]),
    "compare_40": compare([40.1]),
    "compare_two_matches": compare([61.0, 93.3]),
    "compare_empty": compare([]),
    "compare_small_face": compare([95.0], source_width=0.03),
    "compare_no_source": {"SourceImageFace": {}, "FaceMatches": [], "UnmatchedFaces": []},
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    payloads = {name: detect_text(lines) for name, lines in DOCUMENTS.items()} | FACES
    for name, payload in payloads.items():
        (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(payloads)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
