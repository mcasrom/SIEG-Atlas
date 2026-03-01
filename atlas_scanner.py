#!/usr/bin/env python3
"""
SIEG-Atlas — Scanner V1.0
Monitoriza 6 ejes geopoliticos estructurales via RSS + APIs publicas.
Genera ficheros JSON en data/live/ para el dashboard app_atlas.py.

Ejes:
  - Petroleo & Gas    (precios, rutas, OPEC)
  - Rutas Maritimas   (estrechos, alertas navales)
  - Cables Submarinos (incidentes de infraestructura)
  - Mar de China      (disputas, incidentes navales)
  - Espacio           (lanzamientos, incidentes orbitales)
  - Cibergeopolitica  (alertas CISA/ENISA, actores APT)
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------

BASE_DIR      = Path(__file__).resolve().parent
DATA_LIVE     = BASE_DIR / "data" / "live"
DATA_STATIC   = BASE_DIR / "data" / "static"
MAPA_FUENTES  = BASE_DIR / "mapa_atlas.txt"
HISTORY_CSV   = DATA_LIVE / "history_atlas.csv"

RSS_ITEMS     = 20
TIMEOUT_HTTP  = 12
VERSION       = "V1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ATLAS")

# ---------------------------------------------------------------------------
# VOCABULARIO POR EJE
# ---------------------------------------------------------------------------

KEYWORDS = {
    "Petroleo": {
        "alto":  ["oil spill", "pipeline attack", "refinery fire", "opec cut",
                  "embargo", "sanctions oil", "supply disruption", "tanker seized"],
        "medio": ["oil price", "crude", "brent", "wti", "natural gas", "lng",
                  "opec", "energy crisis", "fuel shortage", "pipeline"],
        "bajo":  ["energy", "barrel", "production", "exports", "imports",
                  "reserves", "drilling", "offshore"],
    },
    "Maritimo": {
        "alto":  ["ship seized", "vessel attacked", "naval incident", "strait closed",
                  "piracy attack", "mine detected", "warship blocked", "maritime clash"],
        "medio": ["strait of hormuz", "suez canal", "strait of malacca", "bab el-mandeb",
                  "naval exercise", "coast guard", "shipping lane", "port blockade"],
        "bajo":  ["shipping", "maritime", "vessel", "cargo", "freight",
                  "port", "navigation", "sea route"],
    },
    "Cables": {
        "alto":  ["cable cut", "submarine cable severed", "cable sabotage",
                  "undersea cable damaged", "internet outage", "fiber cut"],
        "medio": ["submarine cable", "undersea fiber", "internet infrastructure",
                  "cable ship", "cable repair", "network disruption", "outage"],
        "bajo":  ["telecommunications", "bandwidth", "latency", "network",
                  "fiber optic", "connectivity", "data center"],
    },
    "MarChina": {
        "alto":  ["chinese warship", "pla navy", "south china sea clash",
                  "taiwan strait incident", "island seized", "naval standoff",
                  "coast guard confrontation", "military drills taiwan"],
        "medio": ["south china sea", "taiwan strait", "nine dash line",
                  "spratly", "paracel", "fiery cross", "militarization",
                  "freedom of navigation", "fonop"],
        "bajo":  ["china sea", "taiwan", "philippines sea", "vietnam sea",
                  "indo-pacific", "quad", "aukus", "asean"],
    },
    "Espacio": {
        "alto":  ["satellite destroyed", "anti-satellite", "asat test",
                  "space collision", "debris field", "orbital weapon",
                  "space attack", "jamming satellite"],
        "medio": ["rocket launch", "missile launch", "military satellite",
                  "space force", "lunar mission", "starlink", "spy satellite",
                  "orbital debris", "space race"],
        "bajo":  ["satellite", "launch", "orbit", "spacecraft", "nasa",
                  "esa", "roscosmos", "cnsa", "space station", "iss"],
    },
    "Ciber": {
        "alto":  ["critical infrastructure attack", "power grid hack",
                  "state-sponsored attack", "cyberwarfare", "ransomware attack",
                  "zero-day exploited", "apt attack", "election interference"],
        "medio": ["cyber attack", "data breach", "hacking", "malware",
                  "phishing campaign", "vulnerability", "exploit", "cisa alert",
                  "enisa warning", "apt group"],
        "bajo":  ["cybersecurity", "cyber", "hack", "security breach",
                  "intrusion", "threat actor", "patch", "cve"],
    },
}

# Terminos de desescalada por eje
DEESCALATION = [
    "resolved", "agreement", "ceasefire", "diplomatic", "normalized",
    "restored", "peace", "cooperation", "joint statement",
]

# Suelos base por modulo (score minimo garantizado)
SUELOS = {
    "Petroleo": 25,
    "Maritimo": 20,
    "Cables":   15,
    "MarChina": 40,
    "Espacio":  20,
    "Ciber":    30,
}

# ---------------------------------------------------------------------------
# CARGA DE FUENTES
# ---------------------------------------------------------------------------

def cargar_fuentes() -> dict:
    fuentes = {}
    if not MAPA_FUENTES.exists():
        log.error("No se encuentra %s", MAPA_FUENTES)
        return {}
    with open(MAPA_FUENTES, "r", encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("#") or not linea.strip():
                continue
            parts = [p.strip() for p in linea.split("|")]
            if len(parts) >= 3:
                try:
                    modulo, url, cf = parts[0], parts[1], float(parts[2])
                    fuentes.setdefault(modulo, []).append({"url": url, "cf": cf})
                except ValueError:
                    log.warning("Linea mal formada: %s", linea.strip())
    return fuentes


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

def _score_texto(texto: str, modulo: str) -> float:
    """Calcula score 0-100 para un texto segun el vocabulario del modulo."""
    t = texto.lower()

    # Desescalada
    deesc = sum(1 for w in DEESCALATION if w in t)
    if deesc >= 2:
        return 12.0

    kw = KEYWORDS.get(modulo, {})
    hits_alto  = sum(1 for w in kw.get("alto",  []) if w in t)
    hits_medio = sum(1 for w in kw.get("medio", []) if w in t)
    hits_bajo  = sum(1 for w in kw.get("bajo",  []) if w in t)

    if hits_alto + hits_medio + hits_bajo == 0:
        return 15.0

    score = (hits_alto * 25) + (hits_medio * 12) + (hits_bajo * 4)
    if deesc == 1:
        score *= 0.75

    return min(95.0, float(score))


def calcular_score_modulo(noticias: list, modulo: str, old_score: float) -> tuple:
    """
    Calcula score final del modulo y lista de titulares relevantes.
    Retorna (score: int, alertas: list[str])
    """
    if not noticias:
        log.warning("%s: Sin noticias.", modulo)
        return int(old_score), []

    scores_pond, pesos, alertas = [], [], []
    kw_alto = KEYWORDS.get(modulo, {}).get("alto", [])

    for n in noticias:
        s = _score_texto(n["text"], modulo)
        scores_pond.append(s * n["cf"])
        pesos.append(n["cf"])
        # Capturar titulares de alta severidad como alertas
        if s >= 50 and any(w in n["text"].lower() for w in kw_alto):
            titulo = n["text"][:120].strip()
            if titulo not in alertas:
                alertas.append(titulo)

    total_cf    = sum(pesos)
    score_bruto = sum(scores_pond) / total_cf if total_cf > 0 else 15.0

    # Suelo
    suelo       = SUELOS.get(modulo, 10)
    score_suelo = max(score_bruto, suelo)

    # Inercia de caida
    if score_suelo < old_score:
        score_final = (old_score * 0.6) + (score_suelo * 0.4)
    else:
        score_final = score_suelo

    return max(10, min(100, int(score_final))), alertas[:5]  # max 5 alertas


# ---------------------------------------------------------------------------
# HISTORICO
# ---------------------------------------------------------------------------

def cargar_old_score(modulo: str) -> float:
    path = DATA_LIVE / f"atlas_{modulo.lower()}.json"
    try:
        with open(path) as f:
            return float(json.load(f).get("score", 20))
    except (OSError, json.JSONDecodeError, ValueError):
        return 20.0


def guardar_resultado(modulo: str, score: int, alertas: list,
                      n_noticias: int, ts: float) -> None:
    path = DATA_LIVE / f"atlas_{modulo.lower()}.json"
    try:
        with open(path, "w") as f:
            json.dump({
                "modulo":    modulo,
                "score":     score,
                "alertas":   alertas,
                "noticias":  n_noticias,
                "timestamp": ts,
                "version":   VERSION,
            }, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.error("%s | No se pudo guardar: %s", modulo, e)


def guardar_historico(modulo: str, score: int, ts: float) -> None:
    try:
        with open(HISTORY_CSV, "a") as f:
            f.write(f"{ts},{modulo},{score}\n")
    except OSError as e:
        log.warning("No se pudo escribir historico: %s", e)


# ---------------------------------------------------------------------------
# FETCH RSS
# ---------------------------------------------------------------------------

def fetch_rss(fuentes: list, modulo: str) -> list:
    """Descarga y parsea todas las fuentes RSS de un modulo."""
    headers  = {"User-Agent": "Mozilla/5.0 (compatible; SIEG-Atlas/1.0)"}
    noticias = []

    for fuente in fuentes:
        try:
            r = requests.get(fuente["url"], headers=headers, timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:RSS_ITEMS]:
                title_el = item.find("title")
                desc_el  = item.find("description")
                title    = (title_el.text or "") if title_el is not None else ""
                desc     = (desc_el.text  or "") if desc_el  is not None else ""
                desc_limpio = re.sub(r"<[^>]+>", " ", desc)
                noticias.append({
                    "text": f"{title} {desc_limpio}",
                    "cf":   fuente["cf"],
                })
        except requests.RequestException as e:
            log.warning("%s | Fuente no disponible: %s", modulo, e)
        except ET.ParseError as e:
            log.warning("%s | RSS malformado: %s", modulo, e)

    return noticias


# ---------------------------------------------------------------------------
# SCAN PRINCIPAL
# ---------------------------------------------------------------------------

def scan() -> None:
    DATA_LIVE.mkdir(parents=True, exist_ok=True)
    DATA_STATIC.mkdir(parents=True, exist_ok=True)

    fuentes = cargar_fuentes()
    if not fuentes:
        log.error("Sin fuentes configuradas. Abortando.")
        return

    ts = time.time()
    print(f"--- S.I.E.G. ATLAS SCANNER {VERSION} | {datetime.now().strftime('%H:%M:%S')} ---")

    resultados = {}

    for modulo, data_fuentes in fuentes.items():
        old_score = cargar_old_score(modulo)
        noticias  = fetch_rss(data_fuentes, modulo)
        score, alertas = calcular_score_modulo(noticias, modulo, old_score)

        guardar_resultado(modulo, score, alertas, len(noticias), ts)
        guardar_historico(modulo, score, ts)
        resultados[modulo] = score

        delta     = score - int(old_score)
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        n_alertas = len(alertas)

        icono = ("🚨" if score >= 70 else
                 "⚠️ " if score >= 45 else "✅")
        print(f"[{icono}] {modulo:12} | Score: {score:3}% ({delta_str:>4}) | "
              f"Fuentes: {len(noticias):3} | Alertas: {n_alertas}")

        # Mostrar alertas activas
        for a in alertas:
            print(f"       ↳ {a[:100]}")

    # Resumen global
    if resultados:
        avg     = sum(resultados.values()) // len(resultados)
        top_mod = max(resultados, key=resultados.get)
        print(f"--- Atlas completado: {len(resultados)} modulos | "
              f"Avg: {avg}% | Modulo critico: {top_mod} ({resultados[top_mod]}%) ---")

        # Guardar resumen global
        try:
            with open(DATA_LIVE / "atlas_global.json", "w") as f:
                json.dump({
                    "scores":    resultados,
                    "avg":       avg,
                    "top":       top_mod,
                    "timestamp": ts,
                    "version":   VERSION,
                }, f, indent=2)
        except OSError as e:
            log.error("No se pudo guardar resumen global: %s", e)


if __name__ == "__main__":
    scan()
