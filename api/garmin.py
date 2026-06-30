from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os
from datetime import date, timedelta

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


def get_mfa_callback():
    """Returns a callable MFA function if TOTP secret is available."""
    totp_secret = os.environ.get('GARMIN_TOTP_SECRET')
    if totp_secret:
        try:
            import pyotp
            def callback():
                return pyotp.TOTP(totp_secret).now()
            return callback
        except ImportError:
            pass
    return None


def make_api():
    """Create and login Garmin API using token store (preferred) or email/password."""
    email = os.environ.get('Garmin_EMAIL') or os.environ.get('GARMIN_EMAIL', '')
    password = os.environ.get('Garmin_Password') or os.environ.get('GARMIN_PASSWORD', '')
    tokens_b64 = os.environ.get('GARMIN_TOKENS_B64')

    mfa_cb = get_mfa_callback()
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=mfa_cb)

    if tokens_b64:
        # Token-based login — no MFA prompt needed
        api.login(tokenstore_base64=tokens_b64)
    else:
        # Email/password — will raise if MFA required and no TOTP secret set
        api.login()

    return api


def get_activities(api):
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
        avg_speed = a.get('averageSpeed')
        pace = None; speed = None
        if act_type in ('run', 'swim', 'hike') and avg_speed and avg_speed > 0:
            pace_sec = 1000 / avg_speed
            pace = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
        elif avg_speed:
            speed = round(avg_speed * 3.6, 1)
        cadence = a.get('averageRunningCadenceInStepsPerMinute')
        swolf = a.get('averageSwolf')
        aerobic_te = a.get('aerobicTrainingEffect')
        anaerobic_te = a.get('anaerobicTrainingEffect')
        activities.append({
            'id': a.get('activityId'),
            'date': a.get('startTimeLocal', '')[:10],
            'name': a.get('activityName', 'Aktivitet'),
            'type': act_type,
            'km': km, 'time': time_str, 'pace': pace, 'speed': speed,
            'hr': int(avg_hr) if avg_hr else None,
            'hrMax': int(a.get('maxHR', 0) or 0) or None,
            'elev': int(a.get('elevationGain', 0) or 0) or None,
            'kcal': int(a.get('calories', 0) or 0) or None,
            'cadence': int(cadence * 2) if cadence else None,
            'vertOsc': round(float(a.get('avgVerticalOscillation') or 0), 1) or None,
            'gct': int(a.get('avgGroundContactTime') or 0) or None,
            'vertRatio': round(float(a.get('avgVerticalRatio') or 0), 1) or None,
            'runPower': int(a.get('avgPower') or 0) or None,
            'swolf': int(swolf) if swolf else None,
            'aerobicTE': round(aerobic_te, 1) if aerobic_te else None,
            'anaerobicTE': round(anaerobic_te, 1) if anaerobic_te else None,
            'trainingLoad': a.get('activityTrainingLoad'),
        })
    return activities


def get_body_data(api):
    today = date.today().isoformat()
    result = {}

    try:
        sleep = api.get_sleep_data(today)
        sd = sleep.get('dailySleepDTO', {})
        result['sleep'] = {
            'score': sd.get('sleepScores', {}).get('overall', {}).get('value'),
            'durationHours': round((sd.get('sleepTimeSeconds', 0) or 0) / 3600, 1),
            'deepSec': sd.get('deepSleepSeconds'),
            'remSec': sd.get('remSleepSeconds'),
            'lightSec': sd.get('lightSleepSeconds'),
            'awakeSec': sd.get('awakeSleepSeconds'),
            'avgHrv': sleep.get('avgOvernightHrv'),
            'avgRespiration': sleep.get('avgSleepRespirationValue'),
            'spO2': sleep.get('avgSleepSpo2'),
        }
    except Exception as e:
        result['sleep'] = {'error': str(e)}

    try:
        bb_list = api.get_body_battery([today])
        if bb_list:
            vals = bb_list[0].get('bodyBatteryValuesArray', [])
            valid = [v[1] for v in vals if v[1] is not None]
            result['bodyBattery'] = {
                'current': valid[-1] if valid else None,
                'max': max(valid) if valid else None,
                'min': min(valid) if valid else None,
            }
    except Exception as e:
        result['bodyBattery'] = {'error': str(e)}

    try:
        hrv = api.get_hrv_data(today)
        s = hrv.get('hrvSummary', {})
        result['hrv'] = {
            'status': s.get('status'),
            'lastNight': s.get('lastNight'),
            'weeklyAvg': s.get('weeklyAvg'),
            'baseline': (s.get('baseline') or {}).get('lowUpper'),
        }
    except Exception as e:
        result['hrv'] = {'error': str(e)}

    try:
        tr_list = api.get_training_readiness(today)
        if tr_list:
            t = tr_list[-1]
            result['trainingReadiness'] = {
                'score': t.get('score'),
                'level': t.get('level'),
                'recoveryTime': t.get('recoveryTime'),
            }
    except Exception as e:
        result['trainingReadiness'] = {'error': str(e)}

    try:
        rhr = api.get_rhr_day(today)
        result['rhr'] = {'value': (rhr.get('allDayHR') or {}).get('restingHeartRate')}
    except Exception as e:
        result['rhr'] = {'error': str(e)}

    try:
        stress = api.get_all_day_stress(today)
        vals = stress.get('stressValuesArray', [])
        valid = [v[1] for v in vals if v[1] is not None and v[1] >= 0]
        result['stress'] = {'avg': round(sum(valid) / len(valid)) if valid else None}
    except Exception as e:
        result['stress'] = {'error': str(e)}

    try:
        metrics = api.get_max_metrics(today)
        if metrics:
            m = metrics[0]
            result['maxMetrics'] = {
                'vo2max': (m.get('generic') or {}).get('vo2MaxPreciseValue'),
                'fitnessAge': (m.get('generic') or {}).get('fitnessAge'),
            }
    except Exception as e:
        result['maxMetrics'] = {'error': str(e)}

    try:
        preds = api.get_race_predictions()
        result['racePredictions'] = {
            'run5k': preds.get('time5K'),
            'run10k': preds.get('time10K'),
            'halfMarathon': preds.get('timeHalfMarathon'),
            'marathon': preds.get('timeMarathon'),
        }
    except Exception as e:
        result['racePredictions'] = {'error': str(e)}

    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        email = os.environ.get('Garmin_EMAIL') or os.environ.get('GARMIN_EMAIL')
        password = os.environ.get('Garmin_Password') or os.environ.get('GARMIN_PASSWORD')
        qs = parse_qs(urlparse(self.path).query)
        data_type = qs.get('type', ['activities'])[0]

        if not email or not password:
            return self._respond(503, {'error': 'Garmin credentials not configured'})
        if not HAS_GARMIN:
            return self._respond(503, {'error': 'garminconnect not installed'})

        tokens_b64 = os.environ.get('GARMIN_TOKENS_B64')
        hint = ('Add GARMIN_TOKENS_B64 to Vercel env vars. '
                'Run generate_tokens.py locally to create it. '
                'Or set GARMIN_TOTP_SECRET if you have your authenticator secret.')
        if not tokens_b64:
            return self._respond(401, {
                'error': 'MFA auth required — no token store configured',
                'hint': hint,
            })

        try:
            api = make_api()
            if data_type == 'body':
                self._respond(200, get_body_data(api))
            else:
                self._respond(200, {'activities': get_activities(api)})
        except Exception as e:
            self._respond(500, {'error': str(e), 'hint': hint})

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
