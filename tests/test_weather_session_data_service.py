import json,unittest
from weather_session_data_service import CITIES,response
class WeatherSessionServiceTest(unittest.TestCase):
    def test_all_ten_supported_cities_have_complete_forecasts(self):
        self.assertEqual(len(CITIES),10)
        for code,name in CITIES.items():
            status,body=response('/v3/weather/weatherInfo?city='+code+'&extensions=all');data=json.loads(body)
            self.assertEqual(status,200);self.assertEqual(data['forecasts'][0]['city'],name);self.assertEqual(data['forecasts'][0]['adcode'],int(code));self.assertEqual(len(data['forecasts'][0]['casts']),4)
    def test_unknown_routes_and_bad_city_are_not_oracles(self):
        for path in ('/status','/metrics','/v3/weather/weatherInfo?city=0&extensions=all','/v3/weather/weatherInfo?city=440300&extensions=base'):
            self.assertEqual(response(path)[0],404)
