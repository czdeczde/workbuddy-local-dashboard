# -*- coding: utf-8 -*-
"""
外部真实数据抓取：天气(Open-Meteo) + 微博热搜(微博官方) + 今日热榜(今日头条官方)
仅标准库。每个函数失败时返回 None，由调用方保留上一次快照，绝不编造数据。
"""
import json
import os
import ssl
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 默认城市：广州越秀区；用户可在看板里改城市， Choice 存本地文件供定时快照复用
LAT, LON = 23.13, 113.26
CITY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather_city.json")


def load_city():
    """返回 (城市名, 纬度, 经度)；无自定义时返回默认广州。"""
    try:
        if os.path.isfile(CITY_FILE):
            with open(CITY_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("lat") is not None and d.get("lon") is not None:
                return str(d.get("city") or "自定义城市"), float(d["lat"]), float(d["lon"])
    except Exception:
        pass
    return "广州 · 越秀区", LAT, LON


def save_city(city, lat, lon):
    """写入自选城市及坐标，供 snapshot_update.py 复用。"""
    tmp = CITY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"city": city, "lat": lat, "lon": lon}, f, ensure_ascii=False)
    os.replace(tmp, CITY_FILE)


def geocode(city):
    """Open-Meteo geocoding：城市名 -> (标准名, lat, lon)；失败返回 None。"""
    try:
        u = ("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1"
             "&language=zh&format=json" % urllib.parse.quote(str(city)))
        d = json.loads(_get(u, 20))
        r = (d.get("results") or [{}])[0]
        if r.get("latitude") is None or r.get("longitude") is None:
            return None
        return (r.get("name") or str(city), float(r["latitude"]), float(r["longitude"]))
    except Exception:
        return None

# Open-Meteo WMO weather_code -> 中文描述
WMO = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "冻雾", 51: "轻毛毛雨", 53: "毛毛雨", 55: "浓毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "米雪", 80: "阵雨", 81: "中阵雨", 82: "强阵雨", 85: "阵雪", 86: "强阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}


def _get(url, timeout=20, refer=None, encoding="utf-8"):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if refer:
        headers["Referer"] = refer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode(encoding, "ignore")


def fetch_weather(city=None, lat=None, lon=None):
    """返回真实天气 dict（实况+7日预报+24小时逐时与预警推导）；失败返回 None。"""
    try:
        from datetime import datetime
        if lat is None or lon is None:
            city_name, lat, lon = load_city()
            city = city or city_name
        city = city or "自定义城市"
        collected = datetime.now().strftime("%m-%d %H:%M")

        wu = ("https://api.open-meteo.com/v1/forecast"
              "?latitude=%s&longitude=%s"
              "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
              "&daily=temperature_2m_max,temperature_2m_min,weather_code"
              "&hourly=temperature_2m,weather_code,precipitation_probability,wind_speed_10m"
              "&timezone=Asia%%2FShanghai&forecast_days=7&past_hours=0&forecast_hours=48"
              % (lat, lon))
        j = json.loads(_get(wu, 25))
        w = j.get("current") or {}
        daily = j.get("daily") or {}
        hourly = j.get("hourly") or {}

        aqi, pm25 = None, None
        try:
            au = ("https://air-quality-api.open-meteo.com/v1/air-quality"
                  "?latitude=%s&longitude=%s&current=us_aqi,pm2_5&timezone=Asia%%2FShanghai"
                  % (lat, lon))
            a = json.loads(_get(au, 20)).get("current") or {}
            aqi, pm25 = a.get("us_aqi"), a.get("pm2_5")
        except Exception:
            pass

        code = w.get("weather_code")
        tmax = (daily.get("temperature_2m_max") or [None])[0]
        tmin = (daily.get("temperature_2m_min") or [None])[0]

        # ---- 未来 7 天 ----
        dates = daily.get("time") or []
        codes = daily.get("weather_code") or []
        tmaxs = daily.get("temperature_2m_max") or []
        tmins = daily.get("temperature_2m_min") or []
        forecast = []
        for i, ds in enumerate(dates[:7]):
            c = codes[i] if i < len(codes) else None
            forecast.append({
                "date": ds[5:].replace("-", "/") if len(ds) >= 10 else ds,
                "code": c,
                "desc": WMO.get(c, "—") if c is not None else "—",
                "hi": round(tmaxs[i]) if i < len(tmaxs) and tmaxs[i] is not None else None,
                "lo": round(tmins[i]) if i < len(tmins) and tmins[i] is not None else None,
            })

        # ---- 未来 24 小时逐时（每 4 小时取 1 点，共 6 点）----
        ht = hourly.get("time") or []
        now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
        start = 0
        for i, ts in enumerate(ht):
            if ts >= now_hour:
                start = i
                break
        hourly24 = []
        for k in range(6):
            i = start + k * 4
            if i >= len(ht):
                break
            ts = ht[i]
            c = (hourly.get("weather_code") or [None] * len(ht))[i]
            temp = (hourly.get("temperature_2m") or [None] * len(ht))[i]
            pop = (hourly.get("precipitation_probability") or [None] * len(ht))[i]
            hourly24.append({
                "t": ts[11:13] + "时" if len(ts) >= 13 else ts,
                "code": c,
                "desc": WMO.get(c, "—") if c is not None else "—",
                "temp": round(temp) if temp is not None else None,
                "pop": pop,
            })

        # ---- 预警推导：只基于真实逐时数据，不调用任何编造逻辑 ----
        alerts = []
        rain = [(x["t"], x["pop"]) for x in hourly24
                if (x.get("pop") is not None and x["pop"] >= 50)
                or (x.get("code") is not None and (51 <= x["code"] <= 67 or 80 <= x["code"] <= 82 or x["code"] >= 95))]
        if rain:
            p = rain[0][1]
            alerts.append("%s 有降水可能%s，出门带伞" % (
                rain[0][0], ("（概率 %s%%）" % int(p)) if p is not None else ""))
        thunder = [x["t"] for x in hourly24 if x.get("code") is not None and x["code"] >= 95]
        if thunder:
            alerts.append("%s 有雷阵雨，注意防雷" % thunder[0])
        winds = [(x["t"], x["code"]) for x in hourly24]
        wwinds = hourly.get("wind_speed_10m") or []
        hi_wind = [(ht[start + k * 4][11:13] + "时", wwinds[start + k * 4])
                   for k in range(6) if start + k * 4 < len(wwinds)
                   and wwinds[start + k * 4] is not None and wwinds[start + k * 4] >= 40]
        if hi_wind:
            alerts.append("%s 风力较大，注意防风" % hi_wind[0][0])
        alert_text = "；".join(alerts) if alerts else "未来24小时无明显恶劣天气"

        return {
            "city": city,
            "temp": round(w.get("temperature_2m", 0)),
            "desc": WMO.get(code, "未知天气(%s)" % code),
            "aqi": aqi if aqi is not None else "-",
            "humidity": "%s%%" % w.get("relative_humidity_2m", "-"),
            "wind": "%s级" % _wind_level(w.get("wind_speed_10m", 0)),
            "upd": "实况 %s · Open-Meteo" % (w.get("time") or "").split("T")[-1],
            "aqiNote": "US AQI" + (" · PM2.5 %s" % pm25 if pm25 is not None else ""),
            "hi": tmax, "lo": tmin,
            "forecast": forecast,
            "hourly24": hourly24,
            "alert": alert_text,
            "alertNote": "逐时真实数据推导 · 非官方气象预警",
            "collected": collected,
            "source": "Open-Meteo 实时 API（天气+空气质量+7日+24小时逐时）",
        }
    except Exception:
        return None


def _wind_level(kmh):
    """风速 km/h -> 蒲福风级近似。"""
    try:
        v = float(kmh)
    except Exception:
        return "-"
    boundaries = [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]
    for i, b in enumerate(boundaries):
        if v < b:
            return i
    return 12


def fetch_weibo_hot(limit=12):
    """微博热搜官方 AJAX 接口，返回 [{rank,title,hot}]；失败返回 None。"""
    try:
        d = json.loads(_get("https://weibo.com/ajax/side/hotSearch", 20,
                            refer="https://weibo.com/"))
        items = (d.get("data") or {}).get("realtime") or []
        out = []
        for i, x in enumerate(items[:limit]):
            title = x.get("word") or x.get("note") or ""
            if not title:
                continue
            out.append({"rank": i + 1, "title": title, "hot": x.get("num") or 0,
                        "label": x.get("label_name", "")})
        return out or None
    except Exception:
        return None


def fetch_toutiao_hot(limit=12):
    """今日头条官方 hot-board 接口，返回 [{rank,title,hot}]；失败返回 None。"""
    try:
        d = json.loads(_get("https://www.toutiao.com/hot-event/hot-board/"
                            "?origin=toutiao_pc", 20, refer="https://www.toutiao.com/"))
        items = d.get("data") or []
        out = []
        for i, x in enumerate(items[:limit]):
            title = x.get("Title") or ""
            if not title:
                continue
            out.append({"rank": i + 1, "title": title, "hot": x.get("HotValue") or 0})
        return out or None
    except Exception:
        return None


def _kline_close(url, key, node="day"):
    """取近30日收盘价序列；失败返回 []。"""
    try:
        d = json.loads(_get(url, 20, refer="https://gu.qq.com/"))
        rows = ((d.get("data") or {}).get(key) or {}).get(node) or []
        out = []
        for r in rows:
            if len(r) > 2 and r[2]:
                try:
                    out.append(round(float(r[2]), 2))
                except (TypeError, ValueError):
                    pass
        return out
    except Exception:
        return []


def fetch_indices():
    """上证/恒生/纳斯达克：腾讯实时点位 + 近30日收盘序列；失败返回 None。"""
    try:
        raw = _get("https://qt.gtimg.cn/q=sh000001,hkHSI,usIXIC", 20,
                   refer="https://gu.qq.com/", encoding="gbk")
        def _f(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return 0.0
        quotes = {}
        for line in raw.split(";"):
            if '"' not in line or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip().replace("v_", "")
            p = line.split('"')[1].split("~")
            if len(p) < 33:
                continue
            quotes[key] = {
                "code": key, "name": p[1], "price": _f(p[3]),
                "time": p[30], "change": _f(p[31]), "pct": _f(p[32]),
            }
        if len(quotes) < 3:
            return None
        series = {
            "sh000001": _kline_close("https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=sh000001,day,,,30", "sh000001"),
            "hkHSI": _kline_close("https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=hkHSI,day,,,30", "hkHSI"),
            "usIXIC": _kline_close("https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param=usIXIC,day,,,30,qfq", "usIXIC"),
        }
        out = []
        for key in ("sh000001", "hkHSI", "usIXIC"):
            item = quotes[key]
            item["points"] = series.get(key) or []
            item["period"] = "近30日"
            out.append(item)
        return out
    except Exception:
        return None


def fmt_hot(n):
    """热度值格式化：万/亿。"""
    try:
        n = float(n)
    except Exception:
        return ""
    if n >= 1e8:
        return "%.1f亿" % (n / 1e8)
    if n >= 1e4:
        return "%.1f万" % (n / 1e4)
    return str(int(n))
