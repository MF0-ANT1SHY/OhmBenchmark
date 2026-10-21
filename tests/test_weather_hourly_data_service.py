import datetime
import json
import unittest

from weather_hourly_data_service import CITIES, response


class HourlyServiceTests(unittest.TestCase):
    def test_all_cities_have_contiguous_seven_day_forecasts(self):
        for code, name in CITIES.items():
            with self.subTest(city=code):
                status, body = response('/v3/weather/weatherInfo?city=' + code + '&extensions=all', '2026-10-21T00:00:00+00:00')
                data = json.loads(body)
                self.assertEqual(status, 200)
                self.assertEqual(data['forecasts'][0]['city'], name)
                self.assertEqual(len(data['hours']), 168)
                times = [datetime.datetime.fromisoformat(h['time']) for h in data['hours']]
                self.assertTrue(all(b - a == datetime.timedelta(hours=1) for a, b in zip(times, times[1:])))
                self.assertTrue(all(0 <= h['humidity'] <= 100 and h['precipitation'] >= 0 and 0 <= h['probability'] <= 100 for h in data['hours']))

    def test_retrieval_time_does_not_change_forecast(self):
        path = '/v3/weather/weatherInfo?city=440300&extensions=all'
        a, b = [json.loads(response(path, time)[1]) for time in ('2026-10-21T00:00:00+00:00', '2026-10-21T00:00:30+00:00')]
        self.assertNotEqual(a.pop('issuedAt'), b.pop('issuedAt'))
        self.assertEqual(a, b)

    def test_only_ordinary_supported_forecast_routes(self):
        for path in ('/metrics', '/status', '/v3/weather/weatherInfo?city=0&extensions=all'):
            self.assertEqual(response(path, 'reference'), (404, b'Not found'))
