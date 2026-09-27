import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security import validate_openai


def test_framework_replays_assistant_text_with_empty_logprobs():
    body = {
        "model": "gpt-5.6-terra",
        "input": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "hello", "annotations": [], "logprobs": []}
                ],
            }
        ],
    }
    assert validate_openai("responses", body)["store"] is False
