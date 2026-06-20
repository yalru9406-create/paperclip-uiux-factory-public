#!/usr/bin/env python3
from __future__ import annotations

import os

from server import AUTH_TOKEN_ENV, AgentCliHandler, request_token


class FakeHandler:
    def __init__(self, headers: dict[str, str], client_address: tuple[str, int] = ("127.0.0.1", 0)) -> None:
        self.headers = headers
        self.client_address = client_address


def test_public_forwarded_for_is_not_loopback() -> None:
    handler = FakeHandler({"X-Yalru-Internal-Proxy": "1", "X-Forwarded-For": "203.0.113.10"}, ("127.0.0.1", 42192))
    assert AgentCliHandler.is_loopback_request(handler) is False


def test_spoofed_forwarded_for_is_not_loopback() -> None:
    handler = FakeHandler({"X-Yalru-Internal-Proxy": "1", "X-Forwarded-For": "127.0.0.1"}, ("127.0.0.1", 42192))
    assert AgentCliHandler.is_loopback_request(handler) is False


def test_loopback_forwarded_for_is_loopback() -> None:
    handler = FakeHandler({"X-Forwarded-For": "127.0.0.1"}, ("127.0.0.1", 42192))
    assert AgentCliHandler.is_loopback_request(handler) is True


def test_bearer_and_header_tokens_are_supported() -> None:
    assert request_token(FakeHandler({"Authorization": "Bearer local-token"})) == "local-token"
    assert request_token(FakeHandler({"X-Yalru-Agent-Token": "local-token"})) == "local-token"


def test_valid_token_requires_configured_secret() -> None:
    original = os.environ.pop(AUTH_TOKEN_ENV, None)
    try:
        handler = FakeHandler({"Authorization": "Bearer local-token"}, ("203.0.113.10", 42192))
        assert AgentCliHandler.has_valid_token(handler) is False
        os.environ[AUTH_TOKEN_ENV] = "local-token"
        assert AgentCliHandler.has_valid_token(handler) is True
    finally:
        if original is None:
            os.environ.pop(AUTH_TOKEN_ENV, None)
        else:
            os.environ[AUTH_TOKEN_ENV] = original


def main() -> int:
    test_public_forwarded_for_is_not_loopback()
    test_spoofed_forwarded_for_is_not_loopback()
    test_loopback_forwarded_for_is_loopback()
    test_bearer_and_header_tokens_are_supported()
    test_valid_token_requires_configured_secret()
    print('{"ok": true, "privateAccessGuard": true}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
