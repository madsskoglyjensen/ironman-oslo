#!/usr/bin/env python3
"""
Kjør denne ÉN gang lokalt for å generere Garmin-tokens til Vercel.

  pip3 install garminconnect
  python3 generate_tokens.py
"""
import base64, json, os, tempfile, getpass, sys

try:
    from garminconnect import Garmin
except ImportError:
    print("Installer garminconnect: pip3 install garminconnect")
    sys.exit(1)

print("=== Garmin Token Generator ===\n")
email = input("Garmin e-post: ").strip()
password = getpass.getpass("Garmin passord: ")
print("\nLogger inn... (e-postkode eller autentiseringsapp kan bli spurt)")

def get_mfa():
    return input("Kode fra e-post eller autentiseringsapp: ").strip()

tmpdir = tempfile.mkdtemp()

try:
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=get_mfa)
    api.login(tokenstore=tmpdir)
    print("\n✅ Login vellykket! Henter tokens...\n")

    tokens_b64 = None

    # Method 1: api.garth.dumps() — garminconnect >= 0.2.x
    try:
        tokens_b64 = api.garth.dumps()
    except AttributeError:
        pass

    # Method 2: garth module directly
    if not tokens_b64:
        try:
            import garth
            tokens_b64 = garth.client.dumps()
        except Exception:
            pass

    # Method 3: read token files from tmpdir
    if not tokens_b64:
        files = {}
        for fname in os.listdir(tmpdir):
            fpath = os.path.join(tmpdir, fname)
            with open(fpath) as f:
                try:
                    files[fname] = json.load(f)
                except Exception:
                    files[fname] = f.read()
        if files:
            tokens_b64 = base64.b64encode(json.dumps(files).encode()).decode()

    if not tokens_b64:
        print("❌ Klarte ikke hente tokens. Prøv å kjøre scriptet på nytt.")
        sys.exit(1)

    print("=" * 60)
    print("GARMIN_TOKENS_B64 (legg til i Vercel env vars):")
    print("=" * 60)
    print(tokens_b64)
    print("=" * 60)
    print("\nVercel Dashboard → ironman-oslo → Settings → Environment Variables")
    print("→ Add New: GARMIN_TOKENS_B64 = (lim inn verdien over)")
    print("→ Save → Deployments → Redeploy siste deployment")

except Exception as e:
    print(f"\n❌ Feil: {e}")
    print("Sjekk e-post/passord og prøv igjen.")
