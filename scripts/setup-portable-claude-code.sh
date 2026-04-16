#!/usr/bin/env bash
# =============================================================================
# SETUP PORTABLE CLAUDE CODE — Facturation MyConfort
# =============================================================================
# A executer UNE FOIS sur un nouveau Mac (ou nouveau portable).
# Prepare l'environnement pour que Claude Code puisse lancer :
#   python3 scripts/facture-colissimo.py --json '{...}'
#
# Usage :
#   cd <racine-du-repo>
#   bash scripts/setup-portable-claude-code.sh
# =============================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "============================================================"
echo "SETUP PORTABLE CLAUDE CODE — Facturation MyConfort"
echo "============================================================"
echo "Repo     : $REPO_DIR"
echo "Scripts  : $SCRIPT_DIR"
echo ""

# -----------------------------------------------------------------------------
# 1. Verifier Python 3
# -----------------------------------------------------------------------------
echo "[1/5] Verification Python 3..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "  ERREUR : python3 introuvable."
    echo "  Installer Python 3 : https://www.python.org/downloads/"
    exit 1
fi
PY_VERSION=$(python3 --version)
echo "  OK — $PY_VERSION"

# -----------------------------------------------------------------------------
# 2. Verifier syntaxe du script Python
# -----------------------------------------------------------------------------
echo ""
echo "[2/5] Verification syntaxe facture-colissimo.py..."
if python3 -m py_compile "$SCRIPT_DIR/facture-colissimo.py"; then
    echo "  OK — syntaxe valide"
else
    echo "  ERREUR : syntaxe invalide dans facture-colissimo.py"
    exit 1
fi

# -----------------------------------------------------------------------------
# 3. Rendre le script executable
# -----------------------------------------------------------------------------
echo ""
echo "[3/5] Permission d'execution sur facture-colissimo.py..."
chmod +x "$SCRIPT_DIR/facture-colissimo.py"
echo "  OK"

# -----------------------------------------------------------------------------
# 4. Creer facture-colissimo.env a partir du template (si absent)
# -----------------------------------------------------------------------------
echo ""
echo "[4/5] Fichier de cles API (facture-colissimo.env)..."
ENV_FILE="$SCRIPT_DIR/facture-colissimo.env"
ENV_EXAMPLE="$SCRIPT_DIR/facture-colissimo.env.example"

if [ -f "$ENV_FILE" ]; then
    echo "  DEJA PRESENT — non ecrase : $ENV_FILE"
else
    if [ ! -f "$ENV_EXAMPLE" ]; then
        echo "  ERREUR : template introuvable : $ENV_EXAMPLE"
        exit 1
    fi
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "  CREE — copie depuis $ENV_EXAMPLE"
fi

# -----------------------------------------------------------------------------
# 5. Verifier si les cles sont remplies
# -----------------------------------------------------------------------------
echo ""
echo "[5/5] Verification des cles..."
MISSING=0
if grep -q "REMPLACER" "$ENV_FILE"; then
    echo "  ATTENTION : des cles contiennent encore 'REMPLACER' :"
    grep -n "REMPLACER" "$ENV_FILE" | sed 's/^/    /'
    MISSING=1
else
    echo "  OK — toutes les cles semblent remplies"
fi

echo ""
echo "============================================================"
if [ $MISSING -eq 1 ]; then
    echo "SETUP INCOMPLET"
    echo ""
    echo "PROCHAINE ETAPE : editer le fichier suivant et remplir"
    echo "les valeurs marquees 'REMPLACER_...' :"
    echo ""
    echo "    $ENV_FILE"
    echo ""
    echo "Cles a obtenir :"
    echo "  - SUPABASE_SERVICE_KEY  (dashboard Supabase > Settings > API)"
    echo "  - EXPRESS_CATALAN_API_KEY  (auprès du fournisseur Express Catalan)"
else
    echo "SETUP TERMINE"
    echo ""
    echo "Tester le script :"
    echo "    python3 $SCRIPT_DIR/facture-colissimo.py --help"
fi
echo "============================================================"
