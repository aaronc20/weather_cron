import datetime
import os
from zoneinfo import ZoneInfo
import requests

# 1. PARAMETERS & CONFIG
LAT = "38.8560"  # Arlington Coordinates
LON = "-77.0500"
HEADERS = {"User-Agent": "(arlingtonrunningbot.com, aaroncchenn@email.com)"}
TARGET_TZ = ZoneInfo("America/New_York")

# 2. FETCH NWS RAW DATA
base_url = "https://api.weather.gov/points"
points_url = f"{base_url}/{LAT},{LON}"
points_data = requests.get(points_url, headers=HEADERS).json()["properties"]

office, grid_x, grid_y = points_data["cwa"], points_data["gridX"], points_data["gridY"]
grid_url = f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}"
grid_data = requests.get(grid_url, headers=HEADERS).json()["properties"]

# Get today's local date string in Eastern Time
today_local = datetime.datetime.now(TARGET_TZ).date()

def parse_grid_to_est(data_source):
    """Parses NWS grid timelines and maps them strictly to Eastern Time hour slots for today."""
    est_day_profile = {}
    for item in data_source["values"]:
        time_part = item["validTime"].split("/")[0]
        utc_dt = datetime.datetime.fromisoformat(time_part)
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
            
        est_dt = utc_dt.astimezone(TARGET_TZ)
        
        if est_dt.date() == today_local:
            est_day_profile[est_dt.hour] = item["value"]
    return est_day_profile

# 3. ALIGN TIME-SERIES MATRICES TO EST
rain_timeline = parse_grid_to_est(grid_data["probabilityOfPrecipitation"])
temp_timeline = parse_grid_to_est(grid_data["temperature"])
dew_timeline = parse_grid_to_est(grid_data["dewpoint"])

# 4. EVALUATE DAILY METRICS & SEPARATE RAIN HOUR LISTS
max_temp = -999
temp_sum = 0
temp_count = 0
dew_point_sum = 0
dew_point_count = 0

light_rain_hours = []  # Rain > 10%
heavy_rain_hours = []  # Rain > 40%

for hr in range(24):
    pop = rain_timeline.get(hr, 0)
    if pop > 40:
        heavy_rain_hours.append(hr)
    if pop > 10:  # Captures light rain, including the heavy hours
        light_rain_hours.append(hr)

    if hr in temp_timeline:
        temp_f = (temp_timeline[hr] * 9/5) + 32
        max_temp = max(max_temp, temp_f)
        temp_sum += temp_f
        temp_count += 1

    if hr in dew_timeline:
        dew_f = (dew_timeline[hr] * 9/5) + 32
        dew_point_sum += dew_f
        dew_point_count += 1

# Calculate the single, reliable daily average dew point
avg_dew_point = int(dew_point_sum / dew_point_count) if dew_point_count > 0 else 0

# Calculate average and current temperature
avg_temp = int(temp_sum / temp_count) if temp_count > 0 else 0
current_hour = datetime.datetime.now(TARGET_TZ).hour
print(current_hour)
current_temp = int((temp_timeline[current_hour] * 9/5) + 32) if current_hour in temp_timeline else avg_temp

# 5. HELPER FUNCTION TO GROUP CONSECUTIVE HOURS INTO TIME SLOTS
def build_time_windows(hour_list):
    if not hour_list:
        return "None"
    
    windows = []
    start_hr = hour_list[0]
    prev_hr = hour_list[0]
    
    for hr in hour_list[1:] + [99]:  # Dummy hour to force flush the final window
        if hr == prev_hr + 1:
            prev_hr = hr
        else:
            start_ampm = datetime.time(start_hr).strftime("%I:%M %p").lstrip("0")
            end_ampm = datetime.time((prev_hr + 1) % 24).strftime("%I:%M %p").lstrip("0")
            windows.append(f"⏱️ **{start_ampm} to {end_ampm}**")
            start_hr = hr
            prev_hr = hr
            
    return ", ".join(windows)

light_rain_slots = build_time_windows(light_rain_hours)
heavy_rain_slots = build_time_windows(heavy_rain_hours)

# 6. ASSESS THE EMBED COLOR TIERS (Decimal value transformation)
if avg_dew_point >= 75:
    vibe_check = f"🚨 **DANGER ZONE (Avg Dew Point: {avg_dew_point}°F)**\nSweat evaporation has completely failed. Hit the indoor AC treadmills or skip entirely."
    embed_color = 10038562  # Dark Crimson
elif 72 <= avg_dew_point < 75:
    vibe_check = f"🥵 **ASS DAY (Avg Dew Point: {avg_dew_point}°F)**\nClassic Arlington swamp mode. Slow paces down by 30-45s/mile and loop near water."
    embed_color = 15158332  # Bright Red
elif 55 <= avg_dew_point < 72:
    vibe_check = f"💪 **AVERAGE DAY (Avg Dew Point: {avg_dew_point}°F)**\nStandard local summer sticky baseline. Workable, but track heart rate drift."
    embed_color = 15105570  # Solid Orange
else:
    vibe_check = f"🦄 **UNICORN WEATHER (Avg Dew Point: {avg_dew_point}°F)**\nRare dry Canadian front! Absolutely beautiful. Go crush your target workout splits."
    embed_color = 3066993   # Emerald Green


# Helper function to get day suffix
def get_day_suffix(n):
    return 'th' if 11 <= n <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')

# Format the date string: E.g., "📅 Thursday June 11th"
day_of_week = today_local.strftime("%A")
month_name = today_local.strftime("%B")
day_num = today_local.day
suffix = get_day_suffix(day_num)

formatted_title = f"📅 {day_of_week}, {month_name} {day_num}{suffix}, {current_hour}:00 🕒"

# 7. ASSEMBLE CLEAN NATIVE DISCORD EMBED PAYLOAD
payload = {
    "embeds": [
        {
            "title": formatted_title,
            "color": embed_color,
            "description": (
                f"• Dew: {avg_dew_point}°F {vibe_check[:1]}\n"
                f"•Rain: {light_rain_slots}\n"
                f"**2. Precipitation Windows:**\n"
                f"🌧️ *Any chance of rain (>10%):*\n{light_rain_slots}\n\n"
                f"🚨 *Heavy risk windows (>40%):*\n{heavy_rain_slots}\n\n"
                f"📈 *Daily Temp: {current_temp}°F Now | {avg_temp}°F Avg | {int(max_temp)}°F Max*"
            ),
            "footer": {
                "text": "Local Runner Dashboard • Data from NWS API"
            }
        }
    ]
}

def get_precip_sparkline(timeline_dict):
    chars = "_▂▃▄▅▆▇█"
    sparkline = ""
    
    # Iterate from 6 to 22 in steps of 2
    for hr in range(0, 24, 2):
        # Average the current hour and the next hour
        val1 = timeline_dict.get(hr, 0)
        val2 = timeline_dict.get(hr + 1, 0)
        avg_pop = (val1 + val2) / 2
        
        # Map average to index (0-7)
        index = min(int(avg_pop / 12.5), 7)
        sparkline += chars[index]
        
    return sparkline

# 2. Get the sparkline
bar_visual = get_precip_sparkline(rain_timeline)
print(bar_visual)

# Integrated into your 4-row payload
payload = {
    "embeds": [{
        "description": (
            f"{formatted_title}\n"
            f"☔ Rain: {bar_visual}\n"
            f"🌡️ Temp: {current_temp}° / {avg_temp}° / {int(max_temp)}°\n"
            f"💧 Dew: {avg_dew_point}° {vibe_check[:1]}\n"
        )
    }]
}



# 8. POST LOGIC WITH ERROR PROTECTION
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
if DISCORD_WEBHOOK and DISCORD_WEBHOOK.startswith("http"):
    try:
        requests.post(DISCORD_WEBHOOK, json=payload)
        print("Embed dashboard successfully sent to Discord!")
    except requests.exceptions.RequestException as e:
        print(f"Network error posting to Discord: {e}")
else:
    print("⚠️ DISCORD_WEBHOOK environment variable is missing or invalid.")
    print("Falling back to local console print:\n")
    print(payload["embeds"][0]["description"])
