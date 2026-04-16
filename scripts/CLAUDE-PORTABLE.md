# CLAUDE.md — Facturation MyConfort (MODE PORTABLE)

## CONTEXTE

Ce projet est utilise sur le portable de Bruno, SANS acces aux MCP du Mac Studio.
Les workflows sont executes via des scripts Python autonomes qui appellent les API directement.

## ACCESSIBILITE

L'utilisateur est malvoyant. Fournir du code complet, jamais de fragments.

## COMMANDE : "facture manuscrite colissimo"

Quand Bruno dit "facture manuscrite colissimo" et fournit une photo :

### ETAPE 1 — Extraction OCR (Claude vision)

Lire la photo et extraire TOUTES les donnees :
- Client : nom, adresse, CP, ville, telephone, email, code porte
- Facture : numero, date, conseiller
- Produits : nom, taille, quantite, prix, montant, observation (a livrer/emporte)
- Paiement : mode, acompte, total

Regles critiques :
- Ne pas confondre les chiffres manuscrits (0/4/6/9, 1/7)
- "Surconfort Bambou" = "Plateau Prestige"
- Prix barre : retenir le prix NON barre
- Verifier : somme des montants = total

### ETAPE 2 — Validation

Presenter les donnees extraites dans un tableau et ATTENDRE validation de Bruno.

### ETAPE 3 — Execution via script

Apres validation, executer :

```bash
python3 scripts/facture-colissimo.py --json '{
  "numero": "001483",
  "date": "2026-04-16",
  "nom": "FORET Bernadette",
  "adresse": "28 Rue de la Rouquette",
  "cp": "31240",
  "ville": "SAINT GILLES",
  "tel": "06 81 72 80 95",
  "email": "bernadette.foret12@gmail.com",
  "code_porte": "",
  "conseiller": "Karima",
  "paiement": "CB",
  "acompte": 0,
  "produits": [{"nom": "Oreiller Dual", "qte": 1, "prix": 60}],
  "total": 60,
  "poids": 1.4
}'
```

Le script fait TOUT automatiquement :
1. Cree la facture dans Supabase
2. Genere l'etiquette Colissimo (PDF)
3. Envoie 3 emails (depot + client + copie interne)
4. Deduit le stock
5. Ouvre le PDF pour impression
6. Affiche le rapport final

### GRILLE DE POIDS

| Produit | Poids |
|---|---|
| Oreiller (tous) | 1.4 kg |
| Oreiller Papillon | 1.8 kg |
| Traversin | 1.8 kg |
| Regulateur jambes | 3.0 kg |

## PREREQUIS

Le fichier `scripts/facture-colissimo.env` doit contenir les cles API.
Python 3 doit etre installe (pre-installe sur macOS).

## FICHIERS

| Fichier | Role |
|---|---|
| `scripts/facture-colissimo.py` | Script autonome complet |
| `scripts/facture-colissimo.env` | Cles API (ne pas commiter) |
| `scripts/CLAUDE-PORTABLE.md` | Ce fichier d'instructions |
