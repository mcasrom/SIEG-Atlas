# 🔧 SIEG — Referencia Técnica / Technical Reference

**Version:** Core V12.0 / Scanner V9.2 · Atlas V1.0 / Scanner V1.2  
**Fecha:** March 2026  
**Autor:** M. Castillo · mybloggingnotes@gmail.com

---

## Indice / Index

1. Arquitectura del sistema
2. SIEG-Core — Scanner V9.2
3. SIEG-Atlas — Scanner V1.2
4. Sistema de autolearning (3 capas)
5. Indicadores de calidad de fuentes
6. Algoritmo de scoring
7. Deteccion de disonancia narrativa
8. Gestion de datos historicos
9. Scripts de mantenimiento
10. Despliegue y cron
11. Dependencias
12. Changelog

---

## 1. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────┐
│                  Odroid-C2 / DietPi                 │
│                                                     │
│  ┌──────────────┐      ┌──────────────────────┐    │
│  │  SIEG-Core   │      │     SIEG-Atlas        │    │
│  │              │      │                      │    │
│  │ intel_scanner│      │ atlas_scanner.py     │    │
│  │ .py V9.2     │      │ V1.2                 │    │
│  │  cada 30min  │      │  cada 60min          │    │
│  └──────┬───────┘      └──────────┬───────────┘    │
│         │                         │                │
│         ▼                         ▼                │
│  data/geoint_*.json      data/live/atlas_*.json    │
│  data/history_log.csv    data/live/history_atlas   │
│         │                         │                │
│         └──────────┬──────────────┘                │
│                    │                               │
│              update_*.sh (git push)                │
└────────────────────┼────────────────────────────────┘
                     │
                     ▼
              GitHub (main branch)
                     │
                     ▼
           Streamlit Cloud (autodeploy)
           ┌─────────────────────────┐
           │ sieg-intelligence-radar │
           │ sieg-atlas-intelligence │
           └─────────────────────────┘
```

---

## 2. SIEG-Core — Scanner V9.2

### Ficheros clave
```
SIEG-Core/
├── intel_scanner.py      Motor principal
├── mapa_fuentes.txt      Fuentes RSS primarias (formato: REGION|URL|CF)
├── app_streamlit.py      Dashboard Streamlit V12.0
├── update_sieg.sh        Git sync V4 (con lock guard)
├── log_history.py        Escritura historico CSV
└── data/
    ├── geoint_REGION.json   Estado por actor (score + calidad)
    ├── history_log.csv      Historico activo (90 dias)
    ├── historico.json       Media global rolling 30 puntos
    ├── sieg_learned_sources.json  Fuentes aprendidas
    └── archive/             Historico comprimido (.csv.gz + .tar.gz)
```

### Actores monitorizados (14)
| Region | Clave | Suelo base |
|--------|-------|-----------|
| Iran / M. Oriente | Iran_M_Oriente | 68% |
| Rusia / Ucrania | Rusia_Ucrania | 62-68% |
| USA | USA | 10% |
| China | China | 10% |
| Corea del Norte | North_Korea | 35% |
| Sahel | Sahel | 32% |
| España | Espana | 10% |
| Latinoamerica | Latam | 10% |
| Mexico | Mexico | 10% |
| Argentina | Argentina | 10% |
| Brasil | Brasil | 10% |
| Asia-Pacifico | Asia_Pacifico | 10% |
| Europa Core | Europa_Core | 10% |
| Australia | Australia | 10% |

### Formato geoint_*.json
```json
{
  "score": 68,
  "disonancia": false,
  "conflict": false,
  "timestamp": 1772436602.77,
  "noticias_procesadas": 95,
  "version": "V9.2",
  "calidad_nivel": "AZUL",
  "calidad_emoji": "🔵",
  "calidad_css": "blue",
  "fuentes_activas": 4,
  "uso_fallback": true,
  "uso_web": false
}
```

---

## 3. SIEG-Atlas — Scanner V1.2

### Ejes monitorizados (6)
| Eje | Clave | Suelo base |
|-----|-------|-----------|
| Petroleo & Gas | Petroleo | 35% |
| Rutas Maritimas | Maritimo | 45% |
| Cables Submarinos | Cables | 15% |
| Mar de China | MarChina | 42% |
| Espacio | Espacio | 20% |
| Cibergeopolitica | Ciber | 33% |

---

## 4. Sistema de Autolearning — 3 Capas

Umbral minimo: **60 noticias** (Core) / **40 noticias** (Atlas)

```
CAPA 1 — Fuentes primarias (mapa_fuentes.txt / mapa_atlas.txt)
   Si noticias < umbral:
CAPA 2 — Banco de fallbacks por actor/eje (FALLBACK_SOURCES dict)
          + fuentes aprendidas en ciclos anteriores (learned_sources.json)
   Si noticias < umbral:
CAPA 3 — Google News RSS (query por keywords del actor)
          URL aprendida → persiste en learned_sources.json
```

### Fichero de fuentes aprendidas
```
data/sieg_learned_sources.json
data/live/atlas_learned_sources.json
```
Formato: `{"Iran_M_Oriente": ["https://news.google.com/rss/..."], ...}`

---

## 5. Indicadores de Calidad de Fuentes

| Nivel | Emoji | CSS class | Noticias | Condicion |
|-------|-------|-----------|----------|-----------|
| VERDE | 🟢 | quality-green | >= 80 (Core) / >= 60 (Atlas) | Optimo |
| AZUL | 🔵 | quality-blue | >= 60 / >= 40 | Aceptable |
| AMARILLO | 🟡 | quality-yellow | >= 40 / >= 25 | Reducido |
| NARANJA | 🟠 | quality-orange | >= 20 / >= 10 | Critico |
| ROJO | 🔴 | quality-red | < 20 / < 10 | Sin cobertura |

Sufijos en terminal: `[FB]` = uso fallback, `[WEB]` = uso Google News

---

## 6. Algoritmo de Scoring

### Pipeline completo
```
1. Fetch RSS (todas las fuentes del actor)
2. Por cada noticia:
   a. Tokenizar en oraciones (split por .!?;)
   b. Por cada oracion:
      - Verificar CRITICAL_ALERTS → score 92
      - Verificar DEESCALATION (>=2 hits) → score 15
      - Calcular hits_alto/medio/bajo del vocabulario cinetico
      - Bonus x1.35 si region presente (via REGION_ALIASES)
      - Penalizacion x0.80 si 1 termino desescalada
   c. Score noticia = percentil 75 de oraciones
   d. Ponderar por CF (Coeficiente de Fiabilidad)
3. Score bruto = media ponderada por CF
4. Aplicar suelo dinamico = max(base, media_reciente * 0.6)
5. Inercia de caida: si baja → 65% old + 35% nuevo
6. Clamp: max(10, min(100, score))
```

### Vocabulario cinetico (extracto)
```python
KINETIC_ALTO  = ["airstrike", "missile strike", "bombing", "drone strike", ...]
KINETIC_MEDIO = ["escalation", "retaliation", "military buildup", ...]
KINETIC_BAJO  = ["tension", "sanctions", "military exercise", ...]
CRITICAL_ALERTS = ["nuclear", "icbm", "chemical weapon", ...]
```

### Pesos de scoring
```
hits_alto  × 22 puntos
hits_medio × 12 puntos
hits_bajo  ×  5 puntos
+ bonus region x1.35
```

---

## 7. Deteccion de Disonancia Narrativa

Compara medias de scores entre fuentes establishment (CF >= 0.8) y alternativas (CF < 0.8).

```python
divergencia = |media_establishment - media_alternativas|
disonancia = True si divergencia > 35 puntos
```

Indicado en dashboard con icono ⚠ y tag DISON bajo el gauge del actor.

---

## 8. Gestion de Datos Historicos

### Retencion activa: 90 dias
- `history_log.csv`: timestamp,REGION,score (una fila por actor por ciclo)
- `history_atlas.csv`: timestamp,modulo,score

### Rotacion semanal (domingos 02:00)
Script: `/home/dietpi/scripts/sieg_rotate.sh`
- Separa registros > 90 dias → `data/archive/core_hasta_FECHA.csv.gz`
- Push a GitHub (rama main)
- Log: `/home/dietpi/logs/sieg_rotate.log`

### Backup mensual (dia 1, 03:00)
Script: `/home/dietpi/scripts/sieg_backup_monthly.sh`
- tar.gz: datos + JSONs + fuentes aprendidas + mapa_fuentes
- Destino: `/home/dietpi/backups/sieg/sieg_core_YYYY-MM.tar.gz`
- Push a GitHub + limpieza backups > 12 meses

### Proyeccion de crecimiento
| Dataset | Filas/dia | MB/año (raw) | MB/año (gzip) |
|---------|-----------|--------------|---------------|
| Core CSV | ~672 | ~32 MB | ~3 MB |
| Atlas CSV | ~144 | ~18 MB | ~2 MB |
| JSONs (14+6) | estatico | < 1 MB | < 200 KB |

eMMC disponible: 47 GB — sin riesgo en horizonte > 10 años.

---

## 9. Scripts de Mantenimiento

| Script | Ubicacion | Funcion | Frecuencia |
|--------|-----------|---------|------------|
| update_sieg.sh | SIEG-Core/ | Scanner + git push | cada 30min |
| update_atlas.sh | SIEG-Atlas/ | Scanner + git push | cada 60min |
| sieg_rotate.sh | scripts/ | Rotacion 90d + archive | semanal |
| sieg_backup_monthly.sh | scripts/ | Backup tar.gz | mensual |

---

## 10. Despliegue y Cron

### Crontab relevante SIEG
```bash
*/30 * * * *  /home/dietpi/SIEG-Core/update_sieg.sh >> /home/dietpi/sieg_cron.log 2>&1
15 * * * *    /bin/bash /home/dietpi/SIEG-Atlas/update_atlas.sh >> /home/dietpi/atlas_cron.log 2>&1
0 2 * * 0     /bin/bash /home/dietpi/scripts/sieg_rotate.sh
0 3 1 * *     /bin/bash /home/dietpi/scripts/sieg_backup_monthly.sh
```

### Streamlit Cloud
- Auto-deploy on push a main branch
- Core: sieg-intelligence-radar.streamlit.app
- Atlas: sieg-atlas-intelligence.streamlit.app
- TTL cache datos: 180s

---

## 11. Dependencias Python

```
streamlit
plotly
pandas
requests
# estandar: json, logging, re, time, xml.etree.ElementTree, pathlib
```

---

## 12. Changelog

| Version | Fecha | Cambios principales |
|---------|-------|---------------------|
| Core V12.0 | 2026-02 | Dashboard completo: gauges, mapa, heatmap, tabs |
| Scanner V9.1 | 2026-03 | REGION_ALIASES, vocabulario Houthi/Iran, suelos reajustados |
| Scanner V9.2 | 2026-03 | Autolearning 3 capas, indicadores calidad, fuentes aprendidas |
| Atlas V1.0 | 2026-03 | Dashboard 7 tabs, precio petroleo RT, mapa incidentes |
| Atlas Scanner V1.1 | 2026-03 | Vocabulario maritimo ampliado, suelos reajustados |
| Atlas Scanner V1.2 | 2026-03 | Autolearning 3 capas, indicadores calidad |

---

*M. Castillo · mybloggingnotes@gmail.com · © 2026*
