"""Offline contract tests; live APIM validation is still required after apply."""

import importlib.util
import pathlib
import sys
import unittest

INFRA = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))


class SecurityTests(unittest.TestCase):
    def test_subscription_index_boundary_and_sdk_routes(self):
        self.assertIsNotNone(importlib.util.find_spec("security"), "security module must exist")
        from security import authorize_route

        for name in ["student01", "student10", "instructor"]:
            for method, tail in [
                ("GET", ""),
                ("PUT", ""),
                ("POST", "/docs/search.index"),
                ("POST", "/docs/search.post.search"),
                ("GET", "/docs/$count"),
            ]:
                self.assertTrue(authorize_route(name, method, f"/search/indexes('{name}'){tail}"))
            self.assertTrue(authorize_route(name, "POST", f"/search/indexes/{name}/docs/search"))
            for other in [
                "student02",
                "../student01",
                "student01%2f..",
                "student01')/docs/search.index?x=",
                "STUDENT01",
            ]:
                if other != name:
                    self.assertFalse(authorize_route(name, "PUT", f"/search/indexes/{other}"))
        self.assertFalse(authorize_route("student11", "POST", "/openai/v1/responses"))
        self.assertFalse(authorize_route("student01", "DELETE", "/search/indexes/student01"))
        self.assertFalse(authorize_route("student01", "GET", "/search/indexes"))
        self.assertFalse(authorize_route("student01", "GET", "/openai/v1/responses/abc"))

    def test_openai_body_guardrails(self):
        import security

        self.assertTrue(hasattr(security, "validate_openai"))
        good = {
            "model": "gpt-5.6-terra",
            "input": "hello",
            "tools": [{"type": "function", "name": "get_weather"}],
        }
        result = security.validate_openai("responses", good)
        self.assertFalse(result["store"])
        self.assertEqual(result["max_output_tokens"], 1500)
        for change in [
            {"model": "other"},
            {"previous_response_id": "r"},
            {"conversation": "c"},
            {"tools": [{"type": "web_search"}]},
            {"max_output_tokens": 1501},
            {"max_output_tokens": 0},
            {"input": "x" * 24001},
            {
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": "https://evil"}],
                    }
                ]
            },
            {"background": True},
            {"input": [{"type": "item_reference", "id": "secret"}]},
        ]:
            with self.subTest(change=next(iter(change))), self.assertRaises(ValueError):
                security.validate_openai("responses", dict(good, **change))
        e = security.validate_openai(
            "embeddings", {"model": "text-embedding-3-small", "input": ["a", "b"]}
        )
        self.assertEqual(e["dimensions"], 1536)
        for change in [{"dimensions": 1}, {"input": ["x"] * 17}, {"input": ""}]:
            with self.assertRaises(ValueError):
                security.validate_openai("embeddings", dict(e, **change))

    def test_stateless_agent_framework_reasoning_round_trip(self):
        from security import validate_openai

        body = {
            "model": "gpt-5.6-terra",
            "include": ["reasoning.encrypted_content"],
            "input": [
                {
                    "type": "reasoning",
                    "id": "rs_local",
                    "summary": [],
                    "encrypted_content": "opaque",
                },
                {
                    "type": "function_call",
                    "id": "fc_local",
                    "call_id": "call1",
                    "name": "weather",
                    "arguments": "{}",
                },
                {"type": "function_call_output", "call_id": "call1", "output": "{}"},
            ],
        }
        self.assertFalse(validate_openai("responses", body)["store"])
        with self.assertRaises(ValueError):
            validate_openai("responses", dict(body, include=["web_search_call.action.sources"]))

    def test_generated_policy_is_fail_closed(self):
        import security

        self.assertTrue(hasattr(security, "render_policy"))
        import xml.etree.ElementTree as ET

        text = security.render_policy(
            "https://unit.openai.azure.com", "https://unit.search.windows.net"
        )
        root = ET.fromstring(text)
        self.assertIsNone(root.find(".//base"))
        self.assertIsNone(root.find(".//trace"))
        self.assertEqual(len(root.findall(".//rate-limit")), 1)
        self.assertIsNone(root.find(".//rate-limit-by-key"))
        for header in ["Authorization", "api-key", "Ocp-Apim-Subscription-Key"]:
            self.assertIsNotNone(
                root.find(f".//set-header[@name='{header}'][@exists-action='delete']")
            )
        self.assertEqual(
            {e.attrib["resource"] for e in root.findall(".//authentication-managed-identity")},
            {"https://cognitiveservices.azure.com", "https://search.azure.com"},
        )
        for marker in [
            "previous_response_id",
            "conversation",
            "function",
            "1500",
            "24000",
            "1536",
            "context.Subscription.Name",
            "vectorizers",
            'copy-unmatched-params="false"',
        ]:
            self.assertIn(marker, text)
        with self.assertRaises(ValueError):
            security.render_policy("https://evil.example/path", "https://unit.search.windows.net")


if __name__ == "__main__":
    unittest.main()
