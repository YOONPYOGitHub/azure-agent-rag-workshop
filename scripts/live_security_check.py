"""Real endpoint acceptance tests. Instructor-only; never prints keys.

Run after provision.py: uv run python scripts/live_security_check.py
Writes only status/timing/counts to .local/security-check.json.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def settings(name: str) -> dict:
    path = ROOT / ".local" / "attendees" / f"{name}.env"
    return dict(dotenv_values(path))


async def main() -> None:
    expected = [f"student{i:02d}" for i in range(1, 11)] + ["instructor"]
    configs = {name: settings(name) for name in expected}
    assert all(c.get("WORKSHOP_API_KEY") for c in configs.values()), "11 private env files required"
    assert len({c["WORKSHOP_API_KEY"] for c in configs.values()}) == 11, "Keys must be distinct"
    student = configs["student01"]
    base = student["AZURE_SEARCH_ENDPOINT"].rstrip("/")
    headers = {"Ocp-Apim-Subscription-Key": student["WORKSHOP_API_KEY"]}
    results = []
    async with httpx.AsyncClient(timeout=120) as client:
        probes = [
            (
                "cross_index_rest",
                "GET",
                f"{base}/indexes/student02?api-version=2024-07-01",
                headers,
                None,
                {403},
            ),
            (
                "cross_index_odata",
                "GET",
                f"{base}/indexes('student02')?api-version=2024-07-01",
                headers,
                None,
                {403},
            ),
            (
                "no_index_listing",
                "GET",
                f"{base}/indexes?api-version=2024-07-01",
                headers,
                None,
                {404},
            ),
            (
                "no_index_delete",
                "DELETE",
                f"{base}/indexes/student01?api-version=2024-07-01",
                headers,
                None,
                {404},
            ),
            (
                "missing_key",
                "POST",
                student["OPENAI_BASE_URL"].rstrip("/") + "/responses",
                {},
                {"model": "gpt-5.6-terra", "input": "hello", "store": False},
                {401},
            ),
            (
                "wrong_model",
                "POST",
                student["OPENAI_BASE_URL"].rstrip("/") + "/responses",
                headers,
                {"model": "not-allowed", "input": "hello", "store": False},
                {400, 403},
            ),
            (
                "no_server_history",
                "GET",
                student["OPENAI_BASE_URL"].rstrip("/") + "/responses/test-id",
                headers,
                None,
                {404},
            ),
        ]
        inference_url = student["OPENAI_BASE_URL"].rstrip("/") + "/responses"
        for name, changes in [
            ("no_previous_response", {"previous_response_id": "resp_other"}),
            ("no_hosted_tools", {"tools": [{"type": "web_search"}]}),
            ("bounded_output", {"max_output_tokens": 1501}),
        ]:
            probes.append(
                (
                    name,
                    "POST",
                    inference_url,
                    headers,
                    {"model": "gpt-5.6-terra", "input": "hello", "store": False, **changes},
                    {400, 403},
                )
            )
        probes.append(
            (
                "key_cannot_use_other_api",
                "POST",
                inference_url.replace("/agent-rag/openai/", "/openai/"),
                headers,
                {
                    "model": "gpt-5.6-terra",
                    "input": "hello",
                    "store": False,
                    "max_output_tokens": 32,
                },
                {401, 403},
            )
        )
        for name, method, url, request_headers, body, allowed in probes:
            response = await client.request(method, url, headers=request_headers, json=body)
            record = {
                "test": name,
                "status": response.status_code,
                "pass": response.status_code in allowed,
            }
            results.append(record)
            print(json.dumps(record))

        async def participant(name: str) -> dict:
            c = configs[name]
            start = time.monotonic()
            r = await client.post(
                c["OPENAI_BASE_URL"].rstrip("/") + "/responses",
                headers={"Ocp-Apim-Subscription-Key": c["WORKSHOP_API_KEY"]},
                json={
                    "model": "gpt-5.6-terra",
                    "input": "Reply exactly READY",
                    "max_output_tokens": 64,
                    "store": False,
                },
            )
            data = r.json()
            text = " ".join(
                part.get("text", "")
                for item in data.get("output", [])
                for part in item.get("content", [])
            )
            return {
                "test": f"concurrent_{name}",
                "status": r.status_code,
                "pass": r.status_code == 200 and "READY" in text,
                "seconds": round(time.monotonic() - start, 2),
                "model": data.get("model"),
            }

        concurrent = await asyncio.gather(*(participant(n) for n in expected if n != "instructor"))
        results.extend(concurrent)
        for record in concurrent:
            print(json.dumps(record))
    output = ROOT / ".local/security-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"results": results, "all_passed": all(r["pass"] for r in results)}, indent=2)
        + "\n"
    )
    assert all(r["pass"] for r in results), f"Failed acceptance checks: {output}"


if __name__ == "__main__":
    asyncio.run(main())
