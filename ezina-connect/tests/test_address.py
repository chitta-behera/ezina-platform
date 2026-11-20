"""Farm address: one full_address_text, country examples, completeness follow-ups, correction at review."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.enums import Intent
from app.models import Farm
from app.schemas.ai_response import AIResponse, Correction, tool_input_schema
from app.services.claude_service import build_user_message
from app.workflows import address_flow
from tests.conftest import BW_ADDRESS, make_ai

ADMIN = {"X-API-Key": "test-admin-key"}


async def draft(env) -> dict:
    return (await env.conv()).draft


async def at_address_stage(env, country: str):
    """Registration up to the address question for the given country (Claude's own wording is not used)."""
    await env.run_registration_until("name")
    env.claude.push(make_ai(country=country, text="Which country? Ok. What is your address?"))
    await env.text(country)
    assert await env.stage() == "COLLECT_FARM_DETAILS"


def followups_asked(env) -> int:
    return sum("Please send only that part" in t for t in env.graph.texts())


# ------------------------------------------------------------------ question wording and config
def test_config_has_the_required_countries_and_a_default():
    assert address_flow.format_for("IN").expected == ("village/town", "district", "state", "PIN code")
    assert address_flow.format_for("IN").helpful == ("plot/survey number", "landmark")
    assert address_flow.format_for("BW").expected == ("village/town", "district")
    assert address_flow.format_for("BW").helpful == ("plot number", "landmark", "ward")
    assert address_flow.format_for("KE").expected == ("sub-county", "county", "plot number or landmark")
    assert address_flow.format_for("KE").helpful == ("village", "ward")
    assert address_flow.format_for("IN").example == (
        "Survey No. 45, near Hanuman temple, Shirur village, Pune district, Maharashtra 412210")
    assert address_flow.format_for("BW").example == "Plot 1234, near Mogoditshane clinic, Mogoditshane, Kweneng District"
    assert address_flow.format_for("KE").example.startswith("Plot No. Nyeri/Gikondi/1234, near Gikondi Primary School")
    other = address_flow.format_for("ZA")  # any other country -> the default
    assert other is address_flow.format_for(None) and other.expected == ("village/town", "district")
    assert other.helpful == ("landmark", "postal code")


@pytest.mark.parametrize("country,code", [("India", "IN"), ("Botswana", "BW"), ("Kenya", "KE"), ("Zambia", None)])
async def test_question_is_the_full_address_with_the_countrys_example(env, country, code):
    await at_address_stage(env, country)
    fmt = address_flow.format_for(code)
    q = env.graph.texts()[-1]
    assert "What is the full address of your farm?" in q and fmt.instruction in q and fmt.example in q
    assert "village or town and district" not in q


async def test_claude_gets_the_example_and_expected_parts_for_the_country(env):
    await at_address_stage(env, "Kenya")
    env.claude.push(make_ai(full_address_text="Plot 9, Gikondi, Mukurwe-ini sub-county, Nyeri County"))
    await env.text("Plot 9, Gikondi, Mukurwe-ini sub-county, Nyeri County")
    ctx = env.claude.contexts[-1]
    assert ctx.address["expected_parts"] == ["sub-county", "county", "plot number or landmark"]
    assert ctx.address["example"] == address_flow.format_for("KE").example
    assert '"address_format"' in build_user_message(ctx)


def test_address_missing_parts_is_in_the_ai_response_schema():
    assert "address_missing_parts" in tool_input_schema()["properties"]
    assert AIResponse(intent=Intent.PROVIDE_INFORMATION, address_missing_parts=None).address_missing_parts == []


# ------------------------------------------------------------------ full address in one message
@pytest.mark.parametrize("country,text", [
    ("India", "Survey No. 7, near the school, Shirur village, Pune district, Maharashtra 412210"),
    ("Botswana", BW_ADDRESS),
    ("Kenya", "Plot No. 12, near Gikondi Primary School, Mukurwe-ini sub-county, Nyeri County"),
])
async def test_full_address_in_one_message_is_saved_as_one_text(env, country, text):
    await at_address_stage(env, country)
    env.claude.push(make_ai(full_address_text=text, text="What crops do you grow at the moment?"))
    await env.text(text)
    d = await draft(env)
    assert d["full_address_text"] == text and d["address_followups"] == 0 and d["address_missing"] == []
    assert await env.stage() == "COLLECT_CROPS"
    assert followups_asked(env) == 0


# ------------------------------------------------------------------ missing parts
async def test_missing_part_asks_only_for_that_part_then_combines_into_one_text(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Plot 77, near the clinic, Mogoditshane", address_missing=["district"]))
    await env.text("Plot 77, near the clinic, Mogoditshane")
    assert await env.stage() == "COLLECT_FARM_DETAILS"
    q = env.graph.texts()[-1]
    assert "*district*" in q and "village" not in q.lower() and "Plot 77" not in q  # only the missing part
    d = await draft(env)
    assert d["address_followups"] == 1 and d["address_missing"] == ["district"]

    env.claude.push(make_ai(full_address_text="Kweneng District", text="What crops do you grow?"))
    await env.text("Kweneng District")
    ctx = env.claude.contexts[-1]  # Claude was told this is a follow-up, with what was already given
    assert ctx.address["address_so_far"] == "Plot 77, near the clinic, Mogoditshane" and ctx.address["asked_for"] == ["district"]
    d = await draft(env)
    assert d["full_address_text"] == "Plot 77, near the clinic, Mogoditshane, Kweneng District"
    assert d["address_missing"] == [] and await env.stage() == "COLLECT_CROPS"
    assert followups_asked(env) == 1


async def test_follow_up_names_several_missing_parts_but_never_helpful_or_unknown_ones(env):
    await at_address_stage(env, "India")
    env.claude.push(make_ai(full_address_text="Shirur village near the temple",
                            address_missing=["district", "PIN code", "landmark", "street"]))  # landmark/street: not expected
    await env.text("Shirur village near the temple")
    assert "*district and PIN code*" in env.graph.texts()[-1]
    assert (await draft(env))["address_missing"] == ["district", "PIN code"]


async def test_follow_up_answer_that_repeats_the_whole_address_is_not_duplicated(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Plot 77, Mogoditshane", address_missing=["district"]))
    await env.text("Plot 77, Mogoditshane")
    env.claude.push(make_ai(full_address_text="Plot 77, Mogoditshane, Kweneng District"))
    await env.text("Plot 77, Mogoditshane, Kweneng District")
    assert (await draft(env))["full_address_text"] == "Plot 77, Mogoditshane, Kweneng District"


# ------------------------------------------------------------------ landmark, length, limits
async def test_landmark_only_address_is_accepted(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Near the Mogoditshane clinic", text="What crops do you grow?"))
    await env.text("Near the Mogoditshane clinic")
    assert (await draft(env))["full_address_text"] == "Near the Mogoditshane clinic"
    assert await env.stage() == "COLLECT_CROPS" and followups_asked(env) == 0


async def test_address_shorter_than_10_characters_is_not_accepted(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Gaborone"))  # 8 characters
    await env.text("Gaborone")
    assert (await draft(env))["full_address_text"] is None and await env.stage() == "COLLECT_FARM_DETAILS"
    assert "couldn't understand the address" in env.graph.texts()[-1] and address_flow.format_for("BW").example in env.graph.texts()[-1]


async def test_after_two_follow_ups_the_address_is_accepted_as_given(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Near the old baobab tree", address_missing=["village/town", "district"]))
    await env.text("Near the old baobab tree")
    env.claude.push(make_ai(full_address_text="by the river", address_missing=["district"]))
    await env.text("by the river")
    assert followups_asked(env) == 2 and await env.stage() == "COLLECT_FARM_DETAILS"
    env.claude.push(make_ai(full_address_text="the red gate", address_missing=["district"], text="What crops do you grow?"))
    await env.text("the red gate")
    assert followups_asked(env) == 2  # no third question
    d = await draft(env)
    assert d["full_address_text"] == "Near the old baobab tree, by the river, the red gate"
    assert d["address_missing"] == [] and await env.stage() == "COLLECT_CROPS"


async def test_replies_that_give_nothing_also_count_towards_the_limit(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text="Plot 77, Mogoditshane", address_missing=["district"]))
    await env.text("Plot 77, Mogoditshane")
    env.claude.push(make_ai(Intent.PROVIDE_INFORMATION))  # "I don't know": nothing extracted -> asked once more
    await env.text("I don't know")
    assert followups_asked(env) == 2 and await env.stage() == "COLLECT_FARM_DETAILS"
    env.claude.push(make_ai(Intent.PROVIDE_INFORMATION))  # limit reached: accepted as given
    await env.text("I really don't know")
    assert (await draft(env))["full_address_text"] == "Plot 77, Mogoditshane" and await env.stage() == "COLLECT_CROPS"


async def test_parts_are_not_stored_anywhere(env):
    await at_address_stage(env, "Botswana")
    env.claude.push(make_ai(full_address_text=BW_ADDRESS))
    await env.text(BW_ADDRESS)
    d = await draft(env)
    assert not {"village", "district", "farm_address", "address_parts"} & set(d)
    assert "village" not in Farm.__table__.columns and "district" not in Farm.__table__.columns


# ------------------------------------------------------------------ review, correction, submission
async def test_review_shows_one_address_line(env):
    await env.run_registration_until("crop_skip")
    body = env.graph.last()["interactive"]["body"]["text"]
    assert f"*Address:* {BW_ADDRESS}" in body and "Village/Town" not in body


async def test_correction_at_review_replaces_the_address_only_after_the_farmer_confirms(env):
    await env.run_registration_until("crop_skip")
    new = "Plot 1234, near Mogoditshane clinic, Mogoditshane, Kiambu District"
    env.claude.push(make_ai(Intent.CORRECT_INFORMATION, corrections=[Correction(field="full_address_text", new_value=new)]))
    await env.text("change the district to Kiambu")
    assert "Is that right?" in env.graph.texts()[-1] and new in env.graph.texts()[-1]
    assert (await draft(env))["full_address_text"] == BW_ADDRESS  # not replaced yet
    await env.button("confirm_yes", "Yes")
    assert (await draft(env))["full_address_text"] == new
    assert await env.stage() == "REVIEW_REGISTRATION" and f"*Address:* {new}" in env.graph.texts()[-1]


async def test_declined_correction_keeps_the_old_address(env):
    await env.run_registration_until("crop_skip")
    env.claude.push(make_ai(Intent.CORRECT_INFORMATION, corrections=[
        Correction(field="full_address_text", new_value="Plot 1, Gaborone, South East District")]))
    await env.text("my address is different")
    await env.button("confirm_no", "No")
    assert (await draft(env))["full_address_text"] == BW_ADDRESS


async def test_submission_saves_full_address_text_and_admin_shows_it(env):
    await env.run_registration_until("confirm")
    (farm,) = await env.all(Farm)
    assert farm.full_address_text == BW_ADDRESS
    f = await env.farmer()
    body = (await env.client.get(f"/api/admin/farmers/{f.id}", headers=ADMIN)).json()
    assert body["farms"][0]["full_address_text"] == BW_ADDRESS
    assert not {"village", "district", "address"} & set(body["farms"][0])


# ------------------------------------------------------------------ migration 0003
def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    root = Path(__file__).resolve().parent.parent
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, env=env, capture_output=True, text=True)


def _farm_cols(db: Path) -> dict[str, int]:
    with sqlite3.connect(db) as c:
        return {r[1]: r[3] for r in c.execute("pragma table_info(farms)")}  # name -> notnull


def test_migration_0003_replaces_village_district_address_with_full_address_text(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # the farms table as it was before this change
        c.execute("create table farms (id CHAR(32) primary key, farmer_id CHAR(32), name varchar(200), "
                  "village varchar(200), district varchar(200), address varchar(500), "
                  "created_at datetime, updated_at datetime)")
        c.execute("insert into farms (id, name, village, district, address) values ('a', 'F', 'Gaborone', 'South East', 'Plot 12')")
        c.execute("insert into farms (id, name, village, district) values ('b', 'G', 'Shirur', 'Pune')")
    assert _alembic(db, "stamp", "0002").returncode == 0
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    cols = _farm_cols(db)
    assert cols["full_address_text"] == 1  # NOT NULL
    assert not {"village", "district", "address"} & set(cols)
    with sqlite3.connect(db) as c:  # existing rows keep what they had, as one text
        assert dict(c.execute("select id, full_address_text from farms")) == {"a": "Plot 12", "b": "Shirur Pune"}
    assert _alembic(db, "downgrade", "0002").returncode == 0  # reversible
    cols = _farm_cols(db)
    assert {"village", "district", "address"} <= set(cols) and "full_address_text" not in cols


def test_migration_0003_on_a_fresh_database_is_a_no_op_after_0001(tmp_path):
    db = tmp_path / "fresh.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    cols = _farm_cols(db)
    assert cols["full_address_text"] == 1 and not {"village", "district", "address"} & set(cols)
    assert _alembic(db, "upgrade", "head").returncode == 0
