"""Unit tests for cookie parsing and BrowserGuardrailTarget."""

import pytest
from reverse_guardrail.core.models import TargetScopeConfig
from reverse_guardrail.guardrail.browser_target import BrowserGuardrailTarget, parse_cookies


def test_parse_cookies_list_of_dicts():
    input_cookies = [
        {"name": "session_id", "value": "xyz123", "domain": "example.com", "path": "/"},
        {"name": "auth_token", "value": "tok999"},
    ]
    cookies = parse_cookies(input_cookies, "https://example.com/chat")
    assert len(cookies) == 2
    assert cookies[0]["name"] == "session_id"
    assert cookies[0]["value"] == "xyz123"
    assert cookies[1]["domain"] == "example.com"
    assert cookies[1]["path"] == "/"


def test_parse_cookies_json_string():
    json_str = '[{"name": "jwt", "value": "abc.def.ghi"}]'
    cookies = parse_cookies(json_str, "https://app.nexustech.internal")
    assert len(cookies) == 1
    assert cookies[0]["name"] == "jwt"
    assert cookies[0]["domain"] == "app.nexustech.internal"


def test_parse_cookies_header_string():
    header_str = "session=12345; user_id=admin_99; theme=dark"
    cookies = parse_cookies(header_str, "https://target.ai/dashboard")
    assert len(cookies) == 3
    names = {c["name"] for c in cookies}
    assert names == {"session", "user_id", "theme"}


def test_browser_target_initialization():
    scope = TargetScopeConfig(
        authorized=True,
        engagement_id="ENG-BROWSER-TEST",
        target_name="Browser Test Target",
        target_url="https://chat.target.internal",
        use_browser=True,
        cookies="token=secret123",
        input_selector="#user-input",
        submit_selector="#send-btn",
        response_selector=".bot-msg",
        headless=True,
    )
    target = BrowserGuardrailTarget(scope_config=scope)
    assert target.target_url == "https://chat.target.internal"
    assert len(target.cookies) == 1
    assert target.cookies[0]["name"] == "token"
    assert target.input_selector == "#user-input"
