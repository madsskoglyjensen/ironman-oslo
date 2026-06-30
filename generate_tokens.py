#!/usr/bin/env python3
"""
Kjør denne ÉN gang lokalt for å generere Garmin-tokens til Vercel.

Steg:
  1. pip install garminconnect
  2. python generate_tokens.py
  3. Kopier GARMIN_TOKENS_B64-verdien
  4. Vercel Dashboard → ironman-oslo → Settings → Environment Variables
     → Add: GARMIN_TOKENS_B64 = <den kopierte verdien>
  5. Redeploy i Vercel

Tokens varer i ~90 dager. Kjør scriptet på nytt hvis API-et slutter å virke.
"""

import base64, json, os, tempfile, getpass

try:
    from garminconnect import Garmin
except ImportError:
    print("Installer garminconnect: pip install garminconnect")
    exit(1)

print("=== Garmin Token Generator ===\n")
email = input("Garmin e-post: ").strip()
password = getpass.getpass("Garmin passord: ")

print("\nLogger inn... (MFA-kode kan bli spurt)")

def get_mfa():
    return input("MFA-kode fra autentiseringsapp: ").strip()

tmpdir = tempfile.mkdtemp()

try:
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=get_mfa)
    api.login(tokenstore=tmpdir)
    tokens_b64 = api.garth.dumps()
    print("\n✅ Login vellykket!\n")
    print("=" * 60)
    print("GARMIN_TOKENS_B64 (legg til i Vercel env vars):")
    print("=" * 60)
    print(tokens_b64)
    print("=" * 60)
    print("\nVercel Dashboard → ironman-oslo → Settings → Environment Variables")
    print("→ Legg til ny: GARMIN_TOKENS_B64 = (lim inn verdien over)")
    print("→ Klikk Save → Deployments → Redeploy")
except Exception as e:
    print(f"\n❌ Feil: {e}")
    print("Sjekk e-post/passord og prøv igjen.")
