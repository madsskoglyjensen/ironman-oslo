from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os
from datetime import date, datetime, timedelta


def today_oslo():
    """Local Norwegian date — date.today() is UTC on Vercel and gives yesterday between 00:00–02:00."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Oslo')).date().isoformat()
    except Exception:
        return date.today().isoformat()

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
    import tempfile as _tempfile, json as _json, base64 as _b64

    email    = os.environ.get('Garmin_EMAIL') or os.environ.get('GARMIN_EMAIL', '')
    password = os.environ.get('Garmin_Password') or os.environ.get('GARMIN_PASSWORD', '')
    tokens_b64 = os.environ.get('GARMIN_TOKENS_B64')

    mfa_cb = get_mfa_callback()
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=mfa_cb)

    if tokens_b64:
        # Method A: tokenstore_base64 kwarg (garminconnect 0.2.x)
        try:
            api.login(tokenstore_base64=tokens_b64)
            return api
        except TypeError:
            pass  # 0.3.x doesn't have this param — fall through

        # Method B: write token files to tmpdir, pass tokenstore path (garminconnect 0.3.x)
        try:
            # Add padding if missing (common when copied from terminal)
            padded = tokens_b64 + "=" * (-len(tokens_b64) % 4)
            raw = _json.loads(_b64.b64decode(padded))
            tmpdir = _tempfile.mkdtemp()
            for k, v in raw.items():
                fname = k if k.endswith('.json') else k + '.json'
                with open(os.path.join(tmpdir, fname), 'w') as fh:
                    _json.dump(v, fh)
            api.login(tokenstore=tmpdir)
            return api
        except Exception as e:
            raise Exception(
                f"Token load failed ({e}). "
                "Please regenerate GARMIN_TOKENS_B64 by running generate_tokens.py locally."
            )

    # No tokens — try direct login (will fail if MFA is enabled)
    api.login()
    return api


def get_activities(api):
    raw = api.get_activities(0, 20)
    activities = []
    for a in raw:
        act_type = map_type((a.get('activityType') or {}).get('typeKey', ''))
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
            'date': (a.get('startTimeLocal') or '')[:10],
            'name': a.get('activityName') or 'Aktivitet',
            'type': act_type,
            'km': km, 'time': time_str, 'pace': pace, 'speed': speed,
            'hr': int(avg_hr) if avg_hr else None,
            'hrMax': int(a.get('maxHR', 0) or 0) or None,
            'elev': int(a.get('elevationGain', 0) or 0) or None,
            'kcal': int(a.get('calories', 0) or 0) or None,
            'cadence': int(cadence) if cadence else None,
            'vertOsc': round(float(a.get('avgVerticalOscillation') or 0), 1) or None,
            'gct': int(a.get('avgGroundContactTime') or 0) or None,
            'vertRatio': round(float(a.get('avgVerticalRatio') or 0), 1) or None,
            'runPower': int(a.get('avgPower') or 0) or None,
            'power': int(a.get('avgPower') or 0) or None,
            'maxPower': int(a.get('maxPower', 0) or 0) or None,
            'normPower': int(a.get('normPower') or a.get('normalizedPower') or 0) or None,
            'bikeCadence': int(a.get('averageBikingCadenceInRevPerMinute') or 0) or None,
            'strokes': int(a.get('averageSwolf') and (a.get('avgStrokes') or 0) or 0) or None,
            'swolf': int(swolf) if swolf else None,
            'aerobicTE': round(aerobic_te, 1) if aerobic_te else None,
            'anaerobicTE': round(anaerobic_te, 1) if anaerobic_te else None,
            'teLabel': a.get('trainingEffectLabel'),
            'avgStride': round(float(a.get('avgStrideLength') or 0), 2) or None,
            'moderateMin': int(a.get('moderateIntensityMinutes', 0) or 0) or None,
            'vigorousMin': int(a.get('vigorousIntensityMinutes', 0) or 0) or None,
            'minTemp': a.get('minTemperature'),
            'trainingLoad': a.get('activityTrainingLoad'),
        })
    return activities


def body_is_empty(result):
    """True when Garmin has no real data for the requested day (e.g. right after midnight)."""
    tr = result.get('trainingReadiness') or {}
    bb = result.get('bodyBattery') or {}
    sl = result.get('sleep') or {}
    return tr.get('score') is None and bb.get('current') is None and sl.get('score') is None


def get_body_data(api, today=None):
    today = today or today_oslo()
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
        bb_list = api.get_body_battery(today)
        if bb_list:
            # get_body_battery may return a list or single dict
            first = bb_list[0] if isinstance(bb_list, list) else bb_list
            vals = first.get('bodyBatteryValuesArray', [])
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
                'feedback': t.get('feedbackLong') or t.get('feedbackShort'),
                'recoveryTime': t.get('recoveryTime'),
                'acuteLoad': t.get('acuteLoad'),
                'sleepScore': t.get('sleepScore'),
                'hrvFactor': t.get('hrvFactorPercent'),
                'sleepFactor': t.get('sleepScoreFactorPercent'),
                'recoveryFactor': t.get('recoveryTimeFactorPercent'),
                'loadFactor': t.get('acwrFactorPercent'),
                'stressFactor': t.get('stressHistoryFactorPercent'),
            }
    except Exception as e:
        result['trainingReadiness'] = {'error': str(e)}

    # Training Status / acute load / load ratio (Fenix 8 Pro)
    try:
        ts = api.get_training_status(today)
        rec = (ts.get('mostRecentTrainingStatus') or {}) if isinstance(ts, dict) else {}
        latest = rec.get('latestTrainingStatusData', {}) or {}
        tsd = next(iter(latest.values()), {}) if latest else {}
        atl = tsd.get('acuteTrainingLoadDTO', {}) or {}
        result['trainingStatus'] = {
            'status': tsd.get('trainingStatusFeedbackPhrase') or tsd.get('trainingStatus'),
            'loadRatio': atl.get('dailyAcuteChronicWorkloadRatio') or atl.get('acwrPercent'),
            'loadRatioStatus': atl.get('acwrStatus'),
            'acuteLoad': atl.get('dailyTrainingLoadAcute'),
            'chronicLoad': atl.get('dailyTrainingLoadChronic'),
        }
    except Exception as e:
        result['trainingStatus'] = {'error': str(e)}

    # Endurance & Hill score (nice-to-have Fenix metrics; skip silently if unsupported)
    try:
        es = api.get_endurance_score(today)
        result['enduranceScore'] = {'value': (es or {}).get('overallScore')} if isinstance(es, dict) else {'value': None}
    except Exception as e:
        result['enduranceScore'] = {'error': str(e)}
    try:
        hs = api.get_hill_score(today)
        result['hillScore'] = {'value': (hs or {}).get('overallScore')} if isinstance(hs, dict) else {'value': None}
    except Exception as e:
        result['hillScore'] = {'error': str(e)}

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

    result['dataDate'] = today
    return result


def get_activity_zones(api, activity_id):
    """Real time-in-HR-zone for a single activity."""
    zones = []
    try:
        raw = api.get_activity_hr_in_timezones(activity_id)
        for z in (raw or []):
            secs = z.get('secsInZone') or 0
            znum = z.get('zoneNumber')
            if znum is not None:
                zones.append({'zone': int(znum), 'secs': int(secs)})
    except Exception as e:
        return {'error': str(e)}
    return {'zones': zones}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        data_type = qs.get('type', ['activities'])[0]

        if not HAS_GARMIN:
            return self._respond(503, {'error': 'garminconnect not installed'})

        # Token store alone is enough (recommended with MFA) — email/password only used as fallback in make_api()
        tokens_b64 = os.environ.get('GARMIN_TOKENS_B64')
        hint = ('Add GARMIN_TOKENS_B64 to Vercel env vars. '
                'Run generate_tokens.py locally to create it.')
        if not tokens_b64:
            return self._respond(401, {
                'error': 'MFA auth required — no token store configured',
                'hint': hint,
            })

        try:
            api = make_api()
            if data_type == 'body':
                # Today (local Norwegian date) — but right after midnight Garmin has no
                # data for the new day yet, so fall back to yesterday's full numbers.
                data = get_body_data(api)
                if body_is_empty(data):
                    yesterday = (datetime.fromisoformat(today_oslo()) - timedelta(days=1)).date().isoformat()
                    data = get_body_data(api, yesterday)
                self._respond(200, data)
            elif data_type == 'zones':
                act_id = qs.get('id', [''])[0]
                if not act_id or not act_id.isdigit():
                    return self._respond(400, {'error': 'missing or invalid activity id'})
                self._respond(200, get_activity_zones(api, act_id))
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
