#!/bin/bash
# =============================================================================
# SIEG-Atlas — Script de Sincronizacion
# Mismo patron robusto que SIEG-Core/update_sieg.sh
# =============================================================================

set -uo pipefail

ATLAS_DIR="/home/dietpi/SIEG-Atlas"
SCANNER_TIMEOUT=120
GIT_TIMEOUT=30
LOCK_FILE="/tmp/atlas_update.lock"
LOG_TAG="SIEG-ATLAS"

log() {
    local level="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" | \
        tee -a "${ATLAS_DIR}/atlas_sync.log" | \
        systemd-cat -t "$LOG_TAG" -p "${level,,}" 2>/dev/null || true
}

cleanup() {
    rm -f "$LOCK_FILE"
    log "INFO" "Lock liberado. Ciclo finalizado."
}

# LOCK GUARD
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "?")
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        log "WARNING" "Ciclo anterior en ejecucion (PID $LOCK_PID). Abortando."
        exit 0
    else
        log "WARNING" "Lock huerfano (PID $LOCK_PID). Limpiando."
        rm -f "$LOCK_FILE"
    fi
fi

echo $$ > "$LOCK_FILE"
trap cleanup EXIT

log "INFO" "=== Iniciando ciclo SIEG-Atlas | PID $$ ==="
cd "$ATLAS_DIR" || { log "ERR" "Directorio $ATLAS_DIR no encontrado."; exit 1; }

# Verificar rama main
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")
if [ "$BRANCH" != "main" ]; then
    log "WARNING" "HEAD en '$BRANCH'. Reconectando a main..."
    git checkout main >> atlas_sync.log 2>&1 || { log "ERR" "checkout main fallo."; exit 1; }
fi

# PASO 1: Scanner live
log "INFO" "Ejecutando atlas_scanner.py (timeout: ${SCANNER_TIMEOUT}s)..."
timeout "$SCANNER_TIMEOUT" /usr/bin/python3 atlas_scanner.py >> atlas_scanner.log 2>&1
EC=$?
if   [ $EC -eq 0 ];   then log "INFO"    "Scanner completado."
elif [ $EC -eq 124 ]; then log "ERR"     "TIMEOUT en scanner."
else                       log "WARNING" "Scanner codigo $EC."
fi

# PASO 2: Git sync
log "INFO" "Sincronizacion Git..."
git add -A >> atlas_sync.log 2>&1 || true

STASH_NEEDED=false
if ! git diff --quiet 2>/dev/null; then
    git stash --include-untracked >> atlas_sync.log 2>&1 || true
    STASH_NEEDED=true
fi

if git diff --cached --quiet; then
    log "INFO" "Sin cambios. Omitiendo commit."
else
    MSG="Atlas-update: $(date '+%a %b %d %H:%M:%S %Z %Y')"
    git commit -m "$MSG" >> atlas_sync.log 2>&1
    log "INFO" "Commit: $MSG"
fi

log "INFO" "git pull --rebase..."
timeout "$GIT_TIMEOUT" git pull --rebase origin main >> atlas_sync.log 2>&1
EC=$?
if [ $EC -ne 0 ]; then
    [ $EC -eq 124 ] && log "ERR" "TIMEOUT git pull." || log "ERR" "git pull fallo ($EC)."
    $STASH_NEEDED && git stash pop >> atlas_sync.log 2>&1 || true
    exit 1
fi

$STASH_NEEDED && git stash pop >> atlas_sync.log 2>&1 || true

log "INFO" "git push..."
timeout "$GIT_TIMEOUT" git push origin main >> atlas_sync.log 2>&1
EC=$?
if   [ $EC -eq 0 ];   then log "INFO" "Push exitoso a GitHub."
elif [ $EC -eq 124 ]; then log "ERR"  "TIMEOUT git push."; exit 1
else                       log "ERR"  "git push fallo ($EC)."; exit 1
fi

log "INFO" "=== Ciclo Atlas completado ==="
