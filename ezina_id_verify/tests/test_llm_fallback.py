"""The optional LLM fallback: off by default, used only when every earlier strategy fails, output validated."""
from types import SimpleNamespace

import pytest
from conftest import jpeg_bytes, make_settings

from ezina_id_verify import extract_name
from ezina_id_verify.config import set_settings
from ezina_id_verify.name import llm

# no label and no layout rule finds anything useful for voter_id here, so only the fallback can
LINES = ["ELECTION COMMISSION OF INDIA", "Vikram Singh", "Date of Birth 01/01/1980", "Mob 9876543210"]


class FakeClaude:
    """Stands in for the Anthropic async client: records the request, answers through a tool_use block."""

    def __init__(self, reply=None, error: Exception | None = None):
        self.reply, self.error, self.calls = reply, error, []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        content = [] if self.reply is None else [SimpleNamespace(type="tool_use", input=self.reply)]
        return SimpleNamespace(content=content)


def enable(client: FakeClaude | None, **settings) -> None:
    set_settings(make_settings(llm_fallback_enabled=True, anthropic_api_key="test-key", claude_model="test-model", **settings))
    llm.set_client(client)


async def run(aws, lines=LINES, doc_type="voter_id"):
    aws.detect_text(lines)
    return await extract_name(doc_type, jpeg_bytes())


GOOD = {"found": True, "given_names": "Vikram", "surname": "Singh", "full_name": "Vikram Singh"}


async def test_disabled_by_default_even_if_a_client_is_available(aws):
    client = FakeClaude(GOOD)
    llm.set_client(client)
    r = await run(aws)
    assert r.found is False and client.calls == []


async def test_used_when_enabled_and_every_earlier_strategy_failed(aws):
    client = FakeClaude(GOOD)
    enable(client)
    r = await run(aws)
    assert r.found and r.method == "llm" and r.confidence == 0.6
    assert (r.given_names, r.surname, r.full_name) == ("VIKRAM", "SINGH", "VIKRAM SINGH")
    assert len(client.calls) == 1


async def test_not_used_when_an_earlier_strategy_succeeds(aws):
    client = FakeClaude(GOOD)
    enable(client)
    r = await run(aws, ["Elector's Name : Anil Kumar"])
    assert r.method == "label" and client.calls == []


async def test_request_has_a_forced_tool_the_model_and_only_masked_ocr_lines(aws):
    client = FakeClaude(GOOD)
    enable(client)
    await run(aws)
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["tool_choice"] == {"type": "tool", "name": "record_name"}
    assert [t["name"] for t in call["tools"]] == ["record_name"]
    schema = call["tools"][0]["input_schema"]
    assert set(schema["properties"]) == {"found", "given_names", "surname", "full_name"}
    prompt = call["messages"][0]["content"]
    assert "voter_id" in prompt and "Vikram Singh" in prompt and "ELECTION COMMISSION" in prompt
    for digits in ("01/01/1980", "1980", "9876543210", "0987"):  # digits (dates, numbers) are masked as #
        assert digits not in prompt
    assert "##/##/####" in prompt and "##########" in prompt
    assert "father" in call["system"].lower() and "husband" in call["system"].lower() and "found to false" in call["system"]


@pytest.mark.parametrize("reply", [
    {"found": False},
    {"found": True, "given_names": "Vikram 2", "surname": "Singh"},  # a digit
    {"found": True, "full_name": "9876543210"},  # a number
    {"found": True, "given_names": "Ramesh", "surname": "Singh"},  # a name that is not on the document (made up)
    {"found": True, "full_name": "Election Commission of India"},  # a header
    {"found": True, "full_name": "one two three four five six seven"},  # too many words
    {"found": True},  # no name at all
    {"found": "yes", "full_name": "Vikram Singh"},  # not a real boolean
    None,  # the model did not use the tool
])
async def test_invalid_llm_output_is_rejected(aws, reply):
    client = FakeClaude(reply)
    enable(client)
    r = await run(aws)
    assert r.found is False and "name_not_found" in r.warnings and len(client.calls) == 1


async def test_a_full_name_only_reply_is_accepted(aws):
    enable(FakeClaude({"found": True, "full_name": "Vikram Singh"}))
    r = await run(aws)
    assert r.found and r.full_name == "VIKRAM SINGH" and r.given_names is None


async def test_enabled_but_not_configured_warns_and_returns_not_found(aws):
    set_settings(make_settings(llm_fallback_enabled=True))  # no key, no model
    r = await run(aws)
    assert r.found is False and "llm_unavailable" in r.warnings and "name_not_found" in r.warnings


async def test_an_llm_api_failure_never_raises(aws):
    enable(FakeClaude(error=RuntimeError("boom")))
    r = await run(aws)
    assert r.found is False and "llm_unavailable" in r.warnings


async def test_the_llm_reply_is_never_logged(aws, caplog):
    import logging

    enable(FakeClaude(error=RuntimeError("Vikram Singh 9876543210")))
    with caplog.at_level(logging.DEBUG, logger="ezina_id_verify"):
        await run(aws)
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records if r.name.startswith("ezina_id_verify"))
    assert "Vikram" not in text and "9876543210" not in text and "RuntimeError" in text
