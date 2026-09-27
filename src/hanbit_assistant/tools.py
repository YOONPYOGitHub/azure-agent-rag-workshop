"""LLM 없이도 호출할 수 있는 읽기 전용 외부 API 함수."""

import math
from decimal import ROUND_HALF_UP, Decimal

import httpx

CURRENCIES = {"KRW", "USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "CNY", "SGD"}


async def convert_currency(
    amount: float, from_currency: str, to_currency: str, *, client: httpx.AsyncClient | None = None
) -> dict:
    """Frankfurter의 최근 영업일 기준 환율. 은행 수수료/회사 정산 환율이 아닙니다."""
    base, target = from_currency.strip().upper(), to_currency.strip().upper()
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or not 0 <= amount <= 1_000_000_000
    ):
        raise ToolError("금액은 0 이상 10억 이하의 유한한 숫자여야 합니다.")
    if base not in CURRENCIES or target not in CURRENCIES:
        raise ToolError("지원 통화: " + ", ".join(sorted(CURRENCIES)))
    rate, date = 1.0, None
    if base != target:
        data = await _get_json(
            "https://api.frankfurter.dev/v1/latest",
            {
                "base": base,
                "symbols": target,
            },
            client,
        )
        try:
            rate, date = float(data["rates"][target]), data["date"]
            if not math.isfinite(rate) or rate <= 0 or not isinstance(date, str):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ToolError("환율 응답 형식이 올바르지 않습니다.") from None
    converted = (Decimal(str(amount)) * Decimal(str(rate))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "amount": amount,
        "from_currency": base,
        "to_currency": target,
        "rate": rate,
        "converted_amount": float(converted),
        "rate_date": date,
        "source": "https://frankfurter.dev/" if date else None,
        "note": "참고용 환산액(소수점 둘째 자리 반올림). 은행 수수료 및 회사 정산 기준과 다를 수 있습니다.",
    }


class ToolError(ValueError):
    """사용자에게 표시해도 되는 검증/외부 서비스 오류."""


CITIES = {
    "Seoul": (37.5665, 126.9780, "Asia/Seoul"),
    "Tokyo": (35.6762, 139.6503, "Asia/Tokyo"),
    "London": (51.5074, -0.1278, "Europe/London"),
    "New York": (40.7128, -74.0060, "America/New_York"),
}
CITY_ALIASES = {
    "서울": "Seoul",
    "도쿄": "Tokyo",
    "동경": "Tokyo",
    "런던": "London",
    "뉴욕": "New York",
    "newyork": "New York",
}
CITY_ALIASES.update({name.lower(): name for name in CITIES})


async def _get_json(url: str, params: dict, client: httpx.AsyncClient | None):
    async def request(active):
        try:
            response = await active.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise ToolError(
                "외부 서비스 응답을 받지 못했습니다. 잠시 후 다시 시도하세요."
            ) from None

    if client is not None:
        return await request(client)
    async with httpx.AsyncClient() as active:
        return await request(active)


async def get_weather(city: str, *, client: httpx.AsyncClient | None = None) -> dict:
    """서울/도쿄/런던/뉴욕의 현재 날씨를 Open-Meteo에서 조회합니다."""
    canonical = CITY_ALIASES.get(city.strip().lower())
    if canonical is None:
        raise ToolError("지원 도시: 서울, 도쿄, 런던, 뉴욕")
    lat, lon, timezone = CITIES[canonical]
    data = await _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone,
            "current": "temperature_2m,weather_code,wind_speed_10m",
        },
        client,
    )
    try:
        current = data["current"]
        for name in ("temperature_2m", "wind_speed_10m", "weather_code"):
            value = current[name]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ToolError("날씨 응답 형식이 올바르지 않습니다.")
        return {
            "city": canonical,
            "temperature": current["temperature_2m"],
            "temperature_unit": data["current_units"]["temperature_2m"],
            "weather_code": current["weather_code"],
            "wind_speed": current["wind_speed_10m"],
            "wind_unit": data["current_units"]["wind_speed_10m"],
            "observed_at": current["time"],
            "timezone": data["timezone"],
            "source": "https://open-meteo.com/",
            "note": "현재 날씨이며 출장일의 예보가 아닙니다.",
        }
    except (KeyError, TypeError):
        raise ToolError("날씨 응답 형식이 올바르지 않습니다.") from None
