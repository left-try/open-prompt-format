"""Explicit outbound publication of verified OPF releases."""

from __future__ import annotations

import base64
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .core import OPFError, VARIABLE_RE, parse
from .compatibility import CompatibilityFinding, CompatibilityReport
from .registry import Registry, RegisteredPrompt, _validate_bundle


def _langfuse_messages(bundle: dict) -> list[dict]:
    definition = bundle["definition"]
    if definition["renderer"] != "opf":
        raise OPFError("Langfuse cannot execute this Jinja2 bundle; export it or render it in Python")
    prompt = parse(bundle["files"][definition["source"]])
    messages = []
    for role, source in prompt.messages:
        if role == "developer":
            raise OPFError("Langfuse chat mapping does not support the OPF developer role")
        if "\\{{" in source:
            raise OPFError("Langfuse cannot preserve escaped literal {{ expressions")
        normalized = VARIABLE_RE.sub(lambda match: "{{" + match.group(1) + "}}", source)
        messages.append({"role": role, "content": normalized})
    return messages


def langfuse_plan(registry: Registry, prompt_id: str, version: str) -> dict:
    """Produce the exact remote payload or explain why this release cannot be mapped."""
    release = registry.get(prompt_id, version=version)
    bundle = release.bundle
    findings = []
    definition = bundle["definition"]
    prompt = None
    if definition["renderer"] != "opf":
        findings.append(CompatibilityFinding("renderer.jinja2.unsupported", "error", "manual", "Langfuse cannot execute this Jinja2 bundle"))
    else:
        prompt = parse(bundle["files"][definition["source"]])
        for role, content in prompt.messages:
            if role == "developer":
                findings.append(CompatibilityFinding("message.developer.unsupported", "error", "dropped", "Langfuse chat mapping does not support the OPF developer role", capability="developer-role"))
            if "\\{{" in content:
                findings.append(CompatibilityFinding("template.literal.unsupported", "error", "manual", "Langfuse cannot preserve escaped literal {{ expressions", capability="literal-template-delimiter"))
        for identifier, extension in prompt.extensions.items():
            if isinstance(extension, dict) and extension.get("required"):
                findings.append(CompatibilityFinding("extension.required.unsupported", "error", "manual", "Langfuse publication stores but does not execute required OPF extensions", capability=identifier))
    findings.extend([
        CompatibilityFinding("langfuse.input.required.not_enforced", "warning", "preserved", "Langfuse stores OPF input declarations but does not enforce required flags", capability="required-input-validation"),
        CompatibilityFinding("langfuse.bundle.size.limit", "warning", "preserved", "Large OPF bundles may exceed the remote prompt config size limit", capability="remote-config-size"),
    ])
    report = CompatibilityReport(
        source_kind="opf-registry",
        target_kind="langfuse",
        findings=tuple(findings),
        lossless=all(item.disposition == "preserved" for item in findings),
        can_apply=not any(item.severity == "error" for item in findings),
    )
    label = "opf-v" + version
    result = {"target": "langfuse", "id": prompt_id, "version": version, "digest": bundle["digest"], "label": label, "compatibility": report.to_dict(), "warnings": [item.message for item in findings if item.severity == "warning"]}
    if not report.can_apply:
        return result
    messages = _langfuse_messages(bundle)
    payload = {
        "name": prompt_id,
        "type": "chat",
        "prompt": messages,
        "config": {"opf": {"id": prompt_id, "version": version, "bundle_digest": bundle["digest"], "inputs": prompt.metadata.get("inputs", {}), "bundle": bundle}},
        "labels": [label],
    }
    result["payload"] = payload
    return result


def _remote_matches(remote: dict, plan: dict) -> bool:
    expected = plan["payload"]
    if remote.get("type") != "chat" or remote.get("prompt") != expected["prompt"]:
        return False
    config = remote.get("config")
    return isinstance(config, dict) and config.get("opf") == expected["config"]["opf"]


class LangfuseRegistry:
    """Explicit remote reader for canonical bundles stored in Langfuse config."""

    def __init__(self, *, base_url: str | None = None, public_key: str | None = None, secret_key: str | None = None):
        self.base, self.authorization = _credentials(base_url, public_key, secret_key)

    def get(self, prompt_id: str, *, channel: str | None = None, version: str | None = None, expected_digest: str | None = None) -> RegisteredPrompt:
        if channel and version:
            raise OPFError("choose either channel or version")
        label = channel or ("opf-v" + version if version else "production")
        endpoint = self.base + "/api/public/v2/prompts/" + quote(prompt_id, safe="") + "?" + urlencode({"label": label})
        status, remote = _request("GET", endpoint, self.authorization)
        if status == 404 or not isinstance(remote, dict):
            raise OPFError("Langfuse prompt {!r} with label {!r} was not found".format(prompt_id, label))
        config = remote.get("config")
        opf = config.get("opf") if isinstance(config, dict) else None
        if not isinstance(opf, dict) or "bundle" not in opf:
            raise OPFError("Langfuse prompt does not contain an OPF bundle")
        bundle = _validate_bundle(opf["bundle"])
        if bundle["id"] != prompt_id or bundle.get("digest") != opf.get("bundle_digest") or bundle.get("version") != opf.get("version") or remote.get("prompt") != _langfuse_messages(bundle):
            raise OPFError("Langfuse prompt differs from its OPF bundle")
        if expected_digest is not None and bundle["digest"] != expected_digest:
            raise OPFError("Langfuse bundle digest differs from the pinned local release")
        if version and bundle.get("version") != version:
            raise OPFError("Langfuse release version differs from requested version")
        return RegisteredPrompt(bundle, version=bundle.get("version"), channel=channel)


def _credentials(base_url: str | None, public_key: str | None, secret_key: str | None) -> tuple[str, str]:
    base = (base_url or os.environ.get("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com").rstrip("/")
    public = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        raise OPFError("set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY before publishing")
    if not base.startswith("https://") and not base.startswith("http://localhost:") and not base.startswith("http://127.0.0.1:"):
        raise OPFError("LANGFUSE_BASE_URL must use HTTPS, except for local development")
    authorization = "Basic " + base64.b64encode((public + ":" + secret).encode("utf-8")).decode("ascii")
    return base, authorization


def _request(method: str, url: str, authorization: str, body: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Authorization": authorization, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        if exc.code == 404 and method == "GET":
            return 404, None
        raise OPFError("Langfuse {} failed with HTTP {}: {}".format(method, exc.code, exc.read().decode("utf-8", errors="replace")[:400])) from exc
    except (URLError, TimeoutError) as exc:
        raise OPFError("Langfuse {} failed: {}".format(method, exc)) from exc


def publish_langfuse(plan: dict, *, base_url: str | None = None, public_key: str | None = None, secret_key: str | None = None) -> dict:
    """Publish once under a deterministic label, then verify the remote copy."""
    if not plan.get("payload") or not plan.get("compatibility", {}).get("can_apply", True):
        raise OPFError("Langfuse adapter cannot preserve required prompt capabilities; inspect the compatibility report")
    base, authorization = _credentials(base_url, public_key, secret_key)
    endpoint = base + "/api/public/v2/prompts"
    lookup = endpoint + "/" + quote(plan["id"], safe="") + "?" + urlencode({"label": plan["label"]})
    status, remote = _request("GET", lookup, authorization)
    created = False
    if status == 404:
        _request("POST", endpoint, authorization, plan["payload"])
        created = True
        for attempt in range(3):
            status, remote = _request("GET", lookup, authorization)
            if status != 404:
                break
            if attempt < 2:
                time.sleep(0.5)
    if status == 404 or not isinstance(remote, dict) or not _remote_matches(remote, plan):
        raise OPFError("Langfuse release label is missing or its content differs from the local release")
    return {"target": "langfuse", "id": plan["id"], "version": plan["version"], "digest": plan["digest"], "label": plan["label"], "remote_version": remote.get("version"), "created": created}
