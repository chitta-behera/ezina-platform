"""AWS failure handling shared by both checks: retries with backoff, then RekognitionServiceError."""
import pytest
from botocore.exceptions import EndpointConnectionError
from conftest import jpeg_bytes, make_settings

from ezina_id_verify import RekognitionServiceError, extract_name, match_face
from ezina_id_verify import rekognition
from ezina_id_verify.config import set_settings


async def test_throttling_is_retried_then_succeeds(aws):
    aws.error("detect_text", "ThrottlingException").error("detect_text", "ThrottlingException").detect_text("voter_id")
    r = await extract_name("voter_id", jpeg_bytes())
    assert r.found and aws.operations() == ["detect_text"] * 3


async def test_server_errors_are_retried(aws):
    aws.error("detect_text", "InternalServerError", status=500).detect_text("voter_id")
    assert (await extract_name("voter_id", jpeg_bytes())).found
    aws.done()


async def test_persistent_failure_raises_after_the_retries(aws):
    for _ in range(4):  # 1 try + AWS_MAX_RETRIES (3)
        aws.error("detect_text", "ThrottlingException")
    with pytest.raises(RekognitionServiceError) as e:
        await extract_name("voter_id", jpeg_bytes())
    assert e.value.code == "ThrottlingException" and "4 attempts" in str(e.value)
    aws.done()


async def test_the_retry_count_is_configurable(aws):
    set_settings(make_settings(aws_max_retries=1))
    aws.error("detect_faces", "ThrottlingException").error("detect_faces", "ThrottlingException")
    with pytest.raises(RekognitionServiceError):
        await match_face(jpeg_bytes(), jpeg_bytes())
    aws.done()


async def test_errors_retrying_cannot_fix_are_raised_at_once(aws):
    aws.error("detect_text", "AccessDeniedException", message="not authorised to perform rekognition:DetectText")
    with pytest.raises(RekognitionServiceError) as e:
        await extract_name("voter_id", jpeg_bytes())
    assert e.value.code == "AccessDeniedException" and aws.operations() == ["detect_text"]


async def test_network_errors_are_retried():
    class Flaky:
        calls = 0

        def detect_text(self, **kw):
            Flaky.calls += 1
            raise EndpointConnectionError(endpoint_url="https://rekognition.invalid")

    rekognition.set_client(Flaky())
    with pytest.raises(RekognitionServiceError):
        await extract_name("voter_id", jpeg_bytes())
    assert Flaky.calls == 4


async def test_backoff_waits_between_retries(monkeypatch, aws):
    waits = []
    monkeypatch.setattr(rekognition.time, "sleep", lambda s: waits.append(s))
    set_settings(make_settings(aws_retry_base_delay=1.0))
    for _ in range(4):
        aws.error("detect_text", "ThrottlingException")
    with pytest.raises(RekognitionServiceError):
        await extract_name("voter_id", jpeg_bytes())
    assert len(waits) == 3 and waits[0] < waits[1] < waits[2]  # 1, 2, 4 seconds plus a little jitter


async def test_calls_do_not_block_the_event_loop(monkeypatch, aws):
    """boto3 is synchronous: the call runs in a worker thread, so another coroutine keeps running meanwhile.

    Deterministic: the worker thread waits until the coroutine has run, which can only happen if the loop is free.
    """
    import asyncio
    import threading

    main = threading.get_ident()
    seen = {}
    coroutine_ran = threading.Event()
    original = rekognition.call

    def blocked_until_the_loop_runs(operation, **kwargs):
        seen["thread"] = threading.get_ident()
        seen["loop_was_free"] = coroutine_ran.wait(timeout=5)
        return original(operation, **kwargs)

    monkeypatch.setattr(rekognition, "call", blocked_until_the_loop_runs)
    aws.detect_text("voter_id")

    async def other_work():
        await asyncio.sleep(0.01)
        coroutine_ran.set()

    await asyncio.gather(extract_name("voter_id", jpeg_bytes()), other_work())
    assert seen["thread"] != main and seen["loop_was_free"] is True
