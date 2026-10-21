"""Check actual native first/last hourly rows against ordinary fixture values."""
import datetime
from ui_driver import UI
from weather_hourly_data_service import forecast

BUNDLE = 'com.alatus.futureweather'


def row_texts(hour):
    h = {k: format(v, 'g') if isinstance(v, (int, float)) else v for k, v in hour.items()}
    return [f"{h['time']} {h['condition']}",
            f"气温 {h['temperature']}° 体感 {h['feelsLike']}° 露点 {h['dewPoint']}°",
            f"湿度 {h['humidity']}% 降水 {h['precipitation']} mm 概率 {h['probability']}%",
            f"气压 {h['pressure']} hPa 云量 {h['cloud']}% 能见度 {h['visibility']} km",
            f"{h['windDirection']}风 {h['windSpeed']} km/h 阵风 {h['windGust']} km/h 紫外线 {h['uv']}"]


def verify_hourly_layouts(record):
    expected = forecast('440300', 'reference')
    receipts = []
    for key, hour in (('first_hour_layout', expected['hours'][0]),
                      ('last_hour_layout', expected['hours'][-1])):
        texts = [n.get('text', '') for n in UI.nodes(record[key])
                 if n.get('bundleName') == BUNDLE and n.get('visible') != 'false']
        required = ['返回天气', '深圳市 七天逐小时预报', *row_texts(hour)]
        if not all(text in texts for text in required):
            raise ValueError('visible hourly detail fields differ from fixture: ' + key)
        retrieval = [t.removeprefix('获取时间 ') for t in texts if t.startswith('获取时间 ')]
        if len(retrieval) != 1 or datetime.datetime.fromisoformat(retrieval[0]).tzinfo is None:
            raise ValueError('actual hourly retrieval time is not displayed')
        receipts.append({'hour': hour['time'], 'displayed_fields': row_texts(hour),
                         'retrieved_at': retrieval[0]})
    if receipts[0]['retrieved_at'] != receipts[1]['retrieved_at']:
        raise ValueError('forecast changed during first-to-last detail navigation')
    return receipts
