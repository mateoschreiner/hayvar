#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAYVAR — servidor local para la Liga Profesional Argentina.

Qué hace:
  1. Sirve index.html y los estáticos de esta carpeta.
  2. Proxea la API pública de 365scores (esquiva el bloqueo CORS que aparece
     al abrir el HTML con file://).
  3. Arma el modelo de datos: partidos, tablas de las dos zonas, tabla anual,
     promedios y goleadores.

Dos fuentes, cada una en lo que es mejor:

  · AFA / DataFactory — fixture de las 16 fechas (con árbitro y horario),
    posiciones de las dos zonas, acumulada, promedios y goleadores. Es el
    dato oficial y se lee de tablas HTML estáticas.
  · 365scores — el minuto a minuto, los escudos y el detalle del partido.

Por qué esta división: 365scores sólo publica el Grupo A del Clausura, e
ignora los parámetros de fecha (devuelve siempre la misma ventana de ~45
partidos, las fechas 4, 5 y 6). AFA, a cambio, no tiene datos en vivo.

Sobre las tablas oficiales se suman los goles de los partidos en curso, así
que las posiciones se mueven mientras se juega.

Uso:
    python3 server.py            # http://localhost:8010
    python3 server.py 9000       # otro puerto

Sólo biblioteca estándar.
"""

import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import threading
import unicodedata
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import almacen
import apifootball

HERE = os.path.dirname(os.path.abspath(__file__))

UPSTREAM = "https://webws.365scores.com/web"
COMPETITION = 72          # Liga Profesional Argentina
LANG = 29                 # español
TZ = "America/Argentina/Buenos_Aires"
STAGE = "clausura"        # etapa que nos interesa
SEASON_START = dt.date(2026, 7, 20)
FECHAS = 16               # el Clausura tiene 16 fechas
# 15 por fecha: 7 de Zona A, 7 de Zona B y 1 interzonal entre los dos equipos
# que de otro modo quedarían libres.
GAMES_POR_FECHA = 15

# ── Cupos a copas desde la Tabla Anual ────────────────────────────────────
# Argentina tiene 12 plazas internacionales. La Anual reparte 9: las tres
# primeras van a Libertadores y de la 4ª a la 9ª a Sudamericana. Los otros
# tres boletos a Libertadores son para los campeones del Apertura, del
# Clausura y de la Copa Argentina.
#
# Un campeón que además entra entre los nueve mejores libera su lugar y
# corre a todos los de abajo. Belgrano ya está adentro por el Apertura.
CUPOS_LIBERTADORES = 3
CUPOS_SUDAMERICANA = 6
YA_CLASIFICADOS = {
    "Belgrano": "Campeón del Apertura 2026 · Libertadores + Supercopa Internacional",
}
# Descienden dos: el último de la tabla de promedios y el último de la anual.
DESCIENDEN = 1            # por promedios
DESCIENDE_ANUAL = 1       # por la tabla anual
UA = "HAYVAR/1.0 (proyecto personal de resultados de futbol argentino)"

# Clave de API-Football. Se lee del entorno o de un archivo local; nunca se
# escribe dentro del código, así no termina publicada en el repositorio.
def _leer_clave():
    k = os.environ.get("APIFOOTBALL_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.join(HERE, "clave.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


APIFOOTBALL_KEY = _leer_clave()

# ─────────────────────────────────────────────────────────────────────────
# Zonas del Clausura 2026 (sorteo AFA, fijas todo el torneo)
# ─────────────────────────────────────────────────────────────────────────
ZONA_A = [
    "Boca Juniors", "Central Córdoba (SdE)", "Defensa y Justicia",
    "Deportivo Riestra", "Estudiantes (LP)", "Gimnasia y Esgrima (M)",
    "Independiente", "Instituto", "Lanús", "Newell's Old Boys", "Platense",
    "San Lorenzo", "Talleres (C)", "Unión", "Vélez Sarsfield",
]
ZONA_B = [
    "Aldosivi", "Argentinos Juniors", "Atlético Tucumán", "Banfield",
    "Barracas Central", "Belgrano", "Estudiantes (RC)",
    "Gimnasia y Esgrima (LP)", "Huracán", "Independiente Rivadavia", "Racing",
    "River Plate", "Rosario Central", "Sarmiento (J)", "Tigre",
]

# ─────────────────────────────────────────────────────────────────────────
# Base de promedios
#
#   promedio = (base_pts + pts_clausura) / (base_pj + pj_clausura)
#
# `base` es la foto al cierre del Apertura 2026 (2024 + 2025 + Apertura).
# Los puntos por año quedan a la vista para poder auditarlos.
# Fuente: AFA, vía la tabla de descenso 2026 de Wikipedia.
# ─────────────────────────────────────────────────────────────────────────
BASE_PROMEDIOS = [
    # nombre                    2024  2025  Apertura26  base_pts  base_pj
    ("Boca Juniors",              67,   62,   27,          156,     88),
    ("River Plate",               70,   53,   29,          152,     88),
    ("Racing",                    70,   53,   20,          143,     88),
    ("Vélez Sarsfield",           76,   40,   27,          143,     88),
    ("Argentinos Juniors",        56,   57,   29,          142,     88),
    ("Rosario Central",           47,   66,   27,          140,     88),
    ("Estudiantes (LP)",          63,   42,   28,          133,     88),
    ("Lanús",                     59,   50,   23,          132,     88),
    ("Independiente",             63,   47,   21,          131,     88),
    ("Talleres (C)",              72,   34,   25,          131,     88),
    ("Huracán",                   62,   47,   21,          130,     88),
    ("Independiente Rivadavia",   46,   43,   33,          122,     88),
    ("Barracas Central",          49,   49,   21,          119,     88),
    ("Unión",                     60,   39,   20,          119,     88),
    ("San Lorenzo",               45,   51,   22,          118,     88),
    ("Defensa y Justicia",        58,   38,   19,          115,     88),
    ("Deportivo Riestra",         48,   52,   10,          110,     88),
    ("Belgrano",                  49,   37,   23,          109,     88),
    ("Gimnasia y Esgrima (LP)",   48,   38,   23,          109,     88),
    ("Platense",                  57,   35,   16,          108,     88),
    ("Tigre",                     39,   49,   19,          107,     88),
    ("Instituto",                 53,   34,   18,          105,     88),
    ("Central Córdoba (SdE)",     42,   42,   16,          100,     88),
    ("Newell's Old Boys",         49,   33,   14,           96,     88),
    ("Atlético Tucumán",          50,   34,   11,           95,     88),
    ("Gimnasia y Esgrima (M)",  None, None,   16,           16,     15),
    ("Banfield",                  41,   35,   15,           91,     88),
    ("Sarmiento (J)",             35,   35,   19,           89,     88),
    ("Aldosivi",                None,   33,    7,           40,     47),
    ("Estudiantes (RC)",        None, None,    5,            5,     15),
]

# Cómo puede nombrar 365scores a cada club, además del nombre canónico.
ALIASES = {
    "boca juniors": ["boca jrs", "boca"],
    "river plate": ["river"],
    "racing": ["racing club"],
    "velez sarsfield": ["velez"],
    "argentinos juniors": ["argentinos jrs", "argentinos"],
    "rosario central": ["central"],
    "estudiantes (lp)": ["estudiantes de la plata", "estudiantes la plata", "estudiantes"],
    "talleres (c)": ["talleres de cordoba", "talleres cordoba", "talleres"],
    "independiente rivadavia": ["independiente riv", "ind rivadavia"],
    "barracas central": ["barracas"],
    "union": ["union de santa fe", "union santa fe"],
    "san lorenzo": ["san lorenzo de almagro"],
    "defensa y justicia": ["defensa"],
    "deportivo riestra": ["riestra"],
    "belgrano": ["belgrano de cordoba"],
    "gimnasia y esgrima (lp)": ["gimnasia y esgrima la plata", "gimnasia la plata",
                                "gimnasia (lp)", "gimnasia"],
    "instituto": ["instituto de cordoba"],
    "central cordoba (sde)": ["central cordoba santiago del estero", "central cordoba sde",
                              "central cordoba"],
    "newell's old boys": ["newells old boys", "newells", "newell s old boys"],
    "atletico tucuman": ["atl tucuman", "tucuman"],
    "gimnasia y esgrima (m)": ["gimnasia y esgrima mendoza", "gimnasia mendoza",
                               "gimnasia (m)", "gimnasia de mendoza"],
    "sarmiento (j)": ["sarmiento de junin", "sarmiento junin", "sarmiento"],
    "estudiantes (rc)": ["estudiantes de rio cuarto", "estudiantes rio cuarto",
                         "estudiantes rc", "estudiantes (rio cuarto)"],
}

# Cómo los nombra DataFactory (el dato oficial de AFA). Verificado uno por uno
# contra las tablas publicadas: son estos 30 exactos.
ALIASES["independiente rivadavia"] += ["independiente riv (m)", "independiente riv m",
                                      "indep mza", "indep mza ", "independiente riv"]
ALIASES["deportivo riestra"] += ["dep riestra"]
ALIASES["gimnasia y esgrima (m)"] += ["gimnasia (mendoza)"]
ALIASES["central cordoba (sde)"] += ["central cordoba (se)", "c cordoba (se)", "c cordoba"]
ALIASES["newell's old boys"] += ["newells"]
ALIASES["rosario central"] += ["r central"]
ALIASES["barracas central"] += ["barracas c"]
ALIASES["atletico tucuman"] += ["atl tucuman"]


def norm(s):
    """minúsculas, sin acentos ni puntuación — para comparar nombres."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    # DataFactory escribe Newell`s con backtick
    s = s.lower().replace("'", "").replace("´", "").replace("`", "")
    s = re.sub(r"[^a-z0-9() ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


NAME_INDEX = {}                     # nombre normalizado -> canónico
for _row in BASE_PROMEDIOS:
    _canon = _row[0]
    NAME_INDEX[norm(_canon)] = _canon
    for _a in ALIASES.get(norm(_canon), []):
        NAME_INDEX.setdefault(norm(_a), _canon)

# Sitio oficial de cada club: se abre al hacer clic en el escudo.
SITIOS = {
    "Aldosivi": "https://www.clubaldosivi.com.ar/",
    "Argentinos Juniors": "https://www.argentinos.com.ar/",
    "Atlético Tucumán": "https://www.clubatleticotucuman.com.ar/",
    "Banfield": "https://www.clubatleticobanfield.com/",
    "Barracas Central": "https://www.clubbarracascentral.com.ar/",
    "Belgrano": "https://belgrano.com.ar/",
    "Boca Juniors": "https://www.bocajuniors.com.ar/",
    "Central Córdoba (SdE)": "https://clubcentralcordoba.com/",
    "Defensa y Justicia": "https://www.clubdefensayjusticia.com.ar/",
    "Deportivo Riestra": "https://clubdeportivoriestra.com.ar/",
    "Estudiantes (LP)": "https://estudiantesdelaplata.com/",
    "Estudiantes (RC)": "https://www.estudiantesderiocuarto.com.ar/",
    "Gimnasia y Esgrima (LP)": "https://clubgimnasia.com.ar/",
    "Gimnasia y Esgrima (M)": "https://gimnasiayesgrima.com.ar/",
    "Huracán": "https://cahuracan.com/",
    "Independiente": "https://www.clubaindependiente.com/",
    "Independiente Rivadavia": "https://www.cirivadavia.com.ar/",
    "Instituto": "https://institutoacc.com.ar/",
    "Lanús": "https://www.clublanus.com/",
    "Newell's Old Boys": "https://www.newellsoldboys.com.ar/",
    "Platense": "https://www.clubatleticoplatense.com.ar/",
    "Racing": "https://www.racingclub.com.ar/",
    "River Plate": "https://www.cariverplate.com.ar/",
    "Rosario Central": "https://www.rosariocentral.com/",
    "San Lorenzo": "https://www.sanlorenzo.com.ar/",
    "Sarmiento (J)": "https://clubsarmiento.com.ar/",
    "Talleres (C)": "https://www.clubatleticotalleres.com/",
    "Tigre": "https://www.catigre.com.ar/",
    "Unión": "https://clubaunion.com.ar/",
    "Vélez Sarsfield": "https://www.velezsarsfield.com.ar/",
}

# Primera Nacional. Varios de estos clubes no tienen web propia o la tienen
# caída, así que se enlaza el Instagram oficial, que es donde realmente
# publican. La clave es el nombre que usa 365scores.
SITIOS_B = {
    "Acassuso": "https://www.instagram.com/clubacassusooficial/",
    "Agropecuario": "https://www.instagram.com/caagropecuario/",
    "All Boys": "https://www.instagram.com/clubatleticoallboys/",
    "Almagro": "https://www.instagram.com/clubalmagrooficial/",
    "Almirante Brown": "https://www.instagram.com/almirantebrownoficial/",
    "Atlanta": "https://www.instagram.com/clubatlanta/",
    "Atlético de Rafaela": "https://www.instagram.com/atleticorafaelaoficial/",
    "Central Norte": "https://www.instagram.com/centralnorteoficial/",
    "Chacarita Juniors": "https://www.instagram.com/chacaritajuniors/",
    "Chaco For Ever": "https://www.instagram.com/clubchacoforever/",
    "Ciudad de Bolívar": "https://www.instagram.com/clubciudaddebolivar/",
    "Colegiales": "https://www.instagram.com/clubcolegiales/",
    "Colón": "https://www.colonoficial.com.ar/",
    "Defensores de Belgrano": "https://www.instagram.com/cadefensoresdebelgrano/",
    "Deportivo Madryn": "https://www.instagram.com/cdmadryn/",
    "Deportivo Maipú": "https://www.instagram.com/cdmaipuoficial/",
    "Deportivo Morón": "https://www.instagram.com/deportivomoronoficial/",
    "Estudiantes": "https://www.instagram.com/caestudiantesbb/",
    "Ferro Carril Oeste": "https://www.ferrocarriloeste.org.ar/",
    "Gimnasia y Esgrima de Jujuy": "https://www.instagram.com/gimnasiajujuyoficial/",
    "Gimnasia y Tiro": "https://www.instagram.com/gimnasiaytirooficial/",
    "Godoy Cruz": "https://www.clubgodoycruz.com.ar/",
    "Güemes": "https://www.instagram.com/clubatleticoguemes/",
    "Los Andes": "https://www.instagram.com/clubatleticolosandes/",
    "Midland": "https://www.instagram.com/clubmidlandoficial/",
    "Mitre SdE": "https://www.instagram.com/clubatleticomitre/",
    "Nueva Chicago": "https://www.instagram.com/canuevachicago/",
    "Patronato": "https://www.instagram.com/clubpatronatooficial/",
    "Quilmes": "https://www.quilmesac.org.ar/",
    "Racing de Córdoba": "https://www.instagram.com/racingdecordoba/",
    "San Martín de San Juan": "https://www.instagram.com/casmoficial/",
    "San Martín de Tucumán": "https://www.instagram.com/csmoficial/",
    "San Miguel": "https://www.instagram.com/clubsanmigueloficial/",
    "San Telmo": "https://www.instagram.com/clubsantelmooficial/",
    "Temperley": "https://www.instagram.com/clubtemperley/",
    "Tristán Suárez": "https://www.instagram.com/clubtristansuarez/",
}


def sitio_de(nombre):
    """Link del club: primero Primera, después la B, y por nombre canónico."""
    if nombre in SITIOS_B:
        return SITIOS_B[nombre]
    canon = match_team(nombre)
    if canon and canon in SITIOS:
        return SITIOS[canon]
    k = emparejar(nombre, {norm(x): x for x in SITIOS_B})
    if k:
        return SITIOS_B[{norm(x): x for x in SITIOS_B}[k]]
    return None


ZONE_OF = {}
for _n in ZONA_A:
    ZONE_OF[_n] = "A"
for _n in ZONA_B:
    ZONE_OF[_n] = "B"


def match_team(name):
    """Nombre canónico de un club, o None si no lo reconocemos."""
    n = norm(name)
    if n in NAME_INDEX:
        return NAME_INDEX[n]
    bare = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    if bare in NAME_INDEX:
        return NAME_INDEX[bare]
    hits = {v for k, v in NAME_INDEX.items() if k.startswith(n) or n.startswith(k)}
    if len(hits) == 1:
        return hits.pop()
    return None


# ─────────────────────────────────────────────────────────────────────────
# HTTP con caché corta, para no castigar a 365scores
# ─────────────────────────────────────────────────────────────────────────
_cache, _lock = {}, threading.Lock()


def fetch(path, params, ttl=15):
    """
    Pedido a 365scores, con dos niveles de caché.

    En memoria para el segundo a segundo, y en la base para todo lo demás.
    La base es la que hace la diferencia: sobrevive a los reinicios y, si la
    fuente se cae, devuelve lo último bueno en vez de dejar la página vacía.
    """
    qs = {"appTypeId": 5, "langId": LANG, "timezoneName": TZ, "userCountryId": 382}
    qs.update(params)
    url = "%s/%s/?%s" % (UPSTREAM, path.strip("/"), urlencode(qs))

    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]

    def ir_a_la_fuente():
        # Sin Referer ni Origin falsos: los pedidos salen identificados como
        # lo que son. Hacerse pasar por su propio sitio no corresponde.
        req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    data, info = almacen.con_respaldo("sc:" + url, ir_a_la_fuente,
                                      max_edad=ttl, tag=path)
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["365scores"] = info

    with _lock:
        _cache[url] = (time.time(), data)
    return data


# Lo último que salió mal por fuente, para poder avisarlo en pantalla.
ULTIMO_PROBLEMA = {}


# ─────────────────────────────────────────────────────────────────────────
# DataFactory — el dato oficial de AFA
#
# La web de la Liga Profesional embebe tablas de DataFactory. Son HTML
# estático (no hace falta ejecutar JavaScript) y traen justo lo que la API
# de 365scores no da: las dos zonas por separado, la acumulada y —sobre
# todo— la tabla de promedios ya calculada por AFA.
# ─────────────────────────────────────────────────────────────────────────
DF_BASE = ("https://datafactory-903663207315-sa-east-1-an.s3.sa-east-1."
           "amazonaws.com/html/v3/htmlCenter/data/deportes/futbol/primeraa/pages/es/")
DF_PAGES = {"zonas": "Fase_1", "anual": "Acumulada",
            "promedios": "descenso", "goleadores": "goleadores",
            "fixture": "fixture"}

# Otras ligas del mismo proveedor. Cambian el host y el nombre de las páginas,
# pero el HTML es idéntico, así que sirve el mismo parser.
NACIONAL_BASE = ("https://info.afa.org.ar/deposito/html/v3/htmlCenter/data/"
                 "deportes/futbol/nacionalb/pages/es/")
LIGAS = {
    "lpf": {
        "nombre": "Liga Profesional", "torneo": "Clausura 2026",
        "base": DF_BASE, "pages": DF_PAGES, "propia": True, "sc": 72,
    },
    "nacional": {
        # Las tablas salen de 365scores (competencia 419) porque ahí vienen
        # las dos zonas juntas, con escudos y en vivo. AFA sirve los
        # goleadores, que 365scores no discrimina por tipo de gol.
        "nombre": "Primera Nacional", "torneo": "Temporada 2026",
        "base": NACIONAL_BASE,
        "pages": {"zonas": "posiciones", "anual": "descenso",
                  "goleadores": "goleadores", "fixture": "fixture"},
        "propia": False, "sc": 419, "pais": "Argentina",
        # Reglamento 2026: 36 equipos en dos zonas de 18, 34 fechas.
        # Ascienden dos. El primer ascenso se define en una final entre los
        # ganadores de cada zona; el perdedor cae al Reducido, que juegan del
        # 2° al 8° de cada zona, por el segundo ascenso.
        # Descienden cuatro: los dos últimos de cada zona.
        "zonas_de": {
            "final": (1, 1),        # 1° de cada zona
            "reducido": (2, 8),     # del 2° al 8°
            "desciende": (-2, -1),  # los dos últimos
        },
    },
    "pbm": {
        "nombre": "Primera B Metro", "torneo": "Temporada 2026",
        "base": ("https://info.afa.org.ar/deposito/html/v3/htmlCenter/data/"
                 "deportes/futbol/primerab/pages/es/"),
        "pages": {"zonas": "posiciones", "goleadores": "goleadores",
                  "fixture": "fixture"},
        "propia": False, "sc": 5077, "pais": "Argentina",
        "anual": False,   # una sola tabla: sin acumulada
        "zonas_de": {"final": (1, 1), "reducido": (2, 8), "desciende": (-1, -1)},
    },
    "fa": {
        # El canal de DataFactory del Federal A es "argentinoa" (lo dice el
        # iframe de afa.com.ar/es/pages/federal-a), pero NO sirve: esa página
        # quedó publicando la Primera Fase —su fecha 1 es del 20-03-2026— y no
        # la Reválida, que es lo que se está jugando. Traerla mezclaba fechas
        # viejas con las nuevas y desordenaba todo el fixture.
        #
        # Así que el Federal A sigue por 365scores. Devuelve pocas fechas de
        # una, pero el servidor las va acumulando en la base y el calendario
        # crece solo, sin fases viejas de por medio.
        "nombre": "Federal A", "torneo": "Temporada 2026",
        "base": None, "pages": {}, "propia": False, "sc": 5078,
        "pais": "Argentina", "anual": False,
    },
    "fem": {
        # Igual que arriba: el canal es "primeraafemenino", según la página
        # de estadísticas del fútbol femenino de AFA.
        "nombre": "Liga Femenina", "torneo": "Temporada 2026",
        "base": ("https://info.afa.org.ar/deposito/html/v3/htmlCenter/data/"
                 "deportes/futbol/primeraafemenino/pages/es/"),
        "pages": {"zonas": "posiciones", "goleadores": "goleadores",
                  "fixture": "fixture"},
        "propia": False, "sc": 6224, "pais": "Argentina",
        "anual": False,
    },
    "laliga": {
        # España. El calendario completo sale de laliga.com (las 38 jornadas);
        # los marcadores y el vivo, de 365scores.
        "nombre": "LaLiga", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 11, "pais": "España",
        "anual": False,   # LaLiga tiene una sola tabla
        "fixture_propio": "laliga",
        # 20 equipos: los 4 primeros a Champions, 5° a Europa League,
        # 6° a Conference y los 3 últimos descienden a Segunda.
        "zonas_de": {
            "champions": (1, 4),
            "europa": (5, 5),
            "conference": (6, 6),
            "desciende": (-3, -1),
        },
    },
    # ── Copas ────────────────────────────────────────────────────────────
    # Los números salen de /api/competencias, no de la memoria: 365scores
    # tiene 799 torneos cargados y varios se llaman parecido (está la
    # Libertadores, la Sub20 y la Femenina, y una Recopa Sudamericana que no
    # es la Sudamericana).
    "lib": {
        "nombre": "Copa Libertadores", "torneo": "Edición 2026",
        "base": None, "pages": {}, "propia": False, "sc": 102,
        "pais": "Sudamérica", "anual": False, "copa": True,
        # fase de grupos: pasan los dos primeros de cada zona
        "zonas_de": {"avanza": (1, 2)},
        "etapas_extra": ["Cuartos de final", "Semifinal", "Final"],
    },
    "sud": {
        "nombre": "Copa Sudamericana", "torneo": "Edición 2026",
        "base": None, "pages": {}, "propia": False, "sc": 389,
        "pais": "Sudamérica", "anual": False, "copa": True,
        # acá pasa sólo el primero; el segundo juega el repechaje contra los
        # terceros de la Libertadores
        "zonas_de": {"avanza": (1, 1), "repechaje": (2, 2)},
        # La ronda extra que tiene la Sudamericana —los que salen segundos
        # contra los terceros de la Libertadores— no se agrega a mano: viene
        # en el fixture con el nombre que le pone CONMEBOL y se traduce a
        # "Pre octavos" al mostrarla.
        "etapas_extra": ["Cuartos de final", "Semifinal", "Final"],
    },
    "ca": {
        # Eliminación directa de punta a punta, sin tabla de posiciones.
        "nombre": "Copa Argentina", "torneo": "Edición 2026",
        "base": None, "pages": {}, "propia": False, "sc": 640,
        "pais": "Argentina", "anual": False, "copa": True,
        # sin zonas_de: acá no hay tabla que marcar, se elimina y listo
        "etapas_extra": ["Cuartos de final", "Semifinal", "Final"],
    },
}

# Colores de cada club para el modo club: (fondo de la barra, color de acento).
# El acento es el que la camiseta usa como segundo color, así "VAR" y el logo
# quedan legibles sobre el fondo. Si alguno no convence, se cambia acá.
COLORES = {
    "Aldosivi":               ('#0b6b3a', '#f7d417'),   # verde y amarillo
    "Argentinos Juniors":     ('#f2f2f2', '#c8102e'),   # blanco y rojo
    "Atlético Tucumán":       ('#5aa9e6', '#f2f2f2'),   # celeste y blanco
    "Banfield":               ('#0d5c34', '#f2f2f2'),   # verde y blanco
    "Barracas Central":       ('#c8102e', '#f2f2f2'),   # rojo y blanco
    "Belgrano":               ('#4aa3dc', '#4aa3dc'),   # celeste
    "Boca Juniors":           ('#0a2472', '#f2c94c'),   # azul y oro
    "Central Córdoba (SdE)":  ('#111111', '#f2f2f2'),   # negro y blanco
    "Defensa y Justicia":     ('#0f8a45', '#f7d417'),   # verde y amarillo
    "Deportivo Riestra":      ('#f2f2f2', '#111111'),   # blanco y negro
    "Estudiantes (LP)":       ('#c8102e', '#f2f2f2'),   # rojo y blanco
    "Estudiantes (RC)":       ('#1668b3', '#1668b3'),   # celeste mas oscuro
    "Gimnasia y Esgrima (LP)":('#f2f2f2', '#12539b'),   # blanco y azul
    "Gimnasia y Esgrima (M)": ('#f2f2f2', '#111111'),   # blanco y negro
    "Huracán":                ('#f2f2f2', '#d81e29'),   # blanco y rojo
    "Independiente":          ('#c8102e', '#c8102e'),   # rojo
    "Independiente Rivadavia":('#3b2f8f', '#3b2f8f'),   # azul casi violeta
    "Instituto":              ('#c8102e', '#f2f2f2'),   # rojo y blanco
    "Lanús":                  ('#6d1b34', '#6d1b34'),   # granate
    "Newell's Old Boys":      ('#c8102e', '#111111'),   # rojo y negro
    "Platense":               ('#f2f2f2', '#6b4423'),   # blanco y marron
    "Racing":                 ('#7ec0ee', '#f2f2f2'),   # celeste y blanco
    "River Plate":            ('#f2f2f2', '#e2001a'),   # blanco y rojo
    "Rosario Central":        ('#1a4fa0', '#f2c94c'),   # azul y amarillo
    "San Lorenzo":            ('#0a2a6b', '#8f1020'),   # azul y rojo oscuro
    "Sarmiento (J)":          ('#0d7a3f', '#0d7a3f'),   # verde
    "Talleres (C)":           ('#12376b', '#f2f2f2'),   # azul y blanco
    "Tigre":                  ('#1a4fa0', '#c8102e'),   # azul y rojo
    "Unión":                  ('#c8102e', '#f2f2f2'),   # rojo y blanco
    "Vélez Sarsfield":        ('#f2f2f2', '#12376b'),   # blanco y azul
}


def _demojibake(s):
    """DataFactory a veces manda UTF-8 leído como latin-1 ('Ãrbitro')."""
    if "Ã" in s or "Â" in s:
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


class _Fixture(HTMLParser):
    """
    Lee el fixture oficial. Cada partido es un <div class="match-inner"> con:
      .equipo (x2) · .badge (x2, los goles) · .arbitro · .mc-date · .mc-time
      · .estado
    y cuelga de un contenedor con data-fecha="nivel1_fechaN".
    """

    WANT = ("equipo", "badge", "arbitro", "mc-date", "mc-time", "hora", "estado")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.matches, self._fecha = [], None
        self._depth_fecha, self._m, self._depth_m = None, None, None
        self._cls, self._buf, self._d = None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        self._d += 1
        if "data-fecha" in a:
            mm = re.search(r"fecha(\d+)", a["data-fecha"])
            self._fecha = int(mm.group(1)) if mm else None
            self._depth_fecha = self._d
        if "match-inner" in cls and self._m is None:
            self._m, self._depth_m = {"fecha": self._fecha, "campos": []}, self._d
        if self._m is not None:
            for w in self.WANT:
                if re.search(r"(^|\s)%s(\s|$)" % re.escape(w), cls):
                    self._cls, self._buf = w, []
                    break

    def handle_endtag(self, tag):
        if self._cls is not None and self._buf is not None:
            txt = _demojibake(re.sub(r"\s+", " ", "".join(self._buf)).strip())
            if txt:
                self._m["campos"].append((self._cls, txt))
            self._cls, self._buf = None, None
        if self._m is not None and self._d == self._depth_m:
            self.matches.append(self._m)
            self._m, self._depth_m = None, None
        if self._depth_fecha is not None and self._d == self._depth_fecha:
            self._fecha, self._depth_fecha = None, None
        self._d -= 1

    def handle_data(self, d):
        if self._buf is not None:
            self._buf.append(d)


_MESES = {}


def _parse_dt(fecha, hora):
    """'23-07-2026' + '19:30hs' -> ISO con huso de Buenos Aires."""
    try:
        d, m, y = (int(x) for x in fecha.split("-"))
    except (ValueError, AttributeError):
        return None
    hh, mi = 0, 0
    mm = re.search(r"(\d{1,2}):(\d{2})", hora or "")
    if mm:
        hh, mi = int(mm.group(1)), int(mm.group(2))
    return "%04d-%02d-%02dT%02d:%02d:00-03:00" % (y, m, d, hh, mi)


_FINALIZADO = ("finalizado", "final", "entretiempo", "suspendido")


def df_fixture(ttl=120):
    """
    El fixture completo del Clausura: las 16 fechas, con árbitro y estadio.

    Hace falta porque 365scores ignora los parámetros de fecha y siempre
    devuelve la misma ventana de ~45 partidos (las fechas 4, 5 y 6). Por eso
    faltaban las primeras.
    """
    url = DF_BASE + "fixture.html"
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]

    def ir_a_la_fuente():
        req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
        p = _Fixture()
        p.feed(html)
        return p.matches

    matches, info = almacen.con_respaldo("dffx:" + url, ir_a_la_fuente,
                                         max_edad=ttl, tag="afa/fixture/lpf")
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["afa"] = info

    p = type("obj", (), {"matches": matches})()
    out = []
    for m in p.matches:
        campos = m["campos"]
        eq = [v for k, v in campos if k == "equipo"]
        goles = [v for k, v in campos if k == "badge"]
        arb = next((v for k, v in campos if k == "arbitro"), "")
        fch = next((v for k, v in campos if k == "mc-date"), "")
        hor = next((v for k, v in campos if k in ("mc-time", "hora")), "")
        est = next((v for k, v in campos if k == "estado"), "")
        if len(eq) < 2:
            continue
        hc, ac = match_team(eq[0]), match_team(eq[1])
        if not hc or not ac:
            continue          # placeholders tipo "A Confirmar" de los playoffs
        gh = _int(goles[0], None) if len(goles) > 0 else None
        ga = _int(goles[1], None) if len(goles) > 1 else None
        jugado = norm(est) in _FINALIZADO or (gh is not None and ga is not None)
        za, zb = ZONE_OF.get(hc), ZONE_OF.get(ac)
        out.append({
            "id": "df-%s-%s-%s" % (m["fecha"], norm(hc)[:6], norm(ac)[:6]),
            "round": m["fecha"],
            "zone": za if za == zb else None,      # None = interzonal
            "interzonal": bool(za and zb and za != zb),
            "stage": "Clausura",
            "start": _parse_dt(fch, hor),
            "status": "FIN" if jugado else "PROG",
            "statusText": est,
            "minute": None,
            "referee": re.sub(r"^\s*Árbitro:\s*", "", arb).strip(),
            "home": {"id": None, "canon": hc, "name": eq[0], "short": "",
                     "logo": None, "score": gh},
            "away": {"id": None, "canon": ac, "name": eq[1], "short": "",
                     "logo": None, "score": ga},
            "gh": gh, "ga": ga, "venue": "",
        })
    out.sort(key=lambda x: (x["round"] or 0, x["interzonal"], x["start"] or ""))
    with _lock:
        _cache[url] = (time.time(), out)
    return out


class _Tables(HTMLParser):
    """
    Extrae <table> como listas de filas de texto. Sólo stdlib.

    Descarta las filas hechas sólo de <th>: AFA repite el encabezado en el
    medio de la tabla (al empezar la Zona B, por ejemplo) y si no se filtra
    aparece un equipo fantasma llamado "Nº".
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._t, self._row, self._cell, self._in, self._td = None, None, None, 0, False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._row, self._td = [], False
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._in = [], 1
            if tag == "td":
                self._td = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            txt = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(txt)
            self._cell, self._in = None, 0
        elif tag == "tr" and self._row is not None:
            if any(self._row) and self._td:
                self._t.append(self._row)
            self._row = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, d):
        if self._in and self._cell is not None:
            self._cell.append(d)


def df_tables(page, ttl=45, liga="lpf"):
    """Tablas de una página de DataFactory, con respaldo en la base."""
    cfg = LIGAS.get(liga, LIGAS["lpf"])
    url = cfg["base"] + cfg["pages"].get(page, page) + ".html"
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]

    def ir_a_la_fuente():
        req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
        p = _Tables()
        p.feed(html)
        return p.tables

    tablas, info = almacen.con_respaldo("df:" + url, ir_a_la_fuente,
                                        max_edad=ttl, tag="afa/" + page)
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["afa"] = info
    with _lock:
        _cache[url] = (time.time(), tablas)
    return tablas


def _cells(row):
    """Celdas no vacías de una fila."""
    return [c for c in row if c]


def _int(v, default=0):
    """'12' -> 12 · '-3' -> -3 · '' o basura -> default."""
    try:
        return int(str(v).replace("+", "").strip())
    except (TypeError, ValueError):
        return default


def df_rows(table):
    """
    Normaliza cada fila a (canónico, nombre_original, celdas_posteriores).

    El formato es: Nº | (escudo) | Equipo | ...números...

    Importante: NO se descartan las celdas vacías. Los equipos recién
    ascendidos no tienen puntos de 2024 ni 2025 y esas celdas vienen en
    blanco; si se filtran, se corren todas las columnas siguientes y el
    promedio sale mal.
    """
    out = []
    for row in table:
        if len(row) < 3:
            continue
        idx = next((i for i, x in enumerate(row)
                    if x and not re.fullmatch(r"-?[\d.,]+", x)), None)
        if idx is None:
            continue
        canon = match_team(row[idx])
        if canon:
            out.append((canon, row[idx], row[idx + 1:]))
    return out


def logo(c):
    """
    Escudo del club, servido desde nuestro propio servidor.

    Antes el navegador iba directo al CDN de 365scores. Eso consume ancho de
    banda ajeno y, publicado, se bloquea con sólo mirar el Referer. Ahora la
    imagen pasa por /img, que la busca una vez y la guarda en memoria.
    """
    cid, ver = c.get("id"), c.get("imageVersion", 1)
    if not cid:
        return None
    return "/img/competidor/%s/%s" % (ver, cid)


def emblema(comp, ver=1):
    return "/img/competencia/%s/%s" % (ver, comp)


_CDN = "https://imagecache.365scores.com/image/upload/f_png,w_128,h_128,c_limit,q_auto:best,dpr_2"
_IMG_CACHE = {}
_IMG_MAX = 400          # los escudos pesan pocos KB: entran todos de sobra


def traer_imagen(tipo, ver, ident):
    """Descarga y cachea un escudo. Devuelve (bytes, content-type)."""
    clave = (tipo, ver, ident)
    with _lock:
        if clave in _IMG_CACHE:
            return _IMG_CACHE[clave]

    carpeta = {"competidor": "Competitors", "competencia": "Competitions"}.get(tipo)
    if not carpeta:
        raise ValueError("tipo de imagen desconocido")
    url = "%s/v%s/%s/%s" % (_CDN, ver, carpeta, ident)
    req = Request(url, headers={"User-Agent": UA, "Accept": "image/png,image/*"})
    with urlopen(req, timeout=15) as r:
        datos = r.read()
        ctype = r.headers.get("Content-Type", "image/png")

    with _lock:
        if len(_IMG_CACHE) >= _IMG_MAX:
            _IMG_CACHE.clear()
        _IMG_CACHE[clave] = (datos, ctype)
    return datos, ctype


def status_of(g):
    """statusGroup: 1/2 programado · 3 en juego · 4 terminado."""
    sg, txt = g.get("statusGroup"), norm(g.get("statusText"))
    if any(w in txt for w in ("suspend", "aplaz", "cancel", "posterg")):
        return "SUSP"
    if sg == 3:
        return "LIVE"
    if sg == 4:
        return "FIN"
    return "PROG"


def side(c):
    sc = c.get("score")
    return {
        "id": c.get("id"),
        "name": c.get("name") or "",
        "canon": match_team(c.get("name")),
        "short": c.get("symbolicName") or "",
        "logo": logo(c),
        "score": None if sc in (None, -1) else int(sc),
        # En las copas, 365scores dice directamente quién clasificó. Es más
        # confiable que sumar los goles de la serie: contempla los penales,
        # el gol de visitante y todo lo que el reglamento diga ese año.
        "pasa": bool(c.get("isQualified") or c.get("toQualify")),
    }


def map_game(g):
    st = status_of(g)
    h, a = side(g.get("homeCompetitor") or {}), side(g.get("awayCompetitor") or {})
    gt = g.get("gameTime")
    live_min = int(gt) if st == "LIVE" and isinstance(gt, (int, float)) and gt > 0 else None
    za, zb = ZONE_OF.get(h["canon"]), ZONE_OF.get(a["canon"])
    return {
        "id": g.get("id"),
        "zone": za if za == zb else None,
        "interzonal": bool(za and zb and za != zb),
        "referee": "",
        "round": g.get("roundNum"),
        "stage": g.get("stageName") or "",
        # En las copas, groupNum no es un grupo: es el lugar que ocupa la
        # llave en el cuadro. Los octavos van del 1 al 8 y de ahí sale quién
        # se cruza con quién, sin tener que adivinarlo. stageNum ordena las
        # rondas mejor que la fecha, porque una ronda puede empezar antes de
        # que termine la anterior.
        "slot": g.get("groupNum"),
        "stageNum": g.get("stageNum"),
        "start": g.get("startTime"),
        "status": st,
        "statusText": g.get("statusText") or "",
        "minute": live_min,
        "home": h, "away": a,
        "gh": h["score"], "ga": a["score"],
        "venue": (g.get("venue") or {}).get("name") or "",
    }


def live_games(ttl=15):
    """La ventana que devuelve 365scores: lo que se juega ahora y alrededor."""
    raw, seen, out = [], set(), []
    for ep in ("games/current", "games/results", "games/fixtures"):
        try:
            raw.extend(fetch(ep, {"competitions": COMPETITION}, ttl=ttl).get("games", []))
        except Exception:
            pass
    for g in raw:
        if g.get("id") in seen:
            continue
        seen.add(g.get("id"))
        m = map_game(g)
        if STAGE in norm(m["stage"]):
            out.append(m)
    return out


def all_games(ttl=25):
    """
    Todo el Clausura: las 16 fechas.

    La base es el fixture oficial de AFA. 365scores no sirve para esto: ignora
    los parámetros startDate/endDate y siempre devuelve la misma ventana de
    ~45 partidos (las fechas 4, 5 y 6) — de ahí que faltaran las primeras.

    Sobre esa base se pega lo que aporta 365scores y AFA no tiene: el minuto
    de los partidos en curso, los escudos y el id para abrir el detalle.
    """
    try:
        base = [dict(m) for m in df_fixture()]
    except Exception:
        base = []

    if not base:                      # plan B: sólo lo que haya en 365scores
        return sorted(live_games(ttl), key=lambda x: (x["start"] or "", str(x["id"])))

    idx = {}
    for m in base:
        idx[(m["round"], m["home"]["canon"], m["away"]["canon"])] = m
        idx[(None, m["home"]["canon"], m["away"]["canon"])] = m

    # Primero todo lo que 365scores tenga guardado —incluidos los partidos
    # viejos que trajo el rescate— y encima lo que está pasando ahora. Sin
    # esto, las fechas anteriores se quedaban sin el id de 365scores y por
    # eso no mostraban ni goleadores ni canal, ni abrían el detalle.
    try:
        historico = _sc_fixture(COMPETITION)
    except Exception:
        historico = []

    for lv in list(historico) + live_games(ttl):
        hc = match_team(lv["home"].get("name")) or lv["home"].get("canon")
        ac = match_team(lv["away"].get("name")) or lv["away"].get("canon")
        m = idx.get((lv["round"], hc, ac)) or idx.get((None, hc, ac))
        if not m:
            continue
        for side_key in ("home", "away"):
            m[side_key]["id"] = lv[side_key]["id"]
            m[side_key]["logo"] = lv[side_key]["logo"]
            m[side_key]["short"] = lv[side_key]["short"]
        m["liveId"] = lv["id"]        # id de 365scores, para el detalle
        m["venue"] = lv["venue"] or m["venue"]
        if lv["status"] == "LIVE" or (lv["status"] == "FIN" and m["gh"] is None):
            m["status"] = lv["status"]
            m["statusText"] = lv["statusText"] or m["statusText"]
            m["minute"] = lv["minute"]
            if lv["gh"] is not None:
                m["gh"], m["ga"] = lv["gh"], lv["ga"]
                m["home"]["score"], m["away"]["score"] = lv["gh"], lv["ga"]

    base.sort(key=lambda x: (x["round"] or 0, x["interzonal"], x["start"] or ""))
    return base


# ─────────────────────────────────────────────────────────────────────────
# Tablas calculadas desde los partidos
# ─────────────────────────────────────────────────────────────────────────
def build_tables(games):
    """Acumula puntos por equipo. Cuenta partidos terminados y en juego."""
    acc = {}

    def slot(canon, meta):
        if canon not in acc:
            acc[canon] = {"canon": canon, "zone": ZONE_OF.get(canon),
                          "team": {"name": canon, "short": meta.get("short") or "",
                                   "logo": meta.get("logo"), "id": meta.get("id")},
                          "pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0,
                          "pts": 0, "form": [], "_live": 0}
        elif meta.get("logo") and not acc[canon]["team"]["logo"]:
            acc[canon]["team"]["logo"] = meta["logo"]
        return acc[canon]

    for m in games:
        hc, ac = m["home"]["canon"], m["away"]["canon"]
        if not hc or not ac:
            continue
        H, A = slot(hc, m["home"]), slot(ac, m["away"])
        if m["status"] not in ("FIN", "LIVE") or m["gh"] is None or m["ga"] is None:
            continue
        gh, ga = m["gh"], m["ga"]
        for me, rival, mine, theirs in ((H, A, gh, ga), (A, H, ga, gh)):
            me["pj"] += 1
            me["gf"] += mine
            me["gc"] += theirs
            if mine > theirs:
                me["g"] += 1
                me["pts"] += 3
                r = "G"
            elif mine == theirs:
                me["e"] += 1
                me["pts"] += 1
                r = "E"
            else:
                me["p"] += 1
                r = "P"
            if m["status"] == "LIVE":
                me["_live"] += 1
            else:
                me["form"].append((m["start"] or "", r))

    for r in acc.values():
        r["dif"] = r["gf"] - r["gc"]
        r["form"] = [x[1] for x in sorted(r["form"])][-5:]
        r["live"] = r.pop("_live") > 0

    # equipos que todavía no jugaron aparecen igual, en cero
    for canon in list(ZONE_OF):
        if canon not in acc:
            acc[canon] = {"canon": canon, "zone": ZONE_OF[canon],
                          "team": {"name": canon, "short": "", "logo": None, "id": None},
                          "pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0,
                          "pts": 0, "dif": 0, "form": [], "live": False}
    return acc


def sort_rows(rows):
    rows = sorted(rows, key=lambda r: (-r["pts"], -r["dif"], -r["gf"], norm(r["canon"])))
    for i, r in enumerate(rows, 1):
        r["pos"] = i
    return rows


def zones_from(games):
    acc = build_tables(games)
    za = sort_rows([r for r in acc.values() if r["zone"] == "A"])
    zb = sort_rows([r for r in acc.values() if r["zone"] == "B"])
    return za, zb, acc


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────
def api_games(q):
    """Partidos. ?date=YYYY-MM-DD filtra por día; ?round=N por fecha."""
    games = all_games()
    date = (q.get("date") or [None])[0]
    rnd = (q.get("round") or [None])[0]
    if date:
        games = [g for g in games if (g["start"] or "")[:10] == date]
    if rnd:
        games = [g for g in games if str(g["round"]) == str(rnd)]
    logos = _logos()
    for g in games:                      # el sitio del club, para el escudo
        for s in ("home", "away"):
            g[s]["site"] = SITIOS.get(g[s]["canon"])
            if not g[s].get("logo"):
                g[s]["logo"] = logos.get(g[s]["canon"], {}).get("logo")
    rounds = sorted({g["round"] for g in games if g["round"]})
    return {"games": games, "count": len(games), "rounds": rounds,
            "live": sum(1 for g in games if g["status"] == "LIVE"),
            "interzonal": sum(1 for g in games if g["interzonal"])}


def api_rounds(q):
    """Qué fechas existen y cuál es la que se está jugando."""
    games = all_games(ttl=90)
    by = {}
    for g in games:
        by.setdefault(g["round"], []).append(g)
    out = []
    for r in sorted(k for k in by if k):
        gs = by[r]
        done = sum(1 for g in gs if g["status"] == "FIN")
        out.append({"round": r, "games": len(gs), "finished": done,
                    "live": sum(1 for g in gs if g["status"] == "LIVE"),
                    # si faltan partidos, la fecha está incompleta y las
                    # tablas van a salir mal: mejor avisarlo
                    "incompleta": len(gs) < GAMES_POR_FECHA,
                    "from": min(g["start"] or "" for g in gs),
                    "to": max(g["start"] or "" for g in gs)})
    # misma regla que en las demás ligas: por calendario, no por estado
    current = fecha_actual([r["round"] for r in out], by)
    faltan = [r["round"] for r in out if r["incompleta"]]
    return {"rounds": out, "current": current, "incompletas": faltan,
            "total_partidos": len(games)}


def _logos(comp=None):
    """
    Escudo y sitio oficial de cada club.

    Sale del array `competitors` que 365scores adjunta a cualquier respuesta
    de partidos: ahí vienen los 30 equipos del torneo, jueguen o no esa fecha.
    Antes se sacaba de los partidos ya cruzados con el fixture de AFA, y por eso
    faltaban escudos en las fechas viejas, en la anual y en los goleadores.
    """
    comp = comp or COMPETITION
    out = {}
    for ep in ("games/results", "games/fixtures", "games/current"):
        try:
            data = fetch(ep, {"competitions": comp}, ttl=600)
        except Exception:
            continue
        for c in (data.get("competitors") or []):
            canon = match_team(c.get("name"))
            if not canon or canon in out:
                continue
            out[canon] = {"name": canon, "short": c.get("symbolicName") or "",
                          "logo": logo(c), "site": SITIOS.get(canon)}
    # el standings suma los que no aparecieron en ningún partido reciente
    try:
        data = fetch("standings", {"competitions": comp, "live": "true"}, ttl=600)
        for b in (data.get("standings") or []):
            for r in b.get("rows", []):
                c = r.get("competitor") or {}
                canon = match_team(c.get("name"))
                if canon and canon not in out:
                    out[canon] = {"name": canon, "short": c.get("symbolicName") or "",
                                  "logo": logo(c), "site": SITIOS.get(canon)}
    except Exception:
        pass

    for canon in ZONE_OF:
        out.setdefault(canon, {"name": canon, "short": "", "logo": None,
                               "site": SITIOS.get(canon)})
    return out


def restantes_por_equipo():
    """Cuántos partidos del Clausura le quedan a cada equipo."""
    faltan = {c: 0 for c in ZONE_OF}
    for m in all_games(ttl=120):
        if m["status"] in ("FIN",):
            continue
        for s in ("home", "away"):
            c = m[s]["canon"]
            if c in faltan:
                faltan[c] += 1
    return faltan


def _live_deltas():
    """Lo que están sumando ahora mismo los partidos en juego."""
    d = {}
    for m in all_games(ttl=15):
        if m["status"] != "LIVE" or m["gh"] is None or m["ga"] is None:
            continue
        for me, rival, mine, theirs in ((m["home"], m["away"], m["gh"], m["ga"]),
                                        (m["away"], m["home"], m["ga"], m["gh"])):
            if not me["canon"]:
                continue
            x = d.setdefault(me["canon"], {"pj": 0, "g": 0, "e": 0, "p": 0,
                                           "gf": 0, "gc": 0, "pts": 0})
            x["pj"] += 1
            x["gf"] += mine
            x["gc"] += theirs
            if mine > theirs:
                x["g"] += 1
                x["pts"] += 3
            elif mine == theirs:
                x["e"] += 1
                x["pts"] += 1
            else:
                x["p"] += 1
    return d


def _tabla(table, logos, deltas, con_vivo):
    """Convierte una tabla de DataFactory (Pts Pj Pg Pe Pp Gf Gc Df) al modelo."""
    rows = []
    for canon, raw_name, nums in df_rows(table):
        pts, pj, g, e, p, gf, gc = (_int(nums[i]) for i in range(7))
        dl = deltas.get(canon) if con_vivo else None
        if dl:
            pts, pj, g, e, p = pts + dl["pts"], pj + dl["pj"], g + dl["g"], e + dl["e"], p + dl["p"]
            gf, gc = gf + dl["gf"], gc + dl["gc"]
        rows.append({"canon": canon, "zone": ZONE_OF.get(canon),
                     "team": logos.get(canon, {"name": canon, "short": "", "logo": None}),
                     "pts": pts, "pj": pj, "g": g, "e": e, "p": p,
                     "gf": gf, "gc": gc, "dif": gf - gc,
                     "form": [], "live": bool(dl)})
    return sort_rows(rows)


def api_standings(q):
    """
    Zona A y Zona B. La base es la tabla oficial de AFA (DataFactory) y,
    encima, se suman los goles de los partidos que se están jugando ahora
    para que las posiciones se muevan en tiempo real.
    """
    con_vivo = (q.get("live") or ["1"])[0] != "0"
    fuente, nota = "AFA / DataFactory", ""
    try:
        tablas = df_tables("zonas")
        if len(tablas) < 2:
            raise ValueError("DataFactory devolvió %d tabla(s), esperaba 2" % len(tablas))
        logos, deltas = _logos(), (_live_deltas() if con_vivo else {})
        za = _tabla(tablas[0], logos, deltas, con_vivo)
        zb = _tabla(tablas[1], logos, deltas, con_vivo)
        if len(za) != 15 or len(zb) != 15:
            nota = "Ojo: %d y %d equipos por zona (deberían ser 15)" % (len(za), len(zb))
        # form (últimos 5) sale de los partidos, que DataFactory no da
        _, _, acc = zones_from(all_games())
        for r in za + zb:
            r["form"] = acc.get(r["canon"], {}).get("form", [])
    except Exception as e:
        # si AFA no responde, caemos a la tabla calculada desde los partidos
        za, zb, _ = zones_from(all_games())
        fuente, nota = "calculada desde los partidos", "DataFactory no respondió: %s" % e

    return {"zones": [{"name": "Zona A", "rows": za}, {"name": "Zona B", "rows": zb}],
            "fuente": fuente, "nota": nota, "envivo": con_vivo}


def api_annual(q):
    """Tabla anual 2026 (acumulada oficial de AFA), con los partidos en curso."""
    con_vivo = (q.get("live") or ["1"])[0] != "0"
    logos, deltas = _logos(), (_live_deltas() if con_vivo else {})
    rows = []
    try:
        tabla = df_tables("anual")[0]
        for canon, _raw, nums in df_rows(tabla):
            pts, pj, g, e, p, gf, gc = (_int(nums[i]) for i in range(7))
            dl = deltas.get(canon)
            if dl:
                pts, pj, gf, gc = pts + dl["pts"], pj + dl["pj"], gf + dl["gf"], gc + dl["gc"]
            rows.append({"team": logos.get(canon, {"name": canon, "short": "", "logo": None}),
                         "zone": ZONE_OF.get(canon), "pts": pts, "pj": pj,
                         "gf": gf, "gc": gc, "dif": gf - gc, "live": bool(dl)})
        fuente = "AFA / DataFactory"
    except Exception as e:
        return {"rows": [], "error": str(e), "fuente": "—"}

    rows.sort(key=lambda r: (-r["pts"], -r["dif"], norm(r["team"]["name"])))

    # Reparto de cupos. Los que ya están clasificados por haber salido
    # campeones no ocupan lugar: liberan el suyo y corren a todos los de abajo.
    libre = 0
    total = len(rows)
    for i, r in enumerate(rows, 1):
        r["pos"] = i
        # además del último de promedios, desciende el último de la anual
        r["desciende"] = i > total - DESCIENDE_ANUAL
        name = r["team"]["name"]
        if r["desciende"]:
            r["copa"], r["copaTexto"] = "desciende", "Desciende por la tabla anual"
            continue
        if name in YA_CLASIFICADOS:
            r["copa"] = "campeon"
            r["copaTexto"] = YA_CLASIFICADOS[name]
            libre += 1
            continue
        efectiva = i - libre
        if efectiva <= CUPOS_LIBERTADORES:
            r["copa"], r["copaTexto"] = "libertadores", "Copa Libertadores 2027"
        elif efectiva <= CUPOS_LIBERTADORES + CUPOS_SUDAMERICANA:
            r["copa"], r["copaTexto"] = "sudamericana", "Copa Sudamericana 2027"
        else:
            r["copa"], r["copaTexto"] = "", ""

    return {"rows": rows, "fuente": fuente,
            "cupos": {"libertadores": CUPOS_LIBERTADORES,
                      "sudamericana": CUPOS_SUDAMERICANA,
                      "yaClasificados": YA_CLASIFICADOS},
            "nota": ("La Anual reparte 9 cupos: 1° a 3° a Libertadores y 4° a 9° a "
                     "Sudamericana. Belgrano ya entró como campeón del Apertura, "
                     "así que libera un lugar y corre a todos una posición.")}


def api_promedios(q):
    """
    Tabla de promedios, tal cual la publica AFA: puntos de 2024, 2025 y 2026
    sobre partidos jugados. Ya no se estima nada — antes se calculaba con una
    base cargada a mano porque no habíamos encontrado esta fuente.
    """
    con_vivo = (q.get("live") or ["1"])[0] != "0"
    logos, deltas = _logos(), (_live_deltas() if con_vivo else {})
    rows, saltadas = [], []
    try:
        tabla = df_tables("promedios")[0]
    except Exception as e:
        return {"rows": [], "error": str(e), "fuente": "—"}

    for canon, raw, nums in df_rows(tabla):
        # columnas: 2024 | 2025 | 2026 | Total | Pj | Prom.
        if len(nums) < 5:
            saltadas.append(raw)
            continue
        p24, p25, p26 = (_int(nums[i], None) for i in range(3))
        pts, pj = _int(nums[3]), _int(nums[4])
        dl = deltas.get(canon)
        if dl:
            pts, pj = pts + dl["pts"], pj + dl["pj"]
            p26 = (p26 or 0) + dl["pts"]
        rows.append({"team": logos.get(canon, {"name": canon, "short": "", "logo": None}),
                     "zone": ZONE_OF.get(canon),
                     "p2024": p24, "p2025": p25, "p2026": p26,
                     "pts": pts, "pj": pj,
                     "prom": round(pts / pj, 4) if pj else 0.0,
                     "live": bool(dl)})

    rows.sort(key=lambda r: (-r["prom"], norm(r["team"]["name"])))
    for i, r in enumerate(rows, 1):
        r["pos"] = i

    # ── Riesgo de descenso ───────────────────────────────────────────────
    # Para cada equipo: el mejor promedio al que puede llegar (gana todo lo
    # que le queda) y el peor (pierde todo). Un equipo de arriba sigue en
    # riesgo mientras su peor promedio sea alcanzable por el mejor promedio
    # de alguno de los que hoy están descendiendo.
    faltan = restantes_por_equipo()
    for r in rows:
        n = faltan.get(r["team"]["name"], 0)
        r["restantes"] = n
        base_pj = r["pj"] + n
        r["promMax"] = round((r["pts"] + 3 * n) / base_pj, 4) if base_pj else 0.0
        r["promMin"] = round(r["pts"] / base_pj, 4) if base_pj else 0.0

    en_descenso = rows[-DESCIENDEN:] if rows else []
    techo = max((r["promMax"] for r in en_descenso), default=0.0)
    for r in rows:
        salvado = r["promMin"] > techo
        r["enRiesgo"] = (not salvado) and r not in en_descenso
        r["descendiendo"] = r in en_descenso
        r["salvado"] = salvado
    riesgo = [r["team"]["name"] for r in rows if r["enRiesgo"]]

    return {"rows": rows, "fuente": "AFA / DataFactory", "saltadas": saltadas,
            "enRiesgo": riesgo, "desciende": DESCIENDEN,
            "nota": ("Promedio oficial: puntos de las últimas 3 temporadas sobre "
                     "partidos jugados. En rojo el que hoy desciende; en amarillo, "
                     "los que todavía pueden ser alcanzados según los partidos que faltan.")}


def api_scorers(q):
    """Goleadores oficiales, con el desglose por tipo de gol que publica AFA."""
    logos = _logos()
    try:
        tabla = df_tables("goleadores", ttl=120)[0]
    except Exception as e:
        return {"rows": [], "error": str(e), "fuente": "—"}

    rows = []
    for fila in tabla:
        c = _cells(fila)
        if len(c) < 3:
            continue
        # Jugador | Equipo | Goles | Jugada | Cabeza | T.Libre | Penal
        jugador, equipo = c[0], c[1]
        if norm(jugador) in ("jugador", "") or not re.fullmatch(r"\d+", c[2] or ""):
            continue
        canon = match_team(equipo)
        if not canon:
            continue
        n = [_int(x) for x in c[2:7]] + [0] * 5
        rows.append({"name": jugador,
                     "team": logos.get(canon, {"name": canon, "short": "", "logo": None}),
                     "goals": n[0], "jugada": n[1], "cabeza": n[2],
                     "tiroLibre": n[3], "pens": n[4]})
    rows.sort(key=lambda x: -x["goals"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"rows": rows, "fuente": "AFA / DataFactory"}


def _num(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def api_match(q):
    """
    Detalle de un partido: goles con nombre, tarjetas, cambios, estadísticas
    y formaciones.

    Ojo con dos cosas de 365scores: los eventos traen `playerId`, no el
    nombre — hay que cruzarlos contra `members` del propio partido. Y las
    estadísticas viven en otro endpoint (`game/stats`), no en el del partido.
    """
    gid = (q.get("id") or [None])[0]
    if not gid:
        return {"error": "falta el parámetro id"}

    data = fetch("game", {"gameId": gid}, ttl=12)
    g = data.get("game") or (data.get("games") or [{}])[0] or {}
    if not g.get("id"):
        return {"error": "partido no encontrado"}

    out = map_game(g)
    hid = (g.get("homeCompetitor") or {}).get("id")

    # playerId -> nombre y número
    quien = {}
    for m in (g.get("members") or []):
        quien[m.get("id")] = {"name": m.get("name") or m.get("shortName") or "",
                              "n": m.get("jerseyNumber"),
                              "aid": m.get("athleteId")}

    TIPOS = {1: "gol", 2: "amarilla", 3: "roja", 1000: "cambio", 12: "palo"}
    events = []
    for e in (g.get("events") or []):
        et = e.get("eventType") or {}
        tid = et.get("id")
        nombre = norm(et.get("name"))
        tipo = TIPOS.get(tid)
        if not tipo:
            tipo = ("gol" if "gol" in nombre else
                    "roja" if "roja" in nombre else
                    "amarilla" if "amarilla" in nombre else
                    "cambio" if "sustitu" in nombre or "substitution" in nombre else "otro")
        p = quien.get(e.get("playerId"), {})
        extra = [quien.get(x, {}).get("name", "") for x in (e.get("extraPlayers") or [])]
        mins = e.get("gameTime")
        # lo mismo que en la lista: el gol anulado llega como evento de gol
        etiqueta = norm("%s %s" % (et.get("name") or "", et.get("subTypeName") or ""))
        anulado = any(x in etiqueta for x in
                      ("anulad", "disallow", "cancel", "invalid", "no valido"))
        # la tanda de penales llega como eventos del minuto 120 en adelante:
        # los convertidos como gol y los errados como otra cosa
        tanda = isinstance(mins, (int, float)) and mins >= 120
        events.append({
            "penales": bool(tanda),
            "anotado": tipo == "gol",
            "min": int(mins) if isinstance(mins, (int, float)) and mins >= 0 else None,
            "added": e.get("addedTime") or 0,
            "side": "h" if e.get("competitorId") == hid else "a",
            "type": tipo,
            "sub": et.get("subTypeName") or "",
            "player": p.get("name", ""),
            "extra": ", ".join(x for x in extra if x),
            "anulado": anulado,
        })
    events.sort(key=lambda x: (x["min"] if x["min"] is not None else 999, x["added"]))

    # estadísticas: endpoint aparte
    hs, as_, orden = {}, {}, []
    try:
        sj = fetch("game/stats", {"games": gid}, ttl=20)
        for s in (sj.get("statistics") or []):
            nombre = s.get("name")
            if not nombre:
                continue
            if nombre not in orden:
                orden.append(nombre)
            (hs if s.get("competitorId") == hid else as_)[nombre] = s.get("value")
    except Exception:
        pass

    stats = []
    for k in orden:
        na, nb = _num(hs.get(k)), _num(as_.get(k))
        t = (na + nb) or 1
        stats.append({"label": k, "h": hs.get(k, "0"), "a": as_.get(k, "0"),
                      "hp": na / t * 100, "ap": nb / t * 100})

    # formaciones: los titulares vienen por id, el nombre está en members
    # titulares y suplentes; el nombre y el número salen de `members`
    lineups = {"home": [], "away": []}
    banco = {"home": [], "away": []}
    banco_real = {"home": True, "away": True}
    formation = {}
    TITULAR = ("titular", "starting", "starter", "titulares")
    SUPLENTE = ("suplente", "suplentes", "substitute", "sub", "banco", "bench")
    # En la Liga Profesional se pueden llevar hasta doce al banco. Si la lista
    # que queda es más larga que eso, no es un banco: es el plantel entero.
    MAX_BANCO = 12

    def es_dt(f):
        """El entrenador: 365scores le pone el dorsal -1."""
        if str(f.get("n")) == "-1":
            return True
        etiqueta = norm("%s %s" % (f.get("puesto") or "", f.get("pos") or ""))
        return any(x in etiqueta for x in ("entrenador", "director tecnico",
                                           "coach", "manager"))
    for c_key, key in (("homeCompetitor", "home"), ("awayCompetitor", "away")):
        lu = (g.get(c_key) or {}).get("lineups") or {}
        formation[key] = lu.get("formation") or ""
        clasificados = []
        for m in (lu.get("members") or []):
            p = quien.get(m.get("id"), {})
            # yardFormation trae dónde para el jugador en la cancha, en
            # porcentajes: fieldLine es la profundidad (0 = línea propia) y
            # fieldSide el costado (0 izquierda, 100 derecha).
            yf = m.get("yardFormation") or {}
            ficha = {"n": p.get("n") or m.get("jerseyNumber"),
                     "name": p.get("name") or "",
                     "id": p.get("aid"),
                     "pos": puesto_ar((m.get("position") or {}).get("name")),
                     "puesto": puesto_ar((m.get("formation") or {}).get("name")),
                     "x": yf.get("fieldSide"), "y": yf.get("fieldLine")}
            if not ficha["name"]:
                continue
            st, txt = m.get("status"), norm(m.get("statusText"))
            if es_dt(ficha):
                rol = "dt"
            elif st == 1 or txt in TITULAR:
                rol = "titular"
            elif st == 2 or txt in SUPLENTE:
                rol = "suplente"
            else:
                rol = "?"          # está en la lista pero sin decir de qué
            clasificados.append((rol, ficha))

        # 365scores manda a todo el plantel en la misma lista. Tomar "el que
        # no es titular" como suplente dejaba a Racing con diecinueve en el
        # banco. Si la fuente marca explícitamente a los suplentes, se usa
        # eso; si no marca nada, se muestran los que quedaron, pero avisando
        # que es el plantel y no el banco.
        lineups[key] = [f for r, f in clasificados if r == "titular"]
        explicitos = [f for r, f in clasificados if r == "suplente"]
        resto = [f for r, f in clasificados if r == "?"]
        elegidos = explicitos or resto
        banco_real[key] = bool(explicitos) or len(elegidos) <= MAX_BANCO
        # el cuerpo técnico va siempre, lo marque como lo marque la fuente
        banco[key] = elegidos + [f for r, f in clasificados if r == "dt"]

    ofic = [o.get("name") if isinstance(o, dict) else str(o) for o in (g.get("officials") or [])]
    venue = g.get("venue") or {}
    for s in ("home", "away"):
        out[s]["site"] = SITIOS.get(out[s]["canon"])

    # Cada formación que vemos alimenta la trayectoria y el conteo de
    # partidos. Es la única fuente propia que tenemos de eso.
    liga_id = (q.get("liga") or ["lpf"])[0]
    for key, lado in (("home", out["home"]), ("away", out["away"])):
        club = lado.get("canon") or lado.get("name")
        for p in lineups[key]:
            anotar_paso(p["name"], club, liga_id, lado.get("logo"))
            anotar_partido(p["name"], liga_id, out.get("id"))
        for p in banco[key]:
            anotar_paso(p["name"], club, liga_id, lado.get("logo"))

    # colores del club, para pintar la cancha
    for key, lado in (("home", out["home"]), ("away", out["away"])):
        c = COLORES.get(lado.get("canon") or "")
        lado["colores"] = list(c) if c else None

    tv = [t.get("name") for t in (g.get("tvNetworks") or []) if t.get("name")]
    # Hasta que el partido está por empezar, 365scores manda el plantel entero
    # sin marcar quién es titular: si eso se muestra tal cual, el banco queda
    # con veinte nombres. Se avisa si la formación ya está confirmada (once
    # titulares) para que la página no publique un banco que todavía no es.
    confirmada = {k: len(v) >= 11 for k, v in lineups.items()}

    out.update({"events": events, "stats": stats, "lineups": lineups,
                "banco": banco, "confirmada": confirmada,
                "bancoReal": banco_real,
                "formation": formation, "tv": tv,
                "referee": ofic[0] if ofic else "",
                "venue": venue.get("name") or out.get("venue") or "",
                "capacidad": venue.get("capacity")})
    return out


# ─────────────────────────────────────────────────────────────────────────
# Otras ligas (Primera Nacional). Sin nombres canónicos ni datos en vivo:
# se muestra tal cual lo publica AFA.
# ─────────────────────────────────────────────────────────────────────────
def _limpio(nombre):
    """Saca marcas del tipo '(*) Partido suspendido' del nombre del equipo."""
    return re.sub(r"\s*\(\*+\)\s*$", "", nombre).strip()


# ── Emparejar nombres entre AFA y 365scores ──────────────────────────────
# En la Liga Profesional alcanzaba con una lista de alias porque son 30
# equipos conocidos. En la Primera Nacional son 36 y cada fuente los escribe
# distinto: AFA pone "Dep. Morón", "Def. de Belgrano", "Racing (Cba)" y
# 365scores "Deportivo Morón", "Defensores de Belgrano", "Racing de Córdoba".
# Comparar por prefijo no alcanza, así que se comparan los tokens que
# importan, después de expandir las abreviaturas.
ABREV = {
    "dep": "deportivo", "def": "defensores", "defensa": "defensores",
    "atl": "atletico", "at": "atletico", "gral": "general", "sp": "sportivo",
    "gim": "gimnasia", "gyt": "gimnasia", "ind": "independiente", "cent": "central",
    "cba": "cordoba", "se": "santiago", "sgo": "santiago", "sj": "juan",
    "sl": "luis", "t": "tucuman", "j": "jujuy", "ba": "aires", "m": "mendoza",
    "lp": "plata", "rc": "cuarto", "ctes": "corrientes",
}
GENERICAS = {"club", "atletico", "deportivo", "de", "del", "la", "el", "los", "y",
             "esgrima", "social", "cultural", "asociacion", "ca", "cd", "csyd",
             "sportivo", "san", "general", "carril", "aires", "buenos"}


def _tokens(nombre):
    """
    Tokens significativos de un nombre, con abreviaturas expandidas.

    Las de una sola letra sólo se expanden si venían entre paréntesis: en
    "San Martín (T)" la T es Tucumán, pero en "T. Suárez" es apenas la
    inicial de Tristán. Expandirla ahí inventaba un "tucumán" que no existe
    y arruinaba el emparejado.
    """
    crudo = norm(nombre)
    entre_parentesis = set()
    for grupo in re.findall(r"\(([^)]*)\)", crudo):
        for t in grupo.split():
            entre_parentesis.add(ABREV.get(t, t))

    out = set(entre_parentesis)
    for t in re.sub(r"\([^)]*\)", " ", crudo).split():
        if len(t) > 1:
            t = ABREV.get(t, t)
        elif len(t) == 1:
            continue                 # inicial suelta: no aporta nada
        if t and t not in GENERICAS and not t.isdigit():
            out.add(t)
    return {t for t in out if t not in GENERICAS} or set(crudo.split())


def nombre_mas_completo(a, b):
    """
    De dos escrituras del mismo club, la que está menos abreviada.

    Cada fuente abrevia distinto y no siempre la misma: AFA pone "Chaco FE"
    donde 365scores pone "Chaco For Ever", pero también hay casos al revés.
    Se descarta la que tenga abreviaturas con punto o iniciales sueltas, y
    entre las que quedan gana la más larga.
    """
    def penaliza(x):
        if not x:
            return 99
        p = len(re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-z]{0,2}\.", x))   # "Dep." "Alte."
        p += len(re.findall(r"\b[A-Z]\b", x))                   # iniciales sueltas
        p += len(re.findall(r"\([^)]{1,4}\)", x))               # "(SE)" "(Cba)"
        return p

    pa, pb = penaliza(a), penaliza(b)
    if pa != pb:
        return a if pa < pb else b
    return a if len(a or "") >= len(b or "") else b


# Nombres que no se parecen en nada al del club y que ninguna regla puede
# adivinar: siglas, apodos, cambios de denominación. Van a mano.
#
#   SATSAID es el sindicato de televisión: el club se llama Social Atlético
#   Televisión y AFA lo publica con la sigla, así que el escudo no aparecía.
ALIAS_EQUIPOS = {
    "satsaid": "social atletico television",
    "sat saird": "social atletico television",
}


def emparejar(nombre, candidatos):
    """
    Devuelve la clave de `candidatos` que mejor corresponde a `nombre`.

    `candidatos` es {clave_normalizada: cualquier_cosa}. Se elige por
    coincidencia de tokens; ante empate gana el que tenga la misma cantidad
    de tokens, para que "Racing" no se lleve por delante a "Racing (Cba)".
    """
    n = norm(nombre)
    if n in candidatos:
        return n

    # las siglas primero: ninguna regla de tokens las va a sacar
    otro = ALIAS_EQUIPOS.get(n)
    if otro and otro != n:
        if otro in candidatos:
            return otro
        # el club puede figurar con otra variante ("Social Atl. Televisión"):
        # se busca el nombre largo con las reglas de siempre
        aprox = emparejar(otro, candidatos)
        if aprox:
            return aprox

    tn = _tokens(nombre)
    if not tn:
        return None
    mejor, puntaje = None, 0.0
    for k in candidatos:
        tk = _tokens(k)
        if not tk:
            continue
        comunes = tn & tk
        if not comunes:
            continue
        # proporción de coincidencia sobre el nombre más corto, penalizando
        # los tokens que sobran de un lado
        base = min(len(tn), len(tk))
        p = len(comunes) / base - abs(len(tn) - len(tk)) * 0.08
        if len(tn) == len(tk) and tn == tk:
            p += 0.5
        if p > puntaje:
            mejor, puntaje = k, p
    if puntaje >= 0.75:
        return mejor

    # Último recurso, y el que salva la mayoría de los casos raros: si alguna
    # palabra del nombre aparece en un solo candidato, es ese y no hay con qué
    # confundirlo. Sirve para lo que ningún diccionario de abreviaturas cubre:
    # "Alte. Brown" comparte sólo "brown", "N. Chicago" sólo "chicago",
    # "Gim. y Tiro" sólo "tiro" — y cada una de esas palabras es única.
    unicos = []
    for t in tn:
        con_ese_token = [k for k in candidatos if t in _tokens(k)]
        if len(con_ese_token) == 1:
            unicos.append(con_ese_token[0])
    if unicos and len(set(unicos)) == 1:
        return unicos[0]

    # Y una más: DataFactory corta los nombres largos a la mitad de la
    # palabra. En la B Metro escribe "Excursion" y el escudo, al lado, dice
    # "Excursionistas". Como no es una abreviatura con punto, nada de lo de
    # arriba lo agarra. Si una palabra de un lado empieza igual que una del
    # otro y son cinco letras o más, es el mismo equipo.
    def empieza_igual(a, b):
        return len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a))

    prefijos = [k for k in candidatos
                if any(empieza_igual(t, u) for t in tn for u in _tokens(k))]
    if len(set(prefijos)) == 1:
        return prefijos[0]
    return None


def _fila_generica(row):
    """(nombre, [números]) de una fila de DataFactory, sin mapear a canónicos."""
    if len(row) < 3:
        return None
    idx = next((i for i, x in enumerate(row)
                if x and not re.fullmatch(r"-?[\d.,]+", x)), None)
    if idx is None:
        return None
    nombre = _limpio(row[idx])
    if norm(nombre) in ("equipo", "zona a", "zona b", "grupo a", "grupo b", "n", "jugador"):
        return None
    return nombre, row[idx + 1:]


def _sc_standings(comp, ttl=25):
    """
    Posiciones de una competencia de 365scores, separadas por zona.
    A diferencia de la Liga Profesional, acá sí vienen las dos juntas: cada
    fila trae su groupNum y el bloque, los nombres de los grupos.
    """
    data = fetch("standings", {"competitions": comp, "live": "true"}, ttl=ttl)
    bloque = (data.get("standings") or [{}])[0]
    nombres = {g.get("num"): g.get("name") for g in (bloque.get("groups") or [])}
    zonas = {}
    for r in bloque.get("rows", []):
        c = r.get("competitor") or {}
        gf, gc = int(r.get("for") or 0), int(r.get("against") or 0)
        form = []
        for m in (r.get("detailedRecentForm") or [])[-5:]:
            hc, ac = m.get("homeCompetitor") or {}, m.get("awayCompetitor") or {}
            me, riv = (hc, ac) if hc.get("id") == c.get("id") else (ac, hc)
            if me.get("score") is None or riv.get("score") is None:
                continue
            form.append("G" if me["score"] > riv["score"]
                        else ("P" if me["score"] < riv["score"] else "E"))
        g = r.get("groupNum")
        zonas.setdefault(g, []).append({
            "team": {"name": c.get("name") or "", "short": c.get("symbolicName") or "",
                     "logo": logo(c), "site": sitio_de(c.get("name") or "")},
            "pts": int(float(r.get("points") or 0)), "pj": int(r.get("gamePlayed") or 0),
            "g": int(r.get("gamesWon") or 0), "e": int(r.get("gamesEven") or 0),
            "p": int(r.get("gamesLost") or 0),
            "gf": gf, "gc": gc, "dif": gf - gc, "form": form, "live": False,
        })
    out = []
    for num in sorted(zonas):
        # Los torneos sin zonas vienen con num en blanco. Antes se armaba
        # "Zona %s" igual y la pestaña terminaba diciendo "Zona None": si no
        # hay nombre ni número, se deja vacío y la página pone "Tabla".
        nombre = nombres.get(num)
        if not nombre and num not in (None, "", 0):
            nombre = "Zona %s" % num
        out.append({"name": nombre or None,
                    "num": num, "rows": sort_rows_simple(zonas[num])})
    return out


LEYENDA_DESTINOS = [
    {"clave": "final", "color": "#f0b429",
     "texto": "Final por el primer ascenso"},
    {"clave": "reducido", "color": "#2f6fed",
     "texto": "Reducido por el segundo ascenso"},
    {"clave": "avanza", "color": "#2f6fed", "texto": "Avanza a octavos"},
    {"clave": "repechaje", "color": "#f0b429",
     "texto": "Juega el repechaje por octavos"},
    {"clave": "champions", "color": "#2f6fed", "texto": "Champions League"},
    {"clave": "europa", "color": "#f0b429", "texto": "Europa League"},
    {"clave": "conference", "color": "#12b76a", "texto": "Conference League"},
    {"clave": "desciende", "color": "#e5484d", "texto": "Descienden"},
]


def marcar_destinos(zonas, reglas):
    """
    Pinta cada fila según a dónde va: ascenso, reducido o descenso.

    `reglas` es {clave: (desde, hasta)} con posiciones que arrancan en 1. Los
    números negativos cuentan desde abajo, así (-2, -1) son los dos últimos
    sin importar cuántos equipos tenga la zona.
    """
    if not reglas:
        return
    for z in zonas:
        n = len(z["rows"])
        for r in z["rows"]:
            r["destino"], r["destinoTexto"] = "", ""
            pos = r.get("pos") or 0
            for clave, (desde, hasta) in reglas.items():
                a = desde if desde > 0 else n + desde + 1
                b = hasta if hasta > 0 else n + hasta + 1
                if a <= pos <= b:
                    r["destino"] = clave
                    r["destinoTexto"] = next(
                        (x["texto"] for x in LEYENDA_DESTINOS if x["clave"] == clave), "")
                    break


def _sc_goleadores(comp, escudos=None):
    """Goleadores desde 365scores, para las ligas que no cubre AFA."""
    data = fetch("stats", {"competitions": comp, "competitor": 0}, ttl=900)
    bloques = data.get("stats") or data.get("statistics") or []

    # El bloque de goles no siempre se llama igual ni viene primero: en las
    # copas la lista arranca por asistencias o tarjetas. Se busca por nombre
    # y, si no aparece, se toma el primero que tenga filas de verdad.
    def es_goles(b):
        n = norm(b.get("name"))
        return n in ("goles", "goals") or n.startswith("gol")

    goles = (next((b for b in bloques if es_goles(b)), None)
             or next((b for b in bloques if b.get("rows")), None))
    if not goles:
        return []

    # nombre de equipo por id, del mismo paquete
    equipos = {}
    for c in (data.get("competitors") or []):
        equipos[c.get("id")] = {"name": c.get("name") or "", "short": c.get("symbolicName") or "",
                                "logo": logo(c), "site": None}

    filas = []
    for r in goles.get("rows", []):
        e = r.get("entity") or {}
        st = r.get("stats") or []
        try:
            g = int(float(st[0].get("value") if st else r.get("value") or 0))
        except (TypeError, ValueError):
            g = 0
        pen = 0
        mm = re.search(r"(\d+)", str(r.get("secondaryStatName") or ""))
        if mm:
            pen = int(mm.group(1))
        eq = equipos.get(e.get("competitorId")) or {"name": "", "short": "",
                                                    "logo": None, "site": None}
        if escudos and not eq["logo"]:
            k = emparejar(eq["name"], escudos)
            if k:
                eq = escudos[k]
        filas.append({"name": e.get("name") or "", "team": eq, "goals": g,
                      "pens": pen, "jugada": None, "cabeza": None, "tiroLibre": None,
                      "athleteId": e.get("id")})
    filas.sort(key=lambda x: -x["goals"])
    for i, r in enumerate(filas, 1):
        r["rank"] = i
    return filas


def api_liga(q):
    """
    Tablas y goleadores de una liga que no sea la Profesional.
    Uso: /api/liga?id=nacional
    """
    lid = (q.get("id") or ["nacional"])[0]
    cfg = LIGAS.get(lid)
    if not cfg:
        return {"error": "liga desconocida: %s" % lid}

    out = {"id": lid, "nombre": cfg["nombre"], "torneo": cfg["torneo"],
           "fuente": ("365scores + AFA" if cfg.get("base")
                      else "365scores + LaLiga" if cfg.get("fixture_propio")
                      else "365scores"),
           "zonas": [], "anual": [], "goleadores": [],
           # Hay ligas que tienen una sola tabla y nada más: LaLiga y la B
           # Metro. Ahí la acumulada no aporta y se esconde la pestaña.
           "conAnual": cfg.get("anual", True)}

    # posiciones por zona, con escudos
    try:
        out["zonas"] = _sc_standings(cfg["sc"])
        marcar_destinos(out["zonas"], cfg.get("zonas_de"))
        # sólo las referencias que esta liga usa de verdad
        usadas = set(cfg.get("zonas_de") or {})
        out["leyenda"] = [x for x in LEYENDA_DESTINOS if x["clave"] in usadas]
    except Exception as e:
        out["errorZonas"] = str(e)

    # marcar con el puntito verde a los que están jugando ahora mismo
    try:
        jugando = set()
        for g in fetch("games/current", {"competitions": cfg["sc"]}, ttl=20).get("games", []):
            lv = map_game(g)
            if lv["status"] == "LIVE":
                jugando.add(norm(lv["home"]["name"]))
                jugando.add(norm(lv["away"]["name"]))
        if jugando:
            for z in out["zonas"]:
                for r in z["rows"]:
                    n = norm(r["team"]["name"])
                    r["live"] = n in jugando or bool(emparejar(n, {x: 1 for x in jugando}))
    except Exception:
        pass

    # Tabla general: los 36 equipos de las dos zonas ordenados por puntos.
    #
    # No se lee de la página de descenso de AFA porque ahí está casi toda en
    # cero: sólo carga la columna de la temporada en curso y deja Total, Pj y
    # Prom. en blanco. Sumar las dos zonas da lo mismo y siempre al día.
    if out["conAnual"]:
        todos = [dict(r, zona=z["name"]) for z in out["zonas"] for r in z["rows"]]
        todos.sort(key=lambda r: (-r["pts"], -r["dif"], -r["gf"],
                                  norm(r["team"]["name"])))
        for i, r in enumerate(todos, 1):
            r["pos"] = i
        out["anual"] = todos
        out["anualNota"] = ("Tabla general: las dos zonas juntas, ordenadas por "
                            "puntos. AFA no publica promedios en esta categoría.")

    # los escudos de la anual salen de las zonas, que sí los tienen
    escudos = {norm(r["team"]["name"]): r["team"]
               for z in out["zonas"] for r in z["rows"]}

    def pegar(nombre):
        k = emparejar(nombre, escudos)
        return escudos[k] if k else None

    # Goleadores. AFA los da con el desglose por tipo de gol, que es mejor,
    # pero sólo para las categorías argentinas. Para el resto, 365scores.
    if not cfg.get("base"):
        try:
            out["goleadores"] = _sc_goleadores(cfg["sc"], escudos)
        except Exception as e:
            out["errorGoleadores"] = str(e)
        # Si la fuente no publica goleadores —pasa en las copas— la tabla se
        # arma con los goles que fuimos guardando de cada partido. No es
        # oficial, así que se avisa.
        if not out["goleadores"]:
            propios = goleadores_propios(lid, escudos)
            if propios:
                out["goleadores"] = propios
                out["goleadoresPropios"] = True
                out["notaGoleadores"] = ("Contados por HAYVAR a partir de los "
                                         "goles de cada partido.")
        return out

    try:
        for tabla in df_tables("goleadores", ttl=300, liga=lid)[:1]:
            for fila in tabla:
                c = _cells(fila)
                if len(c) < 3 or not re.fullmatch(r"\d+", c[2] or ""):
                    continue
                n = [_int(x) for x in c[2:7]] + [0] * 5
                equipo = _limpio(c[1])
                out["goleadores"].append({
                    "name": c[0], "team": pegar(equipo) or {"name": equipo, "short": "",
                                                            "logo": None, "site": None},
                    "goals": n[0], "jugada": n[1], "cabeza": n[2],
                    "tiroLibre": n[3], "pens": n[4]})
        out["goleadores"].sort(key=lambda x: -x["goals"])
        for i, r in enumerate(out["goleadores"], 1):
            r["rank"] = i
    except Exception as e:
        out["errorGoleadores"] = str(e)

    # Si AFA no devolvió nada —la página cambió, se cayó, o esa categoría
    # todavía no la publica— se completa con 365scores antes que dejarlo vacío.
    if not out["goleadores"]:
        try:
            out["goleadores"] = _sc_goleadores(cfg["sc"], escudos)
        except Exception:
            pass

    return out


def sort_rows_simple(rows):
    rows = sorted(rows, key=lambda r: (-r["pts"], -r["dif"], -r["gf"], norm(r["team"]["name"])))
    for i, r in enumerate(rows, 1):
        r["pos"] = i
    return rows


def fetch_ruta(ruta, ttl=86400):
    """
    Pide una dirección de 365scores tal cual viene, sin rearmar los
    parámetros. La usa el rescate de partidos viejos, porque el paginado
    devuelve la dirección de la página anterior ya armada.
    """
    url = ruta if ruta.startswith("http") else "https://webws.365scores.com" + ruta

    def ir_a_la_fuente():
        req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))

    datos, _ = almacen.con_respaldo("pag:" + url, ir_a_la_fuente,
                                    max_edad=ttl, tag="365/paginado")
    return datos or {}


def rescatar_historico(comp, paginas=25):
    """
    Recupera los partidos que ya no entran en la ventana de 365scores.

    La ventana muestra lo de ahora y poco más, así que la fase de grupos de
    la Libertadores —jugada meses atrás— no aparece nunca. Pero la respuesta
    trae un `paging.previousPage`: una dirección a la página anterior. Yendo
    hacia atrás de a una se recorre el torneo entero.

    Se guarda dónde quedó, así cada vuelta sigue desde ahí en lugar de
    empezar de cero, y cuando ya no hay página anterior se marca terminado y
    no se vuelve a pedir.
    """
    estado, _ = almacen.leer("hist:%s" % comp)
    estado = estado or {}
    if estado.get("listo"):
        return {"comp": comp, "estado": "ya estaba completo",
                "rescatados": estado.get("total", 0)}

    ruta = estado.get("siguiente")
    if not ruta:
        try:
            data = fetch("games/fixtures", {"competitions": comp}, ttl=300)
        except Exception as e:
            return {"comp": comp, "error": str(e)}
        ruta = ((data.get("paging") or {}).get("previousPage") or "")

    clave = "fixture:%s" % comp
    guardado, _ = almacen.leer(clave)
    acumulado = {str(m["id"]): m for m in (guardado or [])}
    antes = len(acumulado)

    vueltas, listo = 0, False
    while ruta and vueltas < paginas:
        try:
            data = fetch_ruta(ruta)
        except Exception:
            break
        vueltas += 1
        juegos = data.get("games") or []
        for g in juegos:
            m = map_game(g)
            m["liveId"] = g.get("id")
            m["temporada"] = g.get("seasonNum")
            m["zone"], m["interzonal"] = None, False
            for s in ("home", "away"):
                m[s]["canon"] = m[s]["name"]
            acumulado.setdefault(str(m["id"]), m)
        siguiente = (data.get("paging") or {}).get("previousPage")
        if not siguiente or siguiente == ruta:
            listo = True
            ruta = None
            break
        ruta = siguiente

    almacen.guardar(clave, list(acumulado.values()))
    almacen.guardar("hist:%s" % comp,
                    {"siguiente": ruta, "listo": listo,
                     "total": len(acumulado)})
    return {"comp": comp, "paginas": vueltas, "listo": listo,
            "nuevos": len(acumulado) - antes, "total": len(acumulado)}


def api_historico(q):
    """
    Trae los partidos viejos de un torneo. /api/historico?id=lib
    Se puede repetir: cada vez sigue desde donde quedó.
    """
    lid = (q.get("id") or ["lib"])[0]
    cfg = LIGAS.get(lid)
    if not cfg:
        return {"error": "liga desconocida: %s" % lid}
    paginas = _int((q.get("paginas") or ["25"])[0], 25)
    r = rescatar_historico(cfg["sc"], max(1, min(80, paginas)))
    r["liga"] = cfg["nombre"]
    if not r.get("listo"):
        r["nota"] = ("Todavía queda historia por traer: volvé a entrar para "
                     "seguir desde acá.")
    return r


def _sc_fixture(comp, ttl=120):
    """
    Calendario desde 365scores, acumulado en la base.

    365scores sólo publica una ventana móvil: para LaLiga devuelve las fechas
    36, 37 y 38 de la temporada pasada más la 1 y la 2 de la nueva, y nada de
    lo que hay en el medio. Pedirle el resto no sirve, no lo tiene.

    Por eso cada consulta se fusiona con lo ya guardado: lo que entró una vez
    se queda. La primera vez el calendario está incompleto y se va llenando
    solo a medida que la temporada avanza.
    """
    clave = "fixture:%s" % comp
    guardado, _ = almacen.leer(clave)
    acumulado = {str(m["id"]): m for m in (guardado or [])}

    frescos, temporadas = 0, {}
    for ep in ("games/results", "games/fixtures", "games/current"):
        try:
            data = fetch(ep, {"competitions": comp}, ttl=ttl)
        except Exception:
            continue
        for g in data.get("games", []):
            m = map_game(g)
            m["liveId"] = g.get("id")
            m["temporada"] = g.get("seasonNum")
            m["zone"] = None
            m["interzonal"] = False
            for s in ("home", "away"):
                m[s]["canon"] = m[s]["name"]
            # lo nuevo pisa a lo viejo: el marcador puede haber cambiado
            acumulado[str(m["id"])] = m
            frescos += 1
        for c in (data.get("competitions") or []):
            if c.get("id") == comp and c.get("currentSeasonNum"):
                temporadas["actual"] = c["currentSeasonNum"]

    todos = list(acumulado.values())
    if frescos:
        almacen.guardar(clave, todos)

    # 365scores mezcla el final de la temporada pasada con el arranque de la
    # nueva: para LaLiga devolvía las fechas 36, 37 y 38 del torneo anterior
    # junto a la 1 y la 2. Nos quedamos sólo con la temporada en curso.
    actual = temporadas.get("actual")
    if actual is None:
        vistas = [m.get("temporada") for m in todos if m.get("temporada")]
        actual = max(vistas) if vistas else None
    if actual is not None:
        todos = [m for m in todos
                 if m.get("temporada") in (None, actual)] or todos

    return sorted(todos, key=lambda x: (x["round"] or 0, x["start"] or ""))


# ── Canal de TV y goleadores de cada partido ─────────────────────────────
#
# Los dos salen del detalle del partido, un pedido por partido. Es caro para
# pedirlo en cada visita, pero no cambia: una vez terminado el partido los
# goles son los que son. Por eso se cachea fuerte y sólo se refresca lo que
# está en juego.
def detalle_liviano(game_id, en_juego=False, liga="lpf"):
    ttl = 30 if en_juego else 60 * 60 * 12
    data = fetch("game", {"gameId": game_id}, ttl=ttl)
    g = data.get("game") or {}
    hid = (g.get("homeCompetitor") or {}).get("id")
    quien = {m.get("id"): (m.get("name") or m.get("shortName") or "")
             for m in (g.get("members") or [])}

    # Ya que tenemos el partido entero abierto, anotamos quiénes jugaron.
    # Esto es lo que hace que el contador de partidos se llene solo: /api/
    # detalles se pide para cada fecha que el usuario mira, así que alcanza
    # con navegar el torneo para que se complete.
    for ck in ("homeCompetitor", "awayCompetitor"):
        comp = g.get(ck) or {}
        club = comp.get("name") or ""
        escudo = logo(comp)
        for mm in ((comp.get("lineups") or {}).get("members") or []):
            nom = quien.get(mm.get("id"))
            if not nom:
                continue
            if mm.get("status") == 1 or norm(mm.get("statusText")) in ("titular", "starting", "starter"):
                anotar_partido(nom, liga, game_id)
            anotar_paso(nom, club, liga, escudo)
    goles = []
    for e in (g.get("events") or []):
        et = e.get("eventType") or {}
        if et.get("id") != 1 and "gol" not in norm(et.get("name")):
            continue
        mins = e.get("gameTime")
        # Los goles anulados por el VAR también llegan como evento y se
        # llaman "Gol anulado": entraban por el filtro de arriba y quedaban
        # contados como goles. Platense aparecía con dos y el partido iba 1-1.
        # Se marcan en vez de esconderse: enterarse de que hubo un gol
        # anulado es parte de lo que uno quiere ver.
        etiqueta = norm("%s %s" % (et.get("name") or "", et.get("subTypeName") or ""))
        anulado = any(x in etiqueta for x in
                      ("anulad", "disallow", "cancel", "invalid", "no valido"))
        minuto = int(mins) if isinstance(mins, (int, float)) and mins >= 0 else None
        # La definición por penales llega como goles del minuto 120 y pico,
        # así que se sumaban al resultado y a los goleadores. No son goles
        # del partido: son la tanda. Se separan.
        tanda = minuto is not None and minuto >= 120
        goles.append({
            "min": minuto,
            "added": e.get("addedTime") or 0,
            "side": "h" if e.get("competitorId") == hid else "a",
            "player": quien.get(e.get("playerId"), ""),
            "sub": et.get("subTypeName") or "",
            "anulado": anulado,
            "penales": tanda,
        })
    goles.sort(key=lambda x: (x["min"] if x["min"] is not None else 999, x["added"]))

    # de qué equipo es cada gol, para poder armar la tabla de goleadores
    equipo = {"h": (g.get("homeCompetitor") or {}).get("name") or "",
              "a": (g.get("awayCompetitor") or {}).get("name") or ""}
    for x in goles:
        x["equipo"] = equipo.get(x["side"], "")
    anotar_goles(liga, game_id, goles)

    tv = limpiar_tv([t.get("name") for t in (g.get("tvNetworks") or []) if t.get("name")])
    if tv:
        almacen.guardar("tv:%s:%s" % (liga, game_id), tv)
    return {"tv": tv, "goles": goles}


def limpiar_tv(canales):
    """
    Saca las apps que repiten un canal que ya está.

    Si el partido va por TyC Sports, "TyC Sports Play" no agrega nada: es el
    mismo canal por internet. Se queda el nombre corto, que es el que la
    gente busca en el control remoto.
    """
    salida = []
    for c in canales:
        n = norm(c)
        base = re.sub(r"\s*\b(play|app|online|en vivo)\b.*$", "", n).strip()
        if base and base != n and any(norm(o) == base for o in canales):
            continue
        salida.append(c)
    return salida


def api_detalles(q):
    """
    Canal de TV y goleadores de todos los partidos de una fecha, para poder
    mostrarlos en la lista sin abrir cada uno.
    Uso: /api/detalles?round=5  ·  /api/detalles?id=nacional&round=26
    """
    lid = (q.get("id") or ["lpf"])[0]
    rnd = (q.get("round") or [None])[0]
    fecha = (q.get("date") or [None])[0]

    def de_liga(x):
        return all_games() if x == "lpf" else api_liga_games({"id": [x]}).get("games", [])

    # Cada partido cuesta un pedido a 365scores. Sin este tope, un round
    # vacío pedía el torneo entero: cientos de llamadas para mostrar una
    # pantalla de quince partidos.
    TOPE = 40

    pares = []          # (liga, partido)
    if fecha:
        # la portada: los partidos de ese día, de las ligas que muestra
        for x in HOME_LIGAS:
            try:
                pares += [(x, g) for g in de_liga(x)
                          if (g.get("start") or "")[:10] == fecha]
            except Exception:
                continue
    else:
        try:
            games = de_liga(lid)
        except Exception:
            games = []
        if rnd:
            games = [g for g in games if str(g["round"]) == str(rnd)]
        pares = [(lid, g) for g in games]

    salida = {}
    con_id = [(x, g) for x, g in pares if g.get("liveId")]

    # Lo que ya está guardado se sirve de la base: instantáneo y sin pedirle
    # nada a nadie. Sólo se sale a buscar lo que falta, y de a poco. Antes se
    # pedía todo cada vez y con el tope de 40 los grupos de la Libertadores
    # —que tienen casi cien partidos— se quedaban a medias.
    pendientes = []
    for x, g in con_id:
        if g.get("status") == "LIVE":
            pendientes.append((x, g))
            continue
        guardado, _ = almacen.leer("goles:%s:%s" % (x, g["liveId"]))
        tv, _ = almacen.leer("tv:%s:%s" % (x, g["liveId"]))
        if guardado is None:
            pendientes.append((x, g))
        else:
            salida[str(g["id"])] = {
                "tv": tv or [],
                "goles": [{"player": q["j"], "equipo": q.get("e") or "",
                           "min": q.get("m"), "added": 0,
                           "side": q.get("s") or "h", "sub": "",
                           "anulado": False, "penales": False}
                          for q in guardado],
            }
    pendientes = pendientes[:TOPE]

    # Cada partido es un pedido a 365scores. De a uno, una fecha entera son
    # quince idas y vueltas en fila y por eso los goleadores y el canal
    # tardaban en aparecer después de que la lista ya estaba en pantalla.
    # En paralelo se resuelve en el tiempo del más lento.
    from concurrent.futures import ThreadPoolExecutor

    def uno(par):
        x, g = par
        try:
            return str(g["id"]), detalle_liviano(g["liveId"],
                                                 en_juego=g["status"] == "LIVE",
                                                 liga=x)
        except Exception:
            return None, None

    if pendientes:
        with ThreadPoolExecutor(max_workers=min(8, len(pendientes))) as pool:
            for gid, det in pool.map(uno, pendientes):
                if gid:
                    salida[gid] = det

    return {"detalles": salida, "consultados": len(pendientes),
            "sinDetalle": len(pares) - len(pendientes)}


def fecha_actual(rounds, por_fecha):
    """
    Qué fecha mostrar al entrar.

    Se decide por calendario, no por estado. Antes se tomaba la primera que
    tuviera algún partido sin terminar, pero un suspendido de hace dos meses
    la dejaba clavada ahí para siempre. Ahora: la que se está jugando hoy;
    si no hay ninguna, la próxima que viene; y si el torneo terminó, la última.
    """
    if not rounds:
        return None
    hoy = dt.date.today().isoformat()
    ahora = dt.datetime.now(dt.timezone.utc).isoformat()

    def dias(r):
        return sorted((g["start"] or "")[:10] for g in por_fecha.get(r, []) if g["start"])

    # 1. alguna que tenga partidos hoy
    for r in rounds:
        if hoy in dias(r):
            return r
    # 2. alguna con un partido en juego
    for r in rounds:
        if any(g["status"] == "LIVE" for g in por_fecha.get(r, [])):
            return r
    # 3. la próxima por empezar
    futuras = [(min((g["start"] for g in por_fecha.get(r, []) if g["start"]), default=""), r)
               for r in rounds]
    futuras = [(f, r) for f, r in futuras if f and f > ahora]
    if futuras:
        return min(futuras)[1]
    # 4. el torneo ya terminó
    return rounds[-1]


# El orden natural de las rondas de una copa. Se usa para acomodar las que
# agregamos a mano: si no, "Cuartos de final" caía después de la final sólo
# porque se sumó al final de la lista.
_RANGO_ETAPA = [
    # Las previas van antes que los grupos y son tres en la Libertadores, no
    # una: cada una tiene su rango para que no se pisen entre ellas.
    (("fase 3", "tercera fase", "third stage"), 0.6),
    (("fase 2", "segunda fase", "second stage"), 0.3),
    (("fase 1", "primera fase", "preliminar", "previa", "first stage"), 0),
    (("fase de grupos", "grupo", "group"), 1),
    (("repechaje", "play off", "playoff", "play-off", "pre octavos"), 2),
    (("64avos", "sesentaicuatroavos"), 3),
    (("32avos", "treintaidosavos", "treintaydosavos"), 4),
    (("16avos", "dieciseisavos"), 5),
    (("octavos",), 6),
    (("cuartos",), 7),
    (("semi",), 8),
    (("tercer",), 9),
    (("final",), 10),
]


# Las fases que tiene cada copa, con su nombre y en orden. Sirve de filtro:
# 365scores manda nombres sueltos y a veces alguno que no corresponde —
# apareció un "tercer puesto" que ni la Libertadores ni la Sudamericana
# juegan— y todo lo que no esté en esta lista se descarta.
#
# Libertadores 2026: tres fases previas, grupos y de octavos a la final.
# Sudamericana 2026: una fase previa, grupos, el play-off donde los segundos
# se cruzan con los terceros de la Libertadores, y de octavos a la final.
# Las dos definen a partido único, sin tercer puesto.
FASES_COPA = {
    "lib": ["Fase 1", "Fase 2", "Fase 3", "Fase de grupos", "Octavos de final",
            "Cuartos de final", "Semifinal", "Final"],
    "sud": ["Primera fase", "Fase de grupos", "Pre octavos", "Octavos de final",
            "Cuartos de final", "Semifinal", "Final"],
    "ca":  ["32avos de final", "16avos de final", "Octavos de final",
            "Cuartos de final", "Semifinal", "Final"],
}


def canonizar_fase(crudo, fases):
    """
    Lleva el nombre que manda la fuente al nombre de fase del torneo.

    "Fase 2" y "Fase 3" de la Libertadores son las dos previas: van juntas
    en una sola. Lo que no encaja en ninguna fase del torneo se descarta en
    vez de inventarle un lugar en el cuadro.
    """
    r = rango_etapa(crudo)
    for f in fases:
        if rango_etapa(f) == r:
            return f
    if r <= 1:          # una previa con otro nombre: va a la primera del torneo
        candidatas = [f for f in fases if rango_etapa(f) <= 1]
        return min(candidatas, key=rango_etapa) if candidatas else None
    return None


def rango_etapa(nombre):
    n = norm(nombre)
    for claves, r in _RANGO_ETAPA:
        if any(k in n for k in claves):
            return r
    return 5.5      # algo que no reconocemos: al medio, sin molestar


def llave_de(m):
    """Identifica la serie: los mismos dos equipos, sin importar quién es local."""
    return tuple(sorted((norm(m["home"]["name"]), norm(m["away"]["name"]))))


def marcar_ida_vuelta(games):
    """
    En las llaves de ida y vuelta, marca cuál es cuál.

    Se cruzan los mismos dos equipos dos veces en la misma etapa: el que se
    juega antes es la ida. Con eso el fixture se puede ordenar como se mira
    —todas las idas y después todas las vueltas— y cada partido dice qué es.
    """
    series = {}
    for m in games:
        series.setdefault((m.get("round"), llave_de(m)), []).append(m)
    for partidos in series.values():
        if len(partidos) != 2:
            continue
        partidos.sort(key=lambda x: x.get("start") or "")
        partidos[0]["tramo"] = "Ida"
        partidos[1]["tramo"] = "Vuelta"


def armar_llaves(games, etapas):
    """
    Agrupa el fixture en series para dibujar el cuadro.

    Cada llave son los dos equipos que se cruzan en una etapa, con el global
    de los dos partidos. Si es a un solo partido —Copa Argentina— el global
    es ese resultado. Se devuelve una lista por etapa, de la más lejana a la
    final, que es como se lee un cuadro.
    """
    # El cuadro es de la eliminación directa en serio: ni los grupos ni las
    # fases previas, que son un torneo aparte antes de que empiece este.
    def del_cuadro(nombre):
        return rango_etapa(nombre) >= 2

    por_etapa = {}
    for m in games:
        et = m.get("etapa") or ""
        if not et or not del_cuadro(et):
            continue
        por_etapa.setdefault(et, {}).setdefault(llave_de(m), []).append(m)

    salida = []
    for et in etapas:
        if not del_cuadro(et):
            continue
        llaves = []
        for partidos in (por_etapa.get(et) or {}).values():
            partidos.sort(key=lambda x: x.get("start") or "")
            # el global se cuenta desde el lado del local de la ida
            uno = partidos[0]
            a, b = uno["home"], uno["away"]
            ga = gb = 0
            jugados = 0
            for p in partidos:
                if p.get("gh") is None:
                    continue
                jugados += 1
                if norm(p["home"]["name"]) == norm(a["name"]):
                    ga, gb = ga + p["gh"], gb + p["ga"]
                else:
                    ga, gb = ga + p["ga"], gb + p["gh"]
            cerrada = jugados == len(partidos) and jugados > 0
            posiciones = [p.get("slot") for p in partidos if p.get("slot")]
            llaves.append({
                "slot": min(posiciones) if posiciones else None,
                "equipos": [
                    {"team": a, "goles": ga if jugados else None,
                     "pasa": bool(cerrada and ga > gb)},
                    {"team": b, "goles": gb if jugados else None,
                     "pasa": bool(cerrada and gb > ga)},
                ],
                "partidos": [{"id": p["id"], "start": p.get("start"),
                              "tramo": p.get("tramo"), "status": p.get("status"),
                              "gh": p.get("gh"), "ga": p.get("ga")}
                             for p in partidos],
                "cerrada": cerrada,
            })
        # por lugar en el cuadro si lo sabemos; si no, por fecha
        llaves.sort(key=lambda x: (x["slot"] if x["slot"] else 999,
                                   x["partidos"][0]["start"] or ""))
        salida.append({"etapa": et, "llaves": llaves})
    return salida


def ganador_de(llave):
    """El equipo que pasó, o None si la serie sigue abierta."""
    if not llave.get("cerrada"):
        return None
    return next((e["team"] for e in llave["equipos"] if e["pasa"]), None)


def api_liga_games(q):
    """
    Fixture de otra liga: el calendario completo sale de AFA y lo que se
    juega ahora, de 365scores (que además aporta escudos y zona).
    """
    lid = (q.get("id") or ["nacional"])[0]
    cfg = LIGAS.get(lid)
    if not cfg:
        return {"error": "liga desconocida"}
    err = None
    if cfg.get("fixture_propio") == "laliga":
        # Calendario de laliga.com (las 38 jornadas) con los goles de 365scores.
        try:
            games = laliga_fixture()
        except Exception as e:
            games, err = [], str(e)
        if games:
            try:
                pegar_marcadores(games, _sc_fixture(cfg["sc"]))
            except Exception:
                pass
        else:
            try:
                games, err = _sc_fixture(cfg["sc"]), None
            except Exception:
                pass
    elif not cfg.get("base"):
        # sin fixture propio ni de AFA: el calendario sale entero de 365scores
        try:
            games = _sc_fixture(cfg["sc"])
        except Exception as e:
            games, err = [], str(e)
    else:
        try:
            games = df_fixture_generico(lid)
        except Exception as e:
            games, err = [], str(e)
        if not games:
            try:
                games = _sc_fixture(cfg["sc"])
                err = None
            except Exception:
                pass

    # zona y escudo de cada equipo, desde las posiciones de 365scores
    meta = {}
    try:
        for z in _sc_standings(cfg["sc"], ttl=120):
            for r in z["rows"]:
                meta[norm(r["team"]["name"])] = (z["name"], r["team"])
    except Exception:
        pass

    def buscar(nombre):
        k = emparejar(nombre, meta)
        return meta[k] if k else (None, None)

    for m in games:
        za, ta = buscar(m["home"]["name"])
        zb, tb = buscar(m["away"]["name"])
        for lado, t in (("home", ta), ("away", tb)):
            if not t:
                continue
            m[lado].update({"logo": t["logo"], "short": t["short"], "site": t["site"],
                            "name": nombre_mas_completo(m[lado]["name"], t["name"]),
                            "canon": t["name"]})
        # La zona sale de en qué tabla está cada equipo. Si de uno solo se
        # pudo averiguar, se usa esa: en estas categorías las zonas juegan
        # separadas, así que ambos están en la misma. Sólo se marca como
        # interzonal cuando de los dos se sabe y no coinciden.
        zona = za or zb
        m["zone"] = (zona or "").replace("Zona ", "").replace("Grupo ", "") or None
        m["interzonal"] = bool(za and zb and za != zb)

    # El id de 365scores para cada partido del fixture de AFA. Se busca en
    # todo lo acumulado, no sólo en lo que se juega hoy: si no, las fechas
    # anteriores quedaban sin goleadores, sin canal y sin poder abrirse.
    if cfg.get("base"):
        try:
            porNombre = {}
            for x in _sc_fixture(cfg["sc"]):
                clave = (norm(x["home"]["name"])[:8], norm(x["away"]["name"])[:8])
                porNombre.setdefault(clave, []).append(x)
            for m in games:
                if m.get("liveId"):
                    continue
                cand = porNombre.get((norm(m["home"]["name"])[:8],
                                      norm(m["away"]["name"])[:8]))
                if not cand:
                    continue
                dia = (m.get("start") or "")[:10]
                elegido = next((x for x in cand if (x.get("start") or "")[:10] == dia),
                               cand[0] if len(cand) == 1 else None)
                if elegido:
                    m["liveId"] = elegido["id"]
                    m["venue"] = m.get("venue") or elegido.get("venue") or ""
        except Exception:
            pass

    # partidos en curso
    vivos, jugando = 0, set()
    try:
        raw = fetch("games/current", {"competitions": cfg["sc"]}, ttl=15).get("games", [])
        porNombre = {}
        for m in games:
            porNombre[(norm(m["home"]["name"]), norm(m["away"]["name"]))] = m
        for g in raw:
            lv = map_game(g)
            # Los mismos dos equipos se cruzan más de una vez en el torneo, así
            # que hay que mirar también la fecha: si no, el partido en vivo se
            # pega al de la primera rueda y queda el marcador donde no va.
            candidatos = []
            for (h, a), m in porNombre.items():
                if (h.startswith(norm(lv["home"]["name"])[:6])
                        and a.startswith(norm(lv["away"]["name"])[:6])):
                    candidatos.append(m)
            key = None
            if lv["round"]:
                key = next((m for m in candidatos if m["round"] == lv["round"]), None)
            if not key and lv["start"]:
                dia = lv["start"][:10]
                key = next((m for m in candidatos if (m["start"] or "")[:10] == dia), None)
            if not key and len(candidatos) == 1:
                key = candidatos[0]
            if not key:
                continue
            key["liveId"] = lv["id"]
            key["venue"] = lv["venue"] or key["venue"]
            if lv["status"] in ("LIVE", "FIN") and lv["gh"] is not None:
                key["status"], key["minute"] = lv["status"], lv["minute"]
                key["statusText"] = lv["statusText"] or key["statusText"]
                key["gh"], key["ga"] = lv["gh"], lv["ga"]
            if key["status"] == "LIVE":
                vivos += 1
                jugando.add(norm(key["home"]["name"]))
                jugando.add(norm(key["away"]["name"]))
    except Exception:
        pass

    # En las copas no hay fechas numeradas sino etapas: fase de grupos,
    # octavos, cuartos. 365scores las manda como texto en `stage`, así que se
    # ordenan por cuándo empezaron y se les da un número, que es lo que el
    # resto del servidor ya sabe manejar. El nombre viaja aparte, para el
    # rótulo de los botones.
    etapas = []
    if cfg.get("copa"):
        # ¿el torneo tiene fase de grupos? Lo dice que haya tablas por zona.
        hay_grupos = bool(meta)
        fases = FASES_COPA.get(lid)

        # La fase de cada partido la decide `stageNum`, que es el número de
        # ronda que le pone la propia fuente. Deducirla del nombre no
        # alcanzaba: las previas y el play-off llegan sin nombre y terminaban
        # todas mezcladas dentro de la fase de grupos.
        etiqueta_stage = {}
        for g in games:
            sn = g.get("stageNum")
            crudo = (g.get("stage") or "").strip()
            if crudo:
                etiqueta_stage.setdefault(sn, {}).setdefault(crudo, 0)
                etiqueta_stage[sn][crudo] += 1

        # a cada fase se le pone el nombre que más se repite entre sus partidos
        nombre_stage = {sn: max(c, key=c.get) for sn, c in etiqueta_stage.items()}

        # las que no traen nombre se completan por orden: la que tiene zonas y
        # muchos partidos es la de grupos, y el resto va cayendo en la fase
        # del torneo que corresponda según cuándo se juega
        stages = sorted({g.get("stageNum") for g in games},
                        key=lambda s: (s is None, s))
        libres = [f for f in (fases or [])
                  if f not in {canonizar_fase(n, fases) for n in nombre_stage.values()}]
        for sn in stages:
            if sn in nombre_stage:
                continue
            suyos = [g for g in games if g.get("stageNum") == sn]
            con_zona = sum(1 for g in suyos if g.get("zone"))
            elegida = None
            if con_zona and len(suyos) >= 12:
                elegida = next((f for f in libres if rango_etapa(f) == 1), None)
            if not elegida and libres:
                elegida = libres[0]
            if elegida:
                nombre_stage[sn] = elegida
                libres = [f for f in libres if f != elegida]

        def nombre_etapa(g):
            et = nombre_stage.get(g.get("stageNum")) or (g.get("stage") or "").strip()
            if not et:
                et = ("Fase de grupos" if (g.get("zone") or hay_grupos)
                      else "Fase única")
            return canonizar_fase(et, fases) if fases else et

        # Las rondas se ordenan por stageNum, que es el orden real del
        # torneo. La fecha no sirve sola: los 32avos de una zona pueden
        # jugarse después de los 16avos de otra.
        # los partidos que no encajan en ninguna fase del torneo se van
        games = [g for g in games if nombre_etapa(g)]

        primero = {}
        for g in games:
            et = nombre_etapa(g)
            clave = (g.get("stageNum") if g.get("stageNum") is not None else 999,
                     g.get("start") or "9999")
            if et not in primero or clave < primero[et]:
                primero[et] = clave
        etapas = sorted(primero, key=lambda e: primero[e])

        # Las etapas que todavía no se jugaron no vienen en el fixture, así
        # que la Copa Argentina se quedaba sin cuartos, semis ni final. Se
        # agregan al final para que el botón exista aunque diga "por definir".
        ya = {norm(e) for e in etapas}
        for e in (cfg.get("etapas_extra") or []):
            if norm(e) not in ya:
                etapas.append(e)
                ya.add(norm(e))

        # Y se ordena todo por el orden real de una copa. Sin esto, las que
        # agregamos a mano quedaban pegadas al final: en la Sudamericana los
        # dieciseisavos aparecían después de los octavos.
        # las posiciones se guardan antes: durante sort() la lista queda
        # vacía para Python, así que buscar adentro de la clave revienta
        posicion = {e: i for i, e in enumerate(etapas)}
        etapas.sort(key=lambda e: (rango_etapa(e), posicion[e]))

        idx = {e: i + 1 for i, e in enumerate(etapas)}
        grupos = norm("Fase de grupos")
        for g in games:
            et = nombre_etapa(g)
            g["etapa"] = et
            g["round"] = idx[et]
            # Fuera de la fase de grupos no hay zonas: en octavos se cruzan
            # equipos de grupos distintos y todos los partidos salían
            # marcados como "Interzonal", que acá no quiere decir nada.
            if norm(et) != grupos:
                g["zone"], g["interzonal"] = None, False

        # sólo en las eliminatorias: en los grupos los dos cruces son fechas
        # distintas, no una ida y una vuelta
        marcar_ida_vuelta([g for g in games if norm(g["etapa"]) != grupos])

    # Los torneos que no son copa pero se juegan por fases —el Federal A
    # tiene primera fase y reválida— repiten la numeración de fechas en cada
    # una. Mezcladas quedaba la fecha 3 de este año al lado de la fecha 3 de
    # la fase anterior. Se agrupan las fechas por fase para poder elegir
    # primero una y después la otra.
    fases_liga = []
    if not cfg.get("copa"):
        por_stage = {}
        for g in games:
            sn = g.get("stageNum")
            if sn is None:
                continue
            por_stage.setdefault(sn, {"nombres": {}, "rounds": set()})
            nom = (g.get("stage") or "").strip()
            if nom:
                por_stage[sn]["nombres"][nom] = por_stage[sn]["nombres"].get(nom, 0) + 1
            if g.get("round"):
                por_stage[sn]["rounds"].add(g["round"])
        if len(por_stage) > 1:
            for sn in sorted(por_stage):
                d = por_stage[sn]
                nombre = (max(d["nombres"], key=d["nombres"].get)
                          if d["nombres"] else "Fase %s" % sn)
                if d["rounds"]:
                    fases_liga.append({"num": sn, "nombre": nombre,
                                       "rounds": sorted(d["rounds"])})
            for g in games:
                g["fase"] = g.get("stageNum")

    rnd = (q.get("round") or [None])[0]
    rounds = sorted({g["round"] for g in games if g["round"]})

    por_fecha = {}
    for g in games:
        por_fecha.setdefault(g["round"], []).append(g)
    actual = fecha_actual(rounds, por_fecha)

    sin_zona = sorted({g[s]["name"] for g in games for s in ("home", "away")
                       if not g["zone"]})
    # el cuadro se arma antes de filtrar por etapa: necesita el torneo entero
    llaves = armar_llaves(games, etapas) if cfg.get("copa") else None

    if rnd:
        games = [g for g in games if str(g["round"]) == str(rnd)]
    res = {"games": games, "count": len(games), "rounds": rounds, "current": actual,
           "live": vivos, "interzonal": sum(1 for g in games if g["interzonal"]),
           "sinZona": sin_zona, "nombre": cfg["nombre"],
           "copa": bool(cfg.get("copa")), "etapas": etapas,
           "fasesLiga": fases_liga}
    if llaves is not None:
        res["llaves"] = llaves
    if err:
        res["error"] = err
    return res


# ─────────────────────────────────────────────────────────────────────────
# LaLiga: calendario completo desde laliga.com
# ─────────────────────────────────────────────────────────────────────────
#
# 365scores devuelve siempre la misma ventana de partidos, así que de LaLiga
# se veían tres jornadas y nada más. laliga.com publica cada jornada en su
# propia dirección —.../resultados/2026-27/jornada-N— y con cambiarle el
# número se recorre el torneo entero.
#
# De ahí sale el esqueleto: quién juega contra quién, qué día y a qué hora.
# Los goles y el minuto a minuto los sigue poniendo 365scores.

LALIGA_URL = ("https://www.laliga.com/es-GB/laliga-easports/resultados/"
              "%s/jornada-%d")
LALIGA_TEMPORADA = "2026-27"
LALIGA_JORNADAS = 38

# El nombre del club sale del enlace, no del texto: en la tabla aparece
# "R. Racing Club" o "Celta" y en las posiciones "Racing de Santander" y
# "Celta de Vigo". La dirección, en cambio, no cambia nunca.
LALIGA_CLUBES = {
    "d-alaves": "Alavés",
    "athletic-club": "Athletic Club",
    "atletico-de-madrid": "Atlético de Madrid",
    "rc-celta": "Celta de Vigo",
    "elche-c-f": "Elche CF",
    "fc-barcelona": "FC Barcelona",
    "getafe-cf": "Getafe CF",
    "levante-ud": "Levante UD",
    "malaga-cf": "Málaga CF",
    "c-a-osasuna": "Osasuna",
    "r-racing-club": "Racing de Santander",
    "rayo-vallecano": "Rayo Vallecano",
    "rc-deportivo": "RC Deportivo",
    "rcd-espanyol": "RCD Espanyol",
    "real-betis": "Real Betis",
    "real-madrid": "Real Madrid",
    "real-sociedad": "Real Sociedad",
    "sevilla-fc": "Sevilla FC",
    "valencia-cf": "Valencia CF",
    "villarreal-cf": "Villarreal CF",
}

_LL_CLUB = re.compile(r"/clubes/([a-z0-9\-]+)/", re.I)
_LL_FECHA = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_LL_HORA = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


class _LaLiga(HTMLParser):
    """
    Recorre la página de una jornada y va anotando, en orden, los enlaces a
    clubes y los textos que parecen fecha u hora. Cada par de clubes seguidos
    es un partido, con la última fecha y hora vistas.

    Se mira el enlace y no la clase CSS a propósito: laliga.com rehace su
    maquetación cada tanto, pero las direcciones de los clubes son estables.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partidos = []
        self._pend = []          # clubes esperando pareja
        self._fecha = self._hora = None
        self._buf = None

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        m = _LL_CLUB.search(href)
        if not m:
            return
        slug = m.group(1).lower()
        if slug not in LALIGA_CLUBES:
            return
        self._pend.append(slug)
        if len(self._pend) == 2:
            a, b = self._pend
            self._pend = []
            if a == b:                      # el mismo enlace repetido
                return
            self.partidos.append({"local": a, "visita": b,
                                  "fecha": self._fecha, "hora": self._hora})

    def handle_data(self, d):
        t = d.strip()
        if not t or len(t) > 40:
            return
        f = _LL_FECHA.search(t)
        if f:
            self._fecha = "%s-%s-%s" % (f.group(3), f.group(2), f.group(1))
            self._hora = None
            return
        h = _LL_HORA.match(t)
        if h:
            self._hora = "%02d:%02d" % (int(h.group(1)), int(h.group(2)))


def _laliga_jornada(n, ttl=21600):
    """Los partidos de una jornada. Se guarda 6 horas: el calendario no vuela."""
    url = LALIGA_URL % (LALIGA_TEMPORADA, n)

    def ir_a_la_fuente():
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept": "text/html",
                                    "Accept-Language": "es-ES,es;q=0.9"})
        with urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
        p = _LaLiga()
        p.feed(html)
        return p.partidos

    datos, info = almacen.con_respaldo("laliga:%s:%d" % (LALIGA_TEMPORADA, n),
                                       ir_a_la_fuente, max_edad=ttl,
                                       tag="laliga/jornada")
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["laliga"] = info
    return datos or []


def laliga_fixture(ttl=21600):
    """
    Las 38 jornadas juntas. Se piden de a varias en paralelo porque si no
    son 38 idas y vueltas de una en una y el primer visitante espera medio
    minuto.
    """
    url = "laliga:fixture:" + LALIGA_TEMPORADA
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < 600:
            return hit[1]

    from concurrent.futures import ThreadPoolExecutor

    def una(n):
        try:
            return n, _laliga_jornada(n, ttl)
        except Exception:
            return n, []

    crudo = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n, ps in pool.map(una, range(1, LALIGA_JORNADAS + 1)):
            crudo[n] = ps

    out, vistos = [], set()
    for n in sorted(crudo):
        for p in crudo[n]:
            # laliga.com repite la tabla para la versión de celular; si no se
            # filtra, cada partido aparece dos veces.
            if (n, p["local"], p["visita"]) in vistos:
                continue
            vistos.add((n, p["local"], p["visita"]))
            loc = LALIGA_CLUBES.get(p["local"], p["local"])
            vis = LALIGA_CLUBES.get(p["visita"], p["visita"])
            out.append({
                "id": "ll-%d-%s-%s" % (n, p["local"][:8], p["visita"][:8]),
                "round": n, "zone": None, "interzonal": False,
                "stage": "LaLiga %s" % LALIGA_TEMPORADA,
                "start": _laliga_dt(p["fecha"], p["hora"]),
                "status": "PROG", "statusText": "", "minute": None, "referee": "",
                "home": {"id": None, "canon": loc, "name": loc, "short": "",
                         "logo": None, "score": None, "site": None},
                "away": {"id": None, "canon": vis, "name": vis, "short": "",
                         "logo": None, "score": None, "site": None},
                "gh": None, "ga": None, "venue": "",
            })
    out.sort(key=lambda x: (x["round"] or 0, x["start"] or ""))
    with _lock:
        _cache[url] = (time.time(), out)
    return out


def _laliga_dt(fecha, hora):
    """
    '2026-08-20' + '19:00' -> ISO con huso de Madrid.

    Los horarios de laliga.com son de España; el sitio los muestra en la hora
    local de quien mira, así que hay que decir de dónde salen. En agosto rige
    el horario de verano (+02:00) y desde el último domingo de octubre, +01:00.
    """
    if not fecha:
        return None
    try:
        y, m, d = (int(x) for x in fecha.split("-"))
    except ValueError:
        return None
    hh, mi = 0, 0
    mm = re.search(r"(\d{1,2}):(\d{2})", hora or "")
    if mm:
        hh, mi = int(mm.group(1)), int(mm.group(2))
    dia = dt.date(y, m, d)
    # último domingo de marzo y de octubre
    def ultimo_domingo(anio, mes):
        d31 = dt.date(anio, mes, 31)
        return d31 - dt.timedelta(days=(d31.weekday() + 1) % 7)
    verano = ultimo_domingo(y, 3) <= dia < ultimo_domingo(y, 10)
    huso = "+02:00" if verano else "+01:00"
    return "%04d-%02d-%02dT%02d:%02d:00%s" % (y, m, d, hh, mi, huso)


def pegar_marcadores(base, extra):
    """
    Pone sobre el calendario los goles de otra fuente (365scores).

    El calendario dice quién juega y cuándo; los goles y el estado del
    partido vienen de afuera. Se emparejan por fecha del torneo y equipos.
    """
    if not extra:
        return base
    indice = {}
    for m in extra:
        k = (m.get("round"), norm(m["home"]["name"])[:8], norm(m["away"]["name"])[:8])
        indice[k] = m
    for m in base:
        e = indice.get((m.get("round"), norm(m["home"]["name"])[:8],
                        norm(m["away"]["name"])[:8]))
        if not e:
            # sin la fecha: puede que la fuente numere distinto
            e = next((x for x in extra
                      if norm(x["home"]["name"])[:8] == norm(m["home"]["name"])[:8]
                      and norm(x["away"]["name"])[:8] == norm(m["away"]["name"])[:8]
                      and (x["start"] or "")[:10] == (m["start"] or "")[:10]), None)
        if not e:
            continue
        m["liveId"] = e.get("id")
        m["venue"] = e.get("venue") or m["venue"]
        # El horario de 365scores manda: viene con huso y ya reprogramado.
        if e.get("start"):
            m["start"] = e["start"]
        if e.get("gh") is not None:
            m["gh"], m["ga"] = e["gh"], e["ga"]
            m["home"]["score"], m["away"]["score"] = e["gh"], e["ga"]
            m["status"] = e.get("status") or m["status"]
            m["statusText"] = e.get("statusText") or m["statusText"]
            m["minute"] = e.get("minute")
    return base


def df_fixture_generico(liga):
    """Igual que df_fixture pero sin mapear a nombres canónicos ni zonas."""
    cfg = LIGAS[liga]
    url = cfg["base"] + cfg["pages"].get("fixture", "fixture") + ".html"
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < 300:
            return hit[1]

    def ir_a_la_fuente():
        req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
        p = _Fixture()
        p.feed(html)
        return p.matches

    matches, info = almacen.con_respaldo("dffx:" + url, ir_a_la_fuente,
                                         max_edad=300, tag="afa/fixture/" + liga)
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["afa"] = info

    p = type("obj", (), {"matches": matches})()
    out = []
    for m in p.matches:
        campos = m["campos"]
        eq = [_limpio(v) for k, v in campos if k == "equipo"]
        goles = [v for k, v in campos if k == "badge"]
        if len(eq) < 2 or norm(eq[0]) == "a confirmar":
            continue
        arb = next((v for k, v in campos if k == "arbitro"), "")
        fch = next((v for k, v in campos if k == "mc-date"), "")
        hor = next((v for k, v in campos if k in ("mc-time", "hora")), "")
        est = next((v for k, v in campos if k == "estado"), "")
        gh = _int(goles[0], None) if len(goles) > 0 else None
        ga = _int(goles[1], None) if len(goles) > 1 else None
        jugado = norm(est) in _FINALIZADO or (gh is not None and ga is not None)
        out.append({
            "id": "%s-%s-%s-%s" % (liga, m["fecha"], norm(eq[0])[:6], norm(eq[1])[:6]),
            "round": m["fecha"], "zone": None, "interzonal": False,
            "stage": cfg["torneo"], "start": _parse_dt(fch, hor),
            "status": "FIN" if jugado else "PROG", "statusText": est, "minute": None,
            "referee": re.sub(r"^\s*Árbitro:\s*", "", arb).strip(),
            "home": {"id": None, "canon": eq[0], "name": eq[0], "short": "",
                     "logo": None, "score": gh, "site": None},
            "away": {"id": None, "canon": eq[1], "name": eq[1], "short": "",
                     "logo": None, "score": ga, "site": None},
            "gh": gh, "ga": ga, "venue": "",
        })
    out.sort(key=lambda x: (x["round"] or 0, x["start"] or ""))
    with _lock:
        _cache[url] = (time.time(), out)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Ficha de jugador
# ─────────────────────────────────────────────────────────────────────────
def _tm_link(nombre):
    """Búsqueda en Transfermarkt. No se scrapea el sitio: sólo se enlaza."""
    from urllib.parse import quote
    return ("https://www.transfermarkt.es/schnellsuche/ergebnis/schnellsuche"
            "?query=%s" % quote(nombre))


def api_player(q):
    """
    Ficha de un goleador. Los datos de AFA (goles por tipo) se enriquecen,
    si se puede, con el perfil de 365scores: posición, foto y club.
    """
    nombre = (q.get("name") or [""])[0].strip()
    lid = (q.get("liga") or ["lpf"])[0]
    if not nombre:
        return {"error": "falta el parámetro name"}

    ficha = {"name": nombre, "transfermarkt": _tm_link(nombre), "liga": lid,
             "team": (q.get("team") or [""])[0], "fuente": "AFA / DataFactory"}

    # goles por tipo, de la tabla oficial de la liga que corresponda
    filas = (api_scorers({}).get("rows", []) if lid == "lpf"
             else api_liga({"id": [lid]}).get("goleadores", []))
    for r in filas:
        if norm(r["name"]) == norm(nombre):
            ficha.update({"goals": r["goals"], "jugada": r["jugada"],
                          "cabeza": r["cabeza"], "tiroLibre": r["tiroLibre"],
                          "pens": r["pens"], "rank": r["rank"],
                          "team": r["team"]["name"], "logo": r["team"].get("logo"),
                          "site": r["team"].get("site")})
            break
    if lid != "lpf":
        return ficha        # el perfil de 365scores es sólo para Primera

    # perfil en 365scores (posición, foto). Si falla, la ficha igual sirve.
    atleta = _int((q.get("atleta") or [""])[0], None)
    try:
        data = fetch("stats", {"competitions": COMPETITION, "competitor": 0}, ttl=300)
        blocks = data.get("stats") or []
        goles = next((b for b in blocks if norm(b.get("name")) in ("goles", "goals")), None)
        for r in (goles or {}).get("rows", []):
            e = r.get("entity") or {}
            if norm(e.get("name")) == norm(nombre):
                ficha["posicion"] = e.get("positionName") or ""
                atleta = atleta or e.get("id")
                break
    except Exception:
        pass

    ficha.update(perfil_atleta(atleta))
    return ficha


def perfil_atleta(atleta_id):
    """
    Datos personales del jugador.

    365scores da edad, nacionalidad y puesto. Altura y peso no los publica
    en esta API, así que para eso queda el enlace a Transfermarkt.
    """
    if not atleta_id:
        return {}
    try:
        data = fetch("athletes", {"athletes": atleta_id}, ttl=60 * 60 * 24)
    except Exception:
        return {}
    a = (data.get("athletes") or [{}])[0]
    if not a:
        return {}
    salida = {
        "atletaId": a.get("id"),
        "edad": a.get("age"),
        "nacionalidad": a.get("nationalityName") or "",
        "posicion": puesto_ar((a.get("position") or {}).get("name")),
        "puesto": puesto_ar((a.get("formationPosition") or {}).get("name")),
    }
    if a.get("id"):
        salida["foto"] = ("https://imagecache.365scores.com/image/upload/"
                          "f_png,w_160,h_160,c_limit,q_auto:best,dpr_2/"
                          "v%s/Athletes/%s" % (a.get("imageVersion", 1), a["id"]))
    if a.get("nationalityId"):
        salida["bandera"] = ("https://imagecache.365scores.com/image/upload/"
                             "f_png,w_48,h_48,c_limit,q_auto:eco,dpr_2/"
                             "v1/Countries/Round/%s" % a["nationalityId"])
    return {k: v for k, v in salida.items() if v not in (None, "")}


# ─────────────────────────────────────────────────────────────────────────
# Datos físicos, desde Wikidata
#
# 365scores no publica altura ni peso. Transfermarkt sí, pero scrapearlo
# sería lo mismo que ya decidimos no hacer. Wikidata los tiene, su licencia
# es CC0 —uso libre, sin condiciones— y tiene una API pensada para esto.
# La cobertura no es total: para jugadores de ascenso muchas veces no hay
# ficha. Cuando falta, simplemente no se muestra.
# ─────────────────────────────────────────────────────────────────────────
# 365scores usa el castellano de España; acá se dice de otra manera.
PUESTOS = {
    "portero": "Arquero", "guardameta": "Arquero",
    "defensa central": "Defensor central", "defensa": "Defensor",
    "defensa lateral izquierdo": "Lateral izquierdo",
    "defensa lateral derecho": "Lateral derecho",
    "lateral izquierdo": "Lateral izquierdo", "lateral derecho": "Lateral derecho",
    "centrocampista": "Mediocampista",
    "centrocampista defensivo": "Volante central",
    "centrocampista ofensivo": "Enganche",
    "extremo izquierdo": "Extremo izquierdo", "extremo derecho": "Extremo derecho",
    "delantero centro": "Centrodelantero", "centro delantero": "Centrodelantero",
    "delantero": "Delantero", "mediapunta": "Enganche",
}


def puesto_ar(t):
    return PUESTOS.get(norm(t), t or "")


WD = "https://www.wikidata.org/w/api.php"


def _wd(params):
    from urllib.parse import urlencode
    url = WD + "?" + urlencode(dict(params, format="json"))
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fisico(nombre):
    """Altura, peso y fecha de nacimiento. {} si no se encuentra."""
    if not nombre:
        return {}
    clave = "wd:" + norm(nombre)

    def buscar():
        b = _wd({"action": "wbsearchentities", "search": nombre,
                 "language": "es", "type": "item", "limit": 5})
        # nos quedamos con el que la descripción indique que es futbolista
        cands = b.get("search") or []
        elegido = next((c for c in cands
                        if re.search(r"f[uú]tbol|football|soccer",
                                     (c.get("description") or ""), re.I)), None)
        if not elegido:
            return {}
        ident = elegido["id"]
        e = _wd({"action": "wbgetentities", "ids": ident,
                 "props": "claims", "languages": "es"})
        c = ((e.get("entities") or {}).get(ident) or {}).get("claims") or {}

        def valor(p):
            try:
                return c[p][0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError, TypeError):
                return None

        alt, pes, nac = valor("P2048"), valor("P2067"), valor("P569")
        salida = {"wikidata": ident}
        if isinstance(alt, dict):
            salida["altura"] = int(float(alt.get("amount", 0)))
        if isinstance(pes, dict):
            salida["peso"] = int(float(pes.get("amount", 0)))
        if isinstance(nac, dict) and nac.get("time"):
            salida["nacimiento"] = nac["time"].lstrip("+")[:10]
        return {k: v for k, v in salida.items() if v}

    try:
        datos, _ = almacen.con_respaldo(clave, buscar,
                                        max_edad=60 * 60 * 24 * 30, tag="wikidata")
        return datos or {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────
# Trayectoria propia
#
# Ni 365scores ni Wikidata publican la carrera completa de forma confiable.
# Pero nosotros ya vemos, partido a partido, en qué club juega cada uno. Así
# que lo vamos anotando: cada vez que aparece en una formación o entre los
# goleadores, queda registrado club + liga + temporada. Con el tiempo se
# arma una trayectoria real, la de lo que efectivamente pasó por acá.
# ─────────────────────────────────────────────────────────────────────────
def anotar_paso(nombre, club, liga, escudo=None):
    if not nombre or not club:
        return
    clave = "carrera:" + norm(nombre)
    hist, _ = almacen.leer(clave)
    hist = hist or []
    hoy = dt.date.today().isoformat()
    for h in hist:
        if norm(h["club"]) == norm(club) and h["liga"] == liga:
            h["hasta"] = hoy
            if escudo:
                h["escudo"] = escudo
            almacen.guardar(clave, hist)
            return
    hist.append({"club": club, "liga": liga, "escudo": escudo,
                 "desde": hoy, "hasta": hoy})
    almacen.guardar(clave, hist)


def carrera(nombre):
    hist, _ = almacen.leer("carrera:" + norm(nombre))
    return sorted(hist or [], key=lambda h: h.get("desde") or "", reverse=True)


def partidos_jugados(nombre, liga="lpf"):
    """
    Cuántos partidos del torneo actual jugó, contados sobre lo que ya vimos.

    Sale de las formaciones que fuimos guardando, así que arranca en cero y
    se completa a medida que se abren partidos. Es un piso, no un total
    oficial, y en la ficha se aclara.
    """
    clave = "pj:%s:%s" % (liga, norm(nombre))
    dato, _ = almacen.leer(clave)
    return (dato or {}).get("n", 0)


def anotar_partido(nombre, liga, game_id):
    if not nombre:
        return
    clave = "pj:%s:%s" % (liga, norm(nombre))
    dato, _ = almacen.leer(clave)
    dato = dato or {"n": 0, "ids": []}
    if str(game_id) in dato["ids"]:
        return
    dato["ids"] = (dato["ids"] + [str(game_id)])[-60:]
    dato["n"] = len(set(dato["ids"]))
    almacen.guardar(clave, dato)


def anotar_goles(liga, game_id, goles):
    """
    Guarda quién hizo los goles de un partido.

    Los torneos chicos y las copas no tienen tabla de goleadores publicada,
    pero los autores de cada gol ya los estamos leyendo para mostrarlos en la
    lista de partidos. Guardándolos, la tabla se arma sola.

    Se guarda por partido y no sumando de a uno: si el mismo partido se lee
    diez veces —pasa, se refresca cada veinte segundos— el último pisa al
    anterior y nadie termina con treinta goles.
    """
    if not game_id:
        return
    # ni los anulados ni los de la tanda de penales cuentan para la tabla.
    # Se guarda también de qué lado fue cada gol, para poder mostrarlos en la
    # lista de partidos sin volver a pedir el detalle.
    limpios = [{"j": g["player"], "e": g.get("equipo") or "", "m": g.get("min"),
                "s": g.get("side") or "h"}
               for g in goles
               if g.get("player") and not g.get("anulado") and not g.get("penales")]
    almacen.guardar("goles:%s:%s" % (liga, game_id), limpios)
    indice, _ = almacen.leer("golesidx:%s" % liga)
    indice = indice or []
    if str(game_id) not in indice:
        almacen.guardar("golesidx:%s" % liga, (indice + [str(game_id)])[-400:])


def goleadores_propios(liga, escudos=None):
    """La tabla de goleadores armada con los goles que fuimos guardando."""
    indice, _ = almacen.leer("golesidx:%s" % liga)
    if not indice:
        return []
    cuenta = {}
    for gid in indice:
        goles, _ = almacen.leer("goles:%s:%s" % (liga, gid))
        for g in (goles or []):
            k = norm(g["j"])
            if not k:
                continue
            r = cuenta.setdefault(k, {"name": g["j"], "equipo": g.get("e") or "",
                                      "goals": 0})
            r["goals"] += 1
            if g.get("e"):
                r["equipo"] = g["e"]

    filas = []
    for r in cuenta.values():
        eq = {"name": r["equipo"], "short": "", "logo": None, "site": None}
        if escudos:
            k = emparejar(r["equipo"], escudos)
            if k:
                eq = escudos[k]
        filas.append({"name": r["name"], "team": eq, "goals": r["goals"],
                      "pens": 0, "jugada": None, "cabeza": None,
                      "tiroLibre": None, "athleteId": None})
    filas.sort(key=lambda x: (-x["goals"], norm(x["name"])))
    for i, r in enumerate(filas, 1):
        r["rank"] = i
    return filas


def api_atleta(q):
    """Ficha de un jugador. /api/atleta?id=8167&name=...&liga=lpf"""
    aid = _int((q.get("id") or [""])[0], None)
    nombre = (q.get("name") or [""])[0].strip()
    lid = (q.get("liga") or ["lpf"])[0]
    if not aid and not nombre:
        return {"error": "falta el parámetro id o name"}

    p = perfil_atleta(aid) if aid else {}
    p["name"] = nombre or p.get("name") or ""
    p["transfermarkt"] = _tm_link(p["name"])

    # altura, peso y fecha de nacimiento
    p.update(fisico(p["name"]))
    if p.get("nacimiento") and not p.get("edad"):
        try:
            n = dt.date.fromisoformat(p["nacimiento"])
            hoy = dt.date.today()
            p["edad"] = hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))
        except ValueError:
            pass

    p["carrera"] = carrera(p["name"])
    p["pj"] = partidos_jugados(p["name"], lid)

    # goles en el torneo, si figura entre los goleadores
    try:
        filas = (api_scorers({}).get("rows", []) if lid == "lpf"
                 else api_liga({"id": [lid]}).get("goleadores", []))
        for r in filas:
            if norm(r["name"]) == norm(p["name"]):
                p.update({"goals": r["goals"], "jugada": r.get("jugada"),
                          "cabeza": r.get("cabeza"), "tiroLibre": r.get("tiroLibre"),
                          "pens": r.get("pens"), "rank": r.get("rank"),
                          "team": r["team"]["name"], "logo": r["team"].get("logo"),
                          "site": r["team"].get("site")})
                break
    except Exception:
        pass
    return {k: v for k, v in p.items() if v not in (None, "", [])}


# Qué torneos entran en la portada, y en qué orden aparecen. Cada bloque se
# muestra sólo si ese día hay partidos, así que las copas aparecen y
# desaparecen solas según la semana. Se agrega o saca sumando la clave acá.
HOME_LIGAS = ("lpf", "nacional", "ca", "lib", "sud", "laliga")


def api_home(q):
    """
    Portada: los partidos de un día, de las ligas de HOME_LIGAS.
    Uso: /api/home?date=YYYY-MM-DD (si no, hoy).
    """
    date = (q.get("date") or [dt.date.today().isoformat()])[0]
    bloques, vivos = [], 0

    def dia(games):
        return [g for g in games if (g["start"] or "")[:10] == date]

    try:
        ms = dia(all_games())
        if ms:
            for m in ms:
                m["liga"], m["ligaNombre"] = "lpf", LIGAS["lpf"]["nombre"]
            bloques.append({"liga": "lpf", "nombre": LIGAS["lpf"]["nombre"],
                            "torneo": LIGAS["lpf"]["torneo"], "games": ms})
            vivos += sum(1 for m in ms if m["status"] == "LIVE")
    except Exception:
        pass

    for lid in [k for k in HOME_LIGAS if k != "lpf" and k in LIGAS]:
        try:
            ms = dia(api_liga_games({"id": [lid]}).get("games", []))
            if not ms:
                continue
            for m in ms:
                m["liga"], m["ligaNombre"] = lid, LIGAS[lid]["nombre"]
            bloques.append({"liga": lid, "nombre": LIGAS[lid]["nombre"],
                            "torneo": LIGAS[lid]["torneo"], "games": ms})
            vivos += sum(1 for m in ms if m["status"] == "LIVE")
        except Exception:
            continue

    for b in bloques:
        b["games"].sort(key=lambda x: (x["start"] or ""))
    total = sum(len(b["games"]) for b in bloques)
    return {"date": date, "bloques": bloques, "total": total, "live": vivos,
            "partidazo": partidazo_del_dia(bloques)}


def partidazo_del_dia(bloques):
    """
    El partido más importante de la jornada, entre los de Primera.

    La regla es la de cualquier hincha: el que tiene al equipo mejor ubicado
    en la tabla. La excepción es la fecha de los interzonales, donde se juegan
    los clásicos: ese día el clásico es el partido, aunque los dos equipos
    vengan últimos.
    """
    lpf = next((b["games"] for b in bloques if b["liga"] == "lpf"), [])
    if not lpf:
        return None

    # posición de cada equipo: la anual ordena a los 30 en una sola lista
    puesto = {}
    try:
        for r in api_annual({"live": ["0"]}).get("rows", []):
            puesto[norm(r.get("canon") or r["team"]["name"])] = r.get("pos") or 99
    except Exception:
        pass
    if not puesto:
        try:
            for z in api_standings({"live": ["0"]}).get("zones", []):
                for r in z["rows"]:
                    puesto[norm(r.get("canon") or r["team"]["name"])] = r.get("pos") or 99
        except Exception:
            return lpf[0]["id"]

    def mejor_puesto(m):
        return min(puesto.get(norm(m[s].get("canon") or m[s]["name"]), 99)
                   for s in ("home", "away"))

    clasicos = [m for m in lpf if m.get("interzonal")]
    elegibles = clasicos or lpf
    return min(elegibles, key=mejor_puesto)["id"]


# Emblemas: sólo de las ligas que efectivamente andan. Las que están en
# "pronto" van sin escudo: poner uno estimado quedaba mal y confundía.
EMBLEMAS = {"lpf": 72, "nacional": 419, "pbm": 5077, "fa": 5078,
            "fem": 6224, "laliga": 11,
            "lib": 102, "sud": 389, "ca": 640}


def api_ligas(q):
    """Ligas del menú, con su emblema."""
    # la versión de imagen viene en cualquier respuesta de partidos
    versiones = {}
    for lid, cfg in LIGAS.items():
        try:
            data = fetch("games/results", {"competitions": cfg["sc"]}, ttl=1800)
            for c in (data.get("competitions") or []):
                versiones[c.get("id")] = c.get("imageVersion", 1)
        except Exception:
            pass
    out = []
    for lid, comp in EMBLEMAS.items():
        cfg = LIGAS.get(lid)
        out.append({"id": lid, "sc": comp,
                    "nombre": cfg["nombre"] if cfg else None,
                    "torneo": cfg["torneo"] if cfg else None,
                    "activa": bool(cfg),
                    "emblema": emblema(comp, versiones.get(comp, 1))})
    return {"ligas": out}


def api_competencias(q):
    """
    Busca torneos en 365scores y devuelve el número con el que los identifica.

    Existe para no adivinar: cada torneo tiene un id y ponerle el equivocado
    a una liga hace que la página muestre otra cosa sin avisar, que es peor
    que no tenerla. Se entra una vez, se anota el número y se configura.

    Uso: /api/competencias           → busca las copas que faltan
         /api/competencias?q=copa%20del%20rey
    """
    terminos = [t for t in (q.get("q") or
                            ["libertadores", "sudamericana", "copa argentina"])
                if t.strip()]

    try:
        data = fetch("competitions", {"sports": 1}, ttl=3600)
    except Exception as e:
        return {"error": "no se pudo consultar 365scores: %s" % e,
                "sugerencia": "reintentar en un rato: suele ser pasajero"}

    comps = data.get("competitions") or []
    if not comps:
        # por si cambia el nombre del campo: se busca la lista más larga
        listas = [v for v in data.values() if isinstance(v, list) and v]
        comps = max(listas, key=len) if listas else []

    paises = {c.get("id"): c.get("name") for c in (data.get("countries") or [])}

    salida = {}
    for t in terminos:
        tn = norm(t)
        encontrados = []
        for c in comps:
            nombre = c.get("name") or ""
            if tn in norm(nombre):
                encontrados.append({
                    "id": c.get("id"),
                    "nombre": nombre,
                    "pais": paises.get(c.get("countryId")) or c.get("countryId"),
                    "temporada": c.get("currentSeasonNum"),
                    "fase": c.get("currentStageNum"),
                })
        encontrados.sort(key=lambda x: (len(x["nombre"]), str(x["id"])))
        salida[t] = encontrados

    return {"buscado": terminos, "resultados": salida,
            "torneosLeidos": len(comps),
            "comoUsarlo": ("Pasale a Claudia el número (id) de cada torneo y "
                           "los agrega al menú.")}


def api_club(q):
    """
    El partido anterior y el siguiente de un club, para el modo club.
    Uso: /api/club?name=Racing
    """
    nombre = (q.get("name") or [""])[0].strip()
    if not nombre:
        return {"error": "falta el parámetro name"}
    canon = match_team(nombre) or nombre

    # Todas las competencias, no sólo la liga: si el club juega la Copa
    # Argentina el miércoles y la liga el domingo, el próximo partido es el
    # del miércoles. Antes sólo se miraba la Liga Profesional.
    suyos, err = [], None
    for lid in LIGAS:
        try:
            juegos = (all_games(ttl=120) if lid == "lpf"
                      else api_liga_games({"id": [lid]}).get("games", []))
        except Exception as e:
            err = str(e)
            continue
        for m in juegos:
            lados = (m["home"].get("canon"), m["away"].get("canon"),
                     m["home"].get("name"), m["away"].get("name"))
            if canon in lados or emparejar(canon, {norm(x): 1 for x in lados if x}):
                suyos.append(dict(m, liga=lid, ligaNombre=LIGAS[lid]["nombre"]))

    if not suyos and err:
        return {"error": err, "club": canon}

    # el mismo partido puede venir de dos lados: se deja uno solo
    vistos, unicos = set(), []
    for m in sorted(suyos, key=lambda x: x.get("start") or ""):
        k = (str(m.get("liveId") or m.get("id")))
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append(m)
    suyos = unicos

    ahora = dt.datetime.now(dt.timezone.utc)

    def ya_paso(m):
        if not m["start"]:
            return False
        try:
            return dt.datetime.fromisoformat(m["start"]) < ahora
        except ValueError:
            return False

    envivo = next((m for m in suyos if m["status"] == "LIVE"), None)
    # el último jugado: el más reciente que ya terminó
    ultimo = next((m for m in reversed(suyos) if m["status"] == "FIN"), None)
    # el próximo: el primero que todavía no empezó
    proximo = next((m for m in suyos
                    if m["status"] not in ("FIN", "LIVE") and not ya_paso(m)), None)

    return {"club": canon, "envivo": envivo, "ultimo": ultimo,
            "proximo": proximo, "total": len(suyos)}


def api_clubes(q):
    """Clubes de Primera con sus colores, para el modo club."""
    logos = {}
    try:
        logos = _logos()
    except Exception:
        pass
    return {"clubes": sorted(
        [{"name": n, "primary": c[0], "accent": c[1],
          "logo": (logos.get(n) or {}).get("logo")}
         for n, c in COLORES.items()],
        key=lambda x: norm(x["name"]))}


def api_diagnostico(q):
    """
    Revisión general: la clave, el plan, la base y el estado de las fuentes.
    La clave nunca aparece en la respuesta, sólo si funciona o no.
    """
    ligas = [("Liga Profesional", 128, 2026), ("Primera Nacional", 129, 2026)]
    try:
        af = apifootball.diagnostico(APIFOOTBALL_KEY, ligas)
    except Exception as e:
        af = {"error": str(e), "clave_configurada": bool(APIFOOTBALL_KEY)}

    fuentes = {}
    for nombre, prueba in (("afa", lambda: len(df_tables("zonas", ttl=300))),
                           ("365scores", lambda: len(all_games(ttl=300)))):
        try:
            fuentes[nombre] = {"ok": True, "items": prueba()}
        except Exception as e:
            fuentes[nombre] = {"ok": False, "error": str(e)}
        if nombre in ULTIMO_PROBLEMA:
            fuentes[nombre]["ultimo_problema"] = ULTIMO_PROBLEMA[nombre]

    return {"apifootball": af, "base": almacen.estado(), "fuentes": fuentes,
            "consejo": ("Si alguna liga dice ok=false con 0 partidos, el plan "
                        "gratis no cubre esa temporada. Mientras tanto la página "
                        "sigue andando con AFA y 365scores.")}


ROUTES = {
    "/api/detalles": api_detalles,
    "/api/atleta": api_atleta,
    "/api/diagnostico": api_diagnostico,
    "/api/base": lambda q: almacen.estado(),
    "/api/home": api_home,
    "/api/clubes": api_clubes,
    "/api/club": api_club,
    "/api/competencias": api_competencias,
    "/api/historico": api_historico,
    "/api/liga": api_liga,
    "/api/liga/games": api_liga_games,
    "/api/player": api_player,
    "/api/ligas": lambda q: api_ligas(q),
    "/api/games": api_games,
    "/api/rounds": api_rounds,
    "/api/standings": api_standings,
    "/api/annual": api_annual,
    "/api/promedios": api_promedios,
    "/api/scorers": api_scorers,
    "/api/match": api_match,
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _acepta_gzip(self):
        return "gzip" in (self.headers.get("Accept-Encoding") or "").lower()

    def _comprimir(self, body):
        """
        Devuelve (cuerpo, encoding). Comprime sólo si al navegador le sirve y
        si el ahorro vale la pena: para respuestas chicas, el trabajo de
        comprimir y descomprimir cuesta más que los bytes que se ahorran.
        """
        if len(body) < 1024 or not self._acepta_gzip():
            return body, None
        return gzip.compress(body, 6), "gzip"

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        body, enc = self._comprimir(body)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _archivo(self, ruta, ctype):
        """
        Sirve un archivo del proyecto comprimido. La página pesa 104 KB y
        gzipeada baja a 31: es la diferencia más barata de conseguir.
        """
        try:
            with open(ruta, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        body, enc = self._comprimir(body)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        # se revalida siempre: si sube una versión nueva, se ve al recargar
        self.send_header("Cache-Control", "no-cache")
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        q = parse_qs(parsed.query)

        # escudos servidos desde acá: /img/competidor/<version>/<id>
        if path.startswith("/img/"):
            partes = path.strip("/").split("/")
            if len(partes) != 4:
                self.send_error(404)
                return
            _, tipo, ver, ident = partes
            if not re.fullmatch(r"\d+", ver) or not re.fullmatch(r"\d+", ident):
                self.send_error(400)
                return
            try:
                datos, ctype = traer_imagen(tipo, ver, ident)
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "public, max-age=604800")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
            return

        # passthrough crudo para inspeccionar la API: /api/raw?path=games/results
        if path == "/api/raw":
            ep = (q.get("path") or ["games/results"])[0]
            extra = {k: v[0] for k, v in q.items() if k != "path"}
            try:
                return self._json(fetch(ep, dict({"competitions": COMPETITION}, **extra), ttl=10))
            except Exception as e:
                return self._json({"error": str(e)}, 502)

        fn = ROUTES.get(path)
        if fn:
            try:
                return self._json(fn(q))
            except (HTTPError, URLError) as e:
                return self._json({"error": "no se pudo llegar a 365scores: %s" % e}, 502)
            except Exception as e:
                return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 500)

        # la página, comprimida
        if path in ("/", "/index.html"):
            return self._archivo(os.path.join(HERE, "index.html"),
                                 "text/html; charset=utf-8")
        return super().do_GET()


def precalentar():
    """
    Llena el caché antes de que llegue el primer visitante.

    Sin esto, el que entra justo después de un deploy paga la espera de ir a
    buscar todo a AFA y a 365scores. Corre en segundo plano, así que el
    servidor ya está atendiendo mientras tanto, y si alguna fuente falla no
    pasa nada: se resuelve sola cuando alguien la pida.
    """
    tareas = [
        ("partidos de Primera", lambda: all_games(ttl=0)),
        ("tabla de zonas", lambda: api_standings({"live": ["0"]})),
        ("tabla anual", lambda: api_annual({"live": ["0"]})),
        ("promedios", lambda: api_promedios({"live": ["0"]})),
        ("goleadores", lambda: api_scorers({})),
        ("Primera Nacional", lambda: api_liga_games({"id": ["nacional"]})),
        ("LaLiga", lambda: api_liga_games({"id": ["laliga"]})),
        # las copas también: ahora salen en la portada y el primero que entra
        # no tiene por qué esperarlas
        ("Copa Argentina", lambda: api_liga_games({"id": ["ca"]})),
        ("Libertadores", lambda: api_liga_games({"id": ["lib"]})),
        ("Sudamericana", lambda: api_liga_games({"id": ["sud"]})),
    ]
    for nombre, tarea in tareas:
        arranque = time.time()
        try:
            tarea()
            print("  · %-22s listo en %.1fs" % (nombre, time.time() - arranque), flush=True)
        except Exception as e:
            print("  · %-22s falló (%s), se reintenta al pedirlo"
                  % (nombre, type(e).__name__), flush=True)
    print("  Caché precalentado\n", flush=True)


def juntar_goles(lid, limite=25):
    """
    Busca los autores de los goles de los partidos viejos.

    El rescate histórico trae los partidos con el resultado, pero no con
    quién los hizo: eso está en el detalle de cada uno. Se piden de a poco,
    los que ya terminaron y todavía no tenemos, para no castigar a la fuente.
    """
    cfg = LIGAS.get(lid)
    if not cfg:
        return 0
    try:
        juegos = (all_games(ttl=600) if lid == "lpf"
                  else api_liga_games({"id": [lid]}).get("games", []))
    except Exception:
        return 0

    # Ojo con la clave: los goles se guardan con el id de 365scores, que es
    # el mismo que se usa para pedir el detalle. En la Liga Profesional y en
    # las categorías de AFA el id del partido es otro —viene del fixture
    # oficial— y preguntando por ése nunca encontrábamos nada guardado: se
    # volvían a pedir los mismos partidos una y otra vez, para siempre.
    faltan = []
    for g in juegos:
        if g.get("status") != "FIN" or not g.get("liveId"):
            continue
        guardado, _ = almacen.leer("goles:%s:%s" % (lid, g["liveId"]))
        if guardado is None:
            faltan.append(g)

    hechos = 0
    for g in faltan[:limite]:
        try:
            detalle_liviano(g["liveId"], en_juego=False, liga=lid)
            hechos += 1
        except Exception:
            continue
    return hechos


def rescatar_todo():
    """
    Va llenando la base en segundo plano, sin que nadie tenga que pedirlo.

    Primero recupera los partidos que 365scores ya no muestra —fases de
    grupos jugadas hace meses, rondas viejas de la Copa Argentina— y después
    busca los goleadores de esos partidos. Cada vuelta guarda dónde quedó,
    así que si el servidor se reinicia sigue desde ahí y no vuelve a empezar.
    """
    time.sleep(20)          # que la página arranque tranquila primero
    for vuelta in range(1, 13):
        pendientes, goles_pendientes = 0, 0
        for lid, cfg in LIGAS.items():
            try:
                r = rescatar_historico(cfg["sc"], paginas=20)
                if not r.get("listo"):
                    pendientes += 1
                if r.get("nuevos"):
                    print("  · %-18s +%d partidos viejos (total %d)"
                          % (cfg["nombre"], r["nuevos"], r.get("total", 0)), flush=True)
            except Exception:
                pass
            time.sleep(2)
        for lid in LIGAS:
            try:
                n = juntar_goles(lid, limite=20)
                if n:
                    goles_pendientes += 1
                    print("  · %-18s goles de %d partidos" % (LIGAS[lid]["nombre"], n), flush=True)
            except Exception:
                pass
            time.sleep(2)
        # se corta cuando no queda historia por traer ni goles por buscar
        if not pendientes and not goles_pendientes:
            print("  Historia completa: no queda nada por traer\n", flush=True)
            return
        time.sleep(60)
    print("  Pausa del rescate: sigue en el próximo arranque\n", flush=True)


def main():
    # Python guarda lo que se imprime en un buffer cuando la salida no es una
    # terminal, y en un servidor eso significa que los mensajes no aparecen
    # nunca —o aparecen media hora después, todos juntos—. Pidiendo que
    # escriba línea por línea, el log del hosting va contando lo que pasa en
    # el momento en que pasa.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    # En local escucha sólo en 127.0.0.1. En un hosting (Render y compañía)
    # hay que escuchar en 0.0.0.0 y tomar el puerto de la variable PORT.
    env_port = os.environ.get("PORT")
    if env_port:
        host, port = "0.0.0.0", int(env_port)
    else:
        host = "127.0.0.1"
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010

    srv = ThreadingHTTPServer((host, port), Handler)
    print("\n  HAYVAR — Fútbol Argentino")
    print("  " + "-" * 40)
    print("  Escuchando en %s:%d" % (host, port))
    if host == "127.0.0.1":
        print("  Abrí:  http://localhost:%d" % port)
    print("  Datos: AFA + 365scores")
    print("  Cortar con Ctrl+C\n")
    threading.Thread(target=precalentar, daemon=True).start()
    threading.Thread(target=rescatar_todo, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Listo, servidor detenido.\n")


if __name__ == "__main__":
    main()
