"""Short-lived integrity proof for unsaved local-model previews; no text in token."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException


def encoded(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def decoded(value):
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class SuggestionSigner:
    def __init__(self):
        self.key = secrets.token_bytes(32)

    @staticmethod
    def content_hash(kind, text, context, target_context, purpose):
        content = json.dumps({"kind": kind, "text": text, "context": context, "target_context": target_context, "purpose": purpose}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    def issue(self, actor_id, utterance_id, utterance_version, kind, text, context, target_context, purpose):
        payload = {"actor": actor_id, "source": utterance_id, "version": utterance_version, "kind": kind, "digest": self.content_hash(kind, text, context, target_context, purpose), "expires": int(time.time()) + 600}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return encoded(raw) + "." + encoded(hmac.new(self.key, raw, hashlib.sha256).digest())

    def verify(self, token, actor_id, utterance_id, utterance_version, kind, text, context, target_context, purpose):
        try:
            encoded_body, encoded_signature = token.split(".")
            raw, signature = decoded(encoded_body), decoded(encoded_signature)
            if not hmac.compare_digest(signature, hmac.new(self.key, raw, hashlib.sha256).digest()):
                raise ValueError("invalid signature")
            payload = json.loads(raw)
            expected = {"actor": actor_id, "source": utterance_id, "version": utterance_version, "kind": kind, "digest": self.content_hash(kind, text, context, target_context, purpose)}
            if set(payload) != {*expected, "expires"} or any(payload[key] != value for key, value in expected.items()):
                raise ValueError("invalid binding")
            if type(payload["expires"]) is not int or payload["expires"] <= time.time():
                raise ValueError("expired proof")
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            raise HTTPException(422, "模型建议证明已失效或内容被修改；可去除证明后以本人手写候选保存")
