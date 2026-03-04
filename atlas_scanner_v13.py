#!/usr/bin/env python3
"""
SIEG-Atlas Scanner V1.3 - Autolearning de Fuentes + Flash News
Novedades vs V1.2:
  - Sistema de FLASH NEWS: extraccion automatica de eventos criticos
  - Triggers especificos por modulo de infraestructura (6 x 12 triggers)
  - Umbral flash: score modulo >= 55% + trigger keyword en titular
  - TTL: 48 horas - purga automatica de flashes expirados
  - Max: 15 flashes almacenados, 3 por modulo/ciclo
  - Output CLI: indicador flash N al lado de cada modulo con flashes
  - Flashes persistidos en data/live/atlas_flashes.json
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
FLASHES_FILE  = DATA_LIVE / "atlas_flashes.json"

RSS_ITEMS     = 20
TIMEOUT_HTTP  = 12
VERSION       = "V1.3"
MIN_NOTICIAS  = 40

FLASH_TTL_H   = 48
FLASH_SCORE   = 55
FLASH_MAX     = 15
FLASH_POR_MOD = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ATLAS")

# ---------------------------------------------------------------------------
# INDICADOR DE CALIDAD
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
        "nivel": nivel, "emoji": emoji, "css": css,
        "fuentes_activas": n_fuentes_activas,
        "uso_fallback": uso_fallback, "uso_web": uso_web,
    }

# ---------------------------------------------------------------------------
# FLASH NEWS - V1.3
# ---------------------------------------------------------------------------

FLASH_TRIGGERS_ATLAS = {
    "Petroleo": [
        "oil embargo", "opec cuts", "pipeline explosion", "pipeline attack",
        "saudi attack", "aramco attack", "oil price spike",
        "brent above 120", "energy crisis", "gas cutoff",
        "lng terminal attack", "refinery explosion",
    ],
    "Maritimo": [
        "hormuz closed", "hormuz blocked", "suez closed", "canal blocked",
        "red sea closed", "bab el-mandeb closed", "malacca strait closed",
        "warship sunk", "tanker seized", "tanker attacked",
        "naval blockade", "houthi sinks", "drone hits tanker",
        "port blockade", "shipping halted",
    ],
    "Cables": [
        "submarine cable cut", "undersea cable severed", "internet outage",
        "cable sabotage", "fiber cut", "internet blackout",
        "transatlantic cable", "pacific cable cut",
        "cable damaged", "connectivity disrupted",
        "cable ship attacked", "seabed infrastructure",
    ],
    "MarChina": [
        "taiwan invasion", "taiwan blockade", "pla naval", "pla crosses",
        "strait of taiwan blocked", "south china sea clash",
        "philippine vessel attacked", "us carrier attacked",
        "spratly incident", "paracel incident",
        "china fires missiles", "taiwan strait crisis",
    ],
    "Espacio": [
        "asat test", "satellite destroyed", "starlink down",
        "gps disrupted", "space weapon", "orbital attack",
        "satellite collision", "anti-satellite missile",
        "space debris crisis", "rocket intercept",
        "military satellite", "space warfare",
    ],
    "Ciber": [
        "critical infrastructure hack", "power grid attack",
        "water system hack", "hospital ransomware",
        "nuclear plant cyber", "bank system down",
        "government systems down", "apt attack",
        "supply chain attack", "zero-day exploit critical",
        "cyberattack confirms", "state-sponsored hack",
    ],
}

MODULO_ICONOS = {
    "Petroleo": "🛢",
    "Maritimo": "⚓",
    "Cables":   "🔌",
    "MarChina": "🌊",
    "Espacio":  "🛰",
    "Ciber":    "💻",
}

def cargar_flashes() -> list:
    if not FLASHES_FILE.exists():
        return []
    try:
        with open(FLASHES_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

def guardar_flashes(flashes: list) -> None:
    try:
        with open(FLASHES_FILE, "w") as f:
            json.dump(flashes, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.warning("No se pudo guardar atlas_flashes: %s", e)

def purgar_flashes_expirados(flashes: list, ahora: float) -> list:
    ttl_s = FLASH_TTL_H * 3600
    return [f for f in flashes if (ahora - f.get("ts", 0)) < ttl_s]

def extraer_flashes_modulo(noticias: list, modulo: str,
                           score: float, ahora: float) -> list:
    if score < FLASH_SCORE:
        return []
    triggers = FLASH_TRIGGERS_ATLAS.get(modulo, [])
    icono    = MODULO_ICONOS.get(modulo, "🔴")
    nuevos   = []
    for n in noticias:
        texto      = n.get("text", "").lower()
        titulo_raw = n.get("text", "").split(".")[0].strip()
        titulo     = titulo_raw[:130] if len(titulo_raw) > 130 else titulo_raw
        if not titulo:
            continue
        trigger_hit = next((t for t in triggers if t in texto), None)
        if trigger_hit:
            nuevos.append({
                "ts":      ahora,
                "modulo":  modulo,
                "icono":   icono,
                "titulo":  titulo,
                "trigger": trigger_hit,
                "score":   int(score),
                "cf":      round(float(n.get("cf", 0.7)), 2),
            })
        if len(nuevos) >= FLASH_POR_MOD:
            break
    return nuevos

# ---------------------------------------------------------------------------
# VOCABULARIO
# ---------------------------------------------------------------------------

KINETIC_ALTO = [
    "attack", "strike", "explosion", "bombed", "destroyed",
    "seized", "sunk", "shot down", "invaded", "breached",
    "compromised", "hacked", "disrupted", "sabotage",
]
KINETIC_MEDIO = [
    "incident", "clash", "escalation", "threat", "warning",
    "deployed", "intercepted", "blockade", "sanctions",
    "detained", "challenged", "confrontation",
]
KINETIC_BAJO = [
    "tension", "concern", "monitoring", "exercise",
    "surveillance", "patrol", "dispute", "allegation",
]
CRITICAL_ALERTS = [
    "war", "invasion", "nuclear", "chemical", "biological",
    "critical", "catastrophic", "emergency", "crisis", "collapse",
]
DEESCALATION = [
    "ceasefire", "agreement", "resolution", "diplomatic",
    "talks", "negotiations", "withdrawal", "cooperation",
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
# FALLBACK SOURCES (CAPA 2)
# ---------------------------------------------------------------------------

FALLBACK_SOURCES = {
    "Petroleo": [
        {"url": "https://oilprice.com/rss/main",                    "cf": 0.8},
        {"url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx", "cf": 0.7},
        {"url": "https://feeds.bbci.co.uk/news/business/rss.xml",   "cf": 0.9},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Energy-Environment.xml", "cf": 0.9},
        {"url": "https://foreignpolicy.com/feed/",                  "cf": 0.9},
    ],
    "Maritimo": [
        {"url": "https://www.hellenicshippingnews.com/feed/",        "cf": 0.8},
        {"url": "https://splash247.com/feed/",                      "cf": 0.7},
        {"url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "cf": 0.9},
        {"url": "https://www.aljazeera.com/xml/rss/all.xml",        "cf": 0.7},
        {"url": "https://www.defensenews.com/rss/",                 "cf": 0.8},
    ],
    "Cables": [
        {"url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "cf": 0.9},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "cf": 0.9},
        {"url": "https://foreignpolicy.com/feed/",                  "cf": 0.9},
        {"url": "https://thediplomat.com/feed/",                    "cf": 0.8},
    ],
    "MarChina": [
        {"url": "https://thediplomat.com/feed/",                    "cf": 0.8},
        {"url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "cf": 0.9},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml", "cf": 0.9},
        {"url": "https://asia.nikkei.com/rss/feed/nar",             "cf": 0.8},
        {"url": "https://foreignpolicy.com/feed/",                  "cf": 0.9},
    ],
    "Espacio": [
        {"url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "cf": 0.9},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "cf": 0.9},
        {"url": "https://www.defensenews.com/rss/",                 "cf": 0.8},
        {"url": "https://foreignpolicy.com/feed/",                  "cf": 0.9},
    ],
    "Ciber": [
        {"url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "cf": 0.9},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "cf": 0.9},
        {"url": "https://www.defensenews.com/rss/",                 "cf": 0.8},
        {"url": "https://foreignpolicy.com/feed/",                  "cf": 0.9},
    ],
}

# ---------------------------------------------------------------------------
# GOOGLE NEWS RSS (CAPA 3)
# ---------------------------------------------------------------------------

GOOGLE_NEWS_QUERIES = {
    "Petroleo":  "oil+gas+opec+energy+petroleum+pipeline",
    "Maritimo":  "maritime+shipping+houthi+red+sea+hormuz+tanker",
    "Cables":    "submarine+cable+internet+infrastructure+undersea",
    "MarChina":  "south+china+sea+taiwan+strait+naval+pla",
    "Espacio":   "satellite+space+launch+military+orbit+asat",
    "Ciber":     "cyberattack+hacking+ransomware+apt+critical+infrastructure",
}

def build_google_news_url(modulo: str) -> str:
    query = GOOGLE_NEWS_QUERIES.get(modulo, modulo.lower())
    return f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

# ---------------------------------------------------------------------------
# FUENTES APRENDIDAS
# ---------------------------------------------------------------------------

def cargar_fuentes_aprendidas() -> dict:
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
# FETCH RSS
# ---------------------------------------------------------------------------

def fetch_rss(fuentes_lista: list, modulo: str, label: str = "P") -> tuple:
    noticias        = []
    fuentes_activas = 0
    for fuente in fuentes_lista:
        url = fuente.get("url", "")
        cf  = fuente.get("cf", 0.7)
        try:
            resp = requests.get(url, timeout=TIMEOUT_HTTP,
                                headers={"User-Agent": "SIEG-Atlas/1.3"})
            resp.raise_for_status()
            root  = ET.fromstring(resp.content)
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            count = 0
            for item in items[:RSS_ITEMS]:
                title = (item.findtext("title") or
                         item.findtext("{http://www.w3.org/2005/Atom}title") or "")
                desc  = (item.findtext("description") or
                         item.findtext("{http://www.w3.org/2005/Atom}summary") or "")
                text  = f"{title}  {desc}".strip()
                if text:
                    noticias.append({"text": text, "cf": cf})
                    count += 1
            if count > 0:
                fuentes_activas += 1
        except Exception as e:
            log.debug("[%s][%s] %s: %s", label, modulo, url[:60], e)
    return noticias, fuentes_activas

def fetch_con_autolearning(modulo: str, fuentes_primarias: list,
                           aprendidas: dict) -> tuple:
    uso_fallback = False
    uso_web      = False
    noticias, n_activas = fetch_rss(fuentes_primarias, modulo, "P")
    if len(noticias) < MIN_NOTICIAS:
        uso_fallback   = True
        fb_sources     = FALLBACK_SOURCES.get(modulo, [])
        learned        = aprendidas.get(modulo, [])
        extra, n_extra = fetch_rss(fb_sources + learned, modulo, "FB")
        noticias  += extra
        n_activas += n_extra
    if len(noticias) < MIN_NOTICIAS:
        uso_web   = True
        gn_url    = build_google_news_url(modulo)
        gn_items, gn_act = fetch_rss([{"url": gn_url, "cf": 0.65}], modulo, "WEB")
        noticias  += gn_items
        n_activas += gn_act
        if gn_items:
            aprendidas.setdefault(modulo, [])
            if {"url": gn_url, "cf": 0.65} not in aprendidas[modulo]:
                aprendidas[modulo].append({"url": gn_url, "cf": 0.65})
    calidad = calcular_calidad(len(noticias), n_activas, uso_fallback, uso_web)
    return noticias, calidad, aprendidas

# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

def score_noticia_atlas(text: str, modulo: str, cf: float) -> float:
    tl      = text.lower()
    aliases = ALIASES.get(modulo, [])
    mod_hit = any(a in tl for a in aliases)
    hits_alto  = sum(1 for k in KINETIC_ALTO    if k in tl)
    hits_medio = sum(1 for k in KINETIC_MEDIO   if k in tl)
    hits_bajo  = sum(1 for k in KINETIC_BAJO    if k in tl)
    hits_crit  = sum(1 for k in CRITICAL_ALERTS if k in tl)
    hits_de    = sum(1 for k in DEESCALATION    if k in tl)
    raw = (hits_alto * 20 + hits_medio * 10 + hits_bajo * 4 +
           hits_crit * 30 - hits_de * 6)
    if mod_hit:
        raw = raw * 1.3
    return raw * cf

def calcular_score_modulo(noticias: list, modulo: str,
                          old_score: float) -> tuple:
    if not noticias:
        return int(old_score), []
    scores  = [score_noticia_atlas(n["text"], modulo, n["cf"]) for n in noticias]
    pesos   = [n["cf"] for n in noticias]
    total_w = sum(pesos)
    bruto   = sum(s for s in scores) / total_w if total_w > 0 else 10.0
    suelo   = SUELOS.get(modulo, 10)
    score_s = max(bruto, suelo)
    final   = (old_score * 0.65 + score_s * 0.35) if score_s < old_score else score_s

    # Alertas: noticias con score alto
    alertas = []
    for n, s in zip(noticias, scores):
        if s > 40:
            titulo = n["text"].split(".")[0].strip()[:100]
            alertas.append(f"[{s:.0f}] {titulo}")
    alertas = alertas[:5]

    return max(10, min(100, int(final))), alertas

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

def guardar_resultado(modulo: str, score: float, alertas: list,
                      n_noticias: int, ts: float, calidad: dict) -> None:
    path = DATA_LIVE / f"atlas_{modulo.lower()}.json"
    try:
        with open(path, "w") as f:
            json.dump({
                "modulo":          modulo,
                "score":           score,
                "alertas":         alertas,
                "noticias":        n_noticias,
                "timestamp":       ts,
                "version":         VERSION,
                "calidad_nivel":   calidad["nivel"],
                "calidad_emoji":   calidad["emoji"],
                "calidad_css":     calidad["css"],
                "fuentes_activas": calidad["fuentes_activas"],
                "uso_fallback":    calidad["uso_fallback"],
                "uso_web":         calidad["uso_web"],
            }, f, indent=2)
    except OSError as e:
        log.error("%s | No se pudo guardar resultado: %s", modulo, e)

def guardar_historico(modulo: str, score: float, ts: float) -> None:
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

    ts    = time.time()
    ahora = ts
    print(f"--- S.I.E.G. ATLAS SCANNER {VERSION} | "
          f"{datetime.now().strftime('%H:%M:%S')} ---")
    print(f"    Umbral minimo: {MIN_NOTICIAS} noticias | "
          f"Capas: primarias -> fallback -> Google News | Flash umbral: {FLASH_SCORE}%")
    print()

    resultados           = {}
    flashes_actuales     = purgar_flashes_expirados(cargar_flashes(), ahora)
    nuevos_flashes_total = 0

    for modulo, data_fuentes in fuentes.items():
        old_score = cargar_old_score(modulo)
        noticias, calidad, aprendidas = fetch_con_autolearning(
            modulo, data_fuentes, aprendidas
        )
        score, alertas = calcular_score_modulo(noticias, modulo, old_score)
        guardar_resultado(modulo, score, alertas, len(noticias), ts, calidad)
        guardar_historico(modulo, score, ts)
        resultados[modulo] = score

        # Flash extraction
        nuevos_flashes = extraer_flashes_modulo(noticias, modulo, score, ahora)
        flashes_actuales.extend(nuevos_flashes)
        nuevos_flashes_total += len(nuevos_flashes)

        delta     = score - int(old_score)
        delta_str = f"+{delta}" if delta > 0 else str(delta)

        icono_score  = ("🚨" if score >= 70 else "⚠️ " if score >= 45 else "✅")
        fallback_str = " [FB]"  if calidad["uso_fallback"] else ""
        web_str      = " [WEB]" if calidad["uso_web"]      else ""
        flash_str    = f" ⚡{len(nuevos_flashes)}" if nuevos_flashes else ""

        print(f"[{icono_score}] {modulo:12} | "
              f"Score: {score:3}% ({delta_str:>4}) | "
              f"Noticias: {len(noticias):3} | "
              f"Calidad: {calidad['emoji']} {calidad['nivel']}"
              f"{fallback_str}{web_str}{flash_str}")

        for a in alertas:
            print(f"       ↳ {a[:100]}")

    flashes_actuales = flashes_actuales[-FLASH_MAX:]
    guardar_flashes(flashes_actuales)
    guardar_fuentes_aprendidas(aprendidas)

    if resultados:
        avg     = sum(resultados.values()) // len(resultados)
        top_mod = max(resultados, key=resultados.get)
        print()
        print(f"--- Atlas completado: {len(resultados)} modulos | "
              f"Avg: {avg}% | Critico: {top_mod} ({resultados[top_mod]}%) | "
              f"Flashes: {nuevos_flashes_total} nuevos / {len(flashes_actuales)} activos ---")

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
