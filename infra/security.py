"""Shared route contract for the provisioner and offline security tests."""

import copy
import html
import json
import re
from pathlib import Path


def render_policy(foundry_endpoint, search_endpoint):
    """Only trusted Azure hosts; route allowlist is generated, never prefix-based."""
    for endpoint, suffix in [
        (foundry_endpoint, r"openai\.azure\.com"),
        (search_endpoint, r"search\.windows\.net"),
    ]:
        if not re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\." + suffix, endpoint):
            raise ValueError("Backend must be an Azure service origin, without a path")
    names = " || ".join(f'name == "{n}"' for n in ATTENDEES)
    routes = []
    for _, method, path in OPERATIONS:
        expression = json.dumps("/" + API_PATH + path).replace("{indexName}", '" + name + "')
        routes.append(f'(context.Request.Method == "{method}" && path == {expression})')
    guard = (
        "@{ if (context.Subscription == null) { return true; } var name = context.Subscription.Name; var path = context.Request.OriginalUrl.Path; return !(("
        + names
        + ") && ("
        + " || ".join(routes)
        + ")); }"
    )
    template = Path(__file__).with_name("apim-policy.xml.tpl").read_text()
    return (
        template.replace("{{DENY_ROUTE}}", html.escape(guard, quote=True))
        .replace("{{FOUNDRY_ENDPOINT}}", foundry_endpoint)
        .replace("{{SEARCH_ENDPOINT}}", search_endpoint)
    )


def validate_openai(operation, body):
    """Offline executable contract mirror. APIM enforces the XML, not this helper."""
    b = copy.deepcopy(body)
    embedding = operation == "embeddings"
    allowed = (
        {"model", "input", "dimensions", "encoding_format", "user"}
        if embedding
        else {
            "model",
            "input",
            "instructions",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "max_output_tokens",
            "temperature",
            "top_p",
            "stream",
            "text",
            "reasoning",
            "store",
            "metadata",
            "user",
            "include",
        }
    )
    if (
        not isinstance(b, dict)
        or set(b) - allowed
        or b.get("model") != (EMBEDDING if embedding else MODEL)
    ):
        raise ValueError("Invalid fields or model")
    value = b.get("input")
    if (
        not isinstance(value, (str, list))
        or not value
        or len(value if isinstance(value, str) else json.dumps(value)) > 24000
    ):
        raise ValueError("Invalid input")
    if embedding:
        if isinstance(value, list) and (
            len(value) > 16 or any(not isinstance(x, str) or not x for x in value)
        ):
            raise ValueError("Invalid embedding batch")
        if type(b.get("dimensions", 1536)) is not int or b.get("dimensions", 1536) != 1536:
            raise ValueError("Invalid dimensions")
        b["dimensions"] = 1536
    else:
        if "include" in b and b["include"] not in ([], ["reasoning.encrypted_content"]):
            raise ValueError("Only stateless encrypted reasoning include is allowed")
        if isinstance(value, list):
            if len(value) > 100:
                raise ValueError("Too many messages")
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError("Invalid item")  # noqa: TRY004 — unified invalid-request contract
                kind = item.get("type", "message")
                fields = {
                    "message": {"type", "role", "content"},
                    "function_call": {"type", "id", "call_id", "name", "arguments", "status"},
                    "function_call_output": {"type", "call_id", "output", "status"},
                    "reasoning": {"type", "id", "summary", "encrypted_content", "status"},
                }
                if kind not in fields or set(item) - fields[kind]:
                    raise ValueError("Hosted or referenced item")
                if kind == "message":
                    content = item.get("content")
                    if item.get("role") not in {
                        "user",
                        "assistant",
                        "system",
                        "developer",
                    } or not isinstance(content, (str, list)):
                        raise ValueError("Invalid message")
                    if isinstance(content, list) and any(
                        not isinstance(p, dict)
                        or p.get("type") not in {"input_text", "output_text"}
                        or not isinstance(p.get("text"), str)
                        or set(p) - {"type", "text", "annotations", "logprobs"}
                        for p in content
                    ):
                        raise ValueError("Only text content allowed")
                if kind == "function_call_output" and not isinstance(item.get("output"), str):
                    raise ValueError("Invalid tool output")
                if kind == "reasoning" and (
                    not isinstance(item.get("encrypted_content"), str)
                    or not item["encrypted_content"]
                    or not isinstance(item.get("summary"), list)
                ):
                    raise ValueError("Reasoning must be supplied inline, not by reference")
        if "instructions" in b and (
            not isinstance(b["instructions"], str) or len(b["instructions"]) > 12000
        ):
            raise ValueError("Invalid instructions")
        tools = b.get("tools", [])
        if (
            not isinstance(tools, list)
            or len(tools) > 16
            or any(
                not isinstance(t, dict)
                or t.get("type") != "function"
                or set(t) - {"type", "name", "description", "parameters", "strict"}
                for t in tools
            )
        ):
            raise ValueError("Only function tools allowed")
        choice = b.get("tool_choice", "auto")
        if not (
            (isinstance(choice, str) and choice in {"auto", "none", "required"})
            or (
                isinstance(choice, dict)
                and choice.get("type") == "function"
                and not set(choice) - {"type", "name"}
            )
        ):
            raise ValueError("Invalid tool choice")
        tokens = b.get("max_output_tokens", 1500)
        if type(tokens) is not int or not 1 <= tokens <= 1500:
            raise ValueError("Invalid output bound")
        b.update(store=False, max_output_tokens=tokens)
    return b


ATTENDEES = tuple(f"student{i:02d}" for i in range(1, 11)) + ("instructor",)
API_ID = "agent-rag-workshop"
API_PATH = "agent-rag"
MODEL = "gpt-5.6-terra"
EMBEDDING = "text-embedding-3-small"

# Both canonical REST and the actual azure-search-documents OData routes.
OPERATIONS = [
    ("responses", "POST", "/openai/v1/responses"),
    ("embeddings", "POST", "/openai/v1/embeddings"),
]
for style, index in [
    ("rest", "/search/indexes/{indexName}"),
    ("odata", "/search/indexes('{indexName}')"),
]:
    for op, method, suffix in [
        ("get-index", "GET", ""),
        ("put-index", "PUT", ""),
        ("index-docs", "POST", "/docs/index"),
        ("search-docs", "POST", "/docs/search"),
        ("sdk-index-docs", "POST", "/docs/search.index"),
        ("sdk-search-docs", "POST", "/docs/search.post.search"),
        ("count", "GET", "/docs/$count"),
    ]:
        OPERATIONS.append((f"{style}-{op}", method, index + suffix))


def authorize_route(subscription_name, method, path):
    """Exact paths only: no decoding, wildcards, prefix checks, or query strings."""
    return subscription_name in ATTENDEES and any(
        method == verb and path == template.replace("{indexName}", subscription_name)
        for _, verb, template in OPERATIONS
    )
