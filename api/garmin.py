from http.server import BaseHTTPRequestHandler
import json, os

try:
    from garminconnect import Garmin
    HAS_GARMIN = True
except ImportError:
    HAS_GARMIN = False

def map_type(activity_type):
    t = (activity_type or '').lower()
    if 'running' in t or 'run' in t: return 'run'
    if 'cycling' in t or 'bike' in t or 'biking' in t: return 'bike'
    if 'swimming' in t or 'swim' in t: return 'swim'
    if 'strength' in t or 'gym' in t: return 'strength'
    if 'hiking' in t or 'hike' in t: return 'hike'
    if 'skiing' in t or 'ski' in t: return 'ski'
    if 'soccer' in t or 'football' in t: return 'soccer'
    return 'other'

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        email = os.environ.get('GARMIN_EMAIL')
        password = os.environ.get('GARMIN_PASSWORD')

        if not email or not password:
            self.send_response(503)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Garmin credentials not configured'}).encode())
            return

        if not HAS_GARMIN:
            self.send_response(503)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'garminconnect not installed'}).encode())
            return

        try:
            api = Garmin(email, password)
            api.login()
            raw = api.get_activities(0, 20)

            activities = []
            for a in raw:
                act_type = map_type(a.get('activityType', {}).get('typeKey', ''))
                dist_m = a.get('distance', 0) or 0
                km = round(dist_m / 1000, 2)
                duration_s = a.get('duration', 0) or 0
                h = int(duration_s // 3600)
                m = int((duration_s % 3600) // 60)
                s = int(duration_s % 60)
                time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                avg_hr = a.get('averageHR')
                avg_speed = a.get('averageSpeed')  # m/s
                pace = None
                speed = None
                if act_type in ('run', 'swim', 'hike') and avg_speed and avg_speed > 0:
                    pace_sec = 1000 / avg_speed
                    pace = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}"
                elif avg_speed:
                    speed = round(avg_speed * 3.6, 1)

                activities.append({
                    'date': a.get('startTimeLocal', '')[:10],
                    'name': a.get('activityName', 'Aktivitet'),
                    'type': act_type,
                    'km': km,
                    'time': time_str,
                    'pace': pace,
                    'speed': speed,
                    'hr': int(avg_hr) if avg_hr else None,
                    'elev': int(a.get('elevationGain', 0) or 0) or None,
                    'kcal': int(a.get('calories', 0) or 0) or None,
                })

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'activities': activities}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def log_message(self, format, *args):
        pass
