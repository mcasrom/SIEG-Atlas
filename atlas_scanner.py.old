#!/usr/bin/env python3
"""
SIEG-Atlas Scanner V1.2 — Autolearning de Fuentes
Novedades vs V1.1:
  - Sistema de 3 capas: primarias -> banco alternativas -> Google News RSS
  - Indicador de calidad por modulo: VERDE/AZUL/AMARILLO/NARANJA/ROJO
  - Criterio minimo: 40 noticias procesadas por modulo
  - Fallback automatico hasta alcanzar el minimo
  - Calidad guardada en JSON y mostrada en terminal
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
LEARNED_FILE  = DATA_LIVE / "atlas_learned_sources.json"

RSS_ITEMS     = 20
TIMEOUT_HTTP  = 12
VERSION       = "V1.2"
MIN_NOTICIAS  = 40     # Umbral minimo aceptable de noticias por modulo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ATLAS")

# ---------------------------------------------------------------------------
# INDICADOR DE CALIDAD
# Verde:    >= 60 noticias  (cobertura optima)
# Azul:     >= 40 noticias  (cobertura aceptable — minimo)
# Amarillo: >= 25 noticias  (cobertura reducida)
# Naranja:  >= 10 noticias  (cobertura critica)
# Rojo:      < 10 noticias  (sin cobertura — solo suelo base)
# ---------------------------------------------------------------------------

def calcular_calidad(n_noticias: int, n_fuentes_activas: int,
                     uso_fallback: bool, uso_web: bool) -> dict:
    if n_noticias >= 60:
        nivel, emoji, css = "VERDE",    "🟢", "green"
    elif n_noticias >= 40:
        nivel, emoji, css = "AZUL",     "🔵", "blue"
    elif n_noticias >= 25:
        nivel, emoji, css = "AMARILLO", "🟡", "yellow"
    elif n_noticias >= 10:
        nivel, emoji, css = "NARANJA",  "🟠", "orange"
    else:
        nivel, emoji, css = "ROJO",     "🔴", "red"

    return {
        "nivel":            nivel,
        "emoji":            emoji,
        "css":              css,
        "noticias":         n_noticias,
        "fuentes_activas":  n_fuentes_activas,
        "uso_fallback":     uso_fallback,
        "uso_web":          uso_web,
    }

# ---------------------------------------------------------------------------
# BANCO DE FUENTES ALTERNATIVAS (CAPA 2)
# Fuentes de respaldo por modulo — activadas si primarias insuficientes
# ---------------------------------------------------------------------------

FALLBACK_SOURCES = {
    "Petroleo": [
        {"url": "https://www.ft.com/rss/home/uk",                          "cf": 0.9},
        {"url": "https://www.wsj.com/xml/rss/3_7085.xml",                  "cf": 0.9},
        {"url": "https://feeds.skynews.com/feeds/rss/business.xml",        "cf": 0.8},
        {"url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",    "cf": 0.8},
        {"url": "https://feeds.feedburner.com/PetroleumEconomist",         "cf": 0.9},
    ],
    "Maritimo": [
        {"url": "https://www.navalnews.com/feed/",                         "cf": 0.9},
        {"url": "https://www.maritimebulletin.net/feed/",                  "cf": 0.8},
        {"url": "https://feeds.skynews.com/feeds/rss/world.xml",           "cf": 0.8},
        {"url": "https://www.defensenews.com/rss/",                        "cf": 0.8},
        {"url": "https://www.janes.com/feeds/news",                        "cf": 0.9},
    ],
    "Cables": [
        {"url": "https://feeds.arstechnica.com/arstechnica/index",         "cf": 0.8},
        {"url": "https://www.zdnet.com/news/rss.xml",                      "cf": 0.8},
        {"url": "https://feeds.skynews.com/feeds/rss/technology.xml",      "cf": 0.8},
        {"url": "https://www.computerweekly.com/rss",                      "cf": 0.7},
        {"url": "https://www.networkworld.com/index.rss",                  "cf": 0.7},
    ],
    "MarChina": [
        {"url": "https://feeds.skynews.com/feeds/rss/world.xml",           "cf": 0.8},
        {"url": "https://www.defensenews.com/rss/",                        "cf": 0.8},
        {"url": "https://foreignpolicy.com/feed/",                         "cf": 0.9},
        {"url": "https://www.scmp.com/rss/91/feed",                        "cf": 0.7},
        {"url": "https://asia.nikkei.com/rss/feed/nar",                    "cf": 0.8},
    ],
    "Espacio": [
        {"url": "https://www.spaceflightnow.com/feed/",                    "cf": 0.9},
        {"url": "https://feeds.skynews.com/feeds/rss/science.xml",         "cf": 0.8},
        {"url": "https://phys.org/rss-feed/space-news/",                   "cf": 0.8},
        {"url": "https://www.universetoday.com/feed/",                     "cf": 0.7},
        {"url": "https://astronomy.com/rss/news",                          "cf": 0.7},
    ],
    "Ciber": [
        {"url": "https://www.securityweek.com/feed/",                      "cf": 0.9},
        {"url": "https://www.helpnetsecurity.com/feed/",                   "cf": 0.8},
        {"url": "https://feeds.skynews.com/feeds/rss/technology.xml",      "cf": 0.8},
        {"url": "https://www.infosecurity-magazine.com/rss/news/",         "cf": 0.8},
        {"url": "https://www.cyberscoop.com/feed/",                        "cf": 0.9},
    ],
}

# ---------------------------------------------------------------------------
# CAPA 3: GOOGLE NEWS RSS (ultimo recurso)
# Genera URL de busqueda RSS por terminos clave del modulo
# ---------------------------------------------------------------------------

GOOGLE_NEWS_QUERIES = {
    "Petroleo":  "oil+gas+opec+energy+petroleum",
    "Maritimo":  "maritime+shipping+houthi+red+sea+hormuz",
    "Cables":    "submarine+cable+internet+infrastructure",
    "MarChina":  "south+china+sea+taiwan+strait+naval",
    "Espacio":   "satellite+space+launch+military+orbit",
    "Ciber":     "cyberattack+hacking+ransomware+apt",
}

def build_google_news_url(modulo: str) -> str:
    query = GOOGLE_NEWS_QUERIES.get(modulo, modulo.lower())
    return f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

# ---------------------------------------------------------------------------
# VOCABULARIO (heredado de V1.1)
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
        ],
        "bajo": [
            "shipping", "maritime", "vessel", "cargo", "freight",
            "port", "navigation", "sea route", "naval",
        ],
    },
    "Cables": {
        "alto":  [
            "cable cut", "submarine cable severed", "cable sabotage",
            "undersea cable damaged", "internet outage", "fiber cut",
            "cable attack", "subsea sabotage", "network infrastructure attack",
        ],
        "medio": [
            "submarine cable", "undersea fiber", "internet infrastructure",
            "cable ship", "cable repair", "network disruption", "outage",
            "fiber optic cut", "cable fault", "internet blackout",
        ],
        "bajo": [
            "telecommunications", "bandwidth", "network",
            "fiber optic", "connectivity", "data center",
        ],
    },
    "MarChina": {
        "alto":  [
            "chinese warship", "pla navy", "south china sea clash",
            "taiwan strait incident", "island seized", "naval standoff",
            "coast guard confrontation", "military drills taiwan",
            "china invasion", "taiwan blockade", "pla exercise",
            "water cannon", "laser attack", "ship collision china",
        ],
        "medio": [
            "south china sea", "taiwan strait", "nine dash line",
            "spratly", "paracel", "militarization",
            "freedom of navigation", "fonop", "taiwan independence",
            "china military", "pla", "philippines sea dispute",
        ],
        "bajo": [
            "china sea", "taiwan", "philippines sea",
            "indo-pacific", "quad", "aukus", "asean",
        ],
    },
    "Espacio": {
        "alto":  [
            "satellite destroyed", "anti-satellite", "asat test",
            "space collision", "debris field", "orbital weapon",
            "space attack", "jamming satellite",
        ],
        "medio": [
            "rocket launch", "missile launch", "military satellite",
            "space force", "starlink", "spy satellite",
            "orbital debris", "space race", "hypersonic",
        ],
        "bajo": [
            "satellite", "launch", "orbit", "spacecraft",
            "nasa", "esa", "roscosmos", "cnsa",
        ],
    },
    "Ciber": {
        "alto":  [
            "critical infrastructure attack", "power grid hack",
            "state-sponsored attack", "cyberwarfare", "ransomware attack",
            "zero-day exploited", "apt attack", "election interference",
            "water treatment hack", "hospital ransomware", "pipeline hack",
        ],
        "medio": [
            "cyber attack", "data breach", "hacking", "malware",
            "phishing campaign", "vulnerability", "exploit",
            "apt group", "nation state hacker", "cyber espionage",
        ],
        "bajo": [
            "cybersecurity", "cyber", "hack", "security breach",
            "intrusion", "threat actor", "patch", "cve",
        ],
    },
}

DEESCALATION = [
    "resolved", "agreement", "ceasefire", "diplomatic", "normalized",
    "restored", "peace", "cooperation", "joint statement",
]

SUELOS = {
    "Petroleo": 35,
    "Maritimo": 45,
    "Cables":   15,
    "MarChina": 42,
    "Espacio":  20,
    "Ciber":    33,
}

ALIASES = {
    "Petroleo": ["oil", "gas", "energy", "opec", "brent", "crude",
                 "petroleum", "fuel", "lng", "pipeline", "refinery"],
    "Maritimo": ["ship", "vessel", "tanker", "houthi", "red sea",
                 "hormuz", "suez", "naval", "maritime", "strait",
                 "cargo", "shipping", "port"],
    "Cables":   ["cable", "fiber", "internet", "network", "submarine",
                 "undersea", "telecom", "connectivity"],
    "MarChina": ["china", "taiwan", "philippines", "south china",
                 "pla", "beijing", "spratly"],
    "Espacio":  ["satellite", "rocket", "launch", "orbit", "space",
                 "missile", "debris", "starlink", "asat"],
    "Ciber":    ["cyber", "hack", "malware", "ransomware", "apt",
                 "breach", "attack", "vulnerability", "exploit"],
}

# ---------------------------------------------------------------------------
# CARGA Y GUARDADO DE FUENTES APRENDIDAS
# ---------------------------------------------------------------------------

def cargar_fuentes_aprendidas() -> dict:
    """Carga el historial de fuentes descubiertas en ciclos anteriores."""
    if not LEARNED_FILE.exists():
        return {}
    try:
        with open(LEARNED_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def guardar_fuentes_aprendidas(aprendidas: dict) -> None:
    try:
        with open(LEARNED_FILE, "w") as f:
            json.dump(aprendidas, f, indent=2)
    except OSError as e:
        log.warning("No se pudo guardar fuentes aprendidas: %s", e)

# ---------------------------------------------------------------------------
# CARGA DE FUENTES PRIMARIAS
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
# FETCH RSS — con contador de fuentes activas
# ---------------------------------------------------------------------------

def fetch_rss(fuentes_lista: list, modulo: str,
              label: str = "primaria") -> tuple:
    """
    Descarga RSS. Retorna (noticias, n_fuentes_activas).
    label: 'primaria' | 'fallback' | 'web'
    """
    headers  = {"User-Agent": "Mozilla/5.0 (compatible; SIEG-Atlas/1.2)"}
    noticias = []
    activas  = 0

    for fuente in fuentes_lista:
        try:
            r = requests.get(fuente["url"], headers=headers,
                             timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            root  = ET.fromstring(r.content)
            items = root.findall(".//item")[:RSS_ITEMS]
            if items:
                activas += 1
            for item in items:
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
            if label == "primaria":
                log.warning("%s | [%s] Fuente no disponible: %s",
                            modulo, label, e)
        except ET.ParseError as e:
            if label == "primaria":
                log.warning("%s | [%s] RSS malformado: %s",
                            modulo, label, e)

    return noticias, activas


# ---------------------------------------------------------------------------
# SISTEMA DE 3 CAPAS — autolearning
# ---------------------------------------------------------------------------

def fetch_con_autolearning(modulo: str,
                           fuentes_primarias: list,
                           aprendidas: dict) -> tuple:
    """
    Intenta alcanzar MIN_NOTICIAS usando 3 capas:
      1. Fuentes primarias (mapa_atlas.txt)
      2. Banco de alternativas (FALLBACK_SOURCES)
      3. Google News RSS (busqueda por keywords)

    Retorna (noticias, calidad_dict, aprendidas_actualizadas)
    """
    uso_fallback = False
    uso_web      = False

    # --- CAPA 1: Primarias ---
    noticias, activas = fetch_rss(fuentes_primarias, modulo, "primaria")
    log.info("%s | Capa 1 (primarias): %d noticias / %d fuentes activas",
             modulo, len(noticias), activas)

    # --- CAPA 2: Fallback si insuficiente ---
    if len(noticias) < MIN_NOTICIAS:
        uso_fallback = True
        fallbacks = FALLBACK_SOURCES.get(modulo, [])

        # Incluir fuentes aprendidas en ciclos anteriores
        fuentes_aprendidas_modulo = [
            {"url": u, "cf": 0.7}
            for u in aprendidas.get(modulo, [])
        ]
        todas_fallback = fallbacks + fuentes_aprendidas_modulo

        n2, a2 = fetch_rss(todas_fallback, modulo, "fallback")
        noticias += n2
        activas  += a2
        log.info("%s | Capa 2 (fallback): +%d noticias | Total: %d",
                 modulo, len(n2), len(noticias))

    # --- CAPA 3: Google News RSS si sigue insuficiente ---
    if len(noticias) < MIN_NOTICIAS:
        uso_web = True
        google_url = build_google_news_url(modulo)
        try:
            n3, a3 = fetch_rss(
                [{"url": google_url, "cf": 0.6}],
                modulo, "web"
            )
            noticias += n3
            activas  += a3
            log.info("%s | Capa 3 (Google News): +%d noticias | Total: %d",
                     modulo, len(n3), len(noticias))

            # Guardar URL de Google News como fuente aprendida si aportó noticias
            if n3:
                if modulo not in aprendidas:
                    aprendidas[modulo] = []
                if google_url not in aprendidas[modulo]:
                    aprendidas[modulo].append(google_url)
                    log.info("%s | Nueva fuente aprendida: %s",
                             modulo, google_url)
        except Exception as e:
            log.warning("%s | Capa 3 fallida: %s", modulo, e)

    calidad = calcular_calidad(len(noticias), activas, uso_fallback, uso_web)
    return noticias, calidad, aprendidas


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

def _score_texto(texto: str, modulo: str) -> float:
    t = texto.lower()

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

    aliases = ALIASES.get(modulo, [])
    if any(a in t for a in aliases):
        score *= 1.25

    if deesc == 1:
        score *= 0.75

    return min(95.0, float(score))


def calcular_score_modulo(noticias: list, modulo: str,
                          old_score: float) -> tuple:
    if not noticias:
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
                      n_noticias: int, ts: float,
                      calidad: dict) -> None:
    path = DATA_LIVE / f"atlas_{modulo.lower()}.json"
    try:
        with open(path, "w") as f:
            json.dump({
                "modulo":           modulo,
                "score":            score,
                "alertas":          alertas,
                "noticias":         n_noticias,
                "timestamp":        ts,
                "version":          VERSION,
                # NUEVO: indicador de calidad de fuentes
                "calidad_nivel":    calidad["nivel"],
                "calidad_emoji":    calidad["emoji"],
                "calidad_css":      calidad["css"],
                "fuentes_activas":  calidad["fuentes_activas"],
                "uso_fallback":     calidad["uso_fallback"],
                "uso_web":          calidad["uso_web"],
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
# SCAN PRINCIPAL
# ---------------------------------------------------------------------------

def scan() -> None:
    DATA_LIVE.mkdir(parents=True, exist_ok=True)
    DATA_STATIC.mkdir(parents=True, exist_ok=True)

    fuentes    = cargar_fuentes()
    aprendidas = cargar_fuentes_aprendidas()

    if not fuentes:
        log.error("Sin fuentes configuradas. Abortando.")
        return

    ts = time.time()
    print(f"--- S.I.E.G. ATLAS SCANNER {VERSION} | "
          f"{datetime.now().strftime('%H:%M:%S')} ---")
    print(f"    Umbral minimo: {MIN_NOTICIAS} noticias | "
          f"Capas: primarias -> fallback -> Google News")
    print()

    resultados = {}

    for modulo, data_fuentes in fuentes.items():
        old_score = cargar_old_score(modulo)

        # Sistema de 3 capas
        noticias, calidad, aprendidas = fetch_con_autolearning(
            modulo, data_fuentes, aprendidas
        )

        score, alertas = calcular_score_modulo(noticias, modulo, old_score)

        guardar_resultado(modulo, score, alertas, len(noticias), ts, calidad)
        guardar_historico(modulo, score, ts)
        resultados[modulo] = score

        delta     = score - int(old_score)
        delta_str = f"+{delta}" if delta > 0 else str(delta)

        # Output con indicador de calidad
        icono_score = ("🚨" if score >= 70 else
                       "⚠️ " if score >= 45 else "✅")
        fallback_str = " [FB]" if calidad["uso_fallback"] else ""
        web_str      = " [WEB]" if calidad["uso_web"]      else ""

        print(f"[{icono_score}] {modulo:12} | "
              f"Score: {score:3}% ({delta_str:>4}) | "
              f"Noticias: {len(noticias):3} | "
              f"Calidad: {calidad['emoji']} {calidad['nivel']}"
              f"{fallback_str}{web_str}")

        for a in alertas:
            print(f"       ↳ {a[:100]}")

    # Guardar fuentes aprendidas para proximos ciclos
    guardar_fuentes_aprendidas(aprendidas)

    if resultados:
        avg     = sum(resultados.values()) // len(resultados)
        top_mod = max(resultados, key=resultados.get)
        print()
        print(f"--- Atlas completado: {len(resultados)} modulos | "
              f"Avg: {avg}% | Critico: {top_mod} ({resultados[top_mod]}%) ---")

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
