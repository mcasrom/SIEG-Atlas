#!/usr/bin/env python3
"""
SIEG-Atlas Scanner V1.1
Fixes vs V1.0:
  - Vocabulario ampliado: Houthi, Mar Rojo, Hormuz, tanker, drone ship
  - Suelos reajustados: Maritimo 45, Petroleo 35 (conflicto activo)
  - Aliases de region para capturar menciones indirectas
  - Fuentes muertas reemplazadas
  - Reuters DNS fix: reemplazado por feeds alternativos
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

BASE_DIR     = Path(__file__).resolve().parent
DATA_LIVE    = BASE_DIR / "data" / "live"
DATA_STATIC  = BASE_DIR / "data" / "static"
MAPA_FUENTES = BASE_DIR / "mapa_atlas.txt"
HISTORY_CSV  = DATA_LIVE / "history_atlas.csv"

RSS_ITEMS    = 20
TIMEOUT_HTTP = 12
VERSION      = "V1.1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ATLAS")

# ---------------------------------------------------------------------------
# VOCABULARIO POR EJE — V1.1 ampliado
# ---------------------------------------------------------------------------

KEYWORDS = {
    "Petroleo": {
        "alto":  [
            "oil spill", "pipeline attack", "refinery fire", "opec cut",
            "embargo", "sanctions oil", "supply disruption", "tanker seized",
            "oil embargo", "energy blockade", "fuel crisis", "opec emergency",
            "strait of hormuz closed", "oil supply cut", "pipeline explosion",
            "energy sanctions", "crude oil ban",
        ],
        "medio": [
            "oil price", "crude", "brent", "wti", "natural gas", "lng",
            "opec", "energy crisis", "fuel shortage", "pipeline",
            "oil market", "energy supply", "gas prices", "oil production",
            "tanker", "petroleum", "oil exports", "energy security",
            "red sea shipping", "hormuz", "suez oil",
        ],
        "bajo": [
            "energy", "barrel", "production", "exports", "imports",
            "reserves", "drilling", "offshore", "refinery", "opec meeting",
        ],
    },
    "Maritimo": {
        "alto":  [
            "ship seized", "vessel attacked", "naval incident", "strait closed",
            "piracy attack", "mine detected", "warship blocked", "maritime clash",
            # FIX: vocabulario Houthi/Mar Rojo activo
            "houthi attack", "houthi missile", "houthi drone", "red sea attack",
            "tanker hit", "cargo ship attacked", "vessel struck", "ship fire",
            "naval blockade", "shipping blocked", "hormuz closure",
            "drone attack ship", "anti-ship missile", "ship sinking",
            "maritime emergency", "vessel hijacked", "port under attack",
        ],
        "medio": [
            "strait of hormuz", "suez canal", "strait of malacca", "bab el-mandeb",
            "naval exercise", "coast guard", "shipping lane", "port blockade",
            "houthi", "red sea", "yemen attack", "naval warning",
            "shipping disruption", "maritime alert", "vessel diverted",
            "tanker rerouted", "gulf of aden", "persian gulf tension",
            "naval patrol", "warship deployment",
        ],
        "bajo": [
            "shipping", "maritime", "vessel", "cargo", "freight",
            "port", "navigation", "sea route", "naval", "coast guard",
            "shipping cost", "freight rates", "maritime security",
        ],
    },
    "Cables": {
        "alto":  [
            "cable cut", "submarine cable severed", "cable sabotage",
            "undersea cable damaged", "internet outage", "fiber cut",
            "cable attack", "subsea sabotage", "internet disruption",
            "cable ship attacked", "network infrastructure attack",
        ],
        "medio": [
            "submarine cable", "undersea fiber", "internet infrastructure",
            "cable ship", "cable repair", "network disruption", "outage",
            "fiber optic cut", "cable fault", "internet blackout",
            "connectivity loss", "cable maintenance", "network outage",
        ],
        "bajo": [
            "telecommunications", "bandwidth", "latency", "network",
            "fiber optic", "connectivity", "data center", "internet",
            "submarine", "cable system",
        ],
    },
    "MarChina": {
        "alto":  [
            "chinese warship", "pla navy", "south china sea clash",
            "taiwan strait incident", "island seized", "naval standoff",
            "coast guard confrontation", "military drills taiwan",
            "china invasion", "taiwan blockade", "pla exercise",
            "naval confrontation", "chinese coast guard weapon",
            "water cannon", "laser attack", "ship collision china",
        ],
        "medio": [
            "south china sea", "taiwan strait", "nine dash line",
            "spratly", "paracel", "fiery cross", "militarization",
            "freedom of navigation", "fonop", "taiwan independence",
            "china military", "pla", "philippines sea dispute",
            "vietnam china", "indo-pacific tension",
        ],
        "bajo": [
            "china sea", "taiwan", "philippines sea", "vietnam sea",
            "indo-pacific", "quad", "aukus", "asean", "china navy",
        ],
    },
    "Espacio": {
        "alto":  [
            "satellite destroyed", "anti-satellite", "asat test",
            "space collision", "debris field", "orbital weapon",
            "space attack", "jamming satellite", "satellite blinded",
            "orbital bombardment", "space weapon deployed",
        ],
        "medio": [
            "rocket launch", "missile launch", "military satellite",
            "space force", "lunar mission", "starlink", "spy satellite",
            "orbital debris", "space race", "hypersonic", "icbm test",
            "reentry vehicle", "maneuver satellite",
        ],
        "bajo": [
            "satellite", "launch", "orbit", "spacecraft", "nasa",
            "esa", "roscosmos", "cnsa", "space station", "iss",
        ],
    },
    "Ciber": {
        "alto":  [
            "critical infrastructure attack", "power grid hack",
            "state-sponsored attack", "cyberwarfare", "ransomware attack",
            "zero-day exploited", "apt attack", "election interference",
            "water treatment hack", "hospital ransomware", "pipeline hack",
            "nuclear facility cyber", "military network breach",
        ],
        "medio": [
            "cyber attack", "data breach", "hacking", "malware",
            "phishing campaign", "vulnerability", "exploit", "cisa alert",
            "enisa warning", "apt group", "nation state hacker",
            "cyber espionage", "supply chain attack", "ddos attack",
        ],
        "bajo": [
            "cybersecurity", "cyber", "hack", "security breach",
            "intrusion", "threat actor", "patch", "cve",
            "vulnerability disclosure", "security advisory",
        ],
    },
}

# Desescalada
DEESCALATION = [
    "resolved", "agreement", "ceasefire", "diplomatic", "normalized",
    "restored", "peace", "cooperation", "joint statement", "de-escalation",
]

# ---------------------------------------------------------------------------
# FIX: SUELOS REAJUSTADOS
# Maritimo sube a 45 — Houthi activo, Mar Rojo bloqueado
# Petroleo sube a 35 — impacto energetico del conflicto
# MarChina sube a 42 — tension Taiwan/Filipinas sostenida
# Ciber sube a 33   — actividad APT elevada
# ---------------------------------------------------------------------------
SUELOS = {
    "Petroleo": 35,   # sube — impacto energetico conflicto Iran/Israel
    "Maritimo": 45,   # sube — Houthi activo, Mar Rojo disruption
    "Cables":   15,
    "MarChina": 42,   # sube — tension estructural sostenida
    "Espacio":  20,
    "Ciber":    33,   # sube — APT elevado
}

# ---------------------------------------------------------------------------
# ALIASES POR MODULO
# Captura menciones indirectas en titulares RSS
# ---------------------------------------------------------------------------
ALIASES = {
    "Petroleo": ["oil", "gas", "energy", "opec", "brent", "crude",
                 "petroleum", "fuel", "lng", "pipeline", "refinery"],
    "Maritimo": ["ship", "vessel", "tanker", "houthi", "red sea",
                 "hormuz", "suez", "naval", "maritime", "strait",
                 "cargo", "shipping", "port", "coast guard"],
    "Cables":   ["cable", "fiber", "internet", "network", "submarine",
                 "undersea", "telecom", "connectivity"],
    "MarChina": ["china", "taiwan", "philippines", "south china",
                 "pla", "beijing", "taiwan strait", "spratly"],
    "Espacio":  ["satellite", "rocket", "launch", "orbit", "space",
                 "missile", "debris", "starlink", "asat"],
    "Ciber":    ["cyber", "hack", "malware", "ransomware", "apt",
                 "breach", "attack", "vulnerability", "exploit"],
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
# SCORING V1.1 — con aliases
# ---------------------------------------------------------------------------

def _score_texto(texto: str, modulo: str) -> float:
    t = texto.lower()

    # Desescalada
    deesc = sum(1 for w in DEESCALATION if w in t)
    if deesc >= 2:
        return 12.0

    kw        = KEYWORDS.get(modulo, {})
    hits_alto  = sum(1 for w in kw.get("alto",  []) if w in t)
    hits_medio = sum(1 for w in kw.get("medio", []) if w in t)
    hits_bajo  = sum(1 for w in kw.get("bajo",  []) if w in t)

    if hits_alto + hits_medio + hits_bajo == 0:
        return 15.0

    score = (hits_alto * 25) + (hits_medio * 12) + (hits_bajo * 4)

    # Bonus si alias del modulo presente en el texto
    aliases = ALIASES.get(modulo, [])
    if any(a in t for a in aliases):
        score *= 1.25

    if deesc == 1:
        score *= 0.75

    return min(95.0, float(score))


def calcular_score_modulo(noticias: list, modulo: str,
                          old_score: float) -> tuple:
    if not noticias:
        log.warning("%s: Sin noticias.", modulo)
        return int(old_score), []

    scores_pond, pesos, alertas = [], [], []
    kw_alto = KEYWORDS.get(modulo, {}).get("alto", [])

    for n in noticias:
        s = _score_texto(n["text"], modulo)
        scores_pond.append(s * n["cf"])
        pesos.append(n["cf"])
        if s >= 45 and any(w in n["text"].lower() for w in kw_alto):
            titulo = n["text"][:120].strip()
            if titulo not in alertas:
                alertas.append(titulo)

    total_cf    = sum(pesos)
    score_bruto = sum(scores_pond) / total_cf if total_cf > 0 else 15.0

    suelo       = SUELOS.get(modulo, 10)
    score_suelo = max(score_bruto, suelo)

    if score_suelo < old_score:
        score_final = (old_score * 0.6) + (score_suelo * 0.4)
    else:
        score_final = score_suelo

    return max(10, min(100, int(score_final))), alertas[:5]


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
    headers  = {"User-Agent": "Mozilla/5.0 (compatible; SIEG-Atlas/1.1)"}
    noticias = []

    for fuente in fuentes:
        try:
            r = requests.get(fuente["url"], headers=headers,
                             timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:RSS_ITEMS]:
                title_el    = item.find("title")
                desc_el     = item.find("description")
                title       = (title_el.text or "") if title_el is not None else ""
                desc        = (desc_el.text  or "") if desc_el  is not None else ""
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
    print(f"--- S.I.E.G. ATLAS SCANNER {VERSION} | "
          f"{datetime.now().strftime('%H:%M:%S')} ---")

    resultados = {}

    for modulo, data_fuentes in fuentes.items():
        old_score      = cargar_old_score(modulo)
        noticias       = fetch_rss(data_fuentes, modulo)
        score, alertas = calcular_score_modulo(noticias, modulo, old_score)

        guardar_resultado(modulo, score, alertas, len(noticias), ts)
        guardar_historico(modulo, score, ts)
        resultados[modulo] = score

        delta     = score - int(old_score)
        delta_str = f"+{delta}" if delta > 0 else str(delta)

        icono = ("🚨" if score >= 70 else
                 "⚠️ " if score >= 45 else "✅")
        print(f"[{icono}] {modulo:12} | Score: {score:3}% ({delta_str:>4}) | "
              f"Fuentes: {len(noticias):3} | Alertas: {len(alertas)}")

        for a in alertas:
            print(f"       ↳ {a[:100]}")

    if resultados:
        avg     = sum(resultados.values()) // len(resultados)
        top_mod = max(resultados, key=resultados.get)
        print(f"--- Atlas completado: {len(resultados)} modulos | "
              f"Avg: {avg}% | Modulo critico: {top_mod} "
              f"({resultados[top_mod]}%) ---")

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
