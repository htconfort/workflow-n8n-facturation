#!/usr/bin/env python3
"""
ETIQUETTE COLISSIMO SIMPLE — sans facture Supabase
====================================================
Genere UNIQUEMENT une etiquette Colissimo et ouvre Mail.app (macOS)
avec le PDF attache, pret a envoyer au depot.

PAS de facture Supabase. PAS de deduction stock. PAS d'email client.

Usage :
    python3 scripts/etiquette-colissimo-simple.py \
        --nom "GOY Marcel" \
        --adresse "250 Route des Massues" \
        --cp 69220 \
        --ville "BELLEVILLE-EN-BEAUJOLAIS" \
        --tel "0630985487" \
        --email "mathieu.goy@orange.fr" \
        --poids 2.8
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / "facture-colissimo.env"


def load_env():
    env = {}
    if not ENV_FILE.exists():
        print(f"ERREUR : {ENV_FILE} introuvable.")
        sys.exit(1)
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    required = ["COLISSIMO_PROXY_URL"]
    missing = [k for k in required if not env.get(k) or "REMPLACER" in env.get(k, "")]
    if missing:
        print(f"ERREUR : cles manquantes dans {ENV_FILE} : {', '.join(missing)}")
        sys.exit(1)
    return env


def generate_label(env, args):
    today = datetime.now().strftime("%Y-%m-%d")

    nom_parts = args.nom.split()
    last_name = nom_parts[0] if nom_parts else args.nom
    first_name = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else ""

    payload = {
        "outputFormat": {"x": 0, "y": 0, "outputPrintingType": "PDF_A4_300dpi"},
        "letter": {
            "service": {"productCode": "DOM", "depositDate": today},
            "parcel": {"weight": args.poids},
            "sender": {
                "address": {
                    "companyName": "MY CONFORT",
                    "line2": "88 AVENUE DES TERNES",
                    "countryCode": "FR",
                    "city": "PARIS",
                    "zipCode": "75017",
                }
            },
            "addressee": {
                "address": {
                    "lastName": last_name,
                    "firstName": first_name,
                    "line2": args.adresse,
                    "countryCode": "FR",
                    "city": args.ville.upper(),
                    "zipCode": args.cp,
                    "email": args.email or "",
                    "phone": (args.tel or "").replace(" ", ""),
                }
            },
        },
    }

    if args.code_porte:
        payload["letter"]["addressee"]["address"]["line3"] = args.code_porte

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        env["COLISSIMO_PROXY_URL"],
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"ERREUR Colissimo proxy HTTP {e.code}: {e.read()[:300]}")
        return None
    except Exception as e:
        print(f"ERREUR Colissimo proxy: {e}")
        return None

    text = raw.decode("latin-1", errors="replace")
    parcel_match = re.search(r'"parcelNumber"\s*:\s*"([^"]+)"', text)
    parcel_number = parcel_match.group(1) if parcel_match else "?"

    pdf_start = raw.find(b"%PDF")
    pdf_end = raw.rfind(b"%%EOF")
    if pdf_start < 0 or pdf_end < 0:
        print("ERREUR: PDF non trouve dans la reponse")
        print(f"Reponse brute: {raw[:500]}")
        return None

    pdf_data = raw[pdf_start : pdf_end + 5]
    ref = args.reference or f"{last_name}_{datetime.now().strftime('%Y%m%d-%H%M')}"
    safe_ref = re.sub(r"[^A-Za-z0-9_-]", "_", ref)
    pdf_path = f"/tmp/colissimo_{safe_ref}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_data)

    print(f"  Etiquette     : {pdf_path}")
    print(f"  Numero suivi  : {parcel_number}")
    print(f"  Poids         : {args.poids} kg")
    print(f"  Destinataire  : {last_name} {first_name}, {args.adresse}, {args.cp} {args.ville}")

    return {
        "pdf_path": pdf_path,
        "parcel_number": parcel_number,
        "last_name": last_name,
        "first_name": first_name,
    }


def open_mail_compose_macos(pdf_path, recipient, subject, body):
    """Ouvre Mail.app (macOS) avec message pre-rempli et PDF attache."""

    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''tell application "Mail"
    set newMessage to make new outgoing message with properties {{subject:"{esc(subject)}", content:"{esc(body)}", visible:true}}
    tell newMessage
        make new to recipient with properties {{address:"{esc(recipient)}"}}
        tell content to make new attachment with properties {{file name:(POSIX file "{esc(pdf_path)}") as alias}} at after the last paragraph
    end tell
    activate
end tell'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        subprocess.run(["osascript", script_path], check=True)
        print(f"  Mail.app ouvert — message pret pour {recipient}")
        print(f"  -> Verifier le contenu, puis cliquer Envoyer")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ERREUR osascript (exit {e.returncode})")
        return False
    except Exception as e:
        print(f"  ERREUR Mail.app: {e}")
        return False
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Etiquette Colissimo simple (sans facture)")
    parser.add_argument("--nom", required=True, help="Nom complet ex: 'GOY Marcel'")
    parser.add_argument("--adresse", required=True)
    parser.add_argument("--cp", required=True)
    parser.add_argument("--ville", required=True)
    parser.add_argument("--tel", default="")
    parser.add_argument("--email", default="", help="Email destinataire (optionnel)")
    parser.add_argument("--code-porte", default="")
    parser.add_argument("--poids", type=float, required=True)
    parser.add_argument("--email-depot", default="depothtconfort@gmail.com")
    parser.add_argument("--reference", default="")
    parser.add_argument("--no-mail", action="store_true", help="Ne pas ouvrir Mail.app")
    args = parser.parse_args()

    print("=" * 60)
    print("ETIQUETTE COLISSIMO SIMPLE")
    print("=" * 60)

    env = load_env()

    print("\n[1/2] Generation etiquette Colissimo...")
    result = generate_label(env, args)
    if not result:
        sys.exit(1)

    if not args.no_mail:
        print("\n[2/2] Preparation email depot...")
        nom_sujet = f"{result['last_name']} {result['first_name']}".strip()
        subject = f"Colissimo {nom_sujet} - {args.poids} kg - Suivi {result['parcel_number']}"
        body = (
            f"Etiquette Colissimo pour {nom_sujet}\n\n"
            f"Adresse : {args.adresse}, {args.cp} {args.ville}\n"
            f"Telephone : {args.tel}\n"
            f"Poids : {args.poids} kg\n"
            f"Numero de suivi : {result['parcel_number']}\n\n"
            f"Etiquette en piece jointe."
        )
        if sys.platform == "darwin":
            open_mail_compose_macos(result["pdf_path"], args.email_depot, subject, body)
        else:
            print(f"  macOS uniquement — envoyer manuellement {result['pdf_path']}")
            print(f"  vers {args.email_depot}")

    print("\n" + "=" * 60)
    print(f"__JSON_OUTPUT__:{json.dumps({'pdf_path': result['pdf_path'], 'parcel_number': result['parcel_number']})}")


if __name__ == "__main__":
    main()
