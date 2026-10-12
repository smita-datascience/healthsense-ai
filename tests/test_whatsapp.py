"""Tests for the WhatsApp channel. No network, no LLM: the crew and the
Meta send call are replaced with fakes.

Run:  python -m pytest tests/test_whatsapp.py -v
"""
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.settings import settings
from app.whatsapp import routes
from app.whatsapp.client import split_text
from app.whatsapp.dedup import SeenMessages
from app.whatsapp.security import pseudonymous_user_id, verify_signature

SECRET = "test-app-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", SECRET)
    monkeypatch.setattr(settings, "whatsapp_verify_token", "my-verify-token")
    monkeypatch.setattr(routes, "seen_messages", SeenMessages())
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing WhatsApp messages and fake the crew."""
    outbox = []
    monkeypatch.setattr(routes, "send_text", lambda to, body: outbox.append((to, body)))
    import sys, types

    fake_crew = types.ModuleType("app.agents.crew")
    fake_crew.answer = lambda q, user_id: f"ANSWER[{q}] for {user_id}"
    monkeypatch.setitem(sys.modules, "app.agents.crew", fake_crew)
    return outbox


def signed_post(client, payload: dict, secret: str = SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )


def text_payload(msg_id="wamid.1", sender="919800000000", text="What is anaemia?"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"id": msg_id, "from": sender, "type": "text", "text": {"body": text}}
        ]}}]}],
    }


# --- handshake -------------------------------------------------------------

def test_handshake_echoes_challenge(client):
    r = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "my-verify-token", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"


def test_handshake_rejects_wrong_token(client):
    r = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert r.status_code == 403


def test_handshake_rejects_when_token_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "")
    r = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "42"})
    assert r.status_code == 403


# --- signature (fail-closed) ----------------------------------------------

def test_signature_valid_and_invalid():
    body = b'{"a":1}'
    good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, good, "s")
    assert not verify_signature(body + b" ", good, "s")      # tampered body
    assert not verify_signature(body, good, "other")         # wrong secret
    assert not verify_signature(body, None, "s")             # missing header
    assert not verify_signature(body, good, "")              # secret not configured


def test_unsigned_post_is_rejected_and_crew_not_called(client, sent):
    r = client.post("/webhook/whatsapp", json=text_payload())
    assert r.status_code == 403
    assert sent == []


# --- message flow ----------------------------------------------------------

def test_text_message_is_answered_with_pseudonymous_id(client, sent):
    r = signed_post(client, text_payload())
    assert r.status_code == 200
    assert len(sent) == 1
    to, body = sent[0]
    assert to == "919800000000"                               # reply goes to the real number
    assert pseudonymous_user_id("919800000000") in body      # memory sees only the hash
    assert "919800000000" not in body


def test_duplicate_delivery_answered_once(client, sent):
    signed_post(client, text_payload(msg_id="wamid.dup"))
    signed_post(client, text_payload(msg_id="wamid.dup"))
    assert len(sent) == 1


def test_status_update_is_ignored(client, sent):
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]}
    assert signed_post(client, payload).status_code == 200
    assert sent == []


def test_non_text_gets_polite_reply(client, sent):
    payload = text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
    signed_post(client, payload)
    assert sent and sent[0][1] == routes.NON_TEXT_REPLY


def test_crew_failure_sends_fallback(client, sent, monkeypatch):
    import sys
    def boom(q, user_id):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(sys.modules["app.agents.crew"], "answer", boom)
    signed_post(client, text_payload())
    assert sent and sent[0][1] == routes.FALLBACK_REPLY


# --- helpers ---------------------------------------------------------------

def test_split_text_respects_limit_and_keeps_content():
    text = ("word " * 2000).strip()
    chunks = split_text(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_pseudonymous_id_is_stable_and_hides_number():
    a = pseudonymous_user_id("919800000000")
    assert a == pseudonymous_user_id("919800000000")
    assert "9198" not in a and a.startswith("wa_")
