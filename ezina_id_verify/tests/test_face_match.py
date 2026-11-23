"""match_face end to end with saved (synthetic) DetectFaces / CompareFaces responses. Rekognition is stubbed."""
import inspect
import logging

import pytest
from conftest import jpeg_bytes, make_settings, png_bytes

from ezina_id_verify import FaceMatchResult, RekognitionServiceError, UnsupportedFile, face_match, match_face
from ezina_id_verify.config import set_settings

ID_IMG = jpeg_bytes((1200, 800), color=(200, 40, 40))
SELFIE = jpeg_bytes((1000, 1300), color=(40, 40, 200))


async def compare(aws, faces="faces_good", comparison="compare_96", **settings) -> FaceMatchResult:
    if settings:
        set_settings(make_settings(**settings))
    aws.detect_faces(faces)
    if comparison is not None:
        aws.compare_faces(comparison)
    result = await match_face(ID_IMG, SELFIE)
    aws.done()
    return result


async def test_similarity_96_is_verified_match(aws):
    r = await compare(aws)
    assert r.verified is True and r.similarity == 96.4 and r.confidence_band == "match" and r.threshold == 90.0
    assert (r.face_found_id, r.face_found_selfie) == (True, True)
    assert r.selfie_quality_ok is True and r.warnings == [] and r.error is None
    assert r.liveness_passed is None
    assert r.model == "aws-rekognition-compare-faces" and r.processing_ms >= 0


async def test_similarity_80_is_a_possible_match_but_not_verified(aws):
    r = await compare(aws, comparison="compare_80")
    assert r.verified is False and r.similarity == 80.2 and r.confidence_band == "possible_match"


async def test_similarity_40_is_no_match(aws):
    r = await compare(aws, comparison="compare_40")
    assert r.verified is False and r.similarity == 40.1 and r.confidence_band == "no_match"


async def test_empty_face_matches_means_similarity_0_and_no_match(aws):
    r = await compare(aws, comparison="compare_empty")
    assert r.verified is False and r.similarity == 0.0 and r.confidence_band == "no_match"
    assert (r.face_found_id, r.face_found_selfie) == (True, True)


async def test_the_highest_similarity_entry_is_used(aws):
    r = await compare(aws, comparison="compare_two_matches")
    assert r.similarity == 93.3 and r.verified is True


async def test_thresholds_are_configurable(aws):
    r = await compare(aws, comparison="compare_two_matches", face_match_threshold=95, face_possible_match_threshold=90)
    assert r.verified is False and r.threshold == 95 and r.confidence_band == "possible_match"


async def test_the_threshold_is_applied_in_python_so_compare_faces_is_asked_for_every_score(aws):
    await compare(aws)
    params = aws.params("compare_faces")
    assert params["SimilarityThreshold"] == 0
    assert params["SourceImage"]["Bytes"] == ID_IMG  # source = the ID document
    assert params["TargetImage"]["Bytes"] == SELFIE  # target = the selfie
    detect = aws.params("detect_faces")
    assert detect["Attributes"] == ["ALL"] and detect["Image"]["Bytes"] == SELFIE
    assert aws.operations() == ["detect_faces", "compare_faces"]


async def test_no_face_in_the_selfie_skips_compare_faces(aws):
    r = await compare(aws, faces="faces_none", comparison=None)
    assert r.face_found_selfie is False and r.verified is False and r.confidence_band is None and r.similarity is None
    assert r.selfie_quality_ok is None and aws.operations() == ["detect_faces"]
    assert r.face_found_id is True  # the ID was not examined, so it is not reported as having no face


@pytest.mark.parametrize("comparison", ["compare_no_source"])
async def test_no_face_in_the_id_from_an_empty_source_face(aws, comparison):
    r = await compare(aws, comparison=comparison)
    assert r.face_found_id is False and r.verified is False and r.confidence_band is None and r.similarity is None
    assert r.face_found_selfie is True


async def test_no_face_in_the_id_from_invalid_parameter_exception(aws):
    aws.detect_faces("faces_good")
    aws.error("compare_faces", "InvalidParameterException", message="There are no faces in the image. Should be at least 1.")
    r = await match_face(ID_IMG, SELFIE)
    assert r.face_found_id is False and r.face_found_selfie is True and r.verified is False
    assert r.similarity is None and r.confidence_band is None and r.error is None
    aws.done()


async def test_no_face_in_the_target_message_points_at_the_selfie(aws):
    aws.detect_faces("faces_good")
    aws.error("compare_faces", "InvalidParameterException", message="There are no faces in the target image.")
    r = await match_face(ID_IMG, SELFIE)
    assert r.face_found_selfie is False and r.face_found_id is True


async def test_multiple_faces_in_the_selfie_warn_and_the_largest_is_used(aws):
    r = await compare(aws, faces="faces_two")
    assert "multiple_faces_selfie" in r.warnings
    # the smaller face is blurry (sharpness 10), the largest is fine: quality is judged on the largest
    assert "selfie_blurry" not in r.warnings and r.selfie_quality_ok is True and r.verified is True


@pytest.mark.parametrize("faces,warning", [
    ("faces_blurry", "selfie_blurry"), ("faces_dark", "selfie_dark"), ("faces_sunglasses", "sunglasses"),
    ("faces_eyes_closed", "eyes_closed"),
])
async def test_selfie_quality_problems_become_warnings(aws, faces, warning):
    r = await compare(aws, faces=faces)
    assert r.warnings == [warning] and r.selfie_quality_ok is False
    assert r.verified is True  # quality is advice, it does not change the match


async def test_quality_thresholds_are_configurable(aws):
    r = await compare(aws, faces="faces_blurry", face_min_sharpness=0)
    assert r.warnings == [] and r.selfie_quality_ok is True
    set_settings(make_settings(face_min_brightness=90))
    aws.detect_faces("faces_good").compare_faces("compare_96")
    r = await match_face(ID_IMG, SELFIE)
    assert r.warnings == ["selfie_dark"]


async def test_a_very_small_id_face_adds_a_warning(aws):
    r = await compare(aws, comparison="compare_small_face")
    assert r.warnings == ["small_face_id"] and r.verified is True and r.similarity == 95.0


async def test_liveness_is_always_none(aws):
    for comparison in ("compare_96", "compare_40", "compare_empty"):
        r = await compare(aws, comparison=comparison)
        assert r.liveness_passed is None


async def test_result_field_names_are_compatible_with_ezina_connects_face_check(aws):
    r = await compare(aws)
    assert set(r.model_dump()) == {
        "verified", "similarity", "threshold", "confidence_band", "face_found_id", "face_found_selfie", "liveness_passed",
        "selfie_quality_ok", "model", "processing_ms", "error", "warnings",
    }


async def test_png_inputs_are_accepted(aws):
    aws.detect_faces("faces_good").compare_faces("compare_96")
    assert (await match_face(png_bytes(), png_bytes())).verified is True


async def test_a_rejected_selfie_image_is_a_result_with_an_error_code(aws):
    aws.error("detect_faces", "InvalidImageFormatException", message="bad image")
    r = await match_face(ID_IMG, SELFIE)
    assert r.error == "selfie_image_rejected" and r.verified is False and r.face_found_selfie is False


async def test_a_rejected_id_image_is_a_result_with_an_error_code(aws):
    aws.detect_faces("faces_good").error("compare_faces", "InvalidParameterException", message="Image is too small")
    r = await match_face(ID_IMG, SELFIE)
    assert r.error == "id_image_rejected" and r.verified is False and r.face_found_id is False


async def test_aws_failure_raises_after_retries(aws):
    for _ in range(4):
        aws.error("detect_faces", "ThrottlingException")
    with pytest.raises(RekognitionServiceError):
        await match_face(ID_IMG, SELFIE)
    aws.done()


async def test_aws_failure_in_compare_faces_raises(aws):
    aws.detect_faces("faces_good")
    for _ in range(4):
        aws.error("compare_faces", "InternalServerError", status=500)
    with pytest.raises(RekognitionServiceError):
        await match_face(ID_IMG, SELFIE)


@pytest.mark.parametrize("which", ["id", "selfie"])
async def test_a_pdf_or_other_file_is_unsupported_and_says_which_image(aws, which):
    bad = b"%PDF-1.7 ..."
    args = (bad, SELFIE) if which == "id" else (ID_IMG, bad)
    with pytest.raises(UnsupportedFile, match="Only JPEG and PNG images are supported") as e:
        await match_face(*args)
    assert str(e.value).startswith("ID image" if which == "id" else "Selfie image")
    assert aws.calls == []


async def test_oversized_file_is_unsupported(aws):
    set_settings(make_settings(max_upload_mb=0.001))
    with pytest.raises(UnsupportedFile, match="larger than"):
        await match_face(ID_IMG, SELFIE)


def test_face_matching_is_independent_of_name_extraction():
    source = inspect.getsource(face_match)
    assert "name_extract" not in source and "ezina_id_verify.name" not in source


async def test_logs_have_only_outcome_similarity_and_timing(aws, caplog):
    with caplog.at_level(logging.DEBUG, logger="ezina_id_verify"):
        await compare(aws)
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records if r.name.startswith("ezina_id_verify"))
    assert "face match outcome=match similarity=96.4" in text
    for secret in ("BoundingBox", "ffd8", "\\xff\\xd8", "Landmarks", "0.4"):
        assert secret not in text
