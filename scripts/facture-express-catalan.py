#!/usr/bin/env python3
"""
FACTURE MANUSCRITE EXPRESS CATALAN — Script autonome pour Claude Code (portable)
=================================================================================
Workflow complet : Supabase + expedition Express Catalan (France Express) + emails + stock.
Pour les livraisons de gros colis (matelas, surmatelas) > 4 kg.

Usage par Claude Code :
    python3 scripts/facture-express-catalan.py --json '{
      "numero": "001480",
      "date": "2026-04-16",
      "nom": "LEBALLEUR Michel et Aline",
      "adresse": "21 rue des Coquelicots",
      "cp": "31830",
      "ville": "PLAISANCE DU TOUCH",
      "tel": "0675125406",
      "email": "michel.leballeur0@orange.fr",
      "code_porte": "Maison",
      "conseiller": "Sylvie",
      "paiement": "Cheque (10x168EUR)",
      "acompte": 0,
      "produits": [
        {"nom": "Matelas Bambou 160x200", "qte": 1, "prix": 1680, "livraison": "a_livrer"},
        {"nom": "Plateau Prestige 160x200", "qte": 1, "prix": 166, "remise": 100, "livraison": "emporte"},
        {"nom": "Oreiller Papillon", "qte": 2, "prix": 166, "remise": 100, "livraison": "emporte"}
      ],
      "total": 1680,
      "delivery_date": "2026-05-19",
      "nb_colis": 1,
      "poids_total": 32
    }'

Regles colis (par defaut) :
  - Matelas seul           = 1 colis
  - Matelas + autres       = 2 colis (colis 1 = matelas, colis 2 = reste)
  - Sans matelas           = 1 colis
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / "facture-colissimo.env"  # meme fichier env que Colissimo

# ------------------------------------------------------------------
# TABLE ABREVIATIONS PRODUITS (bordereau Express Catalan)
# ------------------------------------------------------------------
ABREV = {
    "matelas bambou": "mat",
    "plateau prestige": "plat prest",
    "plateau fraiche": "plat fraich",
    "surconfort bambou": "plat prest",
    "surmatelas bambou": "surmat",
    "couette bambou": "couette",
    "oreiller papillon": "orei pap",
    "oreiller panama": "orei pan",
    "oreiller thalasso": "orei thal",
    "oreiller dual": "orei dual",
    "oreiller douceur": "orei douc",
    "oreiller voyage": "orei voy",
    "traversin bambou": "trav",
    "regulateur jambes": "repose pied",
    "repose pied": "repose pied",
    "protege-matelas": "prot mat",
}

# Poids par defaut (kg)
POIDS_DEFAUT = {
    "mat": 32,
    "plat prest": 5,
    "plat fraich": 5,
    "surmat": 10,
    "couette": 5,
    "orei pap": 1.8,
    "orei pan": 1.4,
    "orei thal": 1.4,
    "orei dual": 1.4,
    "orei douc": 1.4,
    "orei voy": 1.4,
    "trav": 1.8,
    "repose pied": 3.0,
    "prot mat": 1.5,
}

STOCK_NAMES = {
    "matelas bambou": "MATELAS BAMBOU",
    "plateau prestige": "PLATEAU PRESTIGE",
    "plateau fraiche": "PLATEAU FRAICHE",
    "surconfort bambou": "PLATEAU PRESTIGE",
    "surmatelas bambou": "SURMATELAS BAMBOU",
    "couette bambou": "Couette Bambou",
    "oreiller papillon": "Oreiller Papillon",
    "oreiller panama": "Oreiller Panama",
    "oreiller thalasso": "Oreiller Thalasso",
    "oreiller dual": "Oreiller Dual",
    "oreiller douceur": "Oreiller Douceur",
    "oreiller voyage": "Oreiller Voyage",
    "traversin bambou": "Traversin Bambou",
    "regulateur jambes": "Regulateur Jambes",
    "repose pied": "Regulateur Jambes",
}


# ------------------------------------------------------------------
# UTILITAIRES
# ------------------------------------------------------------------

def load_env():
    env = {}
    if not ENV_FILE.exists():
        print(f"ERREUR : {ENV_FILE} introuvable.")
        print("Copier facture-colissimo.env dans scripts/ et remplir les cles.")
        sys.exit(1)
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "N8N_BASE_URL", "EXPRESS_CATALAN_API_URL", "EXPRESS_CATALAN_API_KEY"]
    missing = [k for k in required if not env.get(k) or "REMPLACER" in env.get(k, "")]
    if missing:
        print(f"ERREUR : cles manquantes dans {ENV_FILE} : {', '.join(missing)}")
        sys.exit(1)
    return env


def http_post(url, data, headers=None):
    if headers is None:
        headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": resp.read()}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read(), "error": str(e)}
    except Exception as e:
        return {"status": 0, "body": b"", "error": str(e)}


def http_get(url, headers=None):
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": resp.read()}
    except Exception as e:
        return {"status": 0, "body": b"", "error": str(e)}


def supabase_rpc(env, query):
    url = f"{env['SUPABASE_URL']}/rest/v1/rpc/execute_sql"
    headers = {
        "Content-Type": "application/json",
        "apikey": env["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
    }
    result = http_post(url, {"query": query}, headers)
    if result["status"] == 200:
        return json.loads(result["body"])
    print(f"  ERREUR Supabase RPC ({result['status']}): {result['body'][:300]}")
    return None


def supabase_update(env, table, filters, updates):
    filter_str = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    url = f"{env['SUPABASE_URL']}/rest/v1/{table}?{filter_str}"
    headers = {
        "Content-Type": "application/json",
        "apikey": env["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
        "Prefer": "return=representation",
    }
    body = json.dumps(updates).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"[]")
    except Exception as e:
        print(f"  ERREUR Supabase UPDATE: {e}")
        return None


def abrev_produit(nom, taille=""):
    nom_lower = nom.lower()
    short = nom_lower
    for key, val in ABREV.items():
        if key in nom_lower:
            short = val
            break
    if taille:
        taille_clean = taille.replace(" ", "").replace("x", "x")
        return f"{short} {taille_clean}"
    return short


# ------------------------------------------------------------------
# ETAPE 1 : Facture Supabase
# ------------------------------------------------------------------

def create_facture_supabase(env, facture):
    print("\n[ETAPE 1] Creation facture Supabase...")
    url = f"{env['N8N_BASE_URL']}/create-facture"
    payload = {
        "nom_client": facture["nom"],
        "email_client": facture["email"],
        "telephone_client": facture["tel"],
        "adresse_client": f"{facture['adresse']}, {facture['cp']} {facture['ville']}",
        "produits": [
            {
                "nom": p["nom"],
                "prix_ttc": p.get("prix", 0),
                "quantite": p.get("qte", 1),
                "remise": p.get("remise", 0),
                "type_remise": "percent",
            }
            for p in facture["produits"]
        ],
        "montant_ttc": facture["total"],
        "mode_paiement": facture["paiement"],
        "conseiller": facture["conseiller"],
        "acompte": facture.get("acompte", 0),
        "numero_facture": facture["numero"],
        "date_facture": facture["date"],
    }
    result = http_post(url, payload)
    if result["status"] == 200:
        try:
            data = json.loads(result["body"])
            fid = data.get("facture_id", "?")
            print(f"  OK — Facture ID: {fid}, Numero: {facture['numero']}")
            return {"success": True, "facture_id": fid}
        except Exception:
            print(f"  OK (200) — reponse: {result['body'][:200]}")
            return {"success": True, "facture_id": "?"}
    print(f"  ERREUR n8n create-facture ({result['status']}): {result.get('error','')}")
    return {"success": False, "facture_id": None}


# ------------------------------------------------------------------
# ETAPE 2 : Expedition Express Catalan
# ------------------------------------------------------------------

def build_handling_units(facture):
    """
    Construit les handling_units selon les regles :
    - Matelas seul  -> 1 colis
    - Matelas+reste -> 2 colis (mat seul / tout le reste)
    - Sans matelas  -> 1 colis
    Seuls les produits "a_livrer" sont dans les colis.
    """
    produits_livraison = [p for p in facture["produits"] if p.get("livraison", "a_livrer") == "a_livrer"]
    produits_emportes  = [p for p in facture["produits"] if p.get("livraison", "a_livrer") == "emporte"]

    # Si aucun produit a livrer, on liste quand meme tout pour info
    if not produits_livraison:
        produits_livraison = facture["produits"]

    has_matelas = any("matelas" in p["nom"].lower() for p in produits_livraison)
    autres = [p for p in produits_livraison if "matelas" not in p["nom"].lower()]

    units = []

    if has_matelas and autres:
        # 2 colis
        mat = next(p for p in produits_livraison if "matelas" in p["nom"].lower())
        mat_abrev = abrev_produit(mat["nom"], mat.get("taille", ""))
        mat_poids = facture.get("poids_matelas", 32)

        autres_desc = "+".join(
            f"{p.get('qte',1)} {abrev_produit(p['nom'], p.get('taille',''))}"
            for p in autres
        )
        if produits_emportes:
            autres_desc += "+" + "+".join(
                f"{p.get('qte',1)} {abrev_produit(p['nom'], p.get('taille',''))} (emporte)"
                for p in produits_emportes
            )

        autres_poids = facture.get("poids_total", mat_poids + 5) - mat_poids

        units = [
            {"weight": mat_poids, "description": f"{mat.get('qte',1)} {mat_abrev}"},
            {"weight": max(1, autres_poids), "description": autres_desc},
        ]
    else:
        # 1 colis
        all_prod = produits_livraison + [
            {**p, "label": abrev_produit(p["nom"], p.get("taille","")) + " (emporte)"}
            for p in produits_emportes
        ]
        desc = "+".join(
            f"{p.get('qte',1)} {p.get('label', abrev_produit(p['nom'], p.get('taille','')))}"
            for p in all_prod
        )
        units = [{"weight": facture.get("poids_total", 10), "description": desc}]

    return units


def create_express_catalan_order(env, facture):
    print("\n[ETAPE 2] Creation expedition Express Catalan...")

    today_iso = datetime.now().strftime("%Y-%m-%dT08:00:00Z")
    handling_units = build_handling_units(facture)
    nb_colis = len(handling_units)
    poids_total = str(facture.get("poids_total", sum(u["weight"] for u in handling_units)))

    # Remarques destinataire (code porte + paiement)
    remarks_parts = []
    if facture.get("code_porte"):
        remarks_parts.append(facture["code_porte"])
    remarks_parts.append(facture["paiement"])
    remarks = " — ".join(remarks_parts)

    # Resume produits pour notes
    resume = ", ".join(
        f"{p.get('qte',1)} {p['nom']}" + (" (offert)" if p.get("remise",0) == 100 else "")
        for p in facture["produits"]
    )
    products_remarks = f"Fact {facture['numero']} {facture['nom']} — {resume} — {facture['paiement']}"

    payload = {
        "reference": facture["numero"],
        "consignee": {
            "name": facture["nom"],
            "address1": facture["adresse"],
            "zip": facture["cp"],
            "city": facture["ville"].upper(),
            "country": "FR",
            "remarks": remarks,
            "contact": {
                "name": facture["nom"],
                "email": facture["email"],
                "mobile": facture["tel"].replace(" ", ""),
            },
        },
        "packing": {
            "grossWeight": poids_total,
            "packagesTotalNumber": nb_colis,
        },
        "handling_units": handling_units,
        "shipment_date": today_iso,
        "products_remarks": products_remarks,
    }

    if facture.get("delivery_date"):
        payload["delivery_date"] = facture["delivery_date"]

    # Appel direct API Express Catalan via le MCP transport
    # Le MCP est un proxy HTTP — on l'appelle directement
    url = f"{env['EXPRESS_CATALAN_API_URL']}/v1/order"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {env['EXPRESS_CATALAN_API_KEY']}",
        "X-Station": "sc-106",
    }

    result = http_post(url, payload, headers)

    if result["status"] in (200, 201):
        try:
            data = json.loads(result["body"])
            order_uuid = data.get("response", {}).get("orderUUID", data.get("orderUUID", "?"))
            print(f"  OK — Order UUID: {order_uuid}")
            print(f"  Reference: {facture['numero']}, Colis: {nb_colis}, Poids: {poids_total} kg")
            if facture.get("delivery_date"):
                print(f"  Livraison souhaitee: {facture['delivery_date']}")
            return {"success": True, "order_uuid": order_uuid, "nb_colis": nb_colis}
        except Exception as e:
            print(f"  OK (status {result['status']}) mais parsing echoue: {e}")
            print(f"  Reponse brute: {result['body'][:500]}")
            return {"success": True, "order_uuid": "?", "nb_colis": nb_colis}
    else:
        print(f"  ERREUR Express Catalan ({result['status']}): {result.get('error', result['body'][:500])}")
        return {"success": False, "order_uuid": None, "nb_colis": nb_colis}


# ------------------------------------------------------------------
# ETAPE 3 : Email facture client (via n8n create_facture_complete)
# ------------------------------------------------------------------

def send_email_client(env, facture):
    print("\n[ETAPE 3] Envoi email facture au client...")
    url = f"{env['N8N_BASE_URL']}/facture-cursor"
    payload = {
        "nom_client": facture["nom"],
        "email_client": facture["email"],
        "telephone_client": facture["tel"],
        "adresse_client": f"{facture['adresse']}, {facture['cp']} {facture['ville']}",
        "produits": [
            {
                "nom": p["nom"],
                "quantite": p.get("qte", 1),
                "prix_ttc": p.get("prix", 0),
                "total_ttc": p.get("prix", 0) * p.get("qte", 1) if p.get("remise", 0) < 100 else 0,
            }
            for p in facture["produits"]
        ],
        "montant_ttc": facture["total"],
        "mode_paiement": facture["paiement"],
        "conseiller": facture["conseiller"],
        "acompte": facture.get("acompte", 0),
    }
    result = http_post(url, payload)
    if result["status"] == 200:
        print(f"  OK — Email envoye a {facture['email']} + copie myconfort66@gmail.com")
        return True
    print(f"  ERREUR email ({result['status']}): {result.get('error', result['body'][:200])}")
    return False


# ------------------------------------------------------------------
# ETAPE 4 : Deduction stock
# ------------------------------------------------------------------

def deduct_stock(env, facture):
    print("\n[ETAPE 4] Deduction stock...")
    results = []

    for prod in facture["produits"]:
        nom_lower = prod["nom"].lower()
        stock_name = None

        for key, val in STOCK_NAMES.items():
            if key in nom_lower:
                stock_name = val
                if prod.get("taille"):
                    stock_name += f" {prod['taille']}"
                break

        if not stock_name:
            print(f"  SKIP — '{prod['nom']}' non trouve dans table correspondance")
            results.append({"produit": prod["nom"], "status": "skip"})
            continue

        safe_name = stock_name.replace("'", "''")
        query = f"SELECT id, product_name, general_stock FROM stock WHERE product_name ILIKE '%{safe_name}%' LIMIT 1"
        rows = supabase_rpc(env, query)

        if not rows:
            print(f"  WARN — '{stock_name}' non trouve en stock Supabase")
            results.append({"produit": prod["nom"], "status": "not_found"})
            continue

        row = rows[0]
        old_stock = row["general_stock"]
        qte = prod.get("qte", 1)
        new_stock = old_stock - qte

        upd = supabase_update(env, "stock", {"id": row["id"]}, {"general_stock": new_stock})
        if upd is not None:
            print(f"  OK — {row['product_name']}: {old_stock} -> {new_stock} (-{qte})")
            results.append({"produit": row["product_name"], "id": row["id"], "avant": old_stock, "apres": new_stock, "status": "ok"})
        else:
            print(f"  ERREUR — update echoue pour {stock_name}")
            results.append({"produit": stock_name, "status": "error"})

    return results


# ------------------------------------------------------------------
# RAPPORT FINAL
# ------------------------------------------------------------------

def print_report(facture, facture_result, expedition_result, email_ok, stock_results):
    print("\n" + "=" * 65)
    print(f"RAPPORT FINAL — FACTURE {facture['numero']} {facture['nom']} (EXPRESS CATALAN)")
    print("=" * 65)

    print(f"\n1. FACTURE SUPABASE")
    print(f"   ID       : {facture_result.get('facture_id', '?')}")
    print(f"   Numero   : {facture['numero']}")
    print(f"   Client   : {facture['nom']}")
    print(f"   Montant  : {facture['total']} EUR")
    print(f"   Paiement : {facture['paiement']}")

    print(f"\n2. EXPEDITION EXPRESS CATALAN")
    if expedition_result.get("success"):
        print(f"   Order UUID : {expedition_result.get('order_uuid', '?')}")
        print(f"   Colis      : {expedition_result.get('nb_colis', '?')}")
        print(f"   Poids      : {facture.get('poids_total', '?')} kg")
        if facture.get("delivery_date"):
            print(f"   Livraison  : {facture['delivery_date']}")
        print(f"   Statut     : Suspendue (normal — sera activee par Express Catalan)")
    else:
        print(f"   ERREUR : expedition non creee")

    print(f"\n3. EMAILS")
    print(f"   {facture['email']} : {'OK' if email_ok else 'ERREUR'}")
    print(f"   myconfort66@gmail.com : {'OK' if email_ok else 'ERREUR'}")

    print(f"\n4. DEDUCTION STOCK")
    for s in stock_results:
        if s["status"] == "ok":
            print(f"   {s['produit']}: {s['avant']} -> {s['apres']} OK")
        elif s["status"] == "skip":
            print(f"   {s['produit']}: SKIP")
        elif s["status"] == "not_found":
            print(f"   {s['produit']}: NON TROUVE")
        else:
            print(f"   {s['produit']}: ERREUR")

    print("\n" + "=" * 65)

    output = {
        "success": facture_result.get("success") and expedition_result.get("success"),
        "facture_id": facture_result.get("facture_id"),
        "numero": facture["numero"],
        "expedition": {
            "order_uuid": expedition_result.get("order_uuid"),
            "nb_colis": expedition_result.get("nb_colis"),
        },
        "emails": email_ok,
        "stock": stock_results,
    }
    print(f"\n__JSON_OUTPUT__:{json.dumps(output)}")


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Facture manuscrite Express Catalan — script autonome")
    parser.add_argument("--json", required=True, help="JSON complet de la facture")
    args = parser.parse_args()

    env = load_env()
    facture = json.loads(args.json)

    print("=" * 65)
    print(f"FACTURE MANUSCRITE EXPRESS CATALAN — {facture['numero']} {facture['nom']}")
    print("=" * 65)

    facture_result  = create_facture_supabase(env, facture)
    expedition_result = create_express_catalan_order(env, facture)
    email_ok        = send_email_client(env, facture)
    stock_results   = deduct_stock(env, facture)

    print_report(facture, facture_result, expedition_result, email_ok, stock_results)


if __name__ == "__main__":
    main()
