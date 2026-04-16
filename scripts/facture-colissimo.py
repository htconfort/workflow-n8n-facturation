#!/usr/bin/env python3
"""
FACTURE MANUSCRITE COLISSIMO — Script autonome pour Claude Code (portable)
==========================================================================
Ce script reproduit le workflow complet "facture manuscrite colissimo"
sans dependre des MCP du Mac Studio. Il utilise les API directement.

Usage par Claude Code :
    python3 scripts/facture-colissimo.py \
        --numero 001483 \
        --date 2026-04-16 \
        --nom "FORET Bernadette" \
        --adresse "28 Rue de la Rouquette" \
        --cp 31240 \
        --ville "SAINT GILLES" \
        --tel "06 81 72 80 95" \
        --email "bernadette.foret12@gmail.com" \
        --conseiller "Karima" \
        --paiement "CB" \
        --produits '[{"nom":"Oreiller Dual","qte":1,"prix":60}]' \
        --total 60 \
        --poids 1.4

Ou en mode interactif (Claude Code fournit le JSON complet) :
    python3 scripts/facture-colissimo.py --json '{...}'
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / "facture-colissimo.env"


def load_env():
    """Charge les variables depuis facture-colissimo.env"""
    env = {}
    if not ENV_FILE.exists():
        print(f"ERREUR : fichier {ENV_FILE} introuvable.")
        print("Copier facture-colissimo.env dans le meme dossier que ce script.")
        sys.exit(1)

    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()

    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "N8N_BASE_URL", "COLISSIMO_PROXY_URL"]
    missing = [k for k in required if not env.get(k) or "REMPLACER" in env.get(k, "")]
    if missing:
        print(f"ERREUR : cles manquantes dans {ENV_FILE} : {', '.join(missing)}")
        sys.exit(1)

    return env


def http_request(url, data=None, headers=None, method="POST"):
    """Appel HTTP generique avec gestion d'erreur"""
    if headers is None:
        headers = {"Content-Type": "application/json"}

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": resp.read()}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read(), "error": str(e)}
    except Exception as e:
        return {"status": 0, "body": b"", "error": str(e)}


def supabase_rpc(env, query):
    """Execute une requete SQL via la RPC Supabase execute_sql"""
    url = f"{env['SUPABASE_URL']}/rest/v1/rpc/execute_sql"
    headers = {
        "Content-Type": "application/json",
        "apikey": env["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
    }
    result = http_request(url, {"query": query}, headers)
    if result["status"] == 200:
        return json.loads(result["body"])
    else:
        print(f"  ERREUR Supabase RPC: {result.get('error', result['body'][:200])}")
        return None


def supabase_insert(env, table, data):
    """Insert dans une table Supabase"""
    url = f"{env['SUPABASE_URL']}/rest/v1/{table}"
    headers = {
        "Content-Type": "application/json",
        "apikey": env["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
        "Prefer": "return=representation",
    }
    result = http_request(url, data, headers)
    if result["status"] in (200, 201):
        return json.loads(result["body"])
    else:
        print(f"  ERREUR Supabase INSERT: {result.get('error', result['body'][:500])}")
        return None


def supabase_update(env, table, filters, updates):
    """Update dans une table Supabase"""
    filter_str = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    url = f"{env['SUPABASE_URL']}/rest/v1/{table}?{filter_str}"
    headers = {
        "Content-Type": "application/json",
        "apikey": env["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
        "Prefer": "return=representation",
    }
    result = http_request(url, updates, headers, method="PATCH")
    if result["status"] in (200, 204):
        try:
            return json.loads(result["body"])
        except Exception:
            return [{"status": "ok"}]
    else:
        print(f"  ERREUR Supabase UPDATE: {result.get('error', result['body'][:500])}")
        return None


# =========================================================================
# ETAPE 1 : Creation facture Supabase
# =========================================================================

def create_facture_supabase(env, facture):
    """Cree la facture dans Supabase via le webhook n8n create-facture"""
    print("\n[ETAPE 1] Creation facture Supabase...")

    url = f"{env['N8N_BASE_URL']}/create-facture"
    payload = {
        "nom_client": facture["nom"],
        "email_client": facture["email"],
        "telephone_client": facture["tel"],
        "adresse_client": f"{facture['adresse']}, {facture['cp']} {facture['ville']}",
        "produits": facture["produits_supabase"],
        "montant_ttc": facture["total"],
        "mode_paiement": facture["paiement"],
        "conseiller": facture["conseiller"],
        "acompte": facture.get("acompte", 0),
        "numero_facture": facture["numero"],
        "date_facture": facture["date"],
    }

    result = http_request(url, payload)

    if result["status"] == 200:
        try:
            data = json.loads(result["body"])
            facture_id = data.get("facture_id", "?")
            print(f"  OK — Facture ID: {facture_id}, Numero: {facture['numero']}")
            return {"success": True, "facture_id": facture_id}
        except Exception:
            print(f"  OK (status 200) — reponse brute: {result['body'][:200]}")
            return {"success": True, "facture_id": "?"}
    else:
        print(f"  ERREUR: {result.get('error', 'status ' + str(result['status']))}")
        print("  Fallback : creation directe via Supabase RPC...")
        return create_facture_supabase_direct(env, facture)


def create_facture_supabase_direct(env, facture):
    """Fallback : cree la facture directement via Supabase REST API"""
    produits_json = json.dumps(facture["produits_supabase"]).replace("'", "''")
    query = f"""
    INSERT INTO factures_full (
        numero_facture, date_facture, nom_client, email_client,
        telephone_client, adresse_client, produits, montant_ttc,
        mode_paiement, conseiller, acompte, statut
    ) VALUES (
        '{facture["numero"]}',
        '{facture["date"]}',
        '{facture["nom"].replace("'", "''")}',
        '{facture["email"]}',
        '{facture["tel"]}',
        '{facture["adresse"]}, {facture["cp"]} {facture["ville"]}'.replace("'", "''"),
        '{produits_json}'::jsonb,
        {facture["total"]},
        '{facture["paiement"]}',
        '{facture["conseiller"]}',
        {facture.get("acompte", 0)},
        'validee'
    ) RETURNING id, numero_facture;
    """
    result = supabase_rpc(env, query)
    if result:
        print(f"  OK (direct) — {result}")
        return {"success": True, "facture_id": result}
    return {"success": False}


# =========================================================================
# ETAPE 2 : Generation etiquette Colissimo
# =========================================================================

def generate_colissimo_label(env, facture):
    """Genere l'etiquette Colissimo via le proxy Netlify"""
    print("\n[ETAPE 2] Generation etiquette Colissimo...")

    today = datetime.now().strftime("%Y-%m-%d")

    nom_parts = facture["nom"].split()
    last_name = nom_parts[0] if nom_parts else facture["nom"]
    first_name = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else ""

    payload = {
        "outputFormat": {"x": 0, "y": 0, "outputPrintingType": "PDF_A4_300dpi"},
        "letter": {
            "service": {"productCode": "DOM", "depositDate": today},
            "parcel": {"weight": facture["poids"]},
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
                    "line2": facture["adresse"],
                    "countryCode": "FR",
                    "city": facture["ville"].upper(),
                    "zipCode": facture["cp"],
                    "email": facture["email"],
                    "phone": facture["tel"].replace(" ", ""),
                }
            },
        },
    }

    if facture.get("code_porte"):
        payload["letter"]["addressee"]["address"]["line3"] = facture["code_porte"]

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
    except Exception as e:
        print(f"  ERREUR Colissimo proxy: {e}")
        return None

    text = raw.decode("latin-1")
    parcel_match = re.search(r'"parcelNumber"\s*:\s*"([^"]+)"', text)
    parcel_number = parcel_match.group(1) if parcel_match else None

    pdf_start = raw.find(b"%PDF")
    pdf_end = raw.rfind(b"%%EOF")

    if pdf_start < 0 or pdf_end < 0:
        print("  ERREUR: PDF non trouve dans la reponse Colissimo")
        return None

    pdf_data = raw[pdf_start : pdf_end + 5]
    pdf_path = f"/tmp/colissimo_{facture['numero']}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_data)

    pdf_b64 = base64.b64encode(pdf_data).decode()

    print(f"  OK — Numero suivi: {parcel_number}")
    print(f"  PDF: {pdf_path} ({len(pdf_data)} bytes)")

    return {
        "parcel_number": parcel_number,
        "pdf_path": pdf_path,
        "pdf_b64": pdf_b64,
        "url_suivi": f"https://www.laposte.fr/outils/suivre-vos-envois?code={parcel_number}",
    }


# =========================================================================
# ETAPE 3 : Envoi webhook n8n Colissimo (3 emails)
# =========================================================================

def send_colissimo_webhook(env, facture, colissimo):
    """Envoie le webhook n8n qui declenche les 3 emails"""
    print("\n[ETAPE 3] Envoi webhook n8n colissimo-expedition...")

    resume = ", ".join(
        f"{p['qte']} {p['nom']}" for p in facture["produits"]
    )

    payload = {
        "numero_suivi": colissimo["parcel_number"],
        "url_suivi": colissimo["url_suivi"],
        "etiquette_pdf_base64": colissimo["pdf_b64"],
        "poids_kg": facture["poids"],
        "numero_facture": facture["numero"],
        "nom_client": facture["nom"],
        "email_client": facture["email"],
        "resume_produits": resume,
        "objet_email_depot": f"Colissimo {facture['numero']} - {resume} - {facture['nom'].split()[0]}",
        "objet_email_client": f"Votre commande HT CONFORT {facture['numero']} a ete expediee - {resume}",
        "objet_email_copie": f"[COPIE] Colissimo {facture['numero']} - {resume} - {facture['nom'].split()[0]}",
        "email_depot": "depothtconfort@gmail.com",
        "email_verification": "myconfort66@gmail.com",
        "transporteur": "colissimo",
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{env['N8N_BASE_URL']}/colissimo-expedition",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  OK — {result.get('message', 'emails envoyes')}")
            return True
    except Exception as e:
        print(f"  ERREUR webhook: {e}")
        return False


# =========================================================================
# ETAPE 4 : Deduction stock Supabase
# =========================================================================

STOCK_NAMES = {
    "oreiller dual": "Oreiller Dual",
    "oreiller thalasso": "Oreiller Thalasso",
    "oreiller papillon": "Oreiller Papillon",
    "oreiller panama": "Oreiller Panama",
    "oreiller douceur": "Oreiller Douceur",
    "oreiller voyage": "Oreiller Voyage",
    "traversin": "Traversin Bambou",
    "regulateur jambes": "Regulateur Jambes",
    "repose pied": "Regulateur Jambes",
}


def deduct_stock(env, facture):
    """Deduit le stock pour chaque produit"""
    print("\n[ETAPE 4] Deduction stock...")

    results = []
    for prod in facture["produits"]:
        nom_lower = prod["nom"].lower()
        stock_name = None
        for key, val in STOCK_NAMES.items():
            if key in nom_lower:
                stock_name = val
                break

        if not stock_name:
            print(f"  SKIP — Produit '{prod['nom']}' non trouve dans la table de correspondance")
            results.append({"produit": prod["nom"], "status": "skip"})
            continue

        query = f"SELECT id, product_name, general_stock FROM stock WHERE product_name = '{stock_name}'"
        rows = supabase_rpc(env, query)

        if not rows or len(rows) == 0:
            print(f"  WARN — '{stock_name}' non trouve dans la table stock")
            results.append({"produit": prod["nom"], "status": "not_found"})
            continue

        row = rows[0]
        old_stock = row["general_stock"]
        new_stock = old_stock - prod["qte"]

        update_result = supabase_update(
            env, "stock", {"id": row["id"]}, {"general_stock": new_stock}
        )

        if update_result:
            print(f"  OK — {stock_name}: {old_stock} -> {new_stock} (-{prod['qte']})")
            results.append({
                "produit": stock_name,
                "id": row["id"],
                "avant": old_stock,
                "apres": new_stock,
                "status": "ok",
            })
        else:
            print(f"  ERREUR — update stock echoue pour {stock_name}")
            results.append({"produit": stock_name, "status": "error"})

    return results


# =========================================================================
# ETAPE 5 : Ouverture PDF + Rapport
# =========================================================================

def open_pdf(pdf_path):
    """Ouvre le PDF pour impression"""
    if sys.platform == "darwin":
        os.system(f'open "{pdf_path}"')
    elif sys.platform.startswith("linux"):
        os.system(f'xdg-open "{pdf_path}"')


def print_report(facture, facture_result, colissimo, webhook_ok, stock_results):
    """Affiche le rapport final"""
    print("\n" + "=" * 60)
    print(f"RAPPORT FINAL — FACTURE {facture['numero']} {facture['nom']} (COLISSIMO)")
    print("=" * 60)

    print(f"\n1. FACTURE SUPABASE")
    print(f"   ID: {facture_result.get('facture_id', '?')}")
    print(f"   Numero: {facture['numero']}")
    print(f"   Client: {facture['nom']}")
    print(f"   Montant: {facture['total']} EUR")

    if colissimo:
        print(f"\n2. COLISSIMO")
        print(f"   Suivi: {colissimo['parcel_number']}")
        print(f"   Poids: {facture['poids']} kg")
        print(f"   Lien: {colissimo['url_suivi']}")
        print(f"   PDF: {colissimo['pdf_path']}")

    print(f"\n3. EMAILS")
    print(f"   depothtconfort@gmail.com : {'OK' if webhook_ok else 'ERREUR'}")
    print(f"   {facture['email']} : {'OK' if webhook_ok else 'ERREUR'}")
    print(f"   myconfort66@gmail.com : {'OK' if webhook_ok else 'ERREUR'}")

    print(f"\n4. DEDUCTION STOCK")
    for s in stock_results:
        if s["status"] == "ok":
            print(f"   {s['produit']}: {s['avant']} -> {s['apres']} OK")
        elif s["status"] == "skip":
            print(f"   {s['produit']}: SKIP (non dans table)")
        elif s["status"] == "not_found":
            print(f"   {s['produit']}: NON TROUVE en stock")
        else:
            print(f"   {s['produit']}: ERREUR")

    print("\n" + "=" * 60)


# =========================================================================
# MAIN
# =========================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Facture manuscrite Colissimo — script autonome")

    parser.add_argument("--json", help="JSON complet de la facture (alternative aux args individuels)")

    parser.add_argument("--numero", help="Numero de facture (ex: 001483)")
    parser.add_argument("--date", help="Date facture YYYY-MM-DD", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--nom", help="Nom complet du client")
    parser.add_argument("--adresse", help="Adresse (rue)")
    parser.add_argument("--cp", help="Code postal")
    parser.add_argument("--ville", help="Ville")
    parser.add_argument("--tel", help="Telephone")
    parser.add_argument("--email", help="Email client")
    parser.add_argument("--code-porte", help="Code porte / etage", default="")
    parser.add_argument("--conseiller", help="Nom du conseiller", default="")
    parser.add_argument("--paiement", help="Mode de paiement (CB, Cheque, etc.)", default="CB")
    parser.add_argument("--acompte", type=float, help="Montant acompte", default=0)
    parser.add_argument("--produits", help='JSON liste produits: [{"nom":"...","qte":1,"prix":60}]')
    parser.add_argument("--total", type=float, help="Total TTC")
    parser.add_argument("--poids", type=float, help="Poids total en kg")
    parser.add_argument("--no-open-pdf", action="store_true", help="Ne pas ouvrir le PDF automatiquement")

    return parser.parse_args()


def main():
    args = parse_args()
    env = load_env()

    if args.json:
        facture = json.loads(args.json)
    else:
        if not all([args.numero, args.nom, args.adresse, args.cp, args.ville, args.tel, args.email, args.produits]):
            print("ERREUR : arguments manquants. Utiliser --json ou tous les arguments individuels.")
            print("Arguments requis : --numero --nom --adresse --cp --ville --tel --email --produits --total --poids")
            sys.exit(1)

        produits = json.loads(args.produits)
        facture = {
            "numero": args.numero,
            "date": args.date,
            "nom": args.nom,
            "adresse": args.adresse,
            "cp": args.cp,
            "ville": args.ville,
            "tel": args.tel,
            "email": args.email,
            "code_porte": args.code_porte,
            "conseiller": args.conseiller,
            "paiement": args.paiement,
            "acompte": args.acompte,
            "produits": produits,
            "total": args.total,
            "poids": args.poids,
        }

    facture["produits_supabase"] = [
        {
            "nom": p["nom"],
            "prix_ttc": p.get("prix", 0),
            "quantite": p.get("qte", 1),
            "remise": p.get("remise", 0),
            "type_remise": "percent",
        }
        for p in facture["produits"]
    ]

    print("=" * 60)
    print(f"FACTURE MANUSCRITE COLISSIMO — {facture['numero']} {facture['nom']}")
    print("=" * 60)

    # Etape 1 : Facture Supabase
    facture_result = create_facture_supabase(env, facture)

    # Etape 2 : Etiquette Colissimo
    colissimo = generate_colissimo_label(env, facture)

    # Etape 3 : Webhook n8n (3 emails)
    webhook_ok = False
    if colissimo:
        webhook_ok = send_colissimo_webhook(env, facture, colissimo)

    # Etape 4 : Deduction stock
    stock_results = deduct_stock(env, facture)

    # Etape 5 : Ouvrir PDF + Rapport
    if colissimo and not args.no_open_pdf if hasattr(args, "no_open_pdf") else True:
        if colissimo:
            open_pdf(colissimo["pdf_path"])

    print_report(facture, facture_result, colissimo, webhook_ok, stock_results)

    output = {
        "success": facture_result.get("success", False) and colissimo is not None and webhook_ok,
        "facture_id": facture_result.get("facture_id"),
        "numero": facture["numero"],
        "colissimo": {
            "parcel_number": colissimo["parcel_number"] if colissimo else None,
            "url_suivi": colissimo["url_suivi"] if colissimo else None,
            "pdf_path": colissimo["pdf_path"] if colissimo else None,
        },
        "emails": webhook_ok,
        "stock": stock_results,
    }
    print(f"\n__JSON_OUTPUT__:{json.dumps(output)}")


if __name__ == "__main__":
    main()
