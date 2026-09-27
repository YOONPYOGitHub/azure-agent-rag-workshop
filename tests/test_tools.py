import httpx
import pytest


@pytest.mark.parametrize("temperature", [None, "unknown", float("inf")])
async def test_weather_rejects_unusable_current_values(temperature):
    from hanbit_assistant.tools import ToolError, get_weather

    def handler(request):
        data = {
            "current": {
                "time": "2026-09-27T12:00",
                "temperature_2m": temperature,
                "weather_code": 3,
                "wind_speed_10m": 4.2,
            },
            "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
            "timezone": "Asia/Tokyo",
        }
        import json

        return httpx.Response(200, content=json.dumps(data))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolError, match="형식"):
            await get_weather("Tokyo", client=client)


async def test_currency_uses_published_rate_and_date():
    from hanbit_assistant.tools import convert_currency

    def handler(request):
        assert request.url.host == "api.frankfurter.dev"
        assert request.url.params["base"] == "USD"
        assert request.url.params["symbols"] == "KRW"
        return httpx.Response(
            200, json={"date": "2026-09-25", "base": "USD", "rates": {"KRW": 1325.25}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await convert_currency(100, "usd", "krw", client=client)
    assert result["converted_amount"] == 132525.0
    assert result["rate_date"] == "2026-09-25"
    assert result["rate"] == 1325.25


@pytest.mark.parametrize(
    "amount,base,target",
    [
        (float("nan"), "USD", "KRW"),
        (-1, "USD", "KRW"),
        (100, "ZZZ", "KRW"),
        (True, "USD", "KRW"),
        (1e15, "USD", "KRW"),
    ],
)
async def test_currency_rejects_invalid_values_before_network(amount, base, target):
    from hanbit_assistant.tools import ToolError, convert_currency

    with pytest.raises(ToolError):
        await convert_currency(amount, base, target)


async def test_same_currency_needs_no_network():
    from hanbit_assistant.tools import convert_currency

    result = await convert_currency(123, "KRW", "KRW")
    assert result["converted_amount"] == 123
    assert result["rate_date"] is None


async def test_weather_normalizes_korean_city_and_uses_real_response_fields():
    from hanbit_assistant.tools import get_weather

    def handler(request):
        assert request.url.host == "api.open-meteo.com"
        assert request.url.params["latitude"] == "35.6762"
        return httpx.Response(
            200,
            json={
                "current": {
                    "time": "2026-09-27T12:00",
                    "temperature_2m": 24.1,
                    "weather_code": 3,
                    "wind_speed_10m": 4.2,
                },
                "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
                "timezone": "Asia/Tokyo",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await get_weather(" 도쿄 ", client=client)
    assert result["city"] == "Tokyo"
    assert result["temperature"] == 24.1
    assert result["observed_at"] == "2026-09-27T12:00"
    assert result["source"] == "https://open-meteo.com/"


async def test_weather_rejects_unknown_city_without_network():
    from hanbit_assistant.tools import ToolError, get_weather

    with pytest.raises(ToolError, match="지원 도시"):
        await get_weather("https://attacker.test")


async def test_weather_timeout_is_not_fabricated_data():
    from hanbit_assistant.tools import ToolError, get_weather

    def handler(request):
        raise httpx.ReadTimeout("secret url", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolError, match="응답") as exc:
            await get_weather("서울", client=client)
        assert "secret" not in str(exc.value)
