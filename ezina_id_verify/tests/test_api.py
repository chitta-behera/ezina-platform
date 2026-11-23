"""The optional HTTP wrapper: 200 for results, 400 for bad input, 502 for AWS failures, API key enforced."""
import logging

import pytest
from conftest import jpeg_bytes, make_settings, png_bytes
from fastapi.testclient import TestClient

from ezina_id_verify import RekognitionServiceError, UnsupportedDocType, UnsupportedFile
from ezina_id_verify.config import set_settings

JPEG = jpeg_bytes()
KEY = {"X-API-Key": "s3cret"}


def make_client(**settings) -> TestClient:
    from ezina_id_verify.api import create_app

    set_settings(make_settings(**settings))
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return make_client()


def extract(client, *, content=JPEG, doc_type="voter_id", filename="id.jpg", ctype="image/jpeg", headers=None):
    return client.post("/extract-name", data={"doc_type": doc_type}, files={"file": (filename, content, ctype)}, headers=headers or {})


def match(client, *, id_image=JPEG, selfie=JPEG, headers=None):
    return client.post("/match-face", files={"id_image": ("id.jpg", id_image, "image/jpeg"),
                                            "selfie_image": ("s.jpg", selfie, "image/jpeg")}, headers=headers or {})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_extract_name_returns_the_name_result(client, aws):
    aws.detect_text("voter_id")
    r = extract(client)
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["full_name"] == "VIKRAM SINGH" and body["name"] == "VIKRAM SINGH"
    assert body["method"] == "label" and body["doc_type"] == "voter_id" and body["warnings"] == []
    assert set(body) == {"doc_type", "found", "full_name", "name", "given_names", "surname", "method", "confidence", "warnings"}


def test_a_name_not_found_is_still_200(client, aws):
    aws.detect_text("no_name")
    r = extract(client)
    assert r.status_code == 200 and r.json()["found"] is False and "name_not_found" in r.json()["warnings"]


def test_match_face_returns_the_face_result(client, aws):
    aws.detect_faces("faces_good").compare_faces("compare_96")
    r = match(client)
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True and body["similarity"] == 96.4 and body["confidence_band"] == "match"
    assert body["liveness_passed"] is None and body["face_found_id"] is True


def test_no_match_and_no_face_are_200(client, aws):
    aws.detect_faces("faces_good").compare_faces("compare_40")
    assert match(client).json()["verified"] is False
    aws.detect_faces("faces_none")
    r = match(client)
    assert r.status_code == 200 and r.json()["face_found_selfie"] is False


def test_the_file_type_is_detected_from_the_bytes_not_the_name_or_content_type(client, aws):
    aws.detect_text("voter_id")
    r = extract(client, content=JPEG, filename="id.png", ctype="image/png")  # a JPEG wrongly labelled as PNG
    assert r.status_code == 200 and r.json()["found"] is True
    aws.detect_text("voter_id")
    assert extract(client, content=png_bytes(), filename="photo.dat", ctype="application/octet-stream").status_code == 200


@pytest.mark.parametrize("filename,ctype", [("id.pdf", "application/pdf"), ("id.jpg", "image/jpeg"), ("id.png", "image/png")])
def test_a_pdf_is_rejected_with_400_whatever_it_claims_to_be(client, aws, filename, ctype):
    r = extract(client, content=b"%PDF-1.7 fake", filename=filename, ctype=ctype)
    assert r.status_code == 400 and "Only JPEG and PNG images are supported" in r.json()["detail"]
    r = match(client, id_image=b"%PDF-1.7 fake")
    assert r.status_code == 400 and "Only JPEG and PNG" in r.json()["detail"]
    assert aws.calls == []


def test_other_bad_files_and_doc_types_are_400(client):
    assert extract(client, content=b"not an image at all").status_code == 400
    assert extract(client, content=b"").status_code == 400
    r = extract(client, doc_type="library_card")
    assert r.status_code == 400 and "library_card" in r.json()["detail"]


def test_an_oversized_upload_is_400():
    c = make_client(max_upload_mb=0.001)
    r = extract(c)
    assert r.status_code == 400 and "larger than" in r.json()["detail"]


def test_a_missing_field_is_400(client):
    assert client.post("/extract-name", files={"file": ("a.jpg", JPEG, "image/jpeg")}).status_code == 400
    assert client.post("/extract-name", data={"doc_type": "voter_id"}).status_code == 400
    assert client.post("/match-face", files={"id_image": ("a.jpg", JPEG, "image/jpeg")}).status_code == 400


def test_an_aws_failure_is_502(client, aws):
    for _ in range(4):
        aws.error("detect_text", "ThrottlingException")
    r = extract(client)
    assert r.status_code == 502 and "ThrottlingException" in r.json()["detail"]
    for _ in range(4):
        aws.error("detect_faces", "InternalServerError", status=500)
    assert match(client).status_code == 502


# ---------------------------------------------------------------------------------------------- API key
def test_the_api_key_is_enforced_when_set(aws):
    c = make_client(id_verify_api_key="s3cret")
    assert extract(c).status_code == 401
    assert extract(c, headers={"X-API-Key": "wrong"}).status_code == 401
    assert match(c).status_code == 401
    aws.detect_text("voter_id")
    assert extract(c, headers=KEY).status_code == 200
    aws.detect_faces("faces_good").compare_faces("compare_96")
    assert match(c, headers=KEY).status_code == 200
    assert c.get("/health").status_code == 200


def test_an_empty_key_allows_access_but_warns_at_startup(caplog, aws):
    with caplog.at_level(logging.WARNING, logger="ezina_id_verify"):
        with make_client() as c:  # entering the context runs the startup (lifespan)
            aws.detect_text("voter_id")
            assert extract(c).status_code == 200
    assert "ID_VERIFY_API_KEY is empty" in caplog.text


def test_no_warning_when_a_key_is_set(caplog):
    with caplog.at_level(logging.WARNING, logger="ezina_id_verify"):
        with make_client(id_verify_api_key="s3cret"):
            pass
    assert "ID_VERIFY_API_KEY is empty" not in caplog.text


def test_a_malformed_documents_file_stops_the_app_at_startup(tmp_path):
    from ezina_id_verify.api import create_app
    from ezina_id_verify.config import ConfigError

    bad = tmp_path / "documents.yaml"
    bad.write_text("documents: [unclosed", encoding="utf-8")
    set_settings(make_settings(id_verify_documents_config=bad))
    with pytest.raises(ConfigError, match="not valid YAML"):
        create_app()


# ---------------------------------------------------------------------------------------------- no logic in the API layer
def test_the_api_passes_only_the_uploaded_bytes(monkeypatch):
    from ezina_id_verify import api

    seen = {}

    async def fake_extract(doc_type, data):
        seen["extract"] = (doc_type, data)
        raise UnsupportedFile("stop here")

    async def fake_match(id_bytes, selfie_bytes):
        seen["match"] = (id_bytes, selfie_bytes)
        raise RekognitionServiceError("boom", "X")

    monkeypatch.setattr(api, "extract_name", fake_extract)
    monkeypatch.setattr(api, "match_face", fake_match)
    c = make_client()
    other = jpeg_bytes((900, 900), color=(1, 2, 3))
    assert extract(c, doc_type="pan", ctype="image/gif", filename="x.gif").status_code == 400
    assert seen["extract"] == ("pan", JPEG)  # the content type "image/gif" played no part
    assert match(c, id_image=JPEG, selfie=other).status_code == 502
    assert seen["match"] == (JPEG, other)


def test_unsupported_doc_type_maps_to_400(monkeypatch):
    from ezina_id_verify import api

    async def fake_extract(doc_type, data):
        raise UnsupportedDocType("nope")

    monkeypatch.setattr(api, "extract_name", fake_extract)
    assert extract(make_client()).status_code == 400
