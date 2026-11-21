import shutil
from pathlib import Path

import pytest

from slacheck.apex import (blank_strings, lint_project, lint_source, looks_like_id,
                           parse_sla_table, strip_comments)
from slacheck.cli import main

ROOT = Path(__file__).resolve().parent.parent
BAD = ROOT / "examples" / "bad_project"


def rules(findings):
    return {f.rule for f in findings}


def test_clean_project_has_no_findings():
    assert lint_project(ROOT) == []


def test_bad_project_reports_expected_rules():
    found = rules(lint_project(BAD))
    for rule in ("soql-in-loop", "dml-in-loop", "hardcoded-id", "sharing", "see-all-data",
                 "test-asserts", "no-bulk-test", "api-version", "status", "unknown-field"):
        assert rule in found


def test_sla_table_parsed_from_real_class():
    text = (ROOT / "force-app/main/default/classes/ServiceTicketSlaService.cls").read_text(encoding="utf-8")
    assert parse_sla_table(text) == {"Critical": 4, "High": 8, "Normal": 24, "Low": 72}


def test_sla_table_missing_returns_empty():
    assert parse_sla_table("public class A {}") == {}


def test_strip_comments_keeps_line_numbers():
    src = "a // note\n/* x\ny */ b\n"
    out = strip_comments(src)
    assert out.count("\n") == src.count("\n")
    assert "note" not in out and "b" in out


def test_strip_comments_keeps_slashes_in_strings():
    assert "//" in strip_comments("String s = 'http://x';")


def test_blank_strings_hides_keywords():
    assert "update" not in blank_strings("String s = 'update me';")


def test_looks_like_id():
    assert looks_like_id("001000000000001AAA")
    assert not looks_like_id("Critical")


def test_soql_in_loop_detected():
    src = "public with sharing class A { void f(){ for (Integer i : l) { x = [SELECT Id FROM Account]; } } }"
    assert "soql-in-loop" in rules(lint_source("A.cls", src, False))


def test_query_outside_loop_is_fine():
    src = "public with sharing class A { void f(){ x = [SELECT Id FROM Account]; } }"
    assert "soql-in-loop" not in rules(lint_source("A.cls", src, False))


def test_keyword_inside_string_is_ignored():
    src = "public with sharing class A { void f(){ for (Integer i : l) { s = 'update x'; } } }"
    assert "dml-in-loop" not in rules(lint_source("A.cls", src, False))


def test_trigger_with_logic_is_flagged():
    src = "trigger T on Account (before insert) { for (Account a : Trigger.new) { update a; } }"
    assert "logic-in-trigger" in rules(lint_source("T.trigger", src, True))


def test_cli_lint_clean_exit_zero(capsys):
    assert main(["lint", str(ROOT)]) == 0
    assert "0 finding(s)" in capsys.readouterr().out


def test_cli_lint_bad_exit_one(capsys):
    assert main(["lint", str(BAD)]) == 1
    assert "13 finding(s)" in capsys.readouterr().out


def test_cli_missing_folder_exit_two(capsys):
    assert main(["lint", str(ROOT / "nope")]) == 2


def test_cli_table(capsys):
    assert main(["table", str(ROOT)]) == 0
    assert "Critical" in capsys.readouterr().out


def test_cli_due_and_unknown_priority(capsys):
    assert main(["due", "--priority", "High", "--opened", "2026-11-20 09:00", "--path", str(ROOT)]) == 0
    assert "due 2026-11-20 17:00" in capsys.readouterr().out
    assert main(["due", "--priority", "Urgent", "--opened", "2026-11-20 09:00", "--path", str(ROOT)]) == 0
    assert "Urgent -> Normal" in capsys.readouterr().out


def test_cli_due_bad_date(capsys):
    assert main(["due", "--priority", "High", "--opened", "yesterday", "--path", str(ROOT)]) == 2


def test_missing_meta_file_is_flagged(tmp_path):
    shutil.copytree(ROOT / "force-app", tmp_path / "force-app")
    (tmp_path / "force-app/main/default/triggers/ServiceTicketSlaTrigger.trigger-meta.xml").unlink()
    assert "meta-file" in rules(lint_project(tmp_path))


def test_wrong_class_name_is_flagged(tmp_path):
    shutil.copytree(ROOT / "force-app", tmp_path / "force-app")
    p = tmp_path / "force-app/main/default/classes/ServiceTicketSlaService.cls"
    p.write_text(p.read_text(encoding="utf-8").replace("class ServiceTicketSlaService", "class Other"), encoding="utf-8")
    assert "class-name" in rules(lint_project(tmp_path))
