"""Deterministic seven-day hourly weather fixture, with real retrieval timestamps.

All hourly fields have corresponding labels in the ordinary forecast detail page.
The timestamp is displayed as retrieval time, not as a provider observation time.
There are no measurement, readiness, padding, or variant-specific routes.
"""
import datetime
import json
import math
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from weather_session_data_service import CITIES, forecast as daily_forecast


def forecast(code, retrieved_at):
    data = daily_forecast(code)
    start = datetime.datetime(2026, 10, 21)
    city_index = list(CITIES).index(code)
    hours = []
    conditions = ['晴', '多云', '阴', '小雨']
    for offset in range(7 * 24):
        day, hour = divmod(offset, 24)
        temperature = round(22 + city_index / 3 + 5 * math.sin((hour - 8) * math.pi / 12) - day / 4, 1)
        rain = (day + city_index) % 4 == 3 and 8 <= hour <= 18
        hours.append({
            'time': (start + datetime.timedelta(hours=offset)).isoformat(timespec='minutes'),
            'condition': conditions[(day + city_index) % 4],
            'temperature': temperature, 'feelsLike': round(temperature + (1.5 if hour > 11 else -.5), 1),
            'humidity': 55 + (hour + city_index) % 35,
            'precipitation': round(.2 + (hour % 5) * .3, 1) if rain else 0,
            'probability': 75 if rain else 10,
            'pressure': 1008 + (day + hour) % 10,
            'cloud': [10, 45, 85, 95][(day + city_index) % 4],
            'visibility': 8 if rain else 20,
            'windSpeed': 6 + (hour + city_index) % 12,
            'windDirection': ['东南', '东', '南', '东北'][(day + city_index) % 4],
            'windGust': 15 + (hour + city_index) % 16,
            'uv': round(max(0, 7 * math.sin((hour - 6) * math.pi / 12)), 1),
            'dewPoint': round(temperature - 5, 1),
        })
    data.update(issuedAt=retrieved_at, hours=hours)
    return data


def response(path, retrieved_at):
    url = urlsplit(path)
    query = parse_qs(url.query)
    if (url.path != '/v3/weather/weatherInfo' or query.get('extensions') != ['all']
            or len(query.get('city', [])) != 1 or query['city'][0] not in CITIES):
        return 404, b'Not found'
    return 200, json.dumps(forecast(query['city'][0], retrieved_at), ensure_ascii=False).encode()


def handler(observe):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            import time
            start = time.monotonic()
            retrieved_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            status, body = response(self.path, retrieved_at)
            sent, error = 0, None
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
                sent = len(body)
            except (BrokenPipeError, ConnectionResetError) as exc:
                error = type(exc).__name__
            finally:
                observe(self.path, start, time.monotonic(), status, body, sent, error, retrieved_at)
    return Handler
