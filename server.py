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

import base64
import datetime as dt
import gzip
import hmac
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
import visitas
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


# ── Las puertas de servicio ──────────────────────────────────────────────
#
# Hay rutas que no son para los visitantes. Una de ellas, /api/recorrido
# con reconstruir=todo, borra los partidos de los dieciséis torneos y los
# vuelve a bajar de cero: meses de datos. Y encima se autodocumenta, así
# que cualquiera que la abriera de curioso leía en la respuesta cómo
# hacerlo. Otra, /api/raw, es un pasamanos a 365scores usando este
# servidor: si alguien la golpea, el que queda bloqueado sos vos.
#
# Ahora piden una llave. Vive en la variable HAYVAR_LLAVE del hosting o en
# un archivo llave.txt al lado del código; nunca adentro del código, igual
# que la clave de API-Football.
#
# Dos decisiones que valen la pena explicar:
#
#   · En la compu de uno quedan abiertas. Ahí no hay a quién esconderle
#     nada, y tener que pegar una llave para mirar /api/tiempos mientras
#     uno trabaja es la clase de fricción que termina en "lo dejo abierto".
#     Se distingue por el puerto: los hostings lo pasan en PORT, la compu
#     de uno no.
#
#   · Si no hay llave puesta y estamos publicados, quedan CERRADAS, no
#     abiertas. Olvidarse de configurarla tiene que romper algo tuyo, no
#     dejar la puerta abierta sin que nadie se entere.
def _leer_llave():
    k = os.environ.get("HAYVAR_LLAVE", "").strip()
    if k:
        return k
    try:
        with open(os.path.join(HERE, "llave.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


LLAVE = _leer_llave()
EN_CASA = not os.environ.get("PORT")

# Lo que borra, lo que gasta plata o cupo, y lo que cuenta cómo estamos
# hechos por dentro.
PRIVADAS = {
    "/api/recorrido",     # borra y vuelve a bajar torneos enteros
    "/api/raw",           # pasamanos a 365scores con nuestro servidor
    "/api/contenido",     # qué hay adentro de la base
    "/api/diagnostico",   # estado de la clave y del plan
    "/api/tiempos",       # cuánto tarda cada cosa y cuánto tráfico hay
    "/api/base",          # dónde vive la base, cuánto pesa y cuánto tiene
    "/api/visitas",       # quién entró, de dónde y qué miró
    "/admin",             # la página que junta todo lo de arriba
}
# Ojo: /api/visita —sin la ese— NO va acá. Es la que usa la página para
# avisar el tamaño de la pantalla y que la persona sigue leyendo, así que
# tiene que estar abierta. La que muestra los datos juntados es /api/visitas.


def con_llave(q, headers=None):
    """¿Este pedido tiene permiso para las puertas de servicio?"""
    if EN_CASA:
        return True
    if not LLAVE:
        return False
    dada = (q.get("llave") or [""])[0]
    if not dada and headers is not None:
        dada = headers.get("X-Llave") or ""
    # comparación de tiempo constante: comparar con == deja medir, por lo
    # que tarda en fallar, cuántos caracteres del principio acertaste
    return hmac.compare_digest(dada.strip(), LLAVE)

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

# La tienda online oficial, que casi nunca vive en el sitio del club sino en
# un dominio aparte: Boca vende en bocashop, River en tiendariver, Racing en
# locademia. Por eso no alcanza con enlazar el sitio y hay que tenerlas.
#
# Van sólo las del propio club. Las de Mercado Libre, las cadenas
# deportivas y las de la marca que los viste quedan afuera: no son la
# tienda del club aunque vendan su camiseta.
#
# Los que faltan no tienen tienda online propia —venden por Instagram o en
# el local— y para ésos la ficha no muestra la tarjeta. Es preferible eso a
# mandar a alguien a un link que no es.
TIENDAS = {
    "Aldosivi": "https://www.tiendatiburon.com.ar/",
    "Argentinos Juniors": "https://bichostore.com.ar/",
    "Banfield": "https://shopclubabanfield.mitiendanube.com/",
    "Belgrano": "https://www.republicadealberdi.com.ar/",
    "Boca Juniors": "https://www.bocashop.com.ar/",
    "Defensa y Justicia": "https://dyj.tienda.accessfan.ar/",
    "Estudiantes (LP)": "https://tiendapincha.com/",
    "Gimnasia y Esgrima (LP)": "https://www.loboshop.com.ar/",
    "Gimnasia y Esgrima (M)": "https://www.tiendapituca.com.ar/",
    "Huracán": "https://tienda.cahuracan.com/",
    "Independiente": "https://www.independientestore.com.ar/",
    "Independiente Rivadavia": "https://tiendaazul.com.ar/",
    "Instituto": "https://www.tiendainstituto.com.ar/",
    "Lanús": "https://tiendagranate.clublanus.com/",
    "Newell's Old Boys": "https://tiendanewells.com/",
    "Platense": "https://platensemania.com.ar/",
    "Racing": "https://locademia.racingclub.com.ar/",
    "River Plate": "https://www.tiendariver.com/",
    "Rosario Central": "https://centraltienda.com.ar/",
    "San Lorenzo": "https://www.soycuervo.com/",
    "Talleres (C)": "https://tienda.clubtalleres.com.ar/",
    "Tigre": "https://www.tiendatigre.com.ar/",
    "Unión": "https://www.tiendaunion.com.ar/",
    "Vélez Sarsfield": "https://tiendavelez.com.ar/",
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

# El caché en memoria se mide en bytes, no en cantidad de respuestas.
#
# Contar entradas era contar peras: la tabla de posiciones ocupa dos kilos
# y una página del fixture de una copa entera puede ocupar cinco megas, y
# con trescientas entradas permitidas el proceso se comía toda la memoria
# de Render y lo mataban. Peor todavía: un JSON convertido a objetos de
# Python pesa varias veces lo que ocupa como texto, así que el tope real
# era mucho más alto de lo que parecía.
#
# Ahora hay dos límites. Uno por respuesta: lo que pase de trescientos
# kilos no entra —son justamente las páginas del recorrido, que se piden
# una vez y no se vuelven a mirar—. Y uno total, para el resto. Nada de
# esto se pierde: la base en disco sigue teniendo todo, esto es sólo el
# atajo para no volver a leer y parsear.
_CACHE_MAX_BYTES = 8 * 1024 * 1024
_CACHE_MAX_UNO = 300 * 1024
_cache_bytes = 0


def _guardar_en_cache(url, valor, cuanto=None):
    """
    Guarda en el caché de memoria mientras entre en el presupuesto.

    `cuanto` es cuánto ocupa el valor como texto. Es opcional a propósito:
    quien ya lo sabe —el que acaba de leerlo de la base— lo pasa y se
    ahorra la cuenta, y el que no, lo deja y se mide acá. Cuando esto era
    obligatorio, las cuatro llamadas de AFA quedaron rotas y la página
    mostró el error en el cartel de arriba durante horas.
    """
    global _cache_bytes
    if cuanto is None:
        try:
            cuanto = len(json.dumps(valor, ensure_ascii=False))
        except Exception:
            return
    if cuanto > _CACHE_MAX_UNO:
        return
    with _lock:
        viejo = _cache.pop(url, None)
        if viejo:
            _cache_bytes -= viejo[2]
        _cache[url] = (time.time(), valor, cuanto)
        _cache_bytes += cuanto
        if _cache_bytes > _CACHE_MAX_BYTES:
            # se saca lo más viejo hasta volver a entrar, no la mitad de
            # una: con tamaños tan dispares, sacar la mitad podía liberar
            # casi nada o tirar todo lo útil
            for k, v in sorted(_cache.items(), key=lambda kv: kv[1][0]):
                if _cache_bytes <= _CACHE_MAX_BYTES * 0.8:
                    break
                _cache.pop(k, None)
                _cache_bytes -= v[2]


def fetch(path, params, ttl=15, guardar=True):
    """
    Pedido a 365scores, con dos niveles de caché.

    En memoria para el segundo a segundo, y en la base para todo lo demás.
    La base es la que hace la diferencia: sobrevive a los reinicios y, si la
    fuente se cae, devuelve lo último bueno en vez de dejar la página vacía.

    Con `guardar=False` sólo se usa la memoria. Es para los pedidos de un
    solo uso: el buscador de goles recorre todos los partidos de todos los
    calendarios, y de cada uno saca lo que le sirve —los goles, quiénes
    jugaron— y lo guarda aparte. La respuesta cruda que queda son sesenta
    kilobytes por partido que nadie vuelve a leer nunca: eran 2.638
    entradas y 161 MB, el 84% de la base, para nada. Lo que hace la fuente
    de respaldo tampoco se pierde ahí, porque si el pedido falla el
    recolector lo reintenta en la vuelta siguiente.
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

    if guardar:
        data, info = almacen.con_respaldo("sc:" + url, ir_a_la_fuente,
                                          max_edad=ttl, tag=path)
    else:
        data, info = ir_a_la_fuente(), {"origen": "fuente", "edad": 0,
                                        "tag": path, "bytes": 0}
    if info.get("origen") == "cache-vieja":
        ULTIMO_PROBLEMA["365scores"] = info

    _guardar_en_cache(url, data, info.get("bytes") or 0)
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
        # La Primera Fase terminó y 365scores ya no publica sus posiciones:
        # pedírselas devuelve las de la Segunda. Como los partidos sí los
        # tenemos guardados, esa tabla la calculamos nosotros.
        "fases_calculadas": ["Primera Fase"],
        # Los partidos vienen sin nombre de fase y las dos numeran las
        # fechas desde el uno, así que se separan por el calendario.
        "fases_por_calendario": ["Primera Fase", "Segunda Fase"],
        # La Fase Campeonato y la Reválida se juegan a la vez, así que van
        # en una sola pestaña con las cuatro zonas adentro. 365scores las
        # manda como dos fases distintas y quedaban separadas.
        "fases_juntas": {"titulo": "Segunda Fase",
                         "cuales": ["Segunda Fase", "Campeonato", "Reválida"]},
        # Reglamento 2026 (AFA):
        #   · Primera Fase: a la Segunda pasan del 1° al 5° en las zonas de
        #     diez y del 1° al 4° en las de nueve, más el mejor 5° de esas
        #     tres. Los demás van a la Reválida.
        #   · Segunda Fase: del 1° al 4° a la Tercera Fase; el 5° a la
        #     segunda etapa de la Reválida y además a la Copa Argentina;
        #     del 6° al 9°, a la segunda etapa de la Reválida.
        #   · Reválida: los cinco primeros pasan a la segunda etapa.
        #   · Descensos: no salen de estas tablas sino de una general que
        #     suma la Primera Fase con la Reválida. Va aparte, más abajo.
        #
        # El orden importa: gana la primera que coincida. La Reválida va
        # antes que la Segunda Fase porque sus zonas se llaman "Segunda
        # Fase - Reválida A" y si no caerían en la regla de la otra, que
        # las daría por candidatas a la Tercera Fase.
        "zonas_de": [
            {"cuando": "Descenso", "reglas": {"desciende": (-2, -1)}},
            {"cuando": "Reválida", "reglas": {"revalida2": (1, 5)}},
            {"cuando": "Primera Fase", "reglas": {
                "campeonato": lambda n: (1, 5 if n >= 10 else 4),
                "revalida": lambda n: (6 if n >= 10 else 5, n)}},
            {"cuando": "Segunda Fase", "reglas": {
                "tercera": (1, 4), "copaarg": (5, 5), "revalida2": (6, -1)}},
            {"cuando": "Campeonato", "reglas": {
                "tercera": (1, 4), "copaarg": (5, 5), "revalida2": (6, -1)}},
        ],
        # El quinto de las zonas de nueve que mejor terminó también pasa.
        # Es lo único que no se puede decidir mirando una tabla sola.
        "mejor_puesto": {"cuando": "Primera Fase", "de_zonas_de": 9,
                         "puesto": 5, "destino": "campeonato"},
        # Los descensos salen de una tabla general que no publica nadie:
        # los puntos de la Primera Fase más los de la Reválida. La Zona A
        # la promedia por partidos jugados y la Zona B los suma derecho.
        "descenso": {"de": "Reválida", "sumar": "Primera Fase",
                     "promedio": ["A"]},
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
    # ── Europa ───────────────────────────────────────────────────────────
    # Los números salen de /api/competencias: ojo que hay una Bundesliga de
    # Austria y varias "Serie A" en otros países.
    "premier": {
        "nombre": "Premier League", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 7, "pais": "Inglaterra",
        "anual": False,
        # 4 a Champions, 5° a Europa League, 6° a Conference, 3 descienden
        "zonas_de": {"champions": (1, 4), "europa": (5, 5),
                     "conference": (6, 6), "desciende": (-3, -1)},
    },
    "seriea": {
        "nombre": "Serie A", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 17, "pais": "Italia",
        "anual": False,
        "zonas_de": {"champions": (1, 4), "europa": (5, 5),
                     "conference": (6, 6), "desciende": (-3, -1)},
    },
    "bundesliga": {
        # 18 equipos: los dos últimos bajan y el 16° juega la promoción
        "nombre": "Bundesliga", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 25, "pais": "Alemania",
        "anual": False,
        "zonas_de": {"champions": (1, 4), "europa": (5, 5),
                     "conference": (6, 6), "repechaje": (-3, -3),
                     "desciende": (-2, -1)},
    },
    "champions": {
        # Formato nuevo, desde 2024: se terminaron los ocho grupos de cuatro.
        # Ahora son 36 equipos en UNA sola tabla, ocho partidos cada uno
        # contra rivales distintos. Del 1° al 8° pasan derecho a octavos,
        # del 9° al 24° juegan un playoff a ida y vuelta por los ocho
        # lugares que faltan, y del 25° para abajo quedan afuera.
        "nombre": "Champions League", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 572,
        "pais": "Europa", "anual": False, "copa": True,
        # Se cruzan clubes de países distintos: al lado de cada
        # escudo va la bandera de dónde es el club.
        "internacional": True,
        "zonas_de": {"avanza": (1, 8), "repechaje": (9, 24),
                     "afuera": (25, 36)},
        # La fase de liga va en la lista aunque todavía no tenga partidos: se
        # sortea en agosto y hasta entonces la etapa no existe para la
        # fuente, pero es la que uno quiere mirar mientras se juega la
        # clasificación —ahí se ve quién se va metiendo—.
        "etapas_extra": ["Fase de liga", "Octavos de final", "Cuartos de final",
                         "Semifinal", "Final"],
        # La clasificación previa no está adentro del torneo: 365scores la
        # publica como una competencia aparte, la 332. Sin esto la Champions
        # arrancaba en la fase de liga y las eliminatorias de julio y agosto
        # —52 equipos entre la Vía Campeones y la Vía Liga, todas a ida y
        # vuelta— no aparecían por ningún lado.
        "sc_extra": [332],
        "final": {"cuando": "2027-06-05", "sede": "Estadio Metropolitano",
                  "ciudad": "Madrid, España",
                  "nota": "A partido único, en cancha neutral."},
    },
    "europa": {
        # Mismo formato nuevo que la Champions y con el mismo reparto:
        # 36 equipos en una tabla, ocho partidos cada uno, del 1° al 8° a
        # octavos, del 9° al 24° al playoff y del 25° para abajo afuera.
        # Desde 2024 el que queda eliminado ya no baja a la Conference:
        # se termina ahí.
        "nombre": "Europa League", "torneo": "Temporada 2026-27",
        "base": None, "pages": {}, "propia": False, "sc": 573,
        "pais": "Europa", "anual": False, "copa": True,
        # Se cruzan clubes de países distintos: al lado de cada
        # escudo va la bandera de dónde es el club.
        "internacional": True,
        "zonas_de": {"avanza": (1, 8), "repechaje": (9, 24),
                     "afuera": (25, 36)},
        "etapas_extra": ["Fase de liga", "Octavos de final", "Cuartos de final",
                         "Semifinal", "Final"],
        "sc_extra": [596],       # la clasificación, igual que la Champions
        "final": {"cuando": "2027-05-26", "sede": "Stadion Frankfurt",
                  "ciudad": "Fráncfort, Alemania",
                  "nota": "A partido único, en cancha neutral."},
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
        "internacional": True,
        # Fase de grupos: pasan los dos primeros de cada zona a octavos, y
        # el tercero no queda afuera del todo: se va a los pre octavos de la
        # Sudamericana, contra los que salieron segundos allá.
        "zonas_de": {"avanza": (1, 2), "sudamericana": (3, 3)},
        "etapas_extra": ["Cuartos de final", "Semifinal", "Final"],
        # La final se juega en cancha neutral y la sede se sabe desde mucho
        # antes que los finalistas. No viene en el fixture —para la fuente
        # ese partido todavía no existe— así que va a mano.
        "final": {"cuando": "2026-11-28", "sede": "Estadio Centenario",
                  "ciudad": "Montevideo, Uruguay",
                  "nota": "A partido único, en cancha neutral."},
    },
    "sud": {
        "nombre": "Copa Sudamericana", "torneo": "Edición 2026",
        "base": None, "pages": {}, "propia": False, "sc": 389,
        "pais": "Sudamérica", "anual": False, "copa": True,
        "internacional": True,
        # acá pasa sólo el primero; el segundo juega el repechaje contra los
        # terceros de la Libertadores
        "zonas_de": {"avanza": (1, 1), "repechaje": (2, 2)},
        # La ronda extra que tiene la Sudamericana —los que salen segundos
        # contra los terceros de la Libertadores— no se agrega a mano: viene
        # en el fixture con el nombre que le pone CONMEBOL y se traduce a
        # "Pre octavos" al mostrarla.
        "etapas_extra": ["Cuartos de final", "Semifinal", "Final"],
        # Su clasificación previa se juega a partido único, no a ida y
        # vuelta, así que no forma un cuadro: son dieciséis partidos
        # sueltos y dibujarlos como llaves encadenadas es inventar un
        # camino que no existe. Van en el calendario, como cualquier fecha.
        "sin_cuadro_previa": True,
        "final": {"cuando": "2026-11-21",
                  "sede": "Estadio Metropolitano Roberto Meléndez",
                  "ciudad": "Barranquilla, Colombia",
                  "nota": "A partido único, en cancha neutral."},
    },
    "ca": {
        # Eliminación directa de punta a punta, sin tabla de posiciones.
        "nombre": "Copa Argentina", "torneo": "Edición 2026",
        "base": None, "pages": {}, "propia": False, "sc": 640,
        "pais": "Argentina", "anual": False, "copa": True,
        # La fecha está confirmada; la cancha, no. Se muestra lo que se sabe
        # y lo que falta se dice que falta, en vez de inventar una sede.
        "final": {"cuando": "2026-11-04", "sede": None, "ciudad": None,
                  "nota": "A partido único. La cancha todavía no se confirmó."},
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
    _guardar_en_cache(url, out)
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
    _guardar_en_cache(url, tablas)
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
_IMG_MAX = 150          # 150 escudos son unos pocos megas; con 400 no


# Un escudo pesa unos pocos KB y no cambia nunca. Guardarlos en la base
# ahorra volver a bajarlos en cada arranque —y sobre todo hace que la
# página siga mostrando los escudos aunque el CDN de 365scores no conteste—.
# El tope está para que un archivo raro no infle la base.
_IMG_MAX_BYTES = 60 * 1024


def traer_imagen(tipo, ver, ident):
    """Devuelve (bytes, content-type) de un escudo, de donde sea más barato."""
    clave = (tipo, ver, ident)
    with _lock:
        if clave in _IMG_CACHE:
            return _IMG_CACHE[clave]

    def recordar(datos, ctype):
        with _lock:
            if len(_IMG_CACHE) >= _IMG_MAX:
                _IMG_CACHE.clear()
            _IMG_CACHE[clave] = (datos, ctype)
        return datos, ctype

    en_base = "img:%s:%s:%s" % (tipo, ver, ident)
    guardado, _ = almacen.leer(en_base)
    if guardado:
        try:
            return recordar(base64.b64decode(guardado["b64"]), guardado["ct"])
        except Exception:
            pass        # entrada dañada: se vuelve a bajar y se pisa

    carpeta = {"competidor": "Competitors", "competencia": "Competitions"}.get(tipo)
    if not carpeta:
        raise ValueError("tipo de imagen desconocido")
    url = "%s/v%s/%s/%s" % (_CDN, ver, carpeta, ident)
    req = Request(url, headers={"User-Agent": UA, "Accept": "image/png,image/*"})
    try:
        with urlopen(req, timeout=15) as r:
            datos = r.read()
            ctype = r.headers.get("Content-Type", "image/png")
    except Exception:
        # si la fuente falla, sirve cualquier versión vieja del mismo escudo
        # antes que dejar el hueco
        for k in almacen.claves():
            if k.startswith("img:%s:" % tipo) and k.endswith(":%s" % ident):
                v, _ = almacen.leer(k)
                if v:
                    return recordar(base64.b64decode(v["b64"]), v["ct"])
        raise

    if len(datos) <= _IMG_MAX_BYTES:
        almacen.guardar(en_base, {"ct": ctype,
                                  "b64": base64.b64encode(datos).decode("ascii")})
    return recordar(datos, ctype)


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
        # El país sirve para detectar el clásico internacional: dos clubes
        # del mismo país cruzados en una copa. Y `rank` es lo que 365scores
        # llama popularidad, que es lo más cercano a "qué tan grande es el
        # club" que hay sin inventar un ranking propio.
        "pais": c.get("countryId"),
        "rank": c.get("popularityRank"),
        "score": None if sc in (None, -1) else int(sc),
        # En las copas, 365scores dice quién clasificó. Ojo con el campo:
        # `isQualified` es definitivo, `toQualify` es provisional —marca al
        # que va ganando la serie—. Usando los dos, el cuadro daba por
        # clasificado al que ganó la ida antes de que se jugara la vuelta.
        "pasa": bool(c.get("isQualified")),
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
        # De qué competencia es. Importa más de lo que parece: cuando se le
        # piden los partidos a la Europa League, 365scores mete adentro los
        # de su clasificación, que es OTRA competencia (la 596) y numera sus
        # temporadas por su cuenta —va por la 11 mientras la Europa League
        # va por la 61—. Sin este dato, filtrar por temporada los borraba a
        # todos y el torneo quedaba con la edición pasada y nada más.
        "comp": g.get("competitionId"),
        "etapaFuente": g.get("stageName") or "",
        "start": g.get("startTime"),
        "status": st,
        "statusText": g.get("statusText") or "",
        # En el entretiempo 365scores manda gameTime 45, y mostrar "45'"
        # parecía un partido corriendo. Se marca aparte para que la portada
        # pueda decir "entretiempo" en vez de un minuto que no avanza.
        "entretiempo": st == "LIVE" and any(
            w in norm(g.get("statusText"))
            for w in ("entretiempo", "descanso", "medio tiempo",
                      "half time", "halftime")),
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
        # sólo el Clausura: el acumulado también tiene los partidos del
        # Apertura y, sin filtrar, un Argentinos–Huracán de aquel torneo se
        # le pegaba a la fecha 16 del Clausura y la daba por jugada.
        historico = [x for x in _sc_fixture(COMPETITION)
                     if STAGE in norm(x.get("stage"))]
    except Exception:
        historico = []

    for lv in historico + live_games(ttl):
        hc = match_team(lv["home"].get("name")) or lv["home"].get("canon")
        ac = match_team(lv["away"].get("name")) or lv["away"].get("canon")
        # con la fecha del torneo primero; el comodín sólo si no hay otra
        m = idx.get((lv["round"], hc, ac))
        if not m and lv.get("round") is None:
            m = idx.get((None, hc, ac))
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

    # se guardan para poder promediarlas después por equipo y por liga
    if orden:
        anotar_stats((q.get("liga") or ["lpf"])[0], gid,
                     out["home"].get("canon") or out["home"]["name"],
                     out["away"].get("canon") or out["away"]["name"],
                     {k: _num(hs.get(k)) for k in orden},
                     {k: _num(as_.get(k)) for k in orden},
                     out.get("gh"), out.get("ga"))

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
    # lo que hizo cada jugador, para el gráfico de su ficha
    filas_jug = []
    for c_key, key in (("homeCompetitor", "home"), ("awayCompetitor", "away")):
        lu = (g.get(c_key) or {}).get("lineups") or {}
        formation[key] = lu.get("formation") or ""
        club_lado = (out[key].get("canon") or out[key].get("name") or "")
        clasificados = []
        for m in (lu.get("members") or []):
            # Las estadísticas del jugador vienen acá adentro, en el mismo
            # paquete del partido: no hay que pedir nada aparte. Se guardan
            # sólo las que usa algún gráfico.
            suyas = {}
            for s in (m.get("stats") or []):
                cn = norm(s.get("name"))
                if cn in _CLAVES_JUGADOR:
                    v = _num_jug(s.get("value"))
                    if v is not None:
                        suyas[cn] = v
            if suyas or m.get("ranking") is not None:
                p0 = quien.get(m.get("id"), {})
                filas_jug.append({
                    "n": p0.get("name") or "",
                    "eq": club_lado,
                    "p": (puesto_ar((m.get("position") or {}).get("name"))
                          or puesto_ar((m.get("formation") or {}).get("name"))),
                    "r": m.get("ranking"),
                    "v": suyas,
                })
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

    # De dónde es cada uno, para la banderita al lado del nombre.
    #
    # Es el mismo mecanismo del plantel de un club: se piden todos juntos y
    # se guardan por jugador para siempre —la nacionalidad no cambia—, así
    # que un partido cuesta un pedido la primera vez y ninguno después. Y
    # como los jugadores se repiten fecha a fecha, a la segunda semana ya
    # está casi todo guardado.
    #
    # Si la fuente no contesta, el partido se muestra igual: lo que falta
    # es la banderita, no la formación.
    try:
        todos = [f.get("id") for k in ("home", "away")
                 for f in (lineups[k] + banco[k])]
        paises = nacionalidades(todos)
        for k in ("home", "away"):
            for f in lineups[k] + banco[k]:
                p = paises.get(str(f.get("id") or ""))
                if p:
                    f["pais"], f["bandera"] = p.get("pais"), p.get("bandera")
    except Exception:
        pass

    ofic = [o.get("name") if isinstance(o, dict) else str(o) for o in (g.get("officials") or [])]
    venue = g.get("venue") or {}
    for s in ("home", "away"):
        out[s]["site"] = SITIOS.get(out[s]["canon"])

    # Cada formación que vemos alimenta la trayectoria y el conteo de
    # partidos. Es la única fuente propia que tenemos de eso.
    #
    # De qué torneo es: la página lo dice cuando viene de adentro, pero el
    # que entra por el link no lo sabe, así que se busca por el id del
    # partido. Antes acá había un "lpf" por defecto, y eso significaba que
    # cada visita en frío a un partido de la Champions anotaba a sus
    # jugadores como si hubieran jugado en la Liga Profesional.
    pedida = (q.get("liga") or [""])[0]
    liga_id = pedida if pedida in LIGAS else (liga_de_partido(str(gid)) or "lpf")
    for key, lado in (("home", out["home"]), ("away", out["away"])):
        club = lado.get("canon") or lado.get("name")
        for p in lineups[key]:
            anotar_paso(p["name"], club, liga_id, lado.get("logo"))
            anotar_partido(p["name"], liga_id, out.get("id"))
        for p in banco[key]:
            anotar_paso(p["name"], club, liga_id, lado.get("logo"))
    anotar_jugadores(liga_id, gid, filas_jug)

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

    # Y se lo devolvemos a la página, que lo necesita para saber qué tabla
    # de posiciones poner al costado.
    out["liga"] = liga_id
    out["ligaNombre"] = (LIGAS.get(liga_id) or {}).get("nombre") or ""
    out["torneo"] = (LIGAS.get(liga_id) or {}).get("torneo") or ""
    # En una copa la fecha no dice nada: lo que ubica al partido es la
    # instancia. Un Boca–Flamengo es de octavos, no de la "fecha 2".
    out["etapa"] = etapa_de_copa(liga_id, out.get("stage"), out.get("round"),
                                 out.get("start"))

    # Y en un torneo internacional, de qué país es cada club. En la
    # Libertadores hay clubes que se llaman igual —Nacional es el de
    # Uruguay y también el de Potosí, hay una Universidad Católica en Chile
    # y otra en Ecuador— así que la bandera no es un adorno: a veces es lo
    # único que los distingue. El país ya viene con cada equipo; acá sólo
    # se lo convierte en imagen.
    if (LIGAS.get(liga_id) or {}).get("internacional"):
        # Este pedido llega fresco y trae el país, así que de paso deja
        # anotado de dónde son estos dos: el calendario guardado de las
        # copas sudamericanas no lo sabe y así se va llenando solo.
        try:
            tabla = recordar_paises([out])
        except Exception:
            tabla = {}
        for lado in (out["home"], out["away"]):
            pais = lado.get("pais") or tabla.get(str(lado.get("id") or ""))
            if pais:
                lado["bandera"] = bandera_url(pais)
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
             "sportivo", "san", "general", "carril", "aires", "buenos",
             # Apellidos de club que comparten muchos y no distinguen a
             # ninguno. "Juniors" lo llevan Boca, Argentinos y Chacarita:
             # tomándolo por seña particular, Argentinos Juniors salía en la
             # Libertadores con el nombre y el escudo de Boca.
             "juniors", "jrs", "jr", "fc", "sc", "cf", "afc", "united"}


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


def _sc_standings(comp, ttl=25, juntar=None):
    """
    Posiciones de una competencia de 365scores, separadas por zona.
    A diferencia de la Liga Profesional, acá sí vienen las dos juntas: cada
    fila trae su groupNum y el bloque, los nombres de los grupos.

    `juntar` mete varias fases bajo un mismo título. La Fase Campeonato y
    la Reválida del Federal A se juegan al mismo tiempo —son la Segunda
    Fase, repartida según cómo te fue— y tenerlas en dos pestañas obligaba
    a saltar de una a otra para mirar la misma jornada. El nombre de cada
    una no se pierde: pasa a ser el de la zona, "Reválida A" en vez de
    "Zona A", que además es como las nombra AFA.
    """
    data = fetch("standings", {"competitions": comp, "live": "true"}, ttl=ttl)
    todos = data.get("standings") or [{}]

    # 365scores manda una tabla por fase: la primera es la que se está
    # jugando, pero las anteriores también vienen. Antes tomábamos sólo la
    # primera y por eso el Federal A se quedaba sin las zonas de la fase 1.
    # Se juntan todas, poniéndole a cada zona el nombre de su fase adelante.
    zonas = {}
    for bloque in todos:
        fase = (bloque.get("name") or bloque.get("stageName") or "").strip()
        _sc_zonas_de(bloque, fase, zonas, juntar)
    out = []
    for clave in sorted(zonas, key=lambda k: (zonas[k]["orden"], k)):
        z = zonas[clave]
        out.append({"name": z["nombre"], "num": z["num"],
                    "rows": sort_rows_simple(z["filas"])})
    return out


def _sc_zonas_de(bloque, fase, zonas, juntar=None):
    """Vuelca las filas de una tabla en el diccionario de zonas."""
    nombres = {g.get("num"): g.get("name") for g in (bloque.get("groups") or [])}

    # Varias fases bajo un mismo título. La clave del diccionario sigue
    # siendo la fase de verdad: si dos zonas distintas comparten el número
    # de grupo —y la Zona A de la Reválida lo comparte con la Zona A del
    # Campeonato— unirlas por la clave las fusionaría en una sola tabla.
    titulo, propio = fase, ""
    if juntar and any(norm(x) in norm(fase) for x in juntar.get("cuales", [])):
        titulo = juntar.get("titulo") or fase
        if norm(fase) != norm(titulo):
            propio = fase
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
        # Los torneos sin zonas vienen con num en blanco. Sin esto la
        # pestaña terminaba diciendo "Zona None".
        corto = nombres.get(g)
        if not corto and g not in (None, "", 0):
            corto = "Zona %s" % g
        # "Zona A" de la Reválida pasa a llamarse "Reválida A": adentro de
        # la pestaña común hay dos zonas A y así se sabe cuál es cuál.
        if propio and corto:
            corto = "%s %s" % (propio, re.sub(r"^(Zona|Grupo)\s+", "", corto))
        # el nombre lleva la fase adelante para poder agruparlas después
        nombre = (("%s - %s" % (titulo, corto)) if (titulo and corto)
                  else (corto or titulo or None))
        clave = (fase, g)
        z = zonas.setdefault(clave, {"nombre": nombre, "num": g,
                                     "orden": len(zonas), "filas": []})
        z["filas"].append({
            "team": {"name": c.get("name") or "", "short": c.get("symbolicName") or "",
                     "logo": logo(c), "site": sitio_de(c.get("name") or "")},
            "pts": int(float(r.get("points") or 0)), "pj": int(r.get("gamePlayed") or 0),
            "g": int(r.get("gamesWon") or 0), "e": int(r.get("gamesEven") or 0),
            "p": int(r.get("gamesLost") or 0),
            "gf": gf, "gc": gc, "dif": gf - gc, "form": form, "live": False,
        })


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
    {"clave": "afuera", "color": "#e5484d", "texto": "Queda eliminado"},
    {"clave": "campeonato", "color": "#2f6fed",
     "texto": "Clasifica a la Segunda Fase"},
    {"clave": "revalida", "color": "#f0b429", "texto": "Pasa a la Reválida"},
    {"clave": "tercera", "color": "#2f6fed",
     "texto": "Clasifica a la Tercera Fase"},
    {"clave": "copaarg", "color": "#12b76a",
     "texto": "Copa Argentina 2027 y segunda etapa de la Reválida"},
    {"clave": "revalida2", "color": "#f0b429",
     "texto": "Pasa a la segunda etapa de la Reválida"},
    {"clave": "sudamericana", "color": "#f0b429",
     "texto": "Pasa a los pre octavos de la Sudamericana"},
]


def marcar_destinos(zonas, reglas):
    """
    Pinta cada fila según a dónde va: ascenso, reducido o descenso.

    `reglas` es {clave: (desde, hasta)} con posiciones que arrancan en 1. Los
    números negativos cuentan desde abajo, así (-2, -1) son los dos últimos
    sin importar cuántos equipos tenga la zona.

    En un torneo donde no todas las zonas reparten lo mismo, `reglas` puede
    ser una lista de {"cuando": <texto>, "reglas": {...}} y a cada zona se
    le aplica la primera cuyo "cuando" aparezca en su nombre. Hace falta
    para el Federal A: en la Fase Campeonato se pelea el ascenso y en la
    Reválida, no descender. Pintar las dos igual sería decir que el puntero
    de la Reválida asciende.

    Y el rango puede ser una función de la cantidad de equipos, porque hay
    reglamentos que dependen de eso: en la Primera Fase del Federal A pasan
    cinco de las zonas de diez y cuatro de las de nueve.
    """
    if not reglas:
        return
    porNombre = isinstance(reglas, (list, tuple))
    for z in zonas:
        n = len(z["rows"])
        suyas = reglas
        if porNombre:
            nom = norm(z.get("name") or "")
            suyas = next((b["reglas"] for b in reglas
                          if norm(b.get("cuando") or "") in nom), None)
        for r in z["rows"]:
            r["destino"], r["destinoTexto"] = "", ""
            if not suyas:
                continue
            pos = r.get("pos") or 0
            for clave, rango in suyas.items():
                desde, hasta = rango(n) if callable(rango) else rango
                a = desde if desde > 0 else n + desde + 1
                b = hasta if hasta > 0 else n + hasta + 1
                if a <= pos <= b:
                    r["destino"] = clave
                    r["destinoTexto"] = next(
                        (x["texto"] for x in LEYENDA_DESTINOS if x["clave"] == clave), "")
                    break


def texto_destino(clave):
    return next((x["texto"] for x in LEYENDA_DESTINOS if x["clave"] == clave), "")


def marcar_mejor_puesto(zonas, regla):
    """
    El mejor quinto de las zonas de nueve.

    A la Segunda Fase del Federal A pasan cinco de las zonas de diez y
    cuatro de las de nueve, más el que mejor haya terminado quinto entre
    esas tres. Es lo único del reglamento que no se puede resolver mirando
    una tabla sola: hay que comparar zonas entre sí, así que va aparte de
    `marcar_destinos`, que trabaja tabla por tabla.

    Si las zonas todavía no jugaron lo mismo la comparación no es justa,
    pero tampoco lo es la del reglamento: se compara igual y se acomoda
    solo cuando emparejan las fechas.
    """
    if not regla:
        return
    chicas = [z for z in zonas
              if norm(regla["cuando"]) in norm(z.get("name") or "")
              and len(z["rows"]) == regla["de_zonas_de"]]
    if len(chicas) < 2:
        return
    quintos = [r for z in chicas for r in z["rows"]
               if (r.get("pos") or 0) == regla["puesto"]]
    if not quintos:
        return
    mejor = max(quintos, key=lambda r: (r.get("pts") or 0, r.get("dif") or 0,
                                        r.get("gf") or 0))
    mejor["destino"] = regla["destino"]
    mejor["destinoTexto"] = texto_destino(regla["destino"])


def tablas_de_descenso(zonas, juegos, regla):
    """
    Las tablas que definen los descensos del Federal A.

    No es ninguna de las que se ven. El reglamento dice que al terminar la
    primera etapa de la Reválida se arma una tabla general por zona, que
    suma los puntos de la Primera Fase con los de la Reválida, y que
    descienden los dos últimos de cada una. La Zona A la promedia por
    partidos jugados y la Zona B los suma derecho.

    Los puntos de la Reválida están en la tabla que publica la fuente; los
    de la Primera Fase se calculan de los partidos guardados, que es de
    donde ya salen las tablas de esa fase.
    """
    if not regla:
        return []
    de, sumar = regla["de"], regla["sumar"]
    por_promedio = {norm(x) for x in regla.get("promedio", [])}

    previos = {}
    suyos = [m for m in juegos if norm(sumar) in norm(m.get("stage") or "")]
    for t in tablas_por_resultados(suyos, sumar):
        for r in t["rows"]:
            previos[norm(r["team"]["name"])] = (r["pts"], r["pj"])
    if not previos:
        return []

    salida = []
    for z in zonas:
        nombre = (z.get("name") or "").strip()
        if norm(de) not in norm(nombre):
            continue
        letra = nombre[-1:]
        promedia = norm(letra) in por_promedio

        filas = []
        for r in z["rows"]:
            k = norm(r["team"]["name"])
            if k not in previos:
                k = emparejar(r["team"]["name"], {x: x for x in previos}) or k
            antes, jugados = previos.get(k, (0, 0))
            pts, pj = (r.get("pts") or 0) + antes, (r.get("pj") or 0) + jugados
            fila = {"team": r["team"], "pts": pts, "pj": pj,
                    "gf": r.get("gf") or 0, "gc": r.get("gc") or 0,
                    "dif": r.get("dif") or 0, "form": []}
            if promedia:
                fila["prom"] = round(pts / pj, 3) if pj else 0.0
            filas.append(fila)

        filas.sort(key=(lambda f: (f["prom"], f["pts"])) if promedia
                   else (lambda f: (f["pts"], f["dif"], f["gf"])), reverse=True)
        for i, f in enumerate(filas, 1):
            f["pos"] = i
        salida.append({
            "name": "Descenso - Zona %s" % letra, "num": z.get("num"),
            "rows": filas, "calculada": True,
            "nota": ("Puntos de la Primera Fase más los de la Reválida, "
                     + ("promediados por partido jugado." if promedia
                        else "sumados.")
                     + " Descienden los dos últimos.")})
    return salida


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

    # La tabla de una edición que ya terminó es tan vieja como su calendario.
    # El calendario ya dejaba de mostrarse, pero la tabla seguía ahí con los
    # puntos y los equipos del año pasado.
    if edicion_terminada(cfg["sc"]):
        nota = ("La edición anterior terminó y la nueva todavía no empezó: "
                "por ahora se juega la clasificación.")
        out["zonasNota"] = nota
        out["notaGoleadores"] = nota
        out["golesDetallados"] = False
        return out

    # posiciones por zona, con escudos
    try:
        out["zonas"] = _sc_standings(cfg["sc"], juntar=cfg.get("fases_juntas"))
        # Las fases que ya terminaron no las publica más la fuente. Si de
        # alguna tenemos los partidos y no tenemos la tabla, se calcula.
        juegos = []
        if cfg.get("fases_calculadas"):
            try:
                juegos = [dict(m) for m in fixture_de_liga(cfg, ttl=600)]
                # Sin nombre de fase no hay con qué elegir sus partidos.
                # Se copia la lista antes de tocarla: la de `fixture_de_liga`
                # es la que va a la base y no es de acá para escribirla.
                if cfg.get("fases_por_calendario"):
                    marcar_fases_por_calendario(juegos,
                                                cfg["fases_por_calendario"])
                nombres = " ".join(norm(z["name"]) for z in out["zonas"])
                for fase in cfg["fases_calculadas"]:
                    if norm(fase) in nombres:
                        continue      # la fuente ya la da: no la pisamos
                    suyos = [m for m in juegos
                             if norm(fase) in norm(m.get("stage") or "")]
                    out["zonas"] = tablas_por_resultados(suyos, fase) + out["zonas"]
            except Exception:
                pass
        # Los descensos no salen de ninguna tabla que se vea: se arma una
        # general que suma la fase anterior con la de ahora. Va al final,
        # después de las zonas de las que sale.
        if cfg.get("descenso") and juegos:
            try:
                out["zonas"] = out["zonas"] + tablas_de_descenso(
                    out["zonas"], juegos, cfg["descenso"])
            except Exception:
                pass

        marcar_destinos(out["zonas"], cfg.get("zonas_de"))
        # Y el que se decide comparando zonas entre sí, que `marcar_destinos`
        # no puede ver porque trabaja tabla por tabla.
        try:
            marcar_mejor_puesto(out["zonas"], cfg.get("mejor_puesto"))
        except Exception:
            pass
        # sólo las referencias que esta liga usa de verdad
        reglas = cfg.get("zonas_de") or {}
        usadas = (set().union(*(set(b["reglas"]) for b in reglas))
                  if isinstance(reglas, (list, tuple)) and reglas
                  else set(reglas))
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
        # Si el torneo todavía no jugó nada, la tabla de goleadores que
        # publica 365scores es la de la edición anterior. Mostrarla acá era
        # decir que Dembélé lleva 6 goles en una Champions que no empezó.
        if not arranco_el_torneo(cfg):
            out["goleadores"] = []
            out["notaGoleadores"] = ("El torneo todavía no empezó: los "
                                     "goleadores aparecen con la primera fecha.")
            return out
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
        out["golesDetallados"] = hay_desglose_de_goles(out["goleadores"])
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

    out["golesDetallados"] = hay_desglose_de_goles(out["goleadores"])
    return out


def marcar_fases_por_calendario(games, nombres, corte=45):
    """
    Le pone nombre de fase a los partidos cuando la fuente no lo manda.

    El Federal A juega una Primera Fase y una Segunda, y las dos empiezan
    en la fecha 1. 365scores manda los partidos sin nombre de fase, así que
    las dos fechas 1 se sumaban en una sola y en pantalla aparecían 34
    partidos donde son 17.

    La señal está en el calendario. Una fase termina antes de que empiece
    la siguiente, así que los partidos de la fecha 1 de cada una están
    separados por meses, mientras que los de una misma fecha se juegan en
    el mismo fin de semana. Se parte cada fecha en tandas por esa distancia.

    Un puñado de partidos sueltos no es una fase: es un postergado que se
    jugó tarde. Esos vuelven a la tanda anterior, que es de donde salieron.
    Lo que decide no es cuántos son sino qué parte de la fecha ocupan: una
    fecha de treinta y cuatro partidos partida en diecisiete y diecisiete
    son dos fases, y partida en treinta y tres y uno es una postergación.
    """
    def dia(g):
        try:
            return dt.date.fromisoformat((g.get("start") or "")[:10])
        except ValueError:
            return None

    porRonda = {}
    for g in games:
        if g.get("round") and dia(g):
            porRonda.setdefault(g["round"], []).append(g)

    fase_de = {}
    for ronda, ms in porRonda.items():
        tandas, actual, anterior = [], [], None
        for g in sorted(ms, key=lambda x: x["start"]):
            d = dia(g)
            if anterior and (d - anterior).days > corte:
                tandas.append(actual)
                actual = []
            actual.append(g)
            anterior = d
        tandas.append(actual)

        juntas = []
        for t in tandas:
            suelta = len(t) < 2 or len(t) * 3 < len(ms)
            if juntas and suelta:
                juntas[-1].extend(t)
            else:
                juntas.append(t)

        for i, t in enumerate(juntas):
            for g in t:
                fase_de[str(g["id"])] = i

    if not fase_de or max(fase_de.values()) < 1:
        return False        # una sola fase: no hay nada que separar
    for g in games:
        i = fase_de.get(str(g.get("id")))
        if i is None or (g.get("stage") or "").strip():
            continue
        g["stage"] = nombres[i] if i < len(nombres) else "Fase %d" % (i + 1)
    return True


def zonas_por_rivales(juegos):
    """
    Deduce las zonas de una fase mirando quién jugó contra quién.

    En un torneo por zonas nadie cruza de grupo: los de la Zona A juegan
    entre ellos y con nadie más. Así que los equipos forman islas dentro
    del mapa de enfrentamientos, y cada isla es una zona. Sale de los
    partidos y no hace falta que la fuente mande el número de grupo.

    Es la única forma de armar la Primera Fase del Federal A: 365scores
    no le pone zona a esos partidos y la fase ya terminó, así que
    tampoco se la puede pedir a la tabla de posiciones.

    Las zonas salen numeradas por orden de aparición en el calendario.
    Ese número es nuestro y no tiene por qué coincidir con la letra que
    les puso AFA; lo que importa es que cada equipo caiga con los suyos.
    """
    vecinos, primera = {}, {}
    for m in juegos:
        a = (m["home"].get("canon") or m["home"].get("name") or "").strip()
        b = (m["away"].get("canon") or m["away"].get("name") or "").strip()
        if not a or not b:
            continue
        vecinos.setdefault(a, set()).add(b)
        vecinos.setdefault(b, set()).add(a)
        for x in (a, b):
            cuando = m.get("start") or ""
            if cuando and (x not in primera or cuando < primera[x]):
                primera[x] = cuando

    islas, visto = [], set()
    for equipo in sorted(vecinos, key=lambda x: (primera.get(x, ""), x)):
        if equipo in visto:
            continue
        grupo, pila = set(), [equipo]
        while pila:
            actual = pila.pop()
            if actual in grupo:
                continue
            grupo.add(actual)
            pila.extend(vecinos.get(actual, ()) - grupo)
        visto |= grupo
        islas.append(grupo)

    return {equipo: i + 1 for i, grupo in enumerate(islas) for equipo in grupo}


def hay_desglose_de_goles(goleadores):
    """
    ¿La tabla de goleadores trae el detalle de cómo se hizo cada gol?

    AFA lo publica —de jugada, de cabeza, de tiro libre, de penal— pero
    365scores no, y las categorías que no cubre AFA quedaban con las cuatro
    columnas en cero. Cuatro ceros al lado de un goleador no dicen que no
    convirtió de cabeza: dicen que no sabemos, y son cosas distintas. Sin
    dato, la pantalla esconde las columnas.
    """
    return any(g.get(k) for g in (goleadores or [])
               for k in ("jugada", "cabeza", "tiroLibre", "pens"))


def zonas_de_cada_fase(games):
    """
    La zona de cada partido, calculada adentro de su propia fase.

    La zona salía de en qué tabla está hoy cada equipo, y eso funciona
    mientras el torneo tenga una sola. En el Federal A no: los partidos de
    la Primera Fase se leían contra las zonas de la Segunda, donde los
    equipos ya están repartidos de otra manera, y casi todos terminaban
    marcados como "Interzonal" —que es justo lo que no eran—.

    Cada fase se agrupa con sus propios partidos: quiénes se enfrentaron
    entre marzo y julio arma las zonas de la Primera Fase, y quiénes se
    enfrentan ahora, las de la Segunda.

    El nombre de la zona se conserva sólo si todo el grupo coincide en él.
    Los partidos de la Primera Fase también llegan rotulados —con la zona
    donde está hoy cada equipo, que no es la de entonces— y quedarse con el
    rótulo más repetido ponía "Zona Reválida - A" arriba de una fecha de
    abril. Si adentro de un grupo aparecen dos rótulos distintos, el rótulo
    es de otra fase y no sirve: esa zona va numerada.
    """
    porFase = {}
    for g in games:
        porFase.setdefault((g.get("stage") or "").strip(), []).append(g)
    if len(porFase) < 2:
        return

    # Las posiciones que publica la fuente son las de la fase que se juega
    # ahora, así que sólo esa puede quedarse con sus rótulos. Se la conoce
    # por ser la última del calendario.
    def arranque(ms):
        return min((m.get("start") or "9999") for m in ms)
    la_de_ahora = max(porFase, key=lambda f: arranque(porFase[f]))

    for fase, suyos in porFase.items():
        mapa = zonas_por_rivales(suyos)
        if len(set(mapa.values())) < 2:
            continue

        # El rótulo de cada grupo, si todos sus partidos dicen lo mismo.
        rotulos = {}
        if fase == la_de_ahora:
            for g in suyos:
                z = mapa.get(g["home"].get("canon") or g["home"].get("name"))
                if z is not None and g.get("zone"):
                    rotulos.setdefault(z, set()).add(g["zone"])
        nombre = {z: next(iter(c)) for z, c in rotulos.items() if len(c) == 1}

        for g in suyos:
            za = mapa.get(g["home"].get("canon") or g["home"].get("name"))
            zb = mapa.get(g["away"].get("canon") or g["away"].get("name"))
            g["zone"] = nombre.get(za, str(za)) if za is not None else None
            g["interzonal"] = bool(za and zb and za != zb)


def tablas_por_resultados(juegos, etiqueta):
    """
    Arma las tablas de una fase con los partidos que tenemos guardados.

    Existe por el Federal A. Cuando una fase termina, 365scores deja de
    publicar sus posiciones: pedirle las de la Primera Fase devuelve las de
    la Segunda. Pero los partidos sí los tenemos —los fuimos guardando fecha
    a fecha— y una tabla no es más que sumar tres, uno o cero.

    Se agrupa por el número de zona que trae cada partido. Si no viene
    —que es el caso del Federal A— se deduce de quién jugó contra quién.
    """
    jugados = [m for m in juegos if m.get("status") == "FIN"]
    porZona = {}
    for m in jugados:
        if m.get("slot") is not None:
            porZona.setdefault(m["slot"], []).append(m)
    if len(porZona) < 2:
        # Sin número de zona en los partidos, las zonas se deducen. Un
        # partido cuenta para la zona de sus equipos, que es la misma:
        # justamente por eso son zonas.
        deQuien = zonas_por_rivales(jugados)
        porZona = {}
        for m in jugados:
            z = deQuien.get(m["home"].get("canon") or m["home"].get("name"))
            if z is not None:
                porZona.setdefault(z, []).append(m)
    if len(porZona) < 2:
        return []

    salida = []
    for z in sorted(porZona):
        acc = {}
        for m in porZona[z]:
            if m["gh"] is None or m["ga"] is None:
                continue
            for yo, rival, mios, suyos in (
                    (m["home"], m["away"], m["gh"], m["ga"]),
                    (m["away"], m["home"], m["ga"], m["gh"])):
                nombre = yo.get("canon") or yo.get("name")
                if not nombre:
                    continue
                r = acc.setdefault(nombre, {
                    "team": {"name": nombre, "short": yo.get("short") or "",
                             "logo": yo.get("logo"), "site": None},
                    "pts": 0, "pj": 0, "gf": 0, "gc": 0, "dif": 0, "form": []})
                r["pj"] += 1
                r["gf"] += mios
                r["gc"] += suyos
                r["dif"] = r["gf"] - r["gc"]
                r["pts"] += 3 if mios > suyos else (1 if mios == suyos else 0)
                r["form"].append("G" if mios > suyos else
                                 ("E" if mios == suyos else "P"))
        filas = sort_rows_simple(list(acc.values()))
        for r in filas:
            r["form"] = r["form"][-5:]
        if len(filas) >= 4:
            salida.append({"name": "%s - Zona %s" % (etiqueta, z),
                           "num": z, "rows": filas, "calculada": True})
    return salida


def arranco_el_torneo(cfg):
    """
    ¿Ya se jugó algo del torneo propiamente dicho?

    Sólo cuenta la competencia principal. La clasificación se juega en
    julio y agosto, meses antes de la primera fecha, y tomarla como
    "arrancó" hacía que la Champions mostrara los goleadores de la edición
    anterior mientras se jugaban las eliminatorias.
    """
    try:
        return any(m.get("status") in ("FIN", "LIVE")
                   and (m.get("comp") in (None, cfg["sc"]))
                   for m in _sc_fixture(cfg["sc"], ttl=600))
    except Exception:
        return True      # ante la duda, se muestra lo que haya


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

    A propósito no se guarda nada: cada página se lee una sola vez en la
    vida y lo que importa —los partidos— queda en el fixture. Guardarlas
    llenaba la base de cientos de respuestas enormes que no se usaban más.

    Reintenta, y no por prolijidad: un recorrido es una cadena de páginas
    encadenadas por cursor, así que un solo tropiezo no cuesta una página,
    corta la vuelta entera y todo lo que venía atrás queda sin bajar. A la
    Primera Nacional le faltaba septiembre por eso: las dos direcciones
    murieron en un TimeoutError y el recorrido nunca llegó a esas fechas.
    """
    url = ruta if ruta.startswith("http") else "https://webws.365scores.com" + ruta
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    ultimo = None
    for intento in range(INTENTOS_PAGINA):
        try:
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            ultimo = e
            if intento + 1 < INTENTOS_PAGINA:
                time.sleep(1.5 * (intento + 1))
    raise ultimo


# El paginado de 365scores va para los dos lados. Cada dirección lleva su
# propio marcador de "por dónde iba", porque avanzan a ritmos distintos.
_CLAVE_CAMINO = {-1: "hist:%s", 1: "fut:%s"}

# Cuántas páginas seguidas de otra temporada se aguantan antes de dar el
# recorrido por terminado. Con una sola, un hueco en el medio del paginado
# cortaba la bajada de una copa entera.
TOLERA_VACIAS = 3

# Cuántas veces se le pide la misma página a la fuente antes de rendirse.
# Tres y no más: si falla tres veces seguidas no es un tropiezo, es que la
# fuente está caída, y en ese caso conviene cortar la vuelta y volver en la
# siguiente antes que quedarse colgado insistiendo.
INTENTOS_PAGINA = 3


def cursor_manual(comp, direccion, desde_id):
    """
    El cursor del paginado, armado por nosotros.

    365scores devuelve en cada respuesta la dirección de la página de al
    lado, y el recorrido la venía siguiendo a ciegas. El problema es que a
    veces no la manda —le pedí a mano la misma dirección que le tocó al
    servidor y a mí sí me la dio, así que depende de algo que no controlo—
    y entonces el recorrido se daba por terminado con media copa sin bajar.

    Pero la dirección no tiene misterio: es "dame los partidos anteriores a
    este". Con el número del partido más viejo que ya tenemos alcanza para
    armarla. Así el recorrido deja de depender de que la fuente se acuerde
    de incluir el campo.
    """
    return ("/web/games/?appTypeId=5&langId=%s&timezoneName=%s"
            "&userCountryId=382&competitions=%s&games=1&aftergame=%s"
            "&direction=%d" % (LANG, TZ, comp, desde_id, direccion))


def _borde(juegos, comp, direccion):
    """
    El partido del extremo: el más viejo hacia atrás, el más nuevo adelante.

    Ojo con el criterio: se ordena por FECHA, no por número de partido.
    Parece un detalle y era el error que dejaba media Copa Argentina sin
    bajar. El cursor de 365scores significa "dame los partidos anteriores a
    este en el calendario", y los números no siguen el calendario: pidiendo
    los anteriores al 4728058 devuelve el 4728053 pero también el 4728065 y
    el 4728067. Anclando en el número más chico, el cursor no se movía —el
    mínimo ya estaba guardado— y el recorrido se daba por terminado en la
    primera vuelta.
    """
    suyos = [m for m in juegos
             if m.get("comp") in (None, comp) and str(m.get("id")).isdigit()]
    if not suyos:
        return None
    elegir = min if direccion < 0 else max
    conFecha = [m for m in suyos if m.get("start")]
    if conFecha:
        return int(elegir(conFecha, key=lambda m: m["start"])["id"])
    # Sin fechas no queda otra que el número. Es peor —por eso está último—
    # pero es preferible a no tener por dónde empezar.
    return elegir(int(m["id"]) for m in suyos)


def caminar_fixture(comp, direccion=-1, paginas=25):
    """
    Recorre el calendario de un torneo página por página y lo va guardando.

    365scores publica una ventana móvil: lo de ahora y poco más. Todo lo
    anterior y todo lo posterior quedan afuera. Pero la respuesta trae
    `paging.previousPage` y `paging.nextPage`, dos direcciones ya armadas
    que llevan a la página de al lado. Yendo de a una se recorre el torneo
    entero para cualquiera de los dos lados.

    `direccion=-1` va al pasado: recupera la fase de grupos de la
    Libertadores jugada hace meses. `direccion=1` va al futuro: trae las 38
    fechas de la Premier cuando todavía no se jugó ninguna.

    Se guarda dónde quedó cada dirección, así cada vuelta sigue desde ahí en
    vez de empezar de cero.

    La diferencia entre los dos lados es qué pasa al terminar. El pasado ya
    está escrito: una vez recorrido no se vuelve a mirar. El futuro no: la
    AFA reprograma, 365scores publica fechas que antes no tenía. Por eso,
    cuando el camino hacia adelante llega al final, se guarda el último
    tramo y la próxima vuelta se reintenta desde ahí. Si no hay nada nuevo
    es un solo pedido y se corta; si apareció algo, entra.
    """
    campo = "previousPage" if direccion < 0 else "nextPage"
    estado, _ = almacen.leer(_CLAVE_CAMINO[direccion] % comp)
    estado = estado or {}

    # Un marcador escrito por otra versión del recorrido no vale: la lógica
    # cambió y lo que esa versión dio por terminado puede estar a medias.
    # Se descarta y se rehace.
    #
    # Este chequeo es el que hace que subir VERSION_RECORRIDO alcance para
    # que todo se vuelva a bajar. Sin él hacía falta una reparación global
    # que se ejecutaba una sola vez y, si corría con el recorrido roto,
    # dejaba el problema sellado.
    if estado.get("v") != VERSION_RECORRIDO:
        estado = {}

    ruta = estado.get("siguiente")
    if estado.get("listo") and direccion > 0:
        # Un recorrido hacia adelante que ya terminó igual se rechequea: el
        # futuro crece, aparecen fechas nuevas. Pero es un vistazo, no una
        # recorrida entera — si no, cada vuelta del rescate volvería a leer
        # el torneo completo para no encontrar nada.
        paginas = min(paginas, 3)
    if estado.get("listo"):
        if direccion < 0:
            return {"comp": comp, "dir": direccion, "listo": True,
                    "estado": "ya estaba completo", "nuevos": 0,
                    "total": estado.get("total", 0)}
        # hacia adelante se reintenta desde el último tramo conocido
        ruta = estado.get("ultimo")

    if not ruta:
        try:
            data = fetch("games/fixtures", {"competitions": comp}, ttl=300)
        except Exception as e:
            return {"comp": comp, "dir": direccion, "error": str(e)}
        ruta = (data.get("paging") or {}).get(campo) or ""
        if not ruta:
            # Sin paginado de la fuente, se arranca con el cursor propio:
            # "dame los anteriores al partido más viejo que tengo".
            guardados, _ = almacen.leer("fixture:%s" % comp)
            borde = _borde(guardados or [], comp, direccion)
            if borde:
                ruta = cursor_manual(comp, direccion, borde)
        if not ruta:
            # Ni eso: no hay ni un partido del que colgarse. Antes esto
            # quedaba en "sigue" para siempre y mantenía vivo el rescate
            # sin tener nada que hacer.
            almacen.guardar(_CLAVE_CAMINO[direccion] % comp,
                            {"siguiente": None, "ultimo": None, "listo": True,
                             "total": 0, "v": VERSION_RECORRIDO,
                             "motivo": "no hay ni un partido del que colgarse",
                             "cuando": dt.datetime.now().isoformat(
                                 timespec="seconds")})
            return {"comp": comp, "dir": direccion, "paginas": 0,
                    "listo": True, "nuevos": 0,
                    "total": len(almacen.leer("fixture:%s" % comp)[0] or []),
                    "estado": "la fuente no da paginado"}

    temporada = temporada_actual(comp)
    clave = "fixture:%s" % comp
    migrar_fixture(comp)
    reabrir_si_falta(comp)
    guardado, _ = almacen.leer(clave)
    acumulado = {str(m["id"]): m for m in (guardado or [])}
    antes = len(acumulado)

    vueltas, listo, ultimo = 0, False, ruta
    vistas, vacias = set(), 0
    # Por qué se detuvo. Sin esto, un recorrido que se corta antes de tiempo
    # es indistinguible de uno que terminó bien: los dos dicen "listo" y hay
    # que adivinar cuál fue. Va al log y a /api/recorrido.
    motivo = "límite de páginas de esta vuelta"
    while ruta and vueltas < paginas:
        if ruta in vistas:        # el paginado se mordió la cola
            listo, motivo = True, "el paginado se repitió"
            break
        vistas.add(ruta)
        try:
            data = fetch_ruta(ruta)
        except Exception as e:
            motivo = "falló el pedido: %s" % type(e).__name__
            break
        vueltas += 1
        ultimo = ruta
        time.sleep(0.4)     # veinte páginas seguidas sin respirar es abuso
        crudos = data.get("games") or []
        juegos = crudos

        # Por dónde seguir. El orden importa:
        #
        #   1. lo que diga la fuente;
        #   2. el borde de ESTA página —el partido más viejo que vino, se
        #      guarde o no—;
        #   3. el borde de lo que tenemos guardado.
        #
        # El segundo es el que faltaba. Cuando una página venía entera de
        # otra temporada no se guardaba nada, así que el borde propio no se
        # movía, el cursor salía idéntico al anterior y el recorrido se
        # cortaba justo ahí. Por eso a la Primera Nacional le faltaban dos
        # ventanas de días enteras en el medio del torneo.
        def borde_de(lista):
            conFecha = [g for g in lista if g.get("startTime")]
            if not conFecha:
                return None
            elegir = min if direccion < 0 else max
            return elegir(conFecha, key=lambda g: g["startTime"]).get("id")

        def proxima_ruta():
            dela = (data.get("paging") or {}).get(campo)
            if dela and dela != ruta and dela not in vistas:
                return dela
            for donde in (borde_de(crudos),
                          _borde(acumulado.values(), comp, direccion)):
                if donde:
                    propia = cursor_manual(comp, direccion, donde)
                    if propia != ruta and propia not in vistas:
                        return propia
            return None

        # El paginado sigue de largo hacia la temporada anterior. Sin este
        # corte, el rescate volvía a meter en la base los partidos viejos
        # que `_sc_fixture` acababa de podar, y la Europa League mostraba
        # entera la edición pasada.
        if temporada is not None:
            def sirve(g):
                suya = g.get("competitionId")
                if suya and suya != comp:
                    otra = temporada_actual(suya)
                    return otra is None or g.get("seasonNum") in (None, otra)
                return g.get("seasonNum") in (None, temporada)
            juegos = [g for g in crudos if sirve(g)]

        if not juegos:
            # Dos cosas distintas que antes se confundían en una:
            #
            #   · la página vino vacía  -> se acabó el torneo, se corta;
            #   · vino llena pero toda de otra temporada -> es un hueco en
            #     el medio del paginado, se saltea y se sigue.
            #
            # Confundirlas cortaba la bajada de una copa entera en el primer
            # hueco. Se toleran unas cuantas seguidas y recién ahí se cierra.
            if crudos:
                vacias += 1
                if vacias < TOLERA_VACIAS:
                    siguiente = proxima_ruta()
                    if siguiente:
                        ruta = siguiente
                        continue
                motivo = "%d páginas seguidas de otra temporada" % vacias
            else:
                motivo = "la fuente devolvió una página sin partidos"
            listo = True
            ruta = None
            break
        vacias = 0
        for g in juegos:
            m = map_game(g)
            m["liveId"] = g.get("id")
            m["temporada"] = g.get("seasonNum")
            m["zone"], m["interzonal"] = None, False
            for s in ("home", "away"):
                m[s]["canon"] = m[s]["name"]
            # Lo guardado manda para el marcador, pero los datos de forma
            # —de qué competencia es, en qué zona, qué fase— se refrescan:
            # los partidos viejos se guardaron sin ellos.
            k = str(m["id"])
            if k in acumulado:
                for campo in ("comp", "slot", "stageNum", "stage",
                              "etapaFuente", "temporada"):
                    if m.get(campo) is not None:
                        acumulado[k][campo] = m[campo]
            else:
                acumulado[k] = m
        siguiente = proxima_ruta()
        if not siguiente:
            listo = True
            motivo = "no hay por dónde seguir: la fuente ni el cursor propio"
            ruta = None
            break
        ruta = siguiente

    almacen.guardar(clave, list(acumulado.values()))
    almacen.guardar(_CLAVE_CAMINO[direccion] % comp,
                    {"siguiente": ruta, "ultimo": ultimo, "listo": listo,
                     "total": len(acumulado), "motivo": motivo,
                     "v": VERSION_RECORRIDO,
                     "cuando": dt.datetime.now().isoformat(timespec="seconds")})
    return {"comp": comp, "dir": direccion, "paginas": vueltas, "listo": listo,
            "nuevos": len(acumulado) - antes, "total": len(acumulado),
            "motivo": motivo}


def rescatar_historico(comp, paginas=25):
    """Hacia atrás: los partidos que 365scores ya sacó de la ventana."""
    return caminar_fixture(comp, -1, paginas)


def rescatar_futuro(comp, paginas=25):
    """Hacia adelante: las fechas que todavía no entraron en la ventana."""
    return caminar_fixture(comp, 1, paginas)


def api_historico(q):
    """
    Completa el calendario de un torneo. /api/historico?id=lib
    Con `dir=1` va al futuro, con `dir=-1` al pasado, sin `dir` hace los dos.
    Se puede repetir: cada vez sigue desde donde quedó.
    """
    lid = (q.get("id") or ["lib"])[0]
    cfg = LIGAS.get(lid)
    if not cfg:
        return {"error": "liga desconocida: %s" % lid}
    paginas = max(1, min(80, _int((q.get("paginas") or ["25"])[0], 25)))
    pedido = (q.get("dir") or [""])[0]
    lados = [int(pedido)] if pedido in ("1", "-1") else [-1, 1]

    tramos = [caminar_fixture(cfg["sc"], d, paginas) for d in lados]
    r = {"liga": cfg["nombre"], "comp": cfg["sc"],
         "pasado": next((t for t in tramos if t["dir"] < 0), None),
         "futuro": next((t for t in tramos if t["dir"] > 0), None),
         "nuevos": sum(t.get("nuevos") or 0 for t in tramos),
         "total": max((t.get("total") or 0) for t in tramos),
         "listo": all(t.get("listo") for t in tramos)}
    r["fechas"] = fechas_del_torneo(cfg["sc"])
    if not r["listo"]:
        r["nota"] = ("Todavía queda calendario por traer: volvé a entrar "
                     "para seguir desde acá.")
    return r


def fechas_del_torneo(comp):
    """
    Cuántas fechas tiene el torneo, según 365scores.

    Viene en `roundFilters`, la lista con la que arma su propio selector de
    fechas. Sirve para saber que a la Premier le faltan 30 fechas por bajar
    en vez de creer que el torneo tiene ocho.
    """
    n, _ = almacen.leer("fechas:%s" % comp)
    return n or None


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
        # cuántas fechas tiene el torneo. 365scores lo dice en la lista con
        # la que arma su selector: la fecha más alta que figura ahí es el
        # largo del campeonato, aunque todavía no haya bajado esos partidos.
        topes = [_int(f.get("key", "").rsplit("_", 1)[-1], 0)
                 for f in (data.get("roundFilters") or []) if f.get("key")]
        if topes and max(topes) > 1:
            almacen.guardar("fechas:%s" % comp, max(topes))
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

    # 365scores mezcla el final de la temporada pasada con el arranque de la
    # nueva: para LaLiga devolvía las fechas 36, 37 y 38 del torneo anterior
    # junto a la 1 y la 2. Nos quedamos sólo con la temporada en curso.
    #
    # El número de temporada se le pregunta al torneo, no a los partidos.
    # La diferencia importa cuando el torneo todavía no arrancó: la
    # Champions 2026-27 juega su primera fecha en septiembre, así que hoy
    # 365scores sólo tiene partidos de la temporada anterior. Deduciendo el
    # año "del más alto que se vio" salía el año pasado y la página mostraba
    # una Champions vieja como si fuera la de ahora.
    actual = temporada_actual(comp) or temporadas.get("actual")
    if actual is None:
        vistas = [m.get("temporada") for m in todos if m.get("temporada")]
        actual = max(vistas) if vistas else None

    # Una edición que ya terminó no es la de ahora, diga lo que diga la fuente.
    #
    # Entre una y la otra, 365scores tarda en mover el número de temporada.
    # En agosto seguía diciendo que la Europa League corría la 61, que es la
    # que se jugó y terminó en mayo, y la página mostraba esa fase de liga
    # con su tabla completa —y sus octavos, cuartos y la final— como si fuera
    # la de ahora. La Champions no tenía el problema porque ahí el número sí
    # había avanzado: el mismo caso, resuelto de dos maneras distintas por la
    # fuente.
    #
    # Se la da por terminada sólo si están todos sus partidos jugados Y hay
    # partidos más nuevos guardados —los de la clasificación, que ya se está
    # jugando—. Sin esa segunda condición, la Copa Argentina desaparecería
    # de la página cada enero, entre que termina una edición y arranca la
    # siguiente, cuando ahí lo correcto es seguir mostrando la última.
    termino = ya_termino(acumulado.values(), comp, actual)
    almacen.guardar("termino:%s" % comp, bool(termino))

    if actual is not None:
        # Cada partido se compara contra la temporada de SU competencia. Los
        # de la clasificación vienen mezclados acá y llevan otro número: si
        # se los mide con la vara de la competencia principal, se van todos.
        def es_de_ahora(m):
            suya = m.get("comp")
            if suya and suya != comp:
                actual_suya = temporada_actual(suya)
                if actual_suya is None:
                    return True     # sin dato de la otra, no se descarta
                return m.get("temporada") == actual_suya
            return not termino and m.get("temporada") == actual

        # Ojo con la diferencia entre esconder y borrar.
        #
        # Antes esto perdonaba a los partidos sin temporada anotada —los
        # guardados antes de que empezáramos a anotarla— y por eso la
        # Bundesliga seguía abriendo en la fecha 34 de mayo pasado. Ahora no
        # se muestran, pero TAMPOCO se borran: quedan en la base y, si el
        # recorrido vuelve a pasar por ellos y confirma que son de esta
        # temporada, les completa el dato y reaparecen solos.
        #
        # Borrarlos sería repetir el error que ya vació la base una vez.
        todos = [m for m in acumulado.values() if es_de_ahora(m)]

    # Se guarda TODO lo acumulado, no la lista filtrada. Guardar `todos`
    # convertiría el filtro de pantalla en un borrado silencioso: cada vez
    # que alguien abriera la liga, los partidos escondidos desaparecerían
    # de la base para siempre. Se muestra una cosa y se guarda otra, y eso
    # es a propósito.
    if frescos:
        almacen.guardar(clave, list(acumulado.values()))

    return sorted(todos, key=lambda x: (x["round"] or 0, x["start"] or ""))


def migrar_fixture(comp):
    """
    Vuelve a recorrer un calendario cuando lo guardado quedó viejo de forma.

    Los partidos que se guardaron antes de que empezáramos a anotar de qué
    competencia son —y en qué zona se jugaron— no tienen esos campos, y el
    recorrido usa `setdefault`, así que nunca se los volvía a mirar. Sin la
    zona, la Primera Fase del Federal A no puede armar sus tablas.

    Se detecta una vez, se borran los marcadores de por dónde iba el
    recorrido y la próxima vuelta del rescate los vuelve a leer con todo.
    """
    hecho, _ = almacen.leer("migrado2:%s" % comp)
    if hecho:
        return
    guardado, _ = almacen.leer("fixture:%s" % comp)
    if guardado and any("comp" not in m for m in guardado):
        # NO se borra nada. La primera versión de esto descartaba los
        # partidos sin el campo nuevo —o sea, todos los viejos— y vaciaba
        # de un saque el calendario de cada torneo. Un campo que falta se
        # agrega; no se tira el partido entero. Alcanza con reabrir el
        # recorrido: al pasar de nuevo les completa lo que les falta y
        # deja intacto lo que ya estaba.
        for molde in ("hist:%s", "fut:%s"):
            almacen.guardar(molde % comp, {})
        print("  · calendario %s: se relee para completarle zona y "
              "competencia (%d partidos intactos)"
              % (comp, len(guardado)), flush=True)
    almacen.guardar("migrado2:%s" % comp, True)


# Cada vez que hay que volver a recorrer TODOS los calendarios desde cero
# se sube este número. Sirve para dos cosas: cuando cambia lo que guardamos
# de cada partido, y cuando hay que reparar la base porque se perdió algo.
#
# La v3 existió por lo segundo: una migración mal hecha borró los partidos
# guardados de todos los torneos y dejó los marcadores diciendo que ya se
# había recorrido todo.
#
# La v4 existió por un error encima de ese, y la v5 por otro encima: cada
# reparación corrió con el recorrido todavía roto, dejó los marcadores en
# "listo" de nuevo y la marca ya gastada impedía reintentar. Tres veces el
# mismo error: reparar con la herramienta rota y dar el arreglo por hecho.
#
# Por eso ahora la versión va ADENTRO de cada marcador. Un marcador escrito
# por otra versión no se le cree y se rehace, sin depender de una reparación
# global que puede haber corrido en mal momento. Cambiar la lógica del
# recorrido es subir este número y nada más.
# La v6: el cursor propio se anclaba en el número de partido más chico, y
# los números de 365scores no siguen el calendario. Pidiendo los anteriores
# al 4728058 devuelve el 4728053 pero también el 4728065: el mínimo no se
# movía, el cursor se repetía y el recorrido se daba por terminado en la
# primera vuelta. Ahora el ancla es la fecha.
# La v7: cuando una página venía entera de otra temporada, el cursor de
# respaldo se anclaba en lo guardado —que no había cambiado— y salía igual
# al anterior. El recorrido saltaba ese tramo: a la Primera Nacional le
# faltaban dos ventanas de días enteras en el medio del torneo. Ahora se
# ancla en el borde de la página que acaba de llegar, se guarde o no.
VERSION_RECORRIDO = 7

# Qué versión del programa está corriendo. No cumple ninguna función salvo
# una: cuando algo sigue mal después de un arreglo, esto dice de una si el
# servidor tiene el arreglo puesto o si todavía está corriendo el de antes.
# Sin esto hay que deducirlo de los síntomas, que es exactamente la clase de
# adivinanza que hizo perder tres vueltas con los recorridos.
VERSION_APP = "2026-08-25 · el repechaje de agosto de Champions y Europa ya no se confunde con el play-off de febrero, que la fuente llama igual"


def reparar_recorridos():
    """
    Avisa cuántos recorridos quedaron viejos. No toca nada.

    Antes esto reabría los marcadores a mano y se ejecutaba una sola vez por
    versión. Ese diseño falló tres veces seguidas: si la única corrida
    tocaba en un momento en que el recorrido todavía estaba roto, dejaba
    todo sellado en "listo" y no había forma de reintentarlo.

    Ahora cada marcador lleva adentro la versión que lo escribió y se
    descarta solo cuando no coincide. No hay una corrida que pueda salir mal
    y arruinarlo para siempre: cada recorrido se arregla la próxima vez que
    le toca. Esto queda sólo para dejarlo dicho en el log.
    """
    viejos = 0
    for cfg in LIGAS.values():
        for comp in comps_de(cfg):
            for molde in ("hist:%s", "fut:%s"):
                estado, _ = almacen.leer(molde % comp)
                if estado and estado.get("v") != VERSION_RECORRIDO:
                    viejos += 1
    if viejos:
        print("\n  Recorrido v%d: %d marcadores quedaron de una versión "
              "anterior. Se rehacen solos al pasar; lo guardado no se toca.\n"
              % (VERSION_RECORRIDO, viejos), flush=True)


def reabrir_si_falta(comp):
    """
    Reabre el recorrido cuando el calendario quedó corto pero dice "listo".

    Hace falta porque los marcadores de por dónde iba el recorrido y los
    partidos guardados son dos cosas separadas, y pueden quedar peleados: si
    los partidos se pierden —como pasó cuando la primera migración los
    borró— los marcadores siguen diciendo que ya se recorrió todo, y
    entonces nadie los vuelve a bajar nunca. El torneo se queda con las dos
    fechas de la ventana para siempre.

    La señal es simple: si el torneo tiene 38 fechas y hay 2 guardadas, algo
    está mal. Se reabre y el rescate lo vuelve a llenar.

    Se prueba una vez por día por competencia. Los torneos que traen su
    calendario de otra fuente —LaLiga— siempre van a estar cortos acá y no
    tiene sentido insistirles.
    """
    ultimo, edad = almacen.leer("reabierto:%s" % comp, 60 * 60 * 24)
    if ultimo:
        return
    almacen.guardar("reabierto:%s" % comp, True)

    tope = fechas_del_torneo(comp)
    if not tope or tope < 4:
        return
    guardado, _ = almacen.leer("fixture:%s" % comp)
    rondas = {m.get("round") for m in (guardado or []) if m.get("round")}
    if len(rondas) >= tope:
        return

    reabiertos = []
    for molde, como in (("hist:%s", "atrás"), ("fut:%s", "adelante")):
        estado, _ = almacen.leer(molde % comp)
        if (estado or {}).get("listo"):
            almacen.guardar(molde % comp, {})
            reabiertos.append(como)
    if reabiertos:
        print("  · calendario %s: %d de %d fechas y el recorrido decía estar "
              "completo. Se reabre hacia %s."
              % (comp, len(rondas), tope, " y ".join(reabiertos)), flush=True)


def comps_de(cfg):
    """Todas las competencias que forman un torneo: la principal y sus previas."""
    return [cfg["sc"]] + list(cfg.get("sc_extra") or [])


# Cómo se llama cada ronda de la clasificación europea. Se traduce en el
# borde, apenas entra: es más confiable que adivinar después con textos que
# 365scores escribe de diez formas distintas ("3rd Qualifying Round",
# "Tercera Ronda de Clasificación", "Q3"...).
def nombre_de_previa(crudo):
    t = norm(crudo)
    if "prelim" in t:
        return "Ronda preliminar"
    if "play" in t or "repechaje" in t:
        return "Repechaje de acceso"
    for palabra, nombre in ((("3", "tercera", "third"), "Fase previa 3"),
                            (("2", "segunda", "second"), "Fase previa 2"),
                            (("1", "primera", "first"), "Fase previa 1")):
        if any(p in t for p in palabra):
            return nombre
    return "Fase previa 1"


def fixture_de_liga(cfg, ttl=120):
    """
    El calendario de un torneo, juntando las competencias que lo componen.

    La Champions es el caso: la fase de liga es una competencia y la
    clasificación previa es otra. Para el hincha es el mismo torneo, así que
    se juntan acá y el resto de la página ni se entera.
    """
    juegos = []
    for comp in comps_de(cfg):
        try:
            traidos = _sc_fixture(comp, ttl=ttl)
        except Exception:
            if comp == cfg["sc"]:
                raise        # si falla la principal, falla el torneo
            continue
        # Una previa es la de una competencia declarada como previa en
        # `sc_extra`. Ojo con no tomar "cualquier competencia que no sea la
        # principal": a la Sudamericana le llegan partidos mezclados de
        # otros torneos y con esa regla el pre octavos terminaba renombrado
        # como "Fase previa 1" y metido en el cuadro equivocado.
        clasificatorias = set(cfg.get("sc_extra") or [])
        for m in traidos:
            suya = m.get("comp") or comp
            if suya in clasificatorias:
                m["stage"] = nombre_de_previa(m.get("etapaFuente")
                                              or m.get("stage") or "")
                m["previa"] = True
                m["stageNum"] = -10 + rango_etapa(m["stage"])
        juegos.extend(traidos)
    # El mismo partido no puede venir dos veces. Y si vino por los dos
    # lados, manda el nombre de ronda de la previa: la competencia principal
    # lo lista sin decir a qué eliminatoria pertenece.
    unicos = {}
    for m in juegos:
        k = str(m.get("id"))
        if k not in unicos:
            unicos[k] = m
        elif m.get("previa") and not unicos[k].get("previa"):
            unicos[k].update({"stage": m["stage"], "previa": True,
                              "stageNum": m.get("stageNum")})
    return sorted(unicos.values(), key=lambda x: (x.get("start") or ""))


def ya_termino(juegos, comp, actual):
    """
    ¿La edición que la fuente da por corriente ya se jugó entera?

    Entre una y la otra, 365scores tarda en mover el número de temporada. En
    agosto seguía diciendo que la Europa League corría la 61, que es la que
    terminó en mayo, y la página mostraba esa fase de liga con su tabla
    completa —y sus octavos, cuartos y la final— como si fuera la de ahora.
    La Champions no tenía el problema porque ahí el número sí había
    avanzado: el mismo caso, resuelto de dos maneras distintas por la fuente.

    Se la da por terminada sólo si están todos sus partidos jugados Y hay
    partidos más nuevos guardados —los de la clasificación, que ya se está
    jugando—. Sin esa segunda condición, la Copa Argentina desaparecería de
    la página cada enero, entre que termina una edición y arranca la
    siguiente, cuando ahí lo correcto es seguir mostrando la última.
    """
    if actual is None:
        return False
    juegos = list(juegos)
    suyos = [m for m in juegos
             if m.get("comp") in (None, comp) and m.get("temporada") == actual]
    if not suyos or not all(m.get("status") == "FIN" for m in suyos):
        return False
    ultimo = max((m.get("start") or "") for m in suyos)[:10]
    if not ultimo:
        return False
    hace_rato = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    hay_mas_nuevo = any((m.get("start") or "")[:10] > ultimo for m in juegos)
    return ultimo < hace_rato and hay_mas_nuevo


def edicion_terminada(comp):
    """Lo mismo, pero leído de lo que ya se calculó al servir el calendario."""
    guardado, _ = almacen.leer("termino:%s" % comp)
    return bool(guardado)


def temporada_actual(comp):
    """
    Qué temporada está corriendo, según el propio torneo.

    Se le pregunta a la ficha de la competencia y no a los partidos, porque
    entre una temporada y la otra los partidos que hay son los viejos y
    deducirlo de ahí da siempre el año anterior. Se guarda por un día: no
    cambia más seguido que eso.
    """
    clave = "temporada:%s" % comp
    guardado, edad = almacen.leer(clave, 60 * 60 * 24)
    if guardado:
        return guardado
    try:
        data = fetch("competitions", {"competitions": comp}, ttl=3600)
        for c in (data.get("competitions") or []):
            if c.get("id") == comp and c.get("currentSeasonNum"):
                almacen.guardar(clave, c["currentSeasonNum"])
                return c["currentSeasonNum"]
    except Exception:
        pass
    viejo, _ = almacen.leer(clave)
    return viejo


# ── Canal de TV y goleadores de cada partido ─────────────────────────────
#
# Los dos salen del detalle del partido, un pedido por partido. Es caro para
# pedirlo en cada visita, pero no cambia: una vez terminado el partido los
# goles son los que son. Por eso se cachea fuerte y sólo se refresca lo que
# está en juego.
def detalle_liviano(game_id, en_juego=False, liga="lpf"):
    """
    Los goles y el canal de un partido.

    La caché era de doce horas para lo que no estuviera en juego, y ahí
    estaba media trampa: un partido leído antes del pitazo inicial —sin
    ningún gol todavía— quedaba guardado doce horas, así que la lista lo
    mostraba sin goles el resto del día aunque la ficha del partido, que
    pide el detalle por otro lado, los mostrara todos. Peor todavía: al
    querer arreglarlo, el pedido volvía a caer en esa misma foto vieja.

    Ahora son cinco minutos. No cuesta casi nada porque el detalle de un
    partido terminado ya no se vuelve a pedir: queda guardado aparte, y de
    eso se ocupa `detalle_al_dia`.
    """
    ttl = 30 if en_juego else 300
    # El crudo se guarda sólo mientras el partido se juega, que es cuando
    # tener lo último bueno vale algo si la fuente se cae. Terminado el
    # partido no: de acá ya salieron los goles y quiénes jugaron, guardados
    # aparte, y el crudo son sesenta kilobytes que nadie vuelve a leer. Ese
    # era el 84% del disco, y lo llenaba este mismo recorrido.
    data = fetch("game", {"gameId": game_id}, ttl=ttl, guardar=bool(en_juego))
    g = data.get("game") or {}
    hid = (g.get("homeCompetitor") or {}).get("id")
    quien = {m.get("id"): (m.get("name") or m.get("shortName") or "")
             for m in (g.get("members") or [])}
    dorsal = {m.get("id"): m.get("jerseyNumber") for m in (g.get("members") or [])}

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
            titular = (mm.get("status") == 1
                       or norm(mm.get("statusText")) in ("titular", "starting", "starter"))
            if titular:
                anotar_partido(nom, liga, game_id)
            anotar_paso(nom, club, liga, escudo)
            # el plantel del club: dorsal, puesto y si fue titular
            anotar_plantel(club, {
                "nombre": nom,
                "n": mm.get("jerseyNumber") or dorsal.get(mm.get("id")),
                "puesto": puesto_ar((mm.get("position") or {}).get("name")),
                "id": (g.get("members") and next(
                    (m.get("athleteId") for m in g["members"]
                     if m.get("id") == mm.get("id")), None)),
            }, titular, (g.get("startTime") or "")[:10])
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
    # Se anota si el partido ya estaba terminado según la fuente, no según
    # lo que creía el que llamó: es lo que distingue un dato definitivo de
    # una foto sacada a los veinte minutos.
    anotar_goles(liga, game_id, goles, status_of(g) == "FIN")

    tv = limpiar_tv([t.get("name") for t in (g.get("tvNetworks") or []) if t.get("name")])
    if tv:
        almacen.guardar("tv:%s:%s" % (liga, game_id), tv)
    tanda = [x for x in goles if x.get("penales") and not x.get("anulado")]
    pen = ({"h": sum(1 for x in tanda if x["side"] == "h"),
            "a": sum(1 for x in tanda if x["side"] == "a")} if tanda else None)
    return {"tv": tv, "goles": goles, "penales": pen}


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

    Igual que la portada: se contesta con lo último armado y se completa
    por atrás. Acá importa el doble, porque la página vuelve a pedir esto
    cada cuatro segundos mientras queden partidos sin resolver, y antes
    cada una de esas vueltas armaba todo de nuevo.
    """
    lid = (q.get("id") or ["lpf"])[0]
    rnd = (q.get("round") or [None])[0]
    fecha = (q.get("date") or [None])[0]
    return al_toque("det:%s:%s:%s" % (fecha or "", lid, rnd or ""),
                    lambda: armar_detalles(lid, rnd, fecha),
                    # corto porque acá viven los goles de lo que se está
                    # jugando; igual la respuesta sale al toque, esto sólo
                    # dice cada cuánto se rearma por atrás
                    frescura=8)


def armar_detalles(lid, rnd, fecha):

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
    #
    # Pero "guardado" no es lo mismo que "listo": un partido leído mientras
    # se jugaba deja los goles que iban hasta ese momento. Eso lo decide
    # `detalle_al_dia`, que además compara la cantidad con el resultado.
    pendientes = []
    for x, g in con_id:
        guardado, tv, listo = detalle_al_dia(x, g)
        if not listo:
            pendientes.append((x, g))
            continue
        pen, _ = almacen.leer("pen:%s:%s" % (x, g["liveId"]))
        salida[str(g["id"])] = {
            "tv": tv or [],
            "penales": pen,
            "goles": [{"player": q["j"], "equipo": q.get("e") or "",
                       "min": q.get("m"), "added": 0,
                       "side": q.get("s") or "h", "sub": "",
                       "anulado": False, "penales": False}
                      for q in guardado],
        }
    faltan = max(0, len(pendientes) - TOPE)
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

    # `faltan` le dice a la página que todavía queda para traer: en vez de
    # dejar la mitad de los partidos sin goleadores, vuelve a pedir en unos
    # segundos y se completa sola. Los grupos de la Libertadores tienen casi
    # cien partidos y no entran en un solo pedido.
    return {"detalles": salida, "consultados": len(pendientes),
            "faltan": faltan,
            "sinDetalle": len(pares) - len(con_id)}


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
    # 3. La primera que todavía no terminó.
    #
    # Ojo con dos casos opuestos. Una fecha puede estar EN CURSO —empezó el
    # viernes, sigue el domingo— y entonces no entra en "la próxima por
    # empezar": eso hacía que LaLiga abriera en la fecha 2 cuando la 1 se
    # estaba jugando. Y por el otro lado, un partido suspendido hace dos
    # meses no puede dejar la página clavada en esa fecha para siempre.
    #
    # Se toma la primera sin terminar, siempre que no haya arrancado hace
    # más de dos semanas: lo que empezó hace más que eso y sigue abierto es
    # un partido postergado, no la fecha en curso.
    limite = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)).isoformat()
    abiertas = []
    for r in rounds:
        juegos = por_fecha.get(r, [])
        if not any(g["status"] != "FIN" for g in juegos):
            continue
        arranque = min((g["start"] for g in juegos if g["start"]), default="")
        if arranque and arranque >= limite:
            abiertas.append((arranque, r))
    if abiertas:
        return min(abiertas)[1]
    # 4. el torneo ya terminó
    return rounds[-1]


# El orden natural de las rondas de una copa. Se usa para acomodar las que
# agregamos a mano: si no, "Cuartos de final" caía después de la final sólo
# porque se sumó al final de la lista.
_RANGO_ETAPA = [
    # Las eliminatorias europeas van todas antes de la fase de liga. El
    # "repechaje de acceso" es el play-off de agosto —el que da entrada al
    # torneo— y tiene que quedar antes; el "play-off" a secas es el de
    # febrero, entre la fase de liga y los octavos. Van primero en la lista
    # porque gana la primera coincidencia.
    (("ronda preliminar",), 0.05),
    (("fase previa 1", "primera fase previa"), 0.1),
    (("fase previa 2", "segunda fase previa"), 0.2),
    (("fase previa 3", "tercera fase previa"), 0.4),
    # A las clasificatorias de agosto 365scores las llama "Primera/Segunda/
    # Tercera Ronda". Sin estas tres líneas no encajaban en ninguna fase del
    # torneo y los partidos se descartaban enteros; y "Tercera Ronda" era
    # peor, porque caía en `tercer` —el partido por el tercer puesto— y se
    # ordenaba entre la semifinal y la final. Van acá arriba, antes que
    # `tercer`, porque gana la primera coincidencia de la lista.
    (("primera ronda", "ronda 1"), 0.1),
    (("segunda ronda", "ronda 2"), 0.2),
    (("tercera ronda", "ronda 3"), 0.4),
    (("repechaje de acceso", "play-off de acceso"), 0.8),
    (("fase de liga", "league phase"), 1),
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
    # La Libertadores 2026 también tiene una ronda entre los grupos y los
    # octavos: la "Eliminatoria de octavos", donde los segundos de zona se
    # cruzan antes de entrar al cuadro.
    "lib": ["Fase 1", "Fase 2", "Fase 3", "Fase de grupos", "Pre octavos",
            "Octavos de final", "Cuartos de final", "Semifinal", "Final"],
    "sud": ["Primera fase", "Fase de grupos", "Pre octavos", "Octavos de final",
            "Cuartos de final", "Semifinal", "Final"],
    "ca":  ["32avos de final", "16avos de final", "Octavos de final",
            "Cuartos de final", "Semifinal", "Final"],
    # Ojo con los dos "play-off" de la Champions, que no son el mismo: el
    # de agosto es para ENTRAR a la fase de liga —acá "Repechaje de
    # acceso"— y el de febrero es para entrar a octavos.
    "champions": ["Ronda preliminar", "Fase previa 1", "Fase previa 2",
                  "Fase previa 3", "Repechaje de acceso", "Fase de liga",
                  "Play-offs", "Octavos de final", "Cuartos de final",
                  "Semifinal", "Final"],
    "europa": ["Fase previa 1", "Fase previa 2", "Fase previa 3",
               "Repechaje de acceso", "Fase de liga", "Play-offs",
               "Octavos de final", "Cuartos de final", "Semifinal", "Final"],
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


# Los dos "play-off" de la Champions, que la fuente llama igual
#
# UEFA juega dos rondas con ese nombre y no son la misma cosa: la de agosto
# es el último escalón de la clasificación —el que la gana entra a la fase
# de liga— y la de febrero es la que da entrada a los octavos, entre los
# que salieron del 9° al 24°. 365scores manda "Playoff" en las dos, así que
# por el nombre no hay manera de saber cuál es.
#
# Lo que sí las separa sin lugar a dudas es cuándo se juegan. La
# clasificación va de junio a agosto y termina antes de que arranque la
# fase de liga; la otra es a mitad de febrero. En el calendario de este año
# los de la Champions son el 18 y el 19 de agosto, y los de la Europa el
# 20. No hay play-off de acceso en otoño ni de octavos en verano.
MESES_DE_CLASIFICACION = (6, 7, 8)


def desempatar_playoff(fase, fases, cuando):
    """
    De los dos play-off con el mismo nombre, cuál es: lo dice la fecha.

    Sólo se mete cuando hay ambigüedad de verdad: si el torneo tiene una
    sola fase con ese rango —la Libertadores, la Sudamericana— no hay nada
    que desempatar y se devuelve lo que vino.
    """
    if not fase or not cuando or rango_etapa(fase) != 2:
        return fase
    acceso = next((f for f in fases if rango_etapa(f) == 0.8), None)
    if not acceso:
        return fase
    try:
        mes = int(str(cuando)[5:7])
    except (TypeError, ValueError):
        return fase
    return acceso if mes in MESES_DE_CLASIFICACION else fase


def etapa_de_copa(liga_id, stage, round_=None, cuando=""):
    """
    Qué instancia de la copa se está jugando, escrita como la escribe el torneo.

    Hace falta para la página de un partido, que trabaja con un partido solo.
    El calendario completo resuelve esto mirando todas las fases juntas
    (`api_liga_games`), pero desde acá no hay con qué comparar: lo único que
    llega es el `stageName` de 365scores, escrito a su manera —"Octavos de
    Final", "Semifinales", "Primera Fase"—, que `canonizar_fase` lleva al
    nombre del torneo.

    En la fase de grupos ese campo llega vacío y lo único que viene es el
    número de fecha. Ahí se resuelve por descarte: la única fase de una copa
    que numera fechas es la de grupos —o la de liga, en Europa—, que es la
    que tiene rango 1.
    """
    fases = FASES_COPA.get(liga_id)
    if not fases:
        return ""                      # no es copa: la fecha alcanza
    if (stage or "").strip():
        return desempatar_playoff(canonizar_fase(stage, fases),
                                  fases, cuando) or ""
    if round_:
        return next((f for f in fases if rango_etapa(f) == 1), "")
    return ""


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


def armar_llaves(games, etapas, liga_id=""):
    """
    Agrupa el fixture en series para dibujar el cuadro.

    Cada llave son los dos equipos que se cruzan en una etapa, con el global
    de los dos partidos. Si es a un solo partido —Copa Argentina— el global
    es ese resultado. Se devuelve una lista por etapa, de la más lejana a la
    final, que es como se lee un cuadro.
    """
    # Todo lo que se juega por eliminación entra al cuadro: las fases previas
    # también son llaves de ida y vuelta y merecen verse. Lo único que queda
    # afuera es la fase de grupos. Cada bloque dice si es previa, para que la
    # página muestre un cuadro u otro según dónde estés parado.
    def del_cuadro(nombre):
        return rango_etapa(nombre) != 1

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
        series = (por_etapa.get(et) or {})
        # ¿esta ronda es a ida y vuelta? Lo dice la ronda entera, no cada
        # llave: si a una le falta la vuelta por cargar, no está terminada
        # aunque tengamos su único partido jugado.
        por_serie = max((len(v) for v in series.values()), default=1)
        llaves = []
        for partidos in series.values():
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
            cerrada = (jugados == len(partidos) and jugados > 0
                       and len(partidos) >= por_serie)
            posiciones = [p.get("slot") for p in partidos if p.get("slot")]

            # Quién pasó lo dice la fuente, no la suma de goles: una serie
            # puede terminar 1-1 y resolverse por penales, y ahí sumando no
            # hay ganador. Boca pasaba y el cuadro no lo marcaba.
            def clasifico(nombre):
                for p in partidos:
                    for lado in ("home", "away"):
                        if (norm(p[lado]["name"]) == norm(nombre)
                                and p[lado].get("pasa")):
                            return True
                return False

            # nadie pasa hasta que la serie esté terminada
            pasa_a, pasa_b = clasifico(a["name"]), clasifico(b["name"])
            if not cerrada:
                pasa_a = pasa_b = False
            elif not (pasa_a or pasa_b) and ga != gb:
                pasa_a, pasa_b = ga > gb, gb > ga

            # el resultado de la tanda, si la hubo, para mostrarlo al lado
            penales = None
            for p in partidos:
                guardado, _ = almacen.leer("pen:%s:%s" % (liga_id, p["id"]))
                if guardado:
                    mismo = norm(p["home"]["name"]) == norm(a["name"])
                    penales = ([guardado["h"], guardado["a"]] if mismo
                               else [guardado["a"], guardado["h"]])

            llaves.append({
                "slot": min(posiciones) if posiciones else None,
                "penales": penales,
                "equipos": [
                    {"team": a, "goles": ga if jugados else None, "pasa": pasa_a},
                    {"team": b, "goles": gb if jugados else None, "pasa": pasa_b},
                ],
                # cada partido con su local y su visitante de verdad: en la
                # vuelta se dan vuelta, y mostrando siempre el mismo orden el
                # resultado quedaba del lado equivocado
                "partidos": [{"id": p["id"], "start": p.get("start"),
                              "tramo": p.get("tramo"), "status": p.get("status"),
                              "gh": p.get("gh"), "ga": p.get("ga"),
                              "liveId": p.get("liveId"),
                              "home": p["home"], "away": p["away"]}
                             for p in partidos],
                "cerrada": cerrada,
            })
        # por lugar en el cuadro si lo sabemos; si no, por fecha
        llaves.sort(key=lambda x: (x["slot"] if x["slot"] else 999,
                                   x["partidos"][0]["start"] or ""))
        salida.append({"etapa": et, "llaves": llaves,
                       "previa": rango_etapa(et) < 1})
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
                pegar_marcadores(games, fixture_de_liga(cfg))
            except Exception:
                pass
        else:
            try:
                games, err = fixture_de_liga(cfg), None
            except Exception:
                pass
    elif not cfg.get("base"):
        # sin fixture propio ni de AFA: el calendario sale entero de 365scores
        try:
            games = fixture_de_liga(cfg)
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

    # De dónde sale el nombre y el escudo de cada equipo.
    #
    # Cuando el calendario lo arma AFA, los equipos vienen sin escudo y con
    # el nombre abreviado ("Chaco FE"), así que hay que ir a buscarlos a la
    # tabla de posiciones emparejando por nombre.
    #
    # Cuando el calendario ya viene de 365scores, no: cada partido trae el
    # escudo y el nombre de sus dos equipos, tomados del partido mismo. Ir
    # igual a la tabla era cambiarlos por los de otro club cada vez que el
    # emparejado se equivocaba, y en una copa internacional se equivoca
    # seguido porque hay clubes que se llaman igual: Nacional es el de
    # Uruguay y también el de Potosí, y hay una Universidad Católica en
    # Chile y otra en Ecuador. Ningún emparejado por nombre puede
    # distinguirlos, porque el nombre es el mismo. De la tabla se toma
    # nada más lo que el partido no trae.
    propio = not cfg.get("base")
    for m in games:
        za, ta = buscar(m["home"]["name"])
        zb, tb = buscar(m["away"]["name"])
        for lado, t in (("home", ta), ("away", tb)):
            if not t:
                continue
            if propio:
                for campo in ("logo", "short", "site"):
                    if not m[lado].get(campo):
                        m[lado][campo] = t[campo]
                m[lado]["canon"] = m[lado].get("canon") or m[lado]["name"]
            else:
                m[lado].update({"logo": t["logo"], "short": t["short"], "site": t["site"],
                                "name": nombre_mas_completo(m[lado]["name"], t["name"]),
                                "canon": t["name"]})
        # La zona sale de en qué tabla está cada equipo. Si de uno solo se
        # pudo averiguar, se usa esa: en estas categorías las zonas juegan
        # separadas, así que ambos están en la misma. Sólo se marca como
        # interzonal cuando de los dos se sabe y no coinciden.
        zona = za or zb
        m["zone"] = (zona or "").replace("Zona ", "").replace("Grupo ", "") or None
        # Si ninguno de los dos está en las tablas de ahora —pasa con toda
        # la Primera Fase del Federal A, que ya terminó— se usa el número de
        # zona que trae el propio partido. Antes quedaban todos como
        # "Interzonal", que era lo único que no eran.
        if not m["zone"] and m.get("slot"):
            m["zone"] = str(m["slot"])
        m["interzonal"] = bool(za and zb and za != zb)

    # El id de 365scores para cada partido del fixture de AFA. Se busca en
    # todo lo acumulado, no sólo en lo que se juega hoy: si no, las fechas
    # anteriores quedaban sin goleadores, sin canal y sin poder abrirse.
    if cfg.get("base"):
        try:
            porNombre, porId = {}, {}
            for x in fixture_de_liga(cfg):
                clave = (norm(x["home"]["name"])[:8], norm(x["away"]["name"])[:8])
                porNombre.setdefault(clave, []).append(x)
                porId[str(x["id"])] = x
            # Un partido de 365scores no puede engancharse a dos de AFA.
            usados = {str(m["liveId"]) for m in games if m.get("liveId")}

            def dia_de(x):
                try:
                    return dt.date.fromisoformat((x.get("start") or "")[:10])
                except ValueError:
                    return None

            for m in games:
                if m.get("liveId"):
                    continue
                cand = [x for x in porNombre.get((norm(m["home"]["name"])[:8],
                                                  norm(m["away"]["name"])[:8]), [])
                        if str(x["id"]) not in usados]
                if not cand:
                    continue

                # Se prefiere el mismo día. Pero si el partido se postergó,
                # AFA sigue publicando la fecha original y 365scores la real,
                # y ahí no coinciden: entonces vale el más cercano.
                #
                # El límite de tres semanas es lo que separa una postergación
                # de la otra rueda: los mismos dos equipos se vuelven a
                # cruzar recién a los cuatro o cinco meses, así que no hay
                # forma de confundirlas. Sin esto, las fechas 23 y 24 de la
                # Primera Nacional quedaban con seis de dieciocho partidos
                # enganchados y el resto sin poder abrirse.
                mio = dia_de(m)
                elegido = next((x for x in cand if dia_de(x) == mio and mio), None)
                if not elegido and mio:
                    cerca = [(abs((dia_de(x) - mio).days), x)
                             for x in cand if dia_de(x)]
                    cerca = [(d, x) for d, x in cerca if d <= 21]
                    if cerca:
                        elegido = min(cerca, key=lambda p: p[0])[1]
                # Un único candidato sólo vale si no hay fechas que comparar.
                # Con fechas manda la cercanía: si el único candidato está a
                # cuatro meses es el partido de la otra rueda, y engancharlo
                # acá se lo roba a la fecha que de verdad le corresponde.
                if not elegido and len(cand) == 1 and (
                        not mio or not dia_de(cand[0])):
                    elegido = cand[0]

                if elegido:
                    m["liveId"] = elegido["id"]
                    usados.add(str(elegido["id"]))
                    m["venue"] = m.get("venue") or elegido.get("venue") or ""

            # El resultado que AFA no cargó.
            #
            # Pasa: la fecha 21 de la Primera Nacional quedó con nueve
            # marcadores de dieciocho, con los dieciocho partidos ya
            # jugados y enganchados a 365scores. Si el partido terminó y
            # el otro lado tiene el marcador, se completa.
            #
            # Sólo se llena lo que falta: si AFA cargó un resultado, ese
            # manda. Es la fuente oficial y no se le pisa nada.
            for m in games:
                lv = porId.get(str(m.get("liveId") or ""))
                if not lv or m.get("gh") is not None:
                    continue
                if lv.get("status") == "FIN" and lv.get("gh") is not None:
                    m["gh"], m["ga"] = lv["gh"], lv["ga"]
                    m["status"] = "FIN"
                    m["statusText"] = lv.get("statusText") or m.get("statusText")
        except Exception:
            pass

    # partidos en curso
    vivos, jugando = 0, set()
    try:
        raw = fetch("games/current", {"competitions": cfg["sc"]}, ttl=15).get("games", [])
        porNombre = {}
        for m in games:
            porNombre[(norm(m["home"]["name"]), norm(m["away"]["name"]))] = m
        # Esta ventana llega fresca y trae el país de cada club, que el
        # calendario guardado de las copas sudamericanas no tiene. Se anota
        # al pasar: es la única parte de acá que lo sabe.
        aprendidos = []
        for g in raw:
            lv = map_game(g)
            aprendidos.append(lv)
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
        if cfg.get("internacional"):
            recordar_paises(aprendidos)
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
        # Cuándo se juega cada fase, que es lo que distingue a los dos
        # play-off de la Champions: la fuente los llama igual a los dos.
        cuando_stage = {}
        for g in games:
            sn, ini = g.get("stageNum"), g.get("start") or ""
            if ini and (sn not in cuando_stage or ini < cuando_stage[sn]):
                cuando_stage[sn] = ini

        def resolver(crudo, sn=None):
            return desempatar_playoff(canonizar_fase(crudo, fases), fases,
                                      cuando_stage.get(sn))

        libres = [f for f in (fases or [])
                  if f not in {resolver(n, sn)
                               for sn, n in nombre_stage.items()}]
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
            if not fases:
                return et
            # La fecha del partido, no la de la fase: en el borde entre dos
            # meses los dos dan lo mismo, y así no depende de qué partido
            # de la fase se mire primero.
            return desempatar_playoff(canonizar_fase(et, fases), fases,
                                      g.get("start")
                                      or cuando_stage.get(g.get("stageNum")))

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
        # Si la fuente no manda la fase, se deduce del calendario. Sin esto
        # el Federal A mezcla su Primera Fase con la Segunda, porque las dos
        # numeran las fechas desde el uno.
        if cfg.get("fases_por_calendario"):
            try:
                if marcar_fases_por_calendario(games,
                                               cfg["fases_por_calendario"]):
                    # Y con las fases separadas, la zona de cada partido se
                    # recalcula adentro de la suya: leída contra las zonas
                    # de hoy, toda la Primera Fase salía "Interzonal".
                    zonas_de_cada_fase(games)
            except Exception:
                pass

        # La fase de un partido se identifica por su número y, si no lo trae
        # o si todos comparten el mismo, por el nombre. El Federal A llegó a
        # tener las dos fases con el mismo número y volvían a mezclarse.
        def clave_fase(g):
            sn = g.get("stageNum")
            nom = (g.get("stage") or "").strip()
            return (sn if sn is not None else -1, nom)

        por_stage = {}
        for g in games:
            k = clave_fase(g)
            if k == (-1, ""):
                continue
            d = por_stage.setdefault(k, {"rounds": set(), "primero": "9999"})
            if g.get("round"):
                d["rounds"].add(g["round"])
            ini = g.get("start") or "9999"
            if ini < d["primero"]:
                d["primero"] = ini

        if len(por_stage) > 1:
            orden = sorted(por_stage, key=lambda k: (k[0], por_stage[k]["primero"]))
            numero = {k: i + 1 for i, k in enumerate(orden)}
            # Una fase merece pestaña si tiene varias fechas. El repechaje
            # de ascenso de la Bundesliga son dos partidos y armaba una
            # pestaña "Descenso/Ascenso" al lado de las 34 fechas del
            # torneo, que además es lo primero que se abría.
            MIN_FECHAS_FASE = 3
            for k in orden:
                d = por_stage[k]
                if len(d["rounds"]) < MIN_FECHAS_FASE:
                    continue
                fases_liga.append({"num": numero[k],
                                   "nombre": k[1] or "Fase %s" % k[0],
                                   "rounds": sorted(d["rounds"])})
            # Con una sola fase que valga la pena no hay nada que elegir:
            # el selector de fases sobra y encima se llevaba el lugar del
            # selector de fechas.
            if len(fases_liga) < 2:
                fases_liga = []
            else:
                for g in games:
                    g["fase"] = numero.get(clave_fase(g))

                # Dos fases que numeran las fechas desde el uno se pisan:
                # la fecha 1 termina con los partidos de las dos y muestra
                # el doble. Acá se corren las de la segunda para que sigan
                # a las de la primera —1 a 18 y después 19 a 27— y cada
                # fecha vuelva a ser una sola.
                #
                # El número corrido es de uso interno. Cada fase viaja con
                # su `desde`, así el botón sigue diciendo "Fecha 1" de la
                # Segunda Fase y no "Fecha 19", que no existe.
                corrido = 0
                for f in fases_liga:
                    suyas = f["rounds"]
                    if not suyas:
                        continue
                    salto = corrido + 1 - suyas[0] if corrido >= suyas[0] else 0
                    if salto:
                        for g in games:
                            if g.get("fase") == f["num"] and g.get("round"):
                                g["round"] += salto
                        f["rounds"] = [r + salto for r in suyas]
                    f["desde"] = f["rounds"][0]
                    corrido = f["rounds"][-1]

    rnd = (q.get("round") or [None])[0]
    rounds = sorted({g["round"] for g in games if g["round"]})
    # En una copa, la etapa existe aunque todavía no tenga partidos: los
    # cuartos se sortean cuando terminan los octavos. Sin el botón no hay
    # manera de mirar quiénes van clasificando, que es justo lo que uno
    # quiere ver la semana que se están jugando los octavos.
    if cfg.get("copa") and etapas:
        rounds = sorted(set(rounds) | set(range(1, len(etapas) + 1)))

    por_fecha = {}
    for g in games:
        por_fecha.setdefault(g["round"], []).append(g)
    actual = fecha_actual(rounds, por_fecha)

    sin_zona = sorted({g[s]["name"] for g in games for s in ("home", "away")
                       if not g["zone"]})
    # El cuadro se arma antes de filtrar por etapa: necesita el torneo entero.
    #
    # Y va separado en dos. Las eliminatorias previas son un torneo aparte
    # —los que las ganan recién entran al cuadro grande— así que mezclarlas
    # con los octavos daba un cuadro gigante y sin sentido, con ramas que no
    # se conectan con nada. Cada uno en su pestaña.
    llaves = llaves_previa = None
    if cfg.get("copa"):
        previas = [e for e in etapas if rango_etapa(e) < 1]
        del_torneo = [e for e in etapas if rango_etapa(e) >= 1]
        llaves = armar_llaves(games, del_torneo, lid)
        if previas and not cfg.get("sin_cuadro_previa"):
            suyos = [g for g in games if (g.get("etapa") or g.get("stage")) in previas]
            llaves_previa = armar_llaves(suyos, previas, lid)

    if rnd:
        games = [g for g in games if str(g["round"]) == str(rnd)]
    # La bandera del país de cada club, en los torneos internacionales. Va
    # acá, después de filtrar: se copian sólo los partidos que se mandan.
    games = con_banderas(games, lid)
    res = {"games": games, "count": len(games), "rounds": rounds, "current": actual,
           "live": vivos, "interzonal": sum(1 for g in games if g["interzonal"]),
           "sinZona": sin_zona, "nombre": cfg["nombre"],
           "copa": bool(cfg.get("copa")), "etapas": etapas,
           "fasesLiga": fases_liga}
    # Cuántas fechas tiene el torneo en total. Si son más de las que hay
    # cargadas, el calendario todavía se está bajando: mejor decirlo que
    # dejar creer que la Premier tiene ocho fechas.
    total_fechas = fechas_del_torneo(cfg["sc"]) if not cfg.get("copa") else None
    if total_fechas and rounds:
        res["totalFechas"] = total_fechas
        if max(rounds) < total_fechas:
            res["bajando"] = True
    # La final se juega en cancha neutral y la sede se sabe desde antes que
    # los finalistas, así que no viene en el fixture: para la fuente ese
    # partido todavía no existe.
    if cfg.get("final"):
        res["final"] = dict(cfg["final"], etapa="Final")
    if llaves is not None:
        res["llaves"] = llaves
    if llaves_previa and any(b.get("llaves") for b in llaves_previa):
        res["llavesPrevia"] = llaves_previa
    if err:
        res["error"] = err
    # La página de un partido de copa quiere los cruces de su instancia y
    # nada más. Mandarle el calendario entero —163 partidos en la
    # Libertadores— para dibujar ocho cajitas al costado es gastarle la
    # conexión al que está mirando el partido en el celular.
    if (q.get("solo") or [""])[0] == "llaves":
        return {k: v for k, v in res.items()
                if k in ("nombre", "copa", "etapas", "llaves", "llavesPrevia",
                         "final", "error")}
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
    _guardar_en_cache(url, out)
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
    _guardar_en_cache(url, out)
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
        salida["bandera"] = bandera_url(a["nationalityId"])
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


# Los cinco ejes del gráfico.
#
# La idea es que midan cosas distintas: tener la pelota, generar, convertir,
# aguantar atrás y circular. Poner remates, goles y efectividad juntos sería
# medir tres veces lo mismo, porque efectividad es goles sobre remates.
#
# "Solidez" son los goles recibidos dados vuelta. En un radar el polígono
# más grande se lee como "mejor", así que un eje donde más es peor confunde:
# un equipo que recibe muchos goles se vería enorme. Invertido, más grande
# quiere decir que le hacen menos.
EJES_RADAR = [
    {"eje": "Posesión", "tipo": "stat", "unidad": "%",
     "claves": ["posesion de balon", "posesion"]},
    {"eje": "Remates", "tipo": "stat", "unidad": "",
     "claves": ["total remates", "remates"]},
    {"eje": "Efectividad", "tipo": "efectividad", "unidad": "%", "claves": []},
    {"eje": "Solidez", "tipo": "recibidos", "unidad": "", "invertido": True,
     "claves": []},
    # Ojo con este: "pases completados" es la CANTIDAD de pases (330 por
    # partido), no la precisión. Mezclarlos daba un eje de 330% que no
    # significaba nada. Sólo vale la precisión, y si no viene, el eje se cae
    # solo en lugar de mostrar un número inventado.
    {"eje": "Al arco", "tipo": "stat", "unidad": "",
     "claves": ["remates al arco", "tiros al arco", "remates a puerta"]},
]


def anotar_stats(liga, game_id, local, visita, vals_h, vals_a, gh=None, ga=None):
    """
    Guarda las estadísticas de un partido, por equipo.

    Sin esto no se puede promediar nada: hoy se piden para mostrar el
    gráfico de un partido y se tiran. Guardándolas, el promedio de un
    equipo y el de toda la liga salen de la base, sin pedir nada.

    Van también los goles, porque la efectividad y la solidez no salen de
    las estadísticas sino del resultado.

    El índice guarda los últimos quinientos partidos, que son más de un
    torneo y hasta más de una temporada. Hoy el radar del club no los usa
    —promedia sólo el torneo que se está jugando— pero se siguen
    guardando a propósito: es la única serie larga que tenemos, y sin
    juntarla ahora no la vamos a tener nunca. Con eso adentro se pueden
    hacer las comparaciones contra el año pasado o contra la historia del
    club, que hoy no existen.
    """
    if not game_id or not (vals_h or vals_a):
        return
    almacen.guardar("stats:%s:%s" % (liga, game_id),
                    {"h": {"eq": local, "v": vals_h, "gf": gh, "gc": ga},
                     "a": {"eq": visita, "v": vals_a, "gf": ga, "gc": gh}})
    idx, _ = almacen.leer("statsidx:%s" % liga)
    idx = idx or []
    if str(game_id) not in idx:
        almacen.guardar("statsidx:%s" % liga, (idx + [str(game_id)])[-500:])


def _buscar_eje(vals, claves):
    """El valor de un eje, tolerando cómo lo escriba la fuente."""
    for k, v in vals.items():
        n = norm(k)
        if any(n == c for c in claves):
            return v
    for k, v in vals.items():
        n = norm(k)
        if any(c in n for c in claves):
            return v
    return None


def _valor_eje(ac, e):
    """El promedio del acumulador para un eje."""
    if e["tipo"] == "stat":
        s, n = ac["stat"][e["eje"]]
        return (s / n) if n else 0
    if e["tipo"] == "efectividad":
        return (ac["gf"] / ac["remates"] * 100) if ac["remates"] else 0
    if e["tipo"] == "recibidos":
        return (ac["gc"] / ac["partidos"]) if ac["partidos"] else 0
    return 0


def del_torneo():
    """
    Los partidos del torneo que se está jugando, por su id de 365scores.

    El fixture de AFA ya viene filtrado al Clausura, así que alcanza con
    juntar los ids que se le pegaron de 365scores —que son los mismos con
    los que se guardan las estadísticas—. Los que todavía no tienen id
    tampoco tienen estadísticas, así que no se pierde nada.

    Devuelve None si el fixture no se pudo leer, y eso quiere decir "no
    filtres": es preferible un promedio con partidos de más que una
    página vacía.
    """
    try:
        ids = {str(m["liveId"]) for m in all_games() if m.get("liveId")}
    except Exception:
        return None
    return ids or None


def radar_promedio(liga, club, equipos=None, partidos=None):
    """
    El promedio del club contra el de toda la liga, eje por eje, y en qué
    puesto lo deja eso.

    Es la única forma de que el gráfico signifique algo: doce remates por
    partido no dicen nada hasta que sabés que la liga promedia ocho. Y el
    puesto agrega lo que el promedio solo no dice: estar 20% arriba puede
    ser el primero de la liga o el séptimo, según qué tan parejo esté todo.

    Por eso se acumula club por club y no sólo "el club" contra "la liga":
    con la tabla entera armada, el puesto sale de ordenarla.

    Los dos filtros existen por el mismo motivo. El índice de estadísticas
    guarda los últimos quinientos partidos de la competencia, y eso pasa de
    largo el torneo y hasta la temporada.

    `equipos` es contra quiénes se compara. Sin eso quedaban adentro los
    que se fueron al descenso, y cualquier nombre que no reconocemos
    entraba como si fuera un club más: se llegaba a "48º de 53" en un
    torneo de treinta.

    `partidos` es qué partidos entran en la cuenta. Sin eso, el promedio
    de un club mezclaba el Clausura con el Apertura, que se juegan con
    otro plantel y a veces con otro técnico.

    Los quinientos siguen guardándose igual. Que hoy no se usen no
    significa que sobren: son la única serie larga que tenemos, y el día
    que queramos "cómo viene comparado con el año pasado" va a salir de
    ahí. Para eso alcanza con no pasar `partidos`.
    """
    idx, _ = almacen.leer("statsidx:%s" % liga)
    if not idx:
        return None
    permitidos = {norm(x) for x in equipos} if equipos else None
    if partidos is not None:
        idx = [g for g in idx if str(g) in partidos]
        if not idx:
            return None

    def vacio():
        return {"partidos": 0, "remates": 0.0, "gf": 0.0, "gc": 0.0,
                "stat": {e["eje"]: [0.0, 0] for e in EJES_RADAR}}

    por_club, liga_ac = {}, vacio()

    for gid in idx:
        d, _ = almacen.leer("stats:%s:%s" % (liga, gid))
        if not d:
            continue
        for lado in ("h", "a"):
            lo = d.get(lado) or {}
            vals = lo.get("v") or {}
            if not vals:
                continue
            eq = match_team(lo.get("eq") or "") or (lo.get("eq") or "")
            if not eq:
                continue
            if permitidos is not None and norm(eq) not in permitidos:
                continue
            destinos = [liga_ac, por_club.setdefault(eq, vacio())]
            remates = _buscar_eje(vals, ["total remates", "remates"]) or 0
            for ac in destinos:
                ac["partidos"] += 1
                ac["remates"] += remates
                ac["gf"] += lo.get("gf") or 0
                ac["gc"] += lo.get("gc") or 0
                for e in EJES_RADAR:
                    if e["tipo"] != "stat":
                        continue
                    v = _buscar_eje(vals, e["claves"])
                    if v is None:
                        continue
                    ac["stat"][e["eje"]][0] += v
                    ac["stat"][e["eje"]][1] += 1

    # el club puede figurar con otro nombre: se busca con la regla estricta
    mio = next((v for k, v in por_club.items() if mismo_club(k, club)), None)
    if not mio or not mio["partidos"]:
        return None

    # Para el puesto sólo cuentan los clubes con al menos dos partidos
    # cargados: con uno solo, un partido raro los manda al primer puesto y
    # el número miente.
    rivales = {k: v for k, v in por_club.items() if v["partidos"] >= 2}

    ejes = []
    for e in EJES_RADAR:
        c, l = _valor_eje(mio, e), _valor_eje(liga_ac, e)
        # un eje sin datos no se muestra: mejor cuatro puntas de verdad que
        # cinco con un cero inventado
        if not c and not l:
            continue
        # En los ejes invertidos, menos es mejor: el índice se da vuelta.
        # Y cero es el mejor valor posible, no "igual que el promedio":
        # dividir por cero daba 100% y el club que no recibió ningún gol
        # salía del montón.
        if e.get("invertido"):
            indice = 100 if not l else (220 if not c else round(l / c * 100))
        else:
            indice = round((c / l * 100)) if l else 100

        fila = {"eje": e["eje"], "unidad": e.get("unidad", ""),
                "invertido": bool(e.get("invertido")),
                "club": round(c, 1), "liga": round(l, 1),
                "indice": max(0, min(220, indice))}
        if len(rivales) >= 4:
            tabla = sorted(((_valor_eje(v, e), k) for k, v in rivales.items()),
                           reverse=not e.get("invertido"))
            puesto = next((i for i, (_, k) in enumerate(tabla, 1)
                           if mismo_club(k, club)), None)
            if puesto:
                fila["puesto"], fila["de"] = puesto, len(tabla)
        ejes.append(fila)

    return {"partidos": mio["partidos"], "ejes": ejes,
            "deLiga": liga_ac["partidos"], "clubes": len(rivales),
            # para que la página pueda decir de qué se está hablando en vez
            # de un genérico "en la liga"
            "torneo": (LIGAS.get(liga) or {}).get("torneo") if partidos else None}


# ─────────────────────────────────────────────────────────────────────────
# El gráfico de cada jugador
#
# A un arquero no se lo mide con los remates ni a un delantero con los
# despejes. Así que no hay un gráfico sino cuatro, uno por puesto, y cada
# jugador se compara contra el promedio de los que juegan en su mismo
# puesto: que un central meta un gol cada diez partidos es mucho; que lo
# haga un nueve, poco.
#
# Los nombres de cada estadística salen tal cual los manda 365scores en el
# detalle del partido. Van varias claves por eje porque la fuente no siempre
# los escribe igual —y a veces mezcla castellano con inglés en la misma
# lista, "Minutes" al lado de "Despejes"—.
# ─────────────────────────────────────────────────────────────────────────
GRUPOS_PUESTO = ("arquero", "defensor", "volante", "delantero")

EJES_JUGADOR = {
    "arquero": [
        {"eje": "Atajadas", "claves": ["salvadas de portero", "atajadas", "saves"]},
        {"eje": "Goles evitados",
         "claves": ["goles esperados evitados", "goals prevented"]},
        {"eje": "Vallas", "invertido": True,
         "claves": ["goles recibidos", "goals conceded"]},
        {"eje": "Salidas",
         "claves": ["despeje con los punos", "despejes", "punches", "clearances"]},
        {"eje": "Pases largos",
         "claves": ["pases largos completados", "accurate long balls"]},
        {"eje": "Puntaje", "claves": ["__ranking"]},
    ],
    "defensor": [
        {"eje": "Quites", "claves": ["barridas ganadas", "tackles won", "entradas"]},
        {"eje": "Intercepciones", "claves": ["intercepciones", "interceptions"]},
        {"eje": "Despejes", "claves": ["despejes", "clearances"]},
        {"eje": "Duelos", "claves": ["duelos aereos ganados", "duelos aereos",
                                     "duelos en el suelo ganados",
                                     "duelos en el suelo"]},
        {"eje": "Pases", "claves": ["pases completados", "accurate passes"]},
        {"eje": "Puntaje", "claves": ["__ranking"]},
    ],
    "volante": [
        {"eje": "Pases", "claves": ["pases completados", "accurate passes"]},
        {"eje": "Pases clave", "claves": ["pases claves", "key passes"]},
        {"eje": "Recuperos",
         "claves": ["recuperacion de la posesion", "possession won"]},
        {"eje": "Regates", "claves": ["regates", "dribbles", "successful dribbles"]},
        {"eje": "Toques", "claves": ["toques", "touches"]},
        {"eje": "Puntaje", "claves": ["__ranking"]},
    ],
    "delantero": [
        {"eje": "Goles", "claves": ["goles", "goals"]},
        {"eje": "Remates", "claves": ["total remates", "remates", "total shots"]},
        {"eje": "Goles esperados", "claves": ["goles esperados", "expected goals"]},
        {"eje": "Pases clave", "claves": ["pases claves", "key passes"]},
        {"eje": "Regates", "claves": ["regates", "dribbles"]},
        {"eje": "Puntaje", "claves": ["__ranking"]},
    ],
}

# Todo lo que hay que guardar de cada partido: la unión de los seis ejes de
# los cuatro puestos. Guardar el resto sería llenar la base de números que
# nadie mira.
_CLAVES_JUGADOR = sorted({c for ejes in EJES_JUGADOR.values()
                          for e in ejes for c in e["claves"]
                          if not c.startswith("__")})


def grupo_puesto(texto):
    """
    De "Lateral izquierdo" o "Centrodelantero" al grupo que le toca.

    Se mira el texto y no un código porque la fuente cambia el nombre del
    puesto según el idioma y según si lo saca de la ficha del jugador o de
    la formación de ese partido.

    El orden importa y no es caprichoso: "central" aparece igual en "Volante
    central" que en "Defensor central", así que el volante tiene que
    preguntarse antes. Si no, la mitad del mediocampo terminaba comparándose
    contra los defensores.
    """
    t = norm(texto)
    if not t:
        return None
    if any(x in t for x in ("arquero", "portero", "goalkeeper", "guardameta")):
        return "arquero"
    if any(x in t for x in ("volante", "medio", "enganche", "midfield",
                            "centrocampista", "mediapunta", "mediocampista")):
        return "volante"
    if any(x in t for x in ("delantero", "extremo", "punta", "forward",
                            "striker", "winger")):
        return "delantero"
    if any(x in t for x in ("defensor", "defensa", "lateral", "central",
                            "back", "zaguero")):
        return "defensor"
    return None


def _num_jug(v):
    """
    El número de una estadística de jugador.

    Vienen en varios formatos: "90'" los minutos, "3/5" los duelos (ganados
    sobre intentados) y "7.4" el puntaje. De los duelos interesa el primer
    número, que es lo que se ganó.
    """
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    s = s.split("/")[0].replace("'", "").replace("%", "").replace(",", ".")
    try:
        return float(s.strip())
    except ValueError:
        return None


def anotar_jugadores(liga, game_id, filas):
    """
    Guarda lo que hizo cada jugador en un partido.

    Igual que con las estadísticas de equipo: hoy se piden para mostrar el
    partido y se tiran. Guardándolas, el promedio de cada puesto sale de la
    base sin pedirle nada a nadie, y crece solo fecha a fecha.
    """
    filas = [f for f in filas if f.get("n") and f.get("v")]
    if not game_id or not filas:
        return
    almacen.guardar("jug:%s:%s" % (liga, game_id), filas)
    idx, _ = almacen.leer("jugidx:%s" % liga)
    idx = idx or []
    if str(game_id) not in idx:
        almacen.guardar("jugidx:%s" % liga, (idx + [str(game_id)])[-500:])


# Recorrer quinientos partidos por cada jugador que alguien mire sería
# absurdo, así que la tabla entera se arma una vez y se guarda un rato.
# Va también a la base: sin eso, cada reinicio del servidor obliga a leer
# los quinientos de nuevo y el primero que entra espera todo eso.
_AGG_JUG, _AGG_JUG_CUANDO = {}, {}
_AGG_JUG_VIDA = 30 * 60


def agregado_jugadores(liga, forzar=False):
    """
    El promedio por partido de cada jugador de la liga, con su puesto.

    Devuelve {nombre: {puesto, partidos, club, prom: {clave: promedio}}}.
    """
    ahora = time.time()
    if (not forzar and liga in _AGG_JUG
            and ahora - _AGG_JUG_CUANDO.get(liga, 0) < _AGG_JUG_VIDA):
        return _AGG_JUG[liga]

    if not forzar:
        guardado, _ = almacen.leer("jugagg:%s" % liga, _AGG_JUG_VIDA)
        if guardado:
            _AGG_JUG[liga], _AGG_JUG_CUANDO[liga] = guardado, ahora
            return guardado

    idx, _ = almacen.leer("jugidx:%s" % liga)
    acum = {}
    for gid in (idx or []):
        filas, _ = almacen.leer("jug:%s:%s" % (liga, gid))
        for f in (filas or []):
            nombre = f.get("n") or ""
            if not nombre:
                continue
            a = acum.setdefault(norm(nombre), {
                "nombre": nombre, "club": f.get("eq") or "",
                "puestos": {}, "partidos": 0, "suma": {}, "cuenta": {}})
            a["club"] = f.get("eq") or a["club"]
            g = grupo_puesto(f.get("p") or "")
            if g:
                a["puestos"][g] = a["puestos"].get(g, 0) + 1
            a["partidos"] += 1
            vals = f.get("v") or {}
            if f.get("r") is not None:
                vals = dict(vals, __ranking=f["r"])
            for clave, valor in vals.items():
                if valor is None:
                    continue
                a["suma"][clave] = a["suma"].get(clave, 0.0) + valor
                a["cuenta"][clave] = a["cuenta"].get(clave, 0) + 1

    salida = {}
    for k, a in acum.items():
        # el puesto del jugador es el que más veces ocupó, no el del último
        # partido: un lateral que una vez entró de nueve sigue siendo lateral
        puesto = max(a["puestos"], key=a["puestos"].get) if a["puestos"] else None
        salida[k] = {"nombre": a["nombre"], "club": a["club"], "puesto": puesto,
                     "partidos": a["partidos"],
                     "prom": {c: a["suma"][c] / a["cuenta"][c]
                              for c in a["suma"] if a["cuenta"].get(c)}}
    _AGG_JUG[liga], _AGG_JUG_CUANDO[liga] = salida, ahora
    if salida:
        almacen.guardar("jugagg:%s" % liga, salida)
    return salida


def _prom_eje(prom, e):
    """El valor de un eje: la suma de sus claves que existan."""
    total, hubo = 0.0, False
    for c in e["claves"]:
        if c in prom:
            total += prom[c]
            hubo = True
            # el puntaje y los promedios simples no se suman entre sí
            if c.startswith("__"):
                break
    return total if hubo else None


# Con menos de tres partidos el promedio es ruido: entran a la comparación
# pero no definen el puesto de nadie.
MIN_PARTIDOS_JUGADOR = 3


def ranking_jugadores(liga, grupo, eje_nombre):
    """
    La tabla de un eje: todos los del puesto, ordenados por esa estadística.

    Es la misma cuenta con la que el gráfico dice "3° de 137", y por eso
    vive acá y no en dos lugares: si el orden se calculara aparte, tarde o
    temprano el puesto del gráfico y el de la lista dejarían de coincidir.

    Los empates comparten posición —dos primeros y ningún segundo—, que es
    como se lee cualquier tabla.
    """
    edef = next((e for e in EJES_JUGADOR.get(grupo, [])
                 if e["eje"] == eje_nombre), None)
    if not edef:
        return None

    filas = []
    for v in agregado_jugadores(liga).values():
        if v.get("puesto") != grupo or v["partidos"] < MIN_PARTIDOS_JUGADOR:
            continue
        val = _prom_eje(v.get("prom") or {}, edef)
        if val is None:
            continue
        filas.append({"name": v["nombre"], "club": v.get("club") or "",
                      "valor": round(val, 2), "partidos": v["partidos"]})
    if not filas:
        return None

    invertido = bool(edef.get("invertido"))
    filas.sort(key=lambda r: (r["valor"] if invertido else -r["valor"],
                              norm(r["name"])))
    for r in filas:
        mejores = sum(1 for o in filas
                      if (o["valor"] < r["valor"] if invertido
                          else o["valor"] > r["valor"]))
        r["pos"] = mejores + 1

    return {"eje": eje_nombre, "grupo": grupo, "invertido": invertido,
            "total": len(filas), "filas": filas}


def api_ranking(q):
    """
    Las listas por estadística. /api/ranking?grupo=delantero&eje=Goles

    Sin `eje` devuelve qué se puede pedir: los cuatro puestos con sus ejes.
    """
    lid = (q.get("liga") or ["lpf"])[0]
    grupo = (q.get("grupo") or [""])[0].strip().lower()
    eje = (q.get("eje") or [""])[0].strip()

    if not grupo or not eje:
        return {"liga": lid, "puestos": [
            {"grupo": g, "ejes": [e["eje"] for e in EJES_JUGADOR[g]]}
            for g in GRUPOS_PUESTO]}

    r = ranking_jugadores(lid, grupo, eje)
    if not r:
        return {"error": "todavía no hay datos de %s para %s" % (eje, grupo),
                "grupo": grupo, "eje": eje}
    tope = max(1, min(300, _int((q.get("limite") or ["25"])[0], 25)))
    return {"liga": lid, "grupo": grupo, "eje": eje,
            "invertido": r["invertido"], "total": r["total"],
            "minPartidos": MIN_PARTIDOS_JUGADOR,
            "filas": r["filas"][:tope],
            "ejes": [e["eje"] for e in EJES_JUGADOR[grupo]]}


def radar_jugador(liga, nombre, puesto=None):
    """
    El gráfico del jugador contra el promedio de los que juegan en su puesto.

    Compararlo contra toda la liga no diría nada: un arquero tiene cero
    remates y un nueve cero atajadas, y los dos saldrían pésimos. Por eso el
    promedio es el de su grupo —arqueros, defensores, volantes o
    delanteros— y el puesto también.
    """
    if not nombre:
        return None
    tabla = agregado_jugadores(liga)
    yo = tabla.get(norm(nombre))
    if not yo:
        return None

    grupo = yo.get("puesto") or grupo_puesto(puesto or "")
    if not grupo:
        return None
    ejes_def = EJES_JUGADOR[grupo]

    pares = [v for v in tabla.values()
             if v.get("puesto") == grupo and v["partidos"] >= MIN_PARTIDOS_JUGADOR]
    if len(pares) < 4:
        return None

    ejes = []
    for e in ejes_def:
        mio = _prom_eje(yo["prom"], e)
        otros = [x for x in (_prom_eje(p["prom"], e) for p in pares)
                 if x is not None]
        if mio is None or not otros:
            continue
        media = sum(otros) / len(otros)
        if e.get("invertido"):
            indice = 100 if not media else (220 if not mio
                                            else round(media / mio * 100))
        else:
            indice = round(mio / media * 100) if media else 100
        fila = {"eje": e["eje"], "jugador": round(mio, 2),
                "media": round(media, 2), "invertido": bool(e.get("invertido")),
                "indice": max(0, min(220, indice))}
        # El puesto sale de la misma tabla que sirve la lista completa: si
        # se calculara acá aparte, tarde o temprano dirían cosas distintas.
        tabla = ranking_jugadores(liga, grupo, e["eje"])
        if tabla:
            mia = next((f for f in tabla["filas"]
                        if norm(f["name"]) == norm(nombre)), None)
            if mia:
                fila["puesto"], fila["de"] = mia["pos"], tabla["total"]
        ejes.append(fila)

    if len(ejes) < 3:
        return None
    return {"grupo": grupo, "partidos": yo["partidos"], "club": yo["club"],
            # el nombre tal cual está en la tabla: con él se lo encuentra
            # después en la lista completa de cada estadística
            "quien": yo["nombre"],
            "ejes": ejes, "compara": len(pares)}


def anotar_plantel(club, ficha, titular, dia):
    """
    Arma el plantel de un club con los que fueron apareciendo en las
    formaciones. No es la lista oficial —al que nunca jugó no lo vemos— y
    por eso la página lo aclara. Pero para los que juegan es el dato bueno:
    dorsal, puesto y cuándo fue la última vez.
    """
    if not club or not ficha.get("nombre"):
        return
    clave = "plantel:" + norm(club)
    plantel, _ = almacen.leer(clave)
    plantel = plantel or {}
    k = norm(ficha["nombre"])
    viejo = plantel.get(k) or {}
    plantel[k] = {
        "nombre": ficha["nombre"],
        "n": ficha.get("n") or viejo.get("n"),
        "puesto": ficha.get("puesto") or viejo.get("puesto"),
        "id": ficha.get("id") or viejo.get("id"),
        "titulares": (viejo.get("titulares") or 0) + (1 if titular else 0),
        "convocado": (viejo.get("convocado") or 0) + 1,
        "ultimo": max(dia or "", viejo.get("ultimo") or ""),
    }
    almacen.guardar(clave, plantel)


# ─────────────────────────────────────────────────────────────────────────
# Sacar la basura
#
# La base sólo crecía: cada respuesta de la fuente se guardaba y nada se
# borraba nunca. En un disco de 1 GB eso tiene fecha de vencimiento.
#
# Lo que se tira es la caché de pedidos que ya nadie hace, y nada más. Los
# partidos y los jugadores no caducan: alguien puede querer ver un partido
# viejo, y las comparaciones entre temporadas se hacen justamente con eso.
#
# Cada entrada de la caché es la respuesta cruda de una dirección. Las de
# esta lista son todas repetidas: lo que sirve de adentro ya está leído y
# guardado aparte —los goles, las carreras, los calendarios— y si alguna
# hiciera falta otra vez, se vuelve a pedir sola.
#
# Y una que NO está en la lista, a propósito: `sc:game`, el detalle de un
# partido. Ahí viven las formaciones, los cambios y las tarjetas de cada
# partido que alguien abrió. Es la familia más pesada —siete de los nueve
# megas— y es la que crece con las visitas, pero es información de
# partidos y se queda. Si el disco llega a molestar, sale más barato
# agrandarlo: en Render son 25 centavos de dólar por giga por mes.
CACHE_QUE_SOBRA = [
    "sc:https://webws.365scores.com/web/standings",      # tablas de posiciones
    "sc:https://webws.365scores.com/web/games/current",  # la ventana de hoy
    "sc:https://webws.365scores.com/web/games/fixtures", # páginas de calendario
    "sc:https://webws.365scores.com/web/games/results",  # páginas de resultados
    "sc:https://webws.365scores.com/web/athletes",       # fichas de jugador
    "sc:https://webws.365scores.com/web/stats",          # estadísticas sueltas
]
# Un mes sin que nadie la pida. Lo que se sigue usando se reescribe solo
# cada vez que vence, así que treinta días es "esto no lo pidió nadie".
DIAS_DE_CACHE = 30
_ULTIMA_LIMPIEZA = [0.0]


def limpieza_diaria(cada=86400):
    """Tira la caché que ya nadie pide y las visitas viejas. Una vez por día."""
    if time.time() - _ULTIMA_LIMPIEZA[0] < cada:
        return None
    _ULTIMA_LIMPIEZA[0] = time.time()
    hecho = {"familias": [], "filas": 0, "bytes": 0}
    for prefijo in CACHE_QUE_SOBRA:
        try:
            r = almacen.limpiar(prefijo, 60 * 60 * 24 * DIAS_DE_CACHE)
        except Exception:
            continue
        if r["filas"]:
            hecho["familias"].append({"que": almacen.familia(prefijo + "/?"),
                                      "filas": r["filas"], "bytes": r["bytes"]})
            hecho["filas"] += r["filas"]
            hecho["bytes"] += r["bytes"]
    try:
        hecho["visitas"] = visitas.limpiar()
    except Exception:
        hecho["visitas"] = 0
    hecho["cuando"] = dt.datetime.now().isoformat(timespec="seconds")
    almacen.guardar("limpieza:ultima", hecho)
    if hecho["filas"] or hecho["visitas"]:
        print("  Limpieza: %d entradas de caché (%.1f MB) y %d días de visitas"
              % (hecho["filas"], hecho["bytes"] / 1024 / 1024,
                 hecho["visitas"]), flush=True)
    return hecho


def bandera_url(pais_id):
    return ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_48,h_48,c_limit,q_auto:eco,dpr_2/"
            "v1/Countries/Round/%s" % pais_id)


# De qué país es cada club, aprendido de los partidos que van pasando.
#
# Hace falta porque el país no está donde uno lo buscaría. Los calendarios
# guardados de la Libertadores y la Sudamericana no lo tienen: se guardaron
# antes de que el campo existiera, y de un partido ya guardado sólo se
# refrescan la fase y la zona, nunca los equipos. Los de la Champions y la
# Europa sí lo tienen, porque se bajaron después. O sea que leyendo nada
# más el calendario, la bandera aparecería en dos torneos y en los otros
# dos no, que es peor que no ponerla en ninguno.
#
# La ventana de lo que se juega ahora, en cambio, se pide fresca cada vez y
# siempre lo trae. Así que se aprende de ahí: cada club que juega deja
# anotado de dónde es, y de la fecha siguiente en adelante ya se sabe. No
# cuesta un pedido más —esa ventana ya se pedía— y no hay que volver a
# bajar ningún calendario.
_CLAVE_PAIS_CLUB = "paises:clubes"


def recordar_paises(games):
    """Anota de qué país es cada club que aparezca en estos partidos."""
    tabla, _ = almacen.leer(_CLAVE_PAIS_CLUB)
    tabla = tabla or {}
    nuevos = False
    for g in games or []:
        for lado in ("home", "away"):
            t = g.get(lado) or {}
            cid, pais = str(t.get("id") or ""), t.get("pais")
            if cid and pais and tabla.get(cid) != pais:
                tabla[cid], nuevos = pais, True
    if nuevos:
        almacen.guardar(_CLAVE_PAIS_CLUB, tabla)
    return tabla


def con_banderas(games, liga_id):
    """
    Los mismos partidos con la bandera del país de cada club, para los
    torneos internacionales.

    Devuelve copias. La lista que llega es la que está guardada en la base
    y no es de acá para escribirla: sin copiar, la bandera se colaba en el
    calendario guardado en el próximo `guardar`.
    """
    if not (LIGAS.get(liga_id) or {}).get("internacional"):
        return games
    tabla = recordar_paises(games)
    salida = []
    for g in games:
        g = dict(g)
        for lado in ("home", "away"):
            t = dict(g.get(lado) or {})
            pais = t.get("pais") or tabla.get(str(t.get("id") or ""))
            if pais:
                t["bandera"] = bandera_url(pais)
            g[lado] = t
        salida.append(g)
    return salida


def nacionalidades(ids):
    """
    De qué país es cada jugador, para toda una lista de una sola vez.

    La ficha de un jugador ya traía la nacionalidad, pero pedirla de a uno
    para un plantel entero son treinta pedidos cada vez que alguien abre
    la página de un club. La fuente acepta varios atletas en la misma
    dirección, así que van todos juntos.

    Y se guarda por jugador, no por club: el mismo tipo aparece en el
    plantel de su club y en el de los clubes por los que pasó, y la
    nacionalidad no cambia. Una vez pedida, no se vuelve a pedir.
    """
    faltan, salida = [], {}
    for i in {str(x) for x in ids if x}:
        guardado, _ = almacen.leer("nac:%s" % i)
        if guardado:
            salida[i] = guardado
        else:
            faltan.append(i)
    for tanda in [faltan[x:x + 40] for x in range(0, len(faltan), 40)]:
        try:
            data = fetch("athletes", {"athletes": ",".join(tanda)},
                         ttl=60 * 60 * 24)
        except Exception:
            continue
        for a in (data.get("athletes") or []):
            if not a.get("id"):
                continue
            ficha = {"pais": a.get("nationalityName") or ""}
            if a.get("nationalityId"):
                ficha["bandera"] = bandera_url(a["nationalityId"])
            if not ficha["pais"]:
                continue
            almacen.guardar("nac:%s" % a["id"], ficha)
            salida[str(a["id"])] = ficha
    return salida


def plantel_de(club):
    """
    El plantel guardado, ordenado por puesto y después por dorsal, con la
    bandera de cada uno.
    """
    plantel, _ = almacen.leer("plantel:" + norm(club))
    if not plantel:
        return []
    orden = {"arquero": 0, "defensor": 1, "mediocampista": 2, "delantero": 3}

    def puesto_rango(p):
        n = norm(p or "")
        for k, v in orden.items():
            if k in n:
                return v
        return 4

    filas = list(plantel.values())
    filas.sort(key=lambda x: (puesto_rango(x.get("puesto")),
                              x.get("n") if isinstance(x.get("n"), int) else 99,
                              norm(x.get("nombre"))))
    # Si la fuente no contesta, el plantel se muestra igual: lo que falta
    # es la banderita, no la lista.
    try:
        paises = nacionalidades([f.get("id") for f in filas])
    except Exception:
        paises = {}
    for f in filas:
        p = paises.get(str(f.get("id") or ""))
        if p:
            f["pais"] = p.get("pais")
            f["bandera"] = p.get("bandera")
    return filas


def carrera(nombre):
    """
    Por dónde pasó el jugador, un club por línea.

    Se guarda una entrada por club y por torneo —jugó la liga y la Copa
    Argentina con el mismo club—, pero eso en pantalla se veía como si
    hubiera estado dos veces en Platense. Acá se juntan por club.
    """
    hist, _ = almacen.leer("carrera:" + norm(nombre))
    juntos = {}
    for h in (hist or []):
        k = norm(h.get("club") or "")
        if not k:
            continue
        a = juntos.get(k)
        if not a:
            juntos[k] = dict(h)
            continue
        a["desde"] = min(a.get("desde") or "9999", h.get("desde") or "9999")
        a["hasta"] = max(a.get("hasta") or "", h.get("hasta") or "")
        a["escudo"] = a.get("escudo") or h.get("escudo")
    return sorted(juntos.values(), key=lambda h: h.get("hasta") or "",
                  reverse=True)


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


def leer_goles(liga, game_id):
    """
    Los goles guardados de un partido: (lista, si es definitivo).

    Convive con lo guardado antes, que era una lista pelada sin decir si el
    partido había terminado. No se migra: una base que se vuelve a llenar
    sola no vale una migración, y el formato viejo se reconoce solo.
    """
    dato, _ = almacen.leer("goles:%s:%s" % (liga, game_id))
    if dato is None:
        return None, False
    if isinstance(dato, dict):
        return dato.get("g") or [], bool(dato.get("fin"))
    return dato, False


def falta_mucho(g, horas=30):
    """¿El partido es tan lejano que todavía no vale la pena mirarlo?"""
    cuando = g.get("start")
    if not cuando:
        return False
    try:
        t = dt.datetime.fromisoformat(cuando)
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (t - dt.datetime.now(dt.timezone.utc)).total_seconds() > horas * 3600


def detalle_al_dia(liga, g):
    """
    ¿Lo guardado de este partido alcanza, o hay que volver a leerlo?

    Devuelve (goles, canales, listo). Mira las dos cosas que guardamos de
    cada partido —quién hizo los goles y por dónde se ve—, porque cada una
    se completa en un momento distinto y antes bastaba con que *alguna*
    estuviera para no volver a mirar nunca más.

      · en juego → nunca alcanza, hay que ir a buscarlo
      · terminado → alcanza si lo guardamos ya terminado, o si la cantidad
        de goles coincide con el resultado (esto último es para lo que se
        guardó antes de que anotáramos si el partido había terminado)
      · todavía no empezó → alcanza si ya tenemos el canal

    Esa última línea es la que faltaba. El canal se publica horas después
    de que el partido aparece en el calendario, así que lo leíamos vacío y
    quedaba vacío para siempre: los tres partidos de la Liga Profesional
    del lunes se mostraron todo el día sin canal. Ahora se sigue
    preguntando mientras el partido esté cerca; si falta más de un día, no
    se molesta a la fuente, porque a esa altura todavía no lo publicaron.

    El caso "terminado pero incompleto" se vuelve a pedir una sola vez: al
    releerlo queda marcado como definitivo aunque la fuente siga sin decir
    quién hizo un gol. Si no, esos partidos se pedirían para siempre y le
    robarían el lugar a los que sí faltan.
    """
    gid = g.get("liveId")
    lista, fin = leer_goles(liga, gid)
    tv, _ = almacen.leer("tv:%s:%s" % (liga, gid))
    if lista is None:
        return None, tv, False
    estado = g.get("status")
    if estado == "LIVE":
        return lista, tv, False
    if estado != "FIN":
        return lista, tv, bool(tv) or falta_mucho(g)
    if fin:
        return lista, tv, True
    total = (g.get("gh") or 0) + (g.get("ga") or 0)
    return lista, tv, len(lista) >= total


def anotar_goles(liga, game_id, goles, fin=False):
    """
    Guarda quién hizo los goles de un partido.

    Los torneos chicos y las copas no tienen tabla de goleadores publicada,
    pero los autores de cada gol ya los estamos leyendo para mostrarlos en la
    lista de partidos. Guardándolos, la tabla se arma sola.

    Se guarda por partido y no sumando de a uno: si el mismo partido se lee
    diez veces —pasa, se refresca cada veinte segundos— el último pisa al
    anterior y nadie termina con treinta goles.

    `fin` dice si el partido ya había terminado cuando lo leímos. Sin ese
    dato, un partido leído a los veinte minutos quedaba guardado con los
    goles de ese momento y no se volvía a mirar nunca: en la lista se veía
    "Arrascaeta 35'" y el resultado 2-1, y los otros dos goles no aparecían
    hasta abrir la ficha. Ahora lo provisorio se vuelve a pedir.

    Los goles sin autor se guardan igual, con el nombre vacío. Descartarlos
    era peor: el gol desaparecía de la lista en vez de mostrarse como el
    minuto solo, y encima la cuenta no cerraba con el resultado, así que no
    había forma de darse cuenta de que faltaba algo.
    """
    if not game_id:
        return
    # ni los anulados ni los de la tanda de penales cuentan para la tabla.
    # Se guarda también de qué lado fue cada gol, para poder mostrarlos en la
    # lista de partidos sin volver a pedir el detalle.
    limpios = [{"j": g.get("player") or "", "e": g.get("equipo") or "",
                "m": g.get("min"), "s": g.get("side") or "h"}
               for g in goles
               if not g.get("anulado") and not g.get("penales")]
    almacen.guardar("goles:%s:%s" % (liga, game_id),
                    {"g": limpios, "fin": bool(fin)})

    # la tanda, aparte: sirve para mostrar quién pasó en el cuadro
    tanda = [g for g in goles if g.get("penales") and not g.get("anulado")]
    if tanda:
        almacen.guardar("pen:%s:%s" % (liga, game_id),
                        {"h": sum(1 for g in tanda if g.get("side") == "h"),
                         "a": sum(1 for g in tanda if g.get("side") == "a")})
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
        goles, _ = leer_goles(liga, gid)
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


def _nombre_de_slug(slug, lid):
    """
    De 'enzo-fernandez' al nombre como se escribe: 'Enzo Fernández'.

    Hace falta porque una dirección web no lleva acentos, y poner "enzo
    fernandez" como título de la ficha se ve mal. Se busca contra los
    jugadores que fuimos juntando partido a partido. Si no aparece, se
    devuelve el slug con espacios: alcanza igual para encontrarlo, porque
    todas las comparaciones de acá pasan por `norm`, que también saca los
    acentos. Lo único que se pierde es la tilde en el título.
    """
    try:
        for v in agregado_jugadores(lid).values():
            if _slug(v.get("nombre") or "") == slug:
                return v["nombre"]
    except Exception:
        pass
    # No lo conocemos: se arma el nombre desde la dirección. Va con las
    # iniciales en mayúscula, que es como se escribe el nombre de una
    # persona; sin esto la ficha decía "enzo fernandez", todo junto y en
    # minúscula, que se lee como un error y no como un nombre.
    return " ".join(p.capitalize() for p in slug.split("-") if p)


def liga_del_jugador(nombre, pedida=None):
    """
    En qué torneo hay que buscar los datos de este jugador.

    La página manda el torneo que uno está mirando, y eso está bien
    mientras uno esté parado en un torneo. Pero desde la ficha de un club
    manda "club", y desde la portada manda "home", y ninguno de los dos es
    un torneo: los partidos jugados quedaban en cero, los goles no
    aparecían y el gráfico de cómo juega no se dibujaba. El mismo jugador
    abierto desde la formación de un partido salía completo y abierto
    desde el plantel del club salía vacío, que es lo que no cerraba.

    Si lo que mandaron es un torneo de verdad, se respeta —importa cuando
    alguien jugó en dos—. Si no, se elige aquel donde tenemos más partidos
    suyos, que es donde están sus datos.
    """
    if pedida in LIGAS:
        return pedida
    n = norm(nombre)
    if not n:
        return "lpf"
    mejor, cuantos = None, 0
    for lid in LIGAS:
        dato, _ = almacen.leer("pj:%s:%s" % (lid, n))
        pj = (dato or {}).get("n", 0)
        if pj > cuantos:
            mejor, cuantos = lid, pj
    return mejor or "lpf"


def api_atleta(q):
    """
    Ficha de un jugador. /api/atleta?id=8167&name=...&liga=lpf

    También acepta `slug`, que es lo que viene en la dirección cuando
    alguien abre /jugador/enzo-fernandez directo, sin pasar por la página.
    """
    aid = _int((q.get("id") or [""])[0], None)
    nombre = (q.get("name") or [""])[0].strip()
    lid = (q.get("liga") or ["lpf"])[0]
    slug = (q.get("slug") or [""])[0].strip()
    if not nombre and slug:
        nombre = _nombre_de_slug(slug, liga_del_jugador(
            slug.replace("-", " "), lid))
    if not aid and not nombre:
        return {"error": "falta el parámetro id o name"}

    p = perfil_atleta(aid) if aid else {}
    p["name"] = nombre or p.get("name") or ""
    # Recién acá se sabe el nombre, y con el nombre se sabe de qué torneo
    # sacar sus números. Todo lo de abajo depende de esto.
    lid = liga_del_jugador(p["name"], lid)
    p["liga"] = lid
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

    # el gráfico, contra el promedio de los que juegan en su mismo puesto
    try:
        p["radar"] = radar_jugador(lid, p["name"],
                                   p.get("puesto") or p.get("posicion"))
    except Exception:
        pass

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
HOME_LIGAS = ("lpf", "nacional", "ca", "lib", "sud", "champions", "europa",
              "laliga", "premier", "seriea", "bundesliga")


def armar_home(date):
    """
    Los partidos de un día, liga por liga.

    Las once ligas se piden a la vez y no una tras otra. Eran once esperas
    en fila —cada una con su ida y vuelta a AFA o a 365scores— y por eso la
    portada tardaba nueve segundos y medio de promedio. En paralelo, tarda
    lo que la más lenta.

    Cada partido se copia antes de etiquetarlo con su liga: los originales
    son los del calendario guardado, compartidos con todo lo demás, y
    escribirles encima ensuciaba la tabla de posiciones y el fixture.
    """
    from concurrent.futures import ThreadPoolExecutor

    def dia(games):
        return [dict(g) for g in games if (g.get("start") or "")[:10] == date]

    def de(lid):
        try:
            return lid, dia(all_games() if lid == "lpf"
                            else api_liga_games({"id": [lid]}).get("games", []))
        except Exception:
            return lid, []

    cuales = [k for k in HOME_LIGAS if k in LIGAS]
    with ThreadPoolExecutor(max_workers=min(8, len(cuales))) as pool:
        traido = dict(pool.map(de, cuales))

    bloques, vivos = [], 0
    for lid in cuales:                    # el orden lo manda HOME_LIGAS
        ms = traido.get(lid) or []
        if not ms:
            continue
        for m in ms:
            m["liga"], m["ligaNombre"] = lid, LIGAS[lid]["nombre"]
        ms.sort(key=lambda x: (x.get("start") or ""))
        bloques.append({"liga": lid, "nombre": LIGAS[lid]["nombre"],
                        "torneo": LIGAS[lid]["torneo"], "games": ms})
        vivos += sum(1 for m in ms if m.get("status") == "LIVE")

    total = sum(len(b["games"]) for b in bloques)
    # El partidazo del día sale con los mismos criterios de siempre. Y
    # además se calcula uno por torneo, con esos mismos criterios aplicados
    # a un solo bloque: la página elige cuál mostrar según a quién le está
    # hablando. Se calculan todos acá para que la respuesta siga siendo
    # igual para todo el mundo y pueda seguir guardándose armada; si
    # dependiera de quién pregunta, habría que rearmarla en cada visita.
    return {"date": date, "bloques": bloques, "total": total, "live": vivos,
            "partidazo": partidazo_del_dia(bloques),
            "partidazos": {b["liga"]: partidazo_del_dia([b])
                           for b in bloques}}


def api_home(q):
    """
    Portada: los partidos de un día, de las ligas de HOME_LIGAS.
    Uso: /api/home?date=YYYY-MM-DD (si no, hoy).

    Es la pantalla que ve todo el que entra, así que no puede hacer
    esperar: se sirve lo último que se armó y, si ya está viejo, se rearma
    por atrás para el próximo. Ver `al_toque`.
    """
    date = (q.get("date") or [dt.date.today().isoformat()])[0]
    hoy = date == dt.date.today().isoformat()

    def cada_cuanto(ultimo):
        # Un día que ya pasó no cambia más. El de hoy sólo cambia rápido
        # mientras haya algo en juego; si no hay nada rodando, rearmar cada
        # diez segundos es gastar por gastar.
        if not hoy:
            return 600
        return 10 if (ultimo or {}).get("live") else 60

    return al_toque("home:%s" % date, lambda: armar_home(date),
                    frescura=cada_cuanto)


# Los clásicos del fútbol argentino. Un interzonal no es cualquier partido
# cruzado entre zonas: la fecha de clásicos los junta a propósito, y es esa
# la que interesa. Van sólo los que nadie discute.
CLASICOS_AR = [
    {"Boca Juniors", "River Plate"},
    {"Racing", "Independiente"},
    {"San Lorenzo", "Huracán"},
    {"Newell's Old Boys", "Rosario Central"},
    {"Estudiantes (LP)", "Gimnasia y Esgrima (LP)"},
    {"Belgrano", "Talleres (C)"},
    {"Talleres (C)", "Instituto"},
    {"Belgrano", "Instituto"},
    {"Lanús", "Banfield"},
    {"Vélez Sarsfield", "Argentinos Juniors"},
    {"Tigre", "Platense"},
    {"Unión", "Colón"},
    {"Atlético Tucumán", "San Martín (T)"},
    {"Gimnasia y Esgrima (M)", "Independiente Rivadavia"},
    {"Aldosivi", "Alvarado"},
    {"Central Córdoba (SdE)", "Mitre"},
]


def es_clasico_ar(a, b):
    """¿Es un clásico argentino? Se compara con la regla estricta de clubes."""
    for par in CLASICOS_AR:
        x, y = tuple(par)
        if ((mismo_club(a, x) and mismo_club(b, y))
                or (mismo_club(a, y) and mismo_club(b, x))):
            return True
    return False


def partidazo_del_dia(bloques):
    """
    El partido del día, con los criterios en este orden:

      1. El interzonal de Primera, si además es clásico. La fecha de
         interzonales existe justamente para cruzar a los clásicos, y ese
         día el clásico es el partido aunque los dos vengan últimos.
      2. El que tenga al mejor equipo argentino de la Tabla Anual.
      3. El clásico internacional: dos equipos del mismo país cruzados en
         la Libertadores, la Sudamericana, la Champions o la Europa League.
      4. El equipo más grande según el ranking de la fuente.

    Sobre el punto 4: FIFA no publica un ranking de clubes —el suyo es de
    selecciones—. Lo más parecido que tenemos sin inventar nada es el
    `popularityRank` que 365scores le asigna a cada club, que ordena bastante
    bien de Real Madrid para abajo. Si querés otro criterio, se cambia acá.
    """
    todos = [(b["liga"], m) for b in bloques for m in b["games"]]
    if not todos:
        return None
    lpf = [m for lid, m in todos if lid == "lpf"]

    def lado(m, s):
        return m[s].get("canon") or m[s].get("name") or ""

    # ── 1. interzonal de Primera que además sea clásico ──────────────────
    for m in lpf:
        if m.get("interzonal") and es_clasico_ar(lado(m, "home"), lado(m, "away")):
            return m["id"]

    # ── 2. el mejor argentino de la Anual ────────────────────────────────
    puesto = {}
    for traer in (lambda: api_annual({"live": ["0"]}).get("rows", []),
                  lambda: [r for z in api_standings({"live": ["0"]}).get("zones", [])
                           for r in z["rows"]]):
        try:
            for r in traer():
                puesto[norm(r.get("canon") or r["team"]["name"])] = r.get("pos") or 99
            if puesto:
                break
        except Exception:
            continue

    if puesto:
        conocidos = [(min(puesto.get(norm(lado(m, s)), 999)
                          for s in ("home", "away")), m)
                     for _, m in todos]
        mejor = min(conocidos, key=lambda x: x[0])
        if mejor[0] < 999:
            return mejor[1]["id"]

    # ── 3. clásico internacional: dos del mismo país en una copa ─────────
    for lid, m in todos:
        cfg = LIGAS.get(lid) or {}
        if not cfg.get("copa") and lid not in ("champions", "europa"):
            continue
        pa, pb = m["home"].get("pais"), m["away"].get("pais")
        if pa and pb and pa == pb:
            return m["id"]

    # ── 4. el club más grande según la fuente ────────────────────────────
    def tamano(m):
        return max(m[s].get("rank") or 0 for s in ("home", "away"))

    conRank = [m for _, m in todos if tamano(m)]
    if conRank:
        return max(conRank, key=tamano)["id"]
    return todos[0][1]["id"]


# Emblemas: sólo de las ligas que efectivamente andan. Las que están en
# "pronto" van sin escudo: poner uno estimado quedaba mal y confundía.
EMBLEMAS = {"lpf": 72, "nacional": 419, "pbm": 5077, "fa": 5078,
            "fem": 6224, "laliga": 11, "premier": 7, "seriea": 17,
            "bundesliga": 25, "champions": 572, "europa": 573,
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


def api_contenido(q):
    """
    Qué hay guardado en la base, contado por tipo de cosa.

    /api/contenido            → el resumen
    /api/contenido?ver=goles  → las claves de ese grupo, para espiar

    La base guarda todo bajo una clave de texto: "fixture:72" es el
    calendario de la Liga Profesional, "goles:lib:4712799" los autores de
    los goles de un partido. Acá se agrupan por el prefijo.
    """
    try:
        claves = almacen.claves()
    except Exception as e:
        return {"error": str(e)}

    grupos = {}
    for k in claves:
        pref = k.split(":", 1)[0] if ":" in k else k
        grupos[pref] = grupos.get(pref, 0) + 1

    nombres = {
        "fixture": "calendarios de cada torneo",
        "goles": "autores de los goles, partido por partido",
        "tv": "canal de cada partido",
        "pen": "definiciones por penales",
        "pj": "partidos jugados por jugador",
        "paso": "clubes por los que pasó cada jugador",
        "hist": "hasta dónde llegó el rescate de partidos viejos",
        "dffx": "fixtures de AFA",
        "pag": "páginas del histórico de 365scores",
        "laliga": "jornadas de LaLiga",
        "sc": "respuestas de 365scores",
    }

    ver = (q.get("ver") or [""])[0].strip()
    detalle = None
    if ver:
        detalle = sorted(k for k in claves if k.split(":", 1)[0] == ver)[:200]

    return {"base": almacen.estado(),
            "grupos": [{"tipo": t, "cantidad": n, "que_es": nombres.get(t, "")}
                       for t, n in sorted(grupos.items(), key=lambda x: -x[1])],
            "verDetalle": detalle,
            "como": "Agregá ?ver=goles (o el tipo que quieras) para ver las claves."}


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


# Palabras que no distinguen a un club de otro: "Racing" y "Racing Club" son
# el mismo, "Racing" y "Racing de Córdoba" no.
# Sólo formas jurídicas y palabras que ningún club usa para diferenciarse.
# Ojo con "sportivo", "deportivo" y "atlético": parecen genéricas pero no lo
# son —Sportivo Belgrano no es Belgrano, y Atlético Tucumán no es Tucumán—.
# "Esgrima" sí, porque los cuatro Gimnasia del país son "Gimnasia y Esgrima"
# y lo que los distingue es la ciudad.
_RELLENO = {"club", "esgrima", "fc", "cf", "ac", "sc", "cd", "ca", "sad",
            "afc", "cfc"}


def mismo_club(nombre, canon):
    """
    ¿Son el mismo club? Estricto a propósito.

    El modo club se confundía: al elegir Racing te mostraba el último partido
    de Racing de Córdoba, que juega en la Nacional. Se compara por tokens
    —que ya expanden las abreviaturas, así "(LP)" se vuelve "la plata"— y se
    perdona sólo lo que no distingue a un club de otro: "Racing" y "Racing
    Club" son el mismo, "Racing" y "Racing de Córdoba" no.

    No se usa match_team acá: ese matcher es laxo a propósito para leer el
    fixture de AFA y devuelve "Racing" para "Racing de Córdoba".
    """
    if not nombre or not canon:
        return False
    if norm(nombre) == norm(canon):
        return True
    ta, tb = _tokens(nombre), _tokens(canon)
    if not ta or not tb or not (ta & tb):
        return False
    if not ((ta ^ tb) <= _RELLENO):
        return False

    # Y una vuelta más: _tokens descarta por su cuenta algunas palabras
    # —"Sportivo Belgrano" y "Belgrano" le dan el mismo token— y ahí el modo
    # club mostraba partidos del Federal A creyendo que era Belgrano de
    # Córdoba. Se comparan también las palabras que quedaron afuera,
    # ignorando las cortas, que son abreviaturas ya expandidas.
    def descartadas(texto, tokens):
        # sin paréntesis ni puntos: "(LP)" no es una palabra que distinga
        limpio = re.sub(r"[^\w\s]", " ", norm(texto))
        return {p for p in limpio.split()
                if p not in tokens and len(p) > 3}

    return (descartadas(nombre, ta) ^ descartadas(canon, tb)) <= _RELLENO


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
    # El femenino queda afuera por ahora: el modo club es de los planteles
    # masculinos y mezclarlos confunde. Se saca de acá y listo.
    suyos, err = [], None
    for lid in (l for l in LIGAS if l != "fem"):
        try:
            juegos = (all_games(ttl=120) if lid == "lpf"
                      else api_liga_games({"id": [lid]}).get("games", []))
        except Exception as e:
            err = str(e)
            continue
        for m in juegos:
            lados = [m["home"].get("canon"), m["away"].get("canon"),
                     m["home"].get("name"), m["away"].get("name")]
            if any(mismo_club(x, canon) for x in lados if x):
                # en las copas la ronda tiene nombre, no número de fecha
                etapa = m.get("etapa") or m.get("stage") or ""
                suyos.append(dict(m, liga=lid, ligaNombre=LIGAS[lid]["nombre"],
                                  ronda=etapa if LIGAS[lid].get("copa") else None))

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


# Clubes cuyo "VAR" del logo va en negro. El segundo color de la camiseta
# no siempre sirve: el celeste de Belgrano sobre la barra celeste no se lee.
VAR_NEGRO = {"Belgrano", "Banfield", "Gimnasia y Esgrima (LP)", "Independiente",
             "Lanús", "Barracas Central", "Estudiantes (LP)",
             "Independiente Rivadavia", "Sarmiento (J)", "Unión",
             "Atlético Tucumán", "Estudiantes (RC)", "Huracán", "Instituto",
             "Platense", "Talleres (C)"}


# Los datos que no salen de ninguna fuente automática. Belgrano va suelto
# porque fue el primero; los otros veintinueve se arman más abajo a partir
# de _OTROS_CLUBES y se agregan a este mismo diccionario.
CLUBES_INFO = {
    "Belgrano": {
        "nombre": "Club Atlético Belgrano",
        "apodo": "El Pirata",
        "fundado": 1905,
        "estadio": "Estadio Julio César Villagra",
        "estadioApodo": "Gigante de Alberdi",
        "direccion": "Arturo Orgaz 510, Alberdi, Córdoba",
        "capacidad": 30000,
        "sitio": "https://belgrano.com.ar",
        # La 2025/26 de Umbro: celeste lisa con vivos negros la titular, y
        # negra con vivos celestes la suplente. No van las rayas de otras
        # épocas.
        "camisetas": {
            "titular": {
                "patron": "liso", "base": "#29a9e1", "raya": "#29a9e1",
                "detalle": "#141414", "cuello": "#141414",
            },
            "suplente": {
                "patron": "liso", "base": "#141414", "raya": "#141414",
                "detalle": "#29a9e1", "cuello": "#29a9e1",
            },
        },
    },
}


# El resto de Primera. Acá va lo que no cambia de un año al otro: nombre,
# apodo, fundación, cancha y —sobre todo— el diseño de la camiseta.
#
# Sobre las camisetas. Las treinta están confirmadas con la foto de la
# camiseta de esta temporada: no es el diseño "de siempre" de cada club sino
# el que se está usando ahora.
#
# Eso importa porque a veces el club se aleja de su propia tradición. La de
# Banfield 2026, por los 130 años, es una banda diagonal y no las rayas
# verticales; la suplente de River es la tricolor a bastones y no la banda
# en otro color. Cuando alguna cambie, se cambia acá y listo.
#
# Lo que NO va: los sponsors y la marca deportiva. Son marcas registradas
# ajenas, no identifican al club y copiarlas acá es meterse en un lío al
# pedo. Redibujarlas a mano o copiar el png de otro sitio, lo mismo.
#
# El escudo sí va, pero enlazado y no copiado: la camiseta apunta a la
# misma imagen que la página ya usa al lado del nombre del club, que es la
# de la fuente. No se hospeda ninguna copia ni se redibuja nada. Es el
# mismo uso que hace cualquier tabla de posiciones —identificar al club—
# y sin él la camiseta de un club de rayas blancas y negras es la de
# cualquiera de los cuatro que juegan igual.
#
# Si querés una camiseta puntual clavada al detalle de este año, pasame la
# foto como hiciste con la de Belgrano y la dejo exacta.
#
# Las capacidades son las de uso corriente y pueden variar según la fuente:
# tomalas como orientativas hasta que las confirmemos una por una.
#
# El apodo del estadio va sólo cuando es el que usa todo el mundo. Inventar
# uno para rellenar es peor que dejarlo vacío.
_OTROS_CLUBES = {
    "River Plate": {
        "nombre": "Club Atlético River Plate", "apodo": "El Millonario",
        "fundado": 1901, "estadio": "Estadio Más Monumental",
        "estadioApodo": "El Monumental",
        "direccion": "Av. Figueroa Alcorta 7597, Núñez, CABA",
        "capacidad": 83214, "sitio": "https://www.riverplate.com",
        # La banda cae del hombro izquierdo a la cadera derecha, así que
        # mirándola de frente va de arriba a la derecha hacia abajo a la
        # izquierda. La teníamos al revés.
        "titular": ("banda", "#fbfbfb", "#e0202f", "#131313",
                    {"invertida": True}),
        # La tricolor: bastones rojos sobre blanco, con un hilo negro fino
        # a cada lado de cada bastón. Sin el hilo son dos colores, no tres,
        # y "tricolor" deja de querer decir algo.
        "suplente": ("bastones", "#fbfbfb", "#d32232", "#131313",
                     {"hilo": "#131313", "mangaBanda": "#d32232",
                      "mangaHilo": "#131313"}),
    },
    # ── Confirmadas con foto ─────────────────────────────────────────────
    "Boca Juniors": {
        "nombre": "Club Atlético Boca Juniors", "apodo": "El Xeneize",
        "fundado": 1905, "estadio": "Estadio Alberto J. Armando",
        "estadioApodo": "La Bombonera",
        "direccion": "Brandsen 805, La Boca, CABA",
        "capacidad": 54000, "sitio": "https://www.bocajuniors.com.ar",
        "titular": ("franja", "#12409a", "#f2b024", "#f2b024"),
        # la suplente no es una franja sola: son franjas celestes y oro
        # sobre blanco, de arriba a abajo
        "suplente": ("franjas", "#f6f6f6", "#2f56c4", "#12409a", "#f2c73c"),
    },
    "Racing": {
        "nombre": "Racing Club", "apodo": "La Academia",
        "fundado": 1903, "estadio": "Estadio Presidente Perón",
        "estadioApodo": "El Cilindro",
        "direccion": "Mozart y Cuyo, Avellaneda",
        "capacidad": 51389, "sitio": "https://www.racingclub.com.ar",
        "titular": ("rayas", "#ffffff", "#6cb4e4", "#1a2b5e"),
        "suplente": ("liso", "#1a2b5e", "#1a2b5e", "#6cb4e4"),
    },
    "Independiente": {
        "nombre": "Club Atlético Independiente", "apodo": "El Rojo",
        "fundado": 1905,
        "estadio": "Estadio Libertadores de América - Ricardo Enrique Bochini",
        "direccion": "Bochini 751, Avellaneda",
        "capacidad": 48069, "sitio": "https://clubaindependiente.com.ar",
        "titular": ("liso", "#e02329", "#e02329", "#ffffff"),
        "suplente": ("liso", "#f8f8f8", "#f8f8f8", "#e02329"),
    },
    "San Lorenzo": {
        "nombre": "Club Atlético San Lorenzo de Almagro", "apodo": "El Ciclón",
        "fundado": 1908, "estadio": "Estadio Pedro Bidegain",
        "estadioApodo": "El Nuevo Gasómetro",
        "direccion": "Av. Perito Moreno 1500, Bajo Flores, CABA",
        "capacidad": 47964, "sitio": "https://sanlorenzo.com.ar",
        "titular": ("bastones", "#2a3a86", "#d03a2a", "#ffffff"),
        # bordó con los vivos azules, no blanca
        "suplente": ("liso", "#8f2437", "#8f2437", "#26397a"),
    },
    "Huracán": {
        "nombre": "Club Atlético Huracán", "apodo": "El Globo",
        "fundado": 1908, "estadio": "Estadio Tomás Adolfo Ducó",
        "estadioApodo": "El Palacio Ducó",
        "direccion": "Av. Amancio Alcorta 2570, Parque Patricios, CABA",
        "capacidad": 48314, "sitio": "https://cahuracan.com",
        # blanca con la franja roja vertical al medio, no blanca a secas
        "titular": ("centro", "#f8f8f8", "#e22128", "#e22128"),
        "suplente": ("liso", "#e02329", "#e02329", "#ffffff"),
    },
    "Vélez Sarsfield": {
        # la V azul en el pecho: no hay otra camiseta en el fútbol argentino
        # que se reconozca por una letra
        "nombre": "Club Atlético Vélez Sarsfield", "apodo": "El Fortín",
        "fundado": 1910, "estadio": "Estadio José Amalfitani",
        "estadioApodo": "El Fortín",
        "direccion": "Av. Juan B. Justo 9200, Liniers, CABA",
        "capacidad": 49540, "sitio": "https://velez.com.ar",
        # la V va sólo adelante: la espalda es lisa
        "titular": ("uve", "#fbfbfb", "#1a4fd8", "#1a4fd8",
                    {"espalda": {"patron": "liso"}}),
        "suplente": ("uve", "#16255c", "#2b5fe0", "#2b5fe0",
                     {"espalda": {"patron": "liso"}}),
    },
    "Argentinos Juniors": {
        # las tenía al revés: Argentinos juega de rojo, no de blanco
        "nombre": "Asociación Atlética Argentinos Juniors", "apodo": "El Bicho",
        "fundado": 1904, "estadio": "Estadio Diego Armando Maradona",
        "direccion": "Boyacá 2152, La Paternal, CABA",
        "capacidad": 26000, "sitio": "https://argentinosjuniors.com.ar",
        # Las tres de Umbro 25/26, calcadas de las fotos oficiales.
        #
        # Lo que comparten: manga ranglan —y la costura no es la misma de
        # los dos lados: adelante cae casi a plomo desde el cuello y atrás
        # baja mucho más tendida—, cuello banda y un panel estampado de
        # estrellas y del año 1985. El panel no hace el mismo recorrido en
        # las tres, y por eso hay dos formas y no una sola con distinto
        # ancho.
        #
        # La roja: dos vivos blancos que caen en el 70% y el 80% del ancho
        # del pecho, cortados por la costura, que es de donde nacen. El
        # panel va pegado al filo del cuerpo, dobla sobre la axila y baja
        # por debajo de la manga hasta el puño —ahí el puño también es del
        # estampado—. Atrás, la cinta roja del cuello se abre un tramo
        # blanco con las iniciales.
        "titular": {
            "patron": "vivo", "base": "#d8332e", "raya": "#ffffff",
            "detalle": "#ffffff", "manga": "#d8332e", "puno": "#d8332e",
            "cuello": "#d8332e", "cuelloTipo": "muesca",
            "cuelloVivo": "#ffffff", "cuelloBorde": "#c62c27",
            "costuras": True,
            "costados": {"fondo": "#f2dcda", "color": "#cf332e",
                         "contorno": True},
            "espalda": {"patron": "liso", "cuello": "#d8332e",
                        "cuelloVivo": "#d8332e",
                        "cuelloTexto": {"texto": "A.A.A.J.",
                                        "color": "#d8332e",
                                        "fondo": "#ffffff"}},
        },
        # La blanca: cinco bandas grises anchas que empiezan bien abajo del
        # escudo. Acá el panel va pegado a la costura ranglan —nace al lado
        # del cuello, cruza el hombro y sigue por el flanco afinándose
        # hasta cerrar un poco más abajo de la manga—. Atrás es blanca
        # lisa, con un hilo rojo finito en el ruedo.
        "suplente": {
            "patron": "franjas", "base": "#fbfbfb", "raya": "#c8ccd1",
            "raya2": "#fbfbfb", "alto": 18, "hueco": 0, "desde": 64,
            "detalle": "#d8332e", "manga": "#fbfbfb", "puno": "#fbfbfb",
            "cuello": "#fbfbfb", "cuelloVivo": "#d8332e", "costuras": True,
            "costados": {"fondo": "#fbfbfb", "color": "#e0483f",
                         "ranglan": 13, "hasta": 133},
            "espalda": {"patron": "liso", "costados": None,
                        "cuello": "#fbfbfb", "cuelloVivo": "#d8332e",
                        "ruedo": "#d8332e", "ruedoAncho": 2,
                        "cuelloTexto": {"texto": "1985", "color": "#ffffff",
                                        "fondo": "#d8332e"}},
        },
        # La tercera: azul marino jaspeado y el mismo panel que la blanca
        # pero liso, sin las estrellas. El cuello es dorado por delante y
        # azul por detrás.
        "tercera": {
            "patron": "liso", "base": "#2b3560", "raya": "#2b3560",
            "detalle": "#e6cda6", "manga": "#2b3560", "puno": "#2b3560",
            "cuello": "#c9a26d", "sinBrillo": True, "costuras": True,
            "costados": {"fondo": "#e8cfae", "color": "#e8cfae",
                         "liso": True, "ranglan": 14, "hasta": 133},
            "agua": {"oscuro": "#39436f", "medio": "#2f3862",
                     "claro": "#252d51", "semilla": 4, "grano": 0.055,
                     "corte": 0.5, "octavas": 2, "punto": 1.2,
                     "franja": "0 0 0 0 0", "dureza": 4},
            "espalda": {"cuello": "#2b3560", "costados": None,
                        "cuelloTexto": {"texto": "A.A.A.J.",
                                        "color": "#e6cda6"}},
        },
    },
    "Lanús": {
        "nombre": "Club Atlético Lanús", "apodo": "El Granate",
        "fundado": 1915,
        "estadio": "Estadio Ciudad de Lanús - Néstor Díaz Pérez",
        "estadioApodo": "La Fortaleza",
        "direccion": "Av. Hipólito Yrigoyen 3750, Lanús",
        "capacidad": 47027, "sitio": "https://clublanus.com",
        "titular": ("liso", "#6b2233", "#6b2233", "#e08a92"),
        "suplente": ("liso", "#f8f8f8", "#f8f8f8", "#8f2438"),
    },
    "Banfield": {
        # Ojo: la 2026 es la de los 130 años y rompe con la tradición. No
        # son las rayas verticales de siempre sino una banda diagonal
        # verde, en blanco la titular y en negro la suplente. El año que
        # viene esto seguramente vuelva a cambiar.
        "nombre": "Club Atlético Banfield", "apodo": "El Taladro",
        "fundado": 1896, "estadio": "Estadio Florencio Sola",
        "direccion": "Arenales 1457, Banfield",
        "capacidad": 34901, "sitio": "https://clubabanfield.org",
        # la diagonal cae al revés que la de River
        "titular": ("banda", "#f6f6f6", "#1e9b47", "#1e9b47",
                    {"invertida": True}),
        "suplente": ("banda", "#15181b", "#20a04b", "#20a04b",
                     {"invertida": True}),
    },
    "Estudiantes (LP)": {
        "nombre": "Club Estudiantes de La Plata", "apodo": "El Pincha",
        "fundado": 1905, "estadio": "Estadio Jorge Luis Hirschi",
        "estadioApodo": "UNO",
        "direccion": "Calle 1 y 57, La Plata",
        "capacidad": 30018, "sitio": "https://estudiantesdelaplata.com",
        "titular": ("bastones", "#ffffff", "#d92130", "#131313"),
        "suplente": ("liso", "#f8f8f8", "#f8f8f8", "#d92130"),
    },
    "Gimnasia y Esgrima (LP)": {
        "nombre": "Club de Gimnasia y Esgrima La Plata", "apodo": "El Lobo",
        "fundado": 1887, "estadio": "Estadio Juan Carmelo Zerillo",
        "estadioApodo": "El Bosque",
        "direccion": "Calle 60 y 118, La Plata",
        "capacidad": 33000, "sitio": "https://www.gimnasia.org.ar",
        # el Lobo no juega a rayas verticales: es la franja azul cruzada
        "titular": ("franja", "#f6f6f6", "#1b3f8f", "#1b3f8f"),
        # azul con hilos blancos finitos, no aros anchos
        "suplente": ("franjas", "#16306e", "#ffffff", "#ffffff",
                     {"alto": 3, "hueco": 22}),
    },
    "Newell's Old Boys": {
        # media roja y media negra, partida al medio
        "nombre": "Club Atlético Newell's Old Boys", "apodo": "La Lepra",
        "fundado": 1903, "estadio": "Estadio Marcelo Bielsa",
        "estadioApodo": "El Coloso del Parque",
        "direccion": "Parque Independencia, Rosario",
        "capacidad": 42000, "sitio": "https://www.newellsoldboys.com.ar",
        "titular": ("mitades", "#e0342c", "#151515", "#e0342c"),
        "suplente": ("liso", "#f8f8f8", "#f8f8f8", "#e0342c"),
    },
    "Rosario Central": {
        "nombre": "Club Atlético Rosario Central", "apodo": "El Canalla",
        "fundado": 1889, "estadio": "Estadio Gigante de Arroyito",
        "estadioApodo": "El Gigante de Arroyito",
        "direccion": "Av. Génova 640, Rosario",
        "capacidad": 41654, "sitio": "https://rosariocentral.com",
        # los bastones son sólo del frente: la espalda es azul lisa
        "titular": ("bastones", "#2d5fd0", "#f5c518", "#ffffff",
                    {"espalda": {"patron": "liso"}}),
        "suplente": ("liso", "#fbfbfb", "#fbfbfb", "#2d5fd0"),
    },
    "Talleres (C)": {
        "nombre": "Club Atlético Talleres", "apodo": "La T",
        "fundado": 1913, "estadio": "Estadio Mario Alberto Kempes",
        "estadioApodo": "El Kempes",
        "direccion": "Av. Cárcano s/n, Córdoba",
        "capacidad": 57000, "sitio": "https://www.clubtalleres.com.ar",
        # Bastones anchos, no rayas finas: la titular 2026 lleva cuatro
        # franjas azules gruesas sobre blanco, con las mangas azules
        # enteras. Y mueren en la costura, así que atrás es blanca con los
        # costados azules.
        # No son bastones parejos: hay uno central bien grueso, partido al
        # medio por un hilo blanco, y dos finos a los costados. Las mangas
        # van azules enteras. Atrás es blanca: el diseño muere en la costura.
        # Las mangas son blancas como el cuerpo; lo único azul es el puño,
        # la cinta de la costura por donde sale el brazo.
        "titular": ("bastoncentral", "#fbfbfb", "#1e2f6b", "#1e2f6b",
                    {"manga": "#fbfbfb", "puno": "#1e2f6b",
                     "espalda": {"patron": "liso"}}),
        # La suplente azul: cuello y puños en crudo —no en blanco— y un
        # paño en diagonal del hombro a la axila en un azul más claro, que
        # es un corte de la tela y no una franja de otro color.
        "suplente": ("liso", "#26439c", "#26439c", "#efe6d4",
                     {"puno": "#efe6d4", "diagonal": "#3a5cc4",
                      "diagonalInvertida": True,
                      "diagonalSoloAdelante": True}),
    },
    "Instituto": {
        "nombre": "Instituto Atlético Central Córdoba", "apodo": "La Gloria",
        "fundado": 1918, "estadio": "Estadio Juan Domingo Perón",
        "estadioApodo": "Alta Córdoba",
        "direccion": "Av. Cruz Roja Argentina, Córdoba",
        "capacidad": 26000, "sitio": "https://institutoacc.com.ar",
        # el blanco es el fondo y el rojo la raya, no al revés
        "titular": ("rayas", "#f8f8f8", "#d5232c", "#2b3440"),
        "suplente": ("liso", "#8b5fd0", "#8b5fd0", "#e8484f"),
    },
    "Atlético Tucumán": {
        "nombre": "Club Atlético Tucumán", "apodo": "El Decano",
        "fundado": 1902, "estadio": "Estadio Monumental José Fierro",
        "direccion": "Av. Roca 950, San Miguel de Tucumán",
        "capacidad": 35200, "sitio": "https://www.clubatleticotucuman.com.ar",
        "titular": ("rayas", "#5ec3ef", "#ffffff", "#111111"),
        # azul y negra a rayas, nada que ver con la titular
        "suplente": ("rayas", "#2a5cd8", "#131313", "#ffffff"),
    },
    "Central Córdoba (SdE)": {
        "nombre": "Club Atlético Central Córdoba", "apodo": "El Ferroviario",
        "fundado": 1919, "estadio": "Estadio Alfredo Terrera",
        "direccion": "Santiago del Estero",
        "capacidad": 23000, "sitio": "https://www.cacentralcordoba.com",
        "titular": ("rayas", "#131313", "#f4f4f4", "#f4f4f4"),
        "suplente": ("liso", "#f6f6f6", "#f6f6f6", "#131313"),
    },
    "Unión": {
        "nombre": "Club Atlético Unión", "apodo": "El Tatengue",
        "fundado": 1907, "estadio": "Estadio 15 de Abril",
        "direccion": "Av. López y Planes 3200, Santa Fe",
        "capacidad": 28000, "sitio": "https://www.clubaunion.com.ar",
        "titular": ("rayas", "#fbfbfb", "#e02b2b", "#26397a"),
        # roja adelante y azul atrás, tal cual
        "suplente": ("liso", "#d8322f", "#d8322f", "#26397a",
                     {"espalda": {"base": "#26397a", "detalle": "#d8322f",
                                  "cuello": "#d8322f"}}),
    },
    "Defensa y Justicia": {
        "nombre": "Club Social y Deportivo Defensa y Justicia",
        "apodo": "El Halcón", "fundado": 1935,
        "estadio": "Estadio Norberto Tomaghello",
        "direccion": "Av. Frías 361, Florencio Varela",
        "capacidad": 16800, "sitio": "https://www.defensayjusticia.org.ar",
        # también las tenía dadas vuelta: Defensa juega de amarillo
        "titular": ("liso", "#f5d117", "#f5d117", "#12502c"),
        "suplente": ("liso", "#16281c", "#16281c", "#f5d117"),
    },
    "Tigre": {
        "nombre": "Club Atlético Tigre", "apodo": "El Matador",
        "fundado": 1902, "estadio": "Estadio José Dellagiovanna",
        "direccion": "Italia 1001, Victoria, Tigre",
        "capacidad": 26500, "sitio": "https://catigre.com.ar",
        # azul con la franja roja cruzada en el pecho
        "titular": ("franja", "#1d5299", "#c62b32", "#c62b32"),
        # blanca con las dos franjas, la roja arriba y la azul abajo
        "suplente": ("doblefranja", "#fbfbfb", "#d8382f", "#1f4fc4",
                     {"raya2": "#1f4fc4", "espalda": {"patron": "liso"}}),
    },
    "Platense": {
        "nombre": "Club Atlético Platense", "apodo": "El Calamar",
        "fundado": 1905, "estadio": "Estadio Ciudad de Vicente López",
        "direccion": "Manuel Ugarte 2380, Vicente López",
        "capacidad": 26000, "sitio": "https://cap.org.ar",
        # la franja marrón cruzada, en blanco la titular y al revés la
        # otra. Atrás no lleva franja: es lisa de los dos lados.
        "titular": ("franja", "#fbfbfb", "#5f4534", "#5f4534",
                    {"espalda": {"patron": "liso"}}),
        "suplente": ("franja", "#5f4534", "#fbfbfb", "#fbfbfb",
                     {"espalda": {"patron": "liso"}}),
    },
    "Barracas Central": {
        "nombre": "Club Atlético Barracas Central", "apodo": "El Guapo",
        "fundado": 1904, "estadio": "Estadio Claudio Tapia",
        "direccion": "Luna 1500, Barracas, CABA",
        "capacidad": 4500, "sitio": "https://www.barracascentral.com",
        "titular": ("bastones", "#ffffff", "#d2232a", "#111111"),
        # negra con los vivos rojos en cuello y puños
        "suplente": ("liso", "#131313", "#131313", "#e8323a"),
    },
    "Deportivo Riestra": {
        "nombre": "Club Deportivo Riestra", "apodo": "El Malevo",
        "fundado": 1931, "estadio": "Estadio Guillermo Laza",
        "direccion": "Barrio Nueva Pompeya, CABA",
        # el club no tiene sitio propio: lo que publica va por su cuenta
        "capacidad": 3000, "sitio": "https://x.com/prensariestra",
        "titular": ("liso", "#131313", "#131313", "#f6f6f6"),
        "suplente": ("liso", "#f6f6f6", "#f6f6f6", "#131313"),
    },
    "Aldosivi": {
        "nombre": "Club Atlético Aldosivi", "apodo": "El Tiburón",
        "fundado": 1913, "estadio": "Estadio José María Minella",
        "estadioApodo": "El Minella",
        "direccion": "Mar del Plata",
        "capacidad": 35354, "sitio": "https://www.aldosivi.com",
        # Las tres de la 2026/27, sacadas de las fotos oficiales.
        #
        # La titular: siete franjas contadas —cuatro verdes y tres
        # amarillas, la del medio amarilla— y no rayas sueltas, que
        # quedaban centradas donde caía la cuenta. Las mangas repiten el
        # rayado siguiendo la curva del brazo. Atrás, abajo del cuello,
        # dice LA FAMILIA, que es el nombre de la colección.
        "titular": {
            "patron": "rayasn", "cantidad": 7,
            "base": "#f2d65c", "raya": "#2f9e82", "detalle": "#f2d65c",
            "manga": "#2f9e82", "mangaRayas": True, "puno": "#f2d65c",
            "cuello": "#2f9e82", "cuelloLados": "#f2d65c",
            "cuelloAtras": "#f2d65c", "textura": "#4dbb9b",
            "leyenda": {"texto": "LA FAMILIA", "letra": "didona",
                        "color": "#23492f", "tam": 4, "y": 42,
                        "ancho": 19, "claro": 6},
        },
        # La suplente: negra, con el puño mitad amarillo flúor y mitad
        # verde, y el cuello negro adelante con un costado de cada color.
        # Atrás dice EL BARRIO, verde arriba y amarillo abajo.
        "suplente": {
            "patron": "liso",
            "base": "#141414", "raya": "#141414", "detalle": "#c9e04a",
            "cuello": "#141414", "cuelloIzq": "#3fbe6a",
            "cuelloDer": "#d8e832", "puno": "#d8e832", "puno2": "#3fbe6a",
            "sinBrillo": True,
            "leyenda": {"texto": "EL BARRIO", "letra": "angulosa",
                        "degrade": ["#3fd06d", "#e6e838"], "tam": 4,
                        "y": 42, "ancho": 17, "claro": 7, "trazo": 9},
        },
        # La tercera: la trama sublimada que imita el mar, verde petróleo
        # arriba y aguamarina abajo. No son manchas dibujadas a mano sino
        # ruido fractal cortado con un escalón, con el borde punteado,
        # que es como está hecha la de verdad.
        "tercera": {
            "patron": "liso",
            "base": "#cfeae4", "raya": "#cfeae4", "detalle": "#0f7b8a",
            "manga": "#cfeae4", "cuello": "#0f7b8a", "puno": "#0f7b8a",
            "sinBrillo": True,
            "agua": {"oscuro": "#0a6274", "medio": "#2e959e",
                     "claro": "#d2eae5", "semilla": 7, "grano": 0.05,
                     "corte": 0.57, "octavas": 2, "punto": 1.2,
                     "franja": "0 .35 1 .35 0"},
            "leyenda": {"texto": "LOS PRINCIPIOS", "letra": "sistema",
                        "color": "#ecdfba", "tam": 4, "y": 42,
                        "ancho": 28, "peso": 700, "espacio": 0.35},
        },
    },
    "Sarmiento (J)": {
        "nombre": "Club Atlético Sarmiento", "apodo": "El Verde",
        "fundado": 1911, "estadio": "Estadio Eva Perón",
        "direccion": "Junín, Buenos Aires",
        "capacidad": 22000, "sitio": "https://clubatleticosarmiento.com",
        "titular": ("liso", "#14603a", "#14603a", "#2fbf6a"),
        "suplente": ("liso", "#fbfbfb", "#fbfbfb", "#14603a"),
    },
    "Independiente Rivadavia": {
        "nombre": "Club Sportivo Independiente Rivadavia", "apodo": "La Lepra",
        "fundado": 1913, "estadio": "Estadio Bautista Gargantini",
        "direccion": "Mendoza",
        "capacidad": 25000, "sitio": "https://independienterivadavia.com.ar",
        # azul lisa, no a rayas
        "titular": ("liso", "#1b2a5e", "#1b2a5e", "#ffffff"),
        "suplente": ("liso", "#f8f8f8", "#f8f8f8", "#1b2a5e"),
    },
    "Estudiantes (RC)": {
        "nombre": "Club Atlético Estudiantes", "apodo": "El León",
        "fundado": 1968, "estadio": "Estadio Ciudad de Río Cuarto",
        "direccion": "Río Cuarto, Córdoba",
        "capacidad": 12000, "sitio": "https://aaestudiantes.accessfan.ar",
        # celeste lisa, no a rayas
        "titular": ("liso", "#3a9fdb", "#3a9fdb", "#ffffff"),
        "suplente": ("liso", "#1f4a45", "#1f4a45", "#dfe8e6"),
    },
    "Gimnasia y Esgrima (M)": {
        "nombre": "Club Atlético Gimnasia y Esgrima",
        "apodo": "El Lobo mendocino", "fundado": 1908,
        "estadio": "Estadio Víctor Legrotaglie",
        "direccion": "Mendoza",
        "capacidad": 15000, "sitio": "https://gimnasiayesgrimamza.com.ar",
        "titular": ("rayas", "#f6f6f6", "#131313", "#131313"),
        "suplente": ("liso", "#f6f6f6", "#f6f6f6", "#131313"),
    },
}


def _kit(t):
    """
    Del atajo al diccionario que usa el dibujo.

    (patrón, base, raya, detalle) y, si hace falta, un quinto valor:
    un color suelto para el segundo tono de las franjas alternadas —el
    celeste y oro de la suplente de Boca— o un diccionario con lo que sea
    que ese diseño necesite, como el grosor de las líneas.

    El atajo es para las camisetas que se resuelven con cuatro datos. Las
    que no —las tres de Aldosivi, con las franjas contadas, las leyendas
    de la espalda y la trama del mar— se escriben derecho como
    diccionario y pasan tal cual.
    """
    if isinstance(t, dict):
        return dict(t)
    patron, base, raya, detalle = t[:4]
    k = {"patron": patron, "base": base, "raya": raya,
         "detalle": detalle, "cuello": detalle}
    extra = t[4] if len(t) > 4 else None
    if isinstance(extra, dict):
        k.update(extra)
    elif extra:
        k["raya2"] = extra
    return k


for _n, _d in _OTROS_CLUBES.items():
    CLUBES_INFO[_n] = {
        "nombre": _d["nombre"], "apodo": _d["apodo"], "fundado": _d["fundado"],
        "estadio": _d["estadio"], "estadioApodo": _d.get("estadioApodo"),
        "direccion": _d["direccion"], "capacidad": _d["capacidad"],
        "sitio": _d["sitio"],
        # La tercera sólo la tienen algunos: se agrega si está cargada y
        # si no, el club muestra dos y listo.
        "camisetas": {_c: _kit(_d[_c])
                      for _c in ("titular", "suplente", "tercera")
                      if _d.get(_c)},
    }


def api_club_info(q):
    """
    Todo lo del club para su página. /api/club-info?name=Belgrano

    Tardaba 7,8 segundos: adentro recorre las trece ligas para armar el
    fixture del club, y a cada una le pide además la tabla de posiciones
    para saber en qué puesto va. Eran veintiséis esperas en fila.

    Ahora se piden todas juntas, y encima la ficha entera se sirve al toque
    desde lo último armado. Un club no cambia de un minuto al otro: lo que
    se mueve son los resultados, y para eso está el minuto a minuto.
    """
    nombre = (q.get("name") or [""])[0].strip()
    if not nombre:
        return {"error": "falta el parámetro name"}
    canon = match_team(nombre) or nombre
    return al_toque("club:%s" % canon, lambda: armar_club_info(canon),
                    frescura=90)


def armar_club_info(canon):
    ficha = dict(CLUBES_INFO.get(canon) or {})
    colores = COLORES.get(canon)
    escudo = None
    try:
        escudo = (_logos().get(canon) or {}).get("logo")
    except Exception:
        pass

    # el estadio, si no está cargado a mano: el que más se repite de local
    if not ficha.get("estadio"):
        canchas = {}
        try:
            for m in all_games(ttl=600):
                if m["home"].get("canon") == canon and m.get("venue"):
                    canchas[m["venue"]] = canchas.get(m["venue"], 0) + 1
        except Exception:
            pass
        if canchas:
            ficha["estadio"] = max(canchas, key=canchas.get)

    if ficha.get("estadio"):
        from urllib.parse import quote
        ficha["mapa"] = ("https://www.google.com/maps/search/?api=1&query="
                         + quote("%s %s" % (ficha["estadio"],
                                            ficha.get("direccion") or "Argentina")))

    # El fixture completo del club, separado por competencia. Cada liga se
    # resuelve entera —sus partidos y el puesto del club en su tabla— y las
    # trece van a la vez: era lo que hacía esperar ocho segundos.
    from concurrent.futures import ThreadPoolExecutor

    def de_liga(lid):
        try:
            juegos = (all_games(ttl=600) if lid == "lpf"
                      else api_liga_games({"id": [lid]}).get("games", []))
        except Exception:
            return lid, None
        suyos = [m for m in juegos
                 if any(mismo_club(m[s].get("canon") or m[s].get("name"), canon)
                        for s in ("home", "away"))]
        if not suyos:
            return lid, None
        suyos.sort(key=lambda m: m.get("start") or "")

        # dónde está el club en ese torneo: zona, puesto, puntos y los
        # últimos cinco. En las copas no hay tabla, así que queda vacío.
        posicion = None
        if not LIGAS[lid].get("copa"):
            try:
                zonas = (api_standings({"live": ["1"]}).get("zones", [])
                         if lid == "lpf" else _sc_standings(LIGAS[lid]["sc"]))
                for z in zonas:
                    for i, r in enumerate(z.get("rows") or [], 1):
                        nom = r.get("canon") or r["team"]["name"]
                        if mismo_club(nom, canon):
                            posicion = {"zona": z.get("name"),
                                        "pos": r.get("pos") or i,
                                        "pts": r.get("pts"), "pj": r.get("pj"),
                                        "form": r.get("form") or [],
                                        "de": len(z.get("rows") or [])}
                            break
                    if posicion:
                        break
            except Exception:
                pass

        return lid, {"nombre": LIGAS[lid]["nombre"],
                     "copa": bool(LIGAS[lid].get("copa")),
                     "posicion": posicion,
                     "games": suyos}

    cuales = [l for l in LIGAS if l != "fem"]
    with ThreadPoolExecutor(max_workers=min(8, len(cuales))) as pool:
        traido = dict(pool.map(de_liga, cuales))
    # el orden es el de LIGAS, no el que hayan terminado los pedidos
    orden = [l for l in cuales if traido.get(l)]
    fixture = {l: traido[l] for l in orden}

    return {
        "club": canon,
        "escudo": escudo,
        "fixture": [dict(fixture[l], liga=l) for l in orden],
        # El radar promedio, sólo de la liga: en copa son pocos partidos.
        # Y del torneo que se está jugando, contra los treinta que lo
        # juegan. Si el fixture no se pudo leer se compara con lo que haya
        # guardado, que es peor pero es mejor que no mostrar nada.
        "radar": radar_promedio("lpf", canon, set(COLORES) | {canon},
                                del_torneo()),
        "primary": colores[0] if colores else None,
        "accent": colores[1] if colores else None,
        "var": "#111111" if canon in VAR_NEGRO else (colores[1] if colores else None),
        "info": ficha,
        "plantel": plantel_de(canon),
        "partidos": api_club({"name": [canon]}),
        "sitio": ficha.get("sitio") or SITIOS.get(canon),
        "tienda": TIENDAS.get(canon),
    }


def api_clubes(q):
    """Clubes de Primera con sus colores, para el modo club."""
    logos = {}
    try:
        logos = _logos()
    except Exception:
        pass
    return {"clubes": sorted(
        [{"name": n, "primary": c[0], "accent": c[1],
          "var": "#111111" if n in VAR_NEGRO else c[1],
          "logo": (logos.get(n) or {}).get("logo")}
         for n, c in COLORES.items()],
        key=lambda x: norm(x["name"]))}


def api_recorrido(q):
    """
    Qué tiene guardado cada torneo y en qué anda su recorrido.

    Existe porque estuve arreglando la bajada de calendarios a ciegas,
    deduciendo del log lo que se puede ver directamente. Muestra, por
    competencia: cuántos partidos hay, de qué temporadas, qué fases y qué
    fechas, y qué dicen los marcadores del recorrido.

      /api/recorrido             → todo
      /api/recorrido?id=lib      → sólo esa liga
      /api/recorrido?rehacer=lib → reabre los marcadores y la vuelve a
                                   recorrer ahora, sin borrar nada
      /api/recorrido?reconstruir=lib&confirmar=si
                                 → borra los partidos de ese torneo y los
                                   baja de cero. Con `todo` en vez de `lib`,
                                   todos. Pide confirmación porque borra.
    """
    pedido = (q.get("id") or [""])[0]
    rehacer = (q.get("rehacer") or [""])[0]
    reconstruir = (q.get("reconstruir") or [""])[0]

    hecho = None

    # ── volver a la copia de antes de reconstruir ───────────────────────
    restaurar = (q.get("restaurar") or [""])[0]
    if restaurar:
        if (q.get("confirmar") or [""])[0] != "si":
            return {"error": "esto reemplaza lo bajado por la copia guardada",
                    "comoHacerlo": "/api/recorrido?restaurar=%s&confirmar=si"
                                   % restaurar}
        objetivo = [l for l in LIGAS] if restaurar == "todo" else [restaurar]
        if any(l not in LIGAS for l in objetivo):
            return {"error": "liga desconocida: %s" % restaurar}
        vueltos = []
        for lid in objetivo:
            for comp in comps_de(LIGAS[lid]):
                copia, _ = almacen.leer("respaldo:%s" % comp)
                if not copia:
                    continue
                almacen.guardar("fixture:%s" % comp, copia["juegos"])
                for molde in ("hist:%s", "fut:%s"):
                    almacen.guardar(molde % comp, {})
                vueltos.append({"comp": comp, "partidos": len(copia["juegos"]),
                                "eraDe": copia.get("cuando")})
        return {"restaurado": vueltos or "no había copia guardada",
                "nota": "los marcadores quedaron reabiertos: el recorrido "
                        "vuelve a pasar y completa lo que falte"}

    # ── borrar y bajar de nuevo, desde cero ─────────────────────────────
    # Esto sí borra partidos, así que pide confirmación explícita en la
    # dirección. Es para cuando la base quedó en un estado raro y sale más
    # barato empezar de nuevo que adivinar qué le pasó.
    if reconstruir:
        if (q.get("confirmar") or [""])[0] != "si":
            return {"error": "esto borra los partidos guardados de ese torneo",
                    "comoHacerlo": "/api/recorrido?reconstruir=%s&confirmar=si"
                                   % reconstruir,
                    "ojo": ("Con reconstruir=todo se borran los de todos los "
                            "torneos. Se vuelven a bajar solos, pero tarda.")}
        objetivo = ([l for l in LIGAS] if reconstruir == "todo"
                    else [reconstruir])
        if any(l not in LIGAS for l in objetivo):
            return {"error": "liga desconocida: %s" % reconstruir}
        hecho, borrados, respaldo = [], 0, []
        cuando = dt.datetime.now().isoformat(timespec="seconds")
        for lid in objetivo:
            cfg = LIGAS[lid]
            for comp in comps_de(cfg):
                previos, _ = almacen.leer("fixture:%s" % comp)
                borrados += len(previos or [])
                # Copia de seguridad antes de borrar. Ocupa lugar, pero
                # perder meses de partidos por un botón mal apretado sale
                # bastante más caro que unos megas.
                if previos:
                    almacen.guardar("respaldo:%s" % comp,
                                    {"cuando": cuando, "juegos": previos})
                    respaldo.append(comp)
                almacen.guardar("fixture:%s" % comp, [])
                for molde in ("hist:%s", "fut:%s"):
                    almacen.guardar(molde % comp, {})
                # Primero la semilla: la ventana de partidos que la fuente
                # muestra ahora. Sin al menos uno guardado no hay de dónde
                # colgar el cursor y el recorrido no tiene por dónde empezar.
                try:
                    _sc_fixture(comp, ttl=0)
                except Exception:
                    pass
                for direccion, como in ((-1, "atrás"), (1, "adelante")):
                    r = caminar_fixture(comp, direccion, paginas=60)
                    hecho.append({"liga": lid, "comp": comp, "hacia": como,
                                  "paginas": r.get("paginas", 0),
                                  "nuevos": r.get("nuevos", 0),
                                  "total": r.get("total", 0),
                                  "listo": r.get("listo"),
                                  "motivo": r.get("motivo") or r.get("estado")})
        pedido = pedido or (reconstruir if reconstruir != "todo" else "")
        hecho = {"borrados": borrados, "recorridos": hecho,
                 "respaldo": {"competencias": respaldo, "cuando": cuando,
                              "comoVolver": "/api/recorrido?restaurar=%s&confirmar=si"
                                            % reconstruir} if respaldo else None}
    if rehacer:
        cfg = LIGAS.get(rehacer)
        if not cfg:
            return {"error": "liga desconocida: %s" % rehacer}
        paginas = max(1, min(60, _int((q.get("paginas") or ["30"])[0], 30)))
        hecho = []
        for comp in comps_de(cfg):
            for molde in ("hist:%s", "fut:%s"):
                almacen.guardar(molde % comp, {})
            for direccion, como in ((-1, "atrás"), (1, "adelante")):
                r = caminar_fixture(comp, direccion, paginas=paginas)
                hecho.append({"comp": comp, "hacia": como,
                              "paginas": r.get("paginas", 0),
                              "nuevos": r.get("nuevos", 0),
                              "total": r.get("total", 0),
                              "listo": r.get("listo"),
                              "motivo": r.get("motivo") or r.get("estado"),
                              "error": r.get("error")})
        pedido = pedido or rehacer

    salida = []
    for lid, cfg in LIGAS.items():
        if pedido and lid != pedido:
            continue
        comps = []
        for comp in comps_de(cfg):
            guardado, edad = almacen.leer("fixture:%s" % comp)
            juegos = guardado or []
            temporadas = {}
            for m in juegos:
                k = str(m.get("temporada"))
                temporadas[k] = temporadas.get(k, 0) + 1
            fases = {}
            for m in juegos:
                k = (m.get("stage") or "—")
                fases[k] = fases.get(k, 0) + 1
            rondas = sorted(r for r in {m.get("round") for m in juegos} if r)

            # Dos fases con la misma numeración se pisan.
            #
            # El Federal A juega una Primera Fase y una Segunda, y las dos
            # empiezan en la fecha 1. Si la fase no viene con nombre, las
            # dos fechas 1 se suman en una sola y en pantalla aparece el
            # doble de partidos: 34 donde deberían ser 17.
            #
            # Acá se listan las fechas donde eso pasa y con qué se podrían
            # separar: si los `etapaNum` son distintos alcanza con eso; si
            # son iguales, lo único que queda es la fecha del calendario,
            # porque una fase termina antes de que empiece la otra.
            porRondaG = {}
            for m in juegos:
                if m.get("round"):
                    porRondaG.setdefault(m["round"], []).append(m)

            def _entre(a, b):
                try:
                    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
                except Exception:
                    return 0

            mezcladas = []
            for r, ms in sorted(porRondaG.items()):
                dias = sorted((m.get("start") or "")[:10]
                              for m in ms if m.get("start"))
                etapas = sorted({str(m.get("stageNum")) for m in ms})
                if len(etapas) > 1 or (dias and _entre(dias[0], dias[-1]) > 60):
                    mezcladas.append({
                        "fecha": r, "partidos": len(ms),
                        "etapaNum": etapas,
                        "etapaFuente": sorted({str(m.get("etapaFuente"))
                                               for m in ms}),
                        "grupo": sorted({str(m.get("slot")) for m in ms}),
                        "desde": dias[0] if dias else None,
                        "hasta": dias[-1] if dias else None})

            hist, _ = almacen.leer("hist:%s" % comp)
            fut, _ = almacen.leer("fut:%s" % comp)
            comps.append({
                "comp": comp,
                "esPrevia": comp != cfg["sc"],
                "guardados": len(juegos),
                "temporadaActual": temporada_actual(comp),
                "porTemporada": temporadas,
                "fechasQueTiene": len(rondas),
                "fechasDelTorneo": fechas_del_torneo(comp),
                "rango": [rondas[0], rondas[-1]] if rondas else None,
                "fases": fases,
                "fechasMezcladas": mezcladas[:24],
                "atras": hist or {},
                "adelante": fut or {},
                "edadSegundos": round(edad) if edad else None,
            })
        # Lo que la página muestra de verdad, que no es lo mismo que lo
        # guardado de 365scores. La Liga Profesional, la Nacional y la B
        # Metro arman su calendario con AFA y usan 365scores sólo para
        # engancharle el minuto a minuto: mirar nada más el almacén de
        # 365scores para esas ligas es mirar el lugar equivocado.
        servido = None
        try:
            if lid == "lpf":
                juegos = all_games(ttl=300)
                fuente = "AFA / DataFactory"
            else:
                r = api_liga_games({"id": [lid]})
                juegos = r.get("games") or []
                fuente = ("AFA / DataFactory" if cfg.get("base")
                          else "laliga.com" if cfg.get("fixture_propio")
                          else "365scores")
            porRonda = {}
            for m in juegos:
                d = porRonda.setdefault(m.get("round") or m.get("etapa") or "—",
                                        {"partidos": 0, "conResultado": 0,
                                         "conLiveId": 0})
                d["partidos"] += 1
                if m.get("gh") is not None:
                    d["conResultado"] += 1
                if m.get("liveId"):
                    d["conLiveId"] += 1
            # Y cuáles son los que no engancharon, con nombre y fecha. Sin
            # esto sólo se sabe cuántos son, y para saber si el problema es
            # que faltan en la fuente o que no se aparean hay que poder
            # buscarlos a mano.
            def ficha(m):
                return {"fecha": m.get("round"),
                        "partido": "%s - %s" % (m["home"].get("canon")
                                                or m["home"]["name"],
                                                m["away"].get("canon")
                                                or m["away"]["name"]),
                        "dia": (m.get("start") or "")[:10]}
            sueltos = [ficha(m) for m in juegos if not m.get("liveId")]

            # Los que ya se jugaron y siguen sin marcador, con lo que dice
            # 365scores del mismo partido al lado. Así se ve de una si el
            # que no cargó el resultado fue AFA —y entonces hay que
            # completarlo— o si tampoco lo tiene la otra fuente, que es
            # otro problema. La fecha 21 de la Primera Nacional quedó con
            # nueve de dieciocho y sin esto no había cómo saber cuál.
            hoy = dt.date.today().isoformat()
            try:
                deSC = {str(x["id"]): x for x in fixture_de_liga(cfg)}
            except Exception:
                deSC = {}
            secos = []
            for m in juegos:
                dia = (m.get("start") or "")[:10]
                if m.get("gh") is not None or not dia or dia >= hoy:
                    continue
                lv = deSC.get(str(m.get("liveId") or ""))
                f = ficha(m)
                f["liveId"] = m.get("liveId")
                f["dice365"] = (None if not lv else
                                "%s %s-%s" % (lv.get("status"), lv.get("gh"),
                                              lv.get("ga")))
                secos.append(f)

            servido = {"fuente": fuente, "partidos": len(juegos),
                       "fechas": len(porRonda),
                       "sinLiveId": len(sueltos),
                       "cualesSinLiveId": sueltos[:24],
                       "sinResultado": len(secos),
                       "cualesSinResultado": secos[:24],
                       "porFecha": {str(k): v for k, v in
                                    sorted(porRonda.items(), key=lambda x: str(x[0]))}}
        except Exception as e:
            servido = {"error": "%s: %s" % (type(e).__name__, e)}

        salida.append({"id": lid, "nombre": cfg["nombre"], "comps": comps,
                       "loQueSeMuestra": servido})

    return {"version": VERSION_RECORRIDO, "programa": VERSION_APP,
            "ligas": salida, "rehecho": hecho,
            "como": ("Agregá ?id=lib para una sola, o ?rehacer=lib para "
                     "borrar sus marcadores y volver a bajarla ahora.")}


def api_buscar(q):
    """
    Buscador: clubes y jugadores. /api/buscar?q=aldosivi

    Los jugadores salen de lo que se fue juntando partido a partido, así que
    al principio hay pocos y con las fechas aparecen todos. Es a propósito:
    la única lista completa de planteles que existe es la que armamos
    nosotros mirando las formaciones.
    """
    texto = norm((q.get("q") or [""])[0])
    lid = (q.get("liga") or ["lpf"])[0]
    if len(texto) < 2:
        return {"q": texto, "clubes": [], "jugadores": []}

    def ordenar(items, clave):
        empiezan = [x for x in items if clave(x).startswith(texto)]
        contienen = [x for x in items
                     if texto in clave(x) and not clave(x).startswith(texto)]
        return empiezan + contienen

    try:
        clubes = ordenar(api_clubes({})["clubes"], lambda c: norm(c["name"]))[:6]
    except Exception:
        clubes = []

    jugadores = []
    try:
        tabla = agregado_jugadores(lid)
        candidatos = [{"name": v["nombre"], "club": v.get("club") or "",
                       "puesto": v.get("puesto") or "",
                       "partidos": v.get("partidos") or 0}
                      for v in tabla.values()]
        # los que más jugaron primero: es lo que más se busca
        candidatos.sort(key=lambda x: -x["partidos"])
        jugadores = ordenar(candidatos, lambda j: norm(j["name"]))[:8]
    except Exception:
        pass

    return {"q": texto, "clubes": clubes, "jugadores": jugadores,
            "liga": lid}


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

    # Cuánta memoria se está usando de caché. Sirve para diagnosticar los
    # reinicios por memoria del hosting sin tener que adivinar: si esto
    # está cerca del tope, el problema es acá; si está bajo, hay que
    # mirar en otro lado.
    with _lock:
        memoria = {"respuestas": len(_cache),
                   "megas": round(_cache_bytes / 1024 / 1024, 2),
                   "tope_megas": round(_CACHE_MAX_BYTES / 1024 / 1024, 1),
                   "escudos": len(_IMG_CACHE)}

    return {"apifootball": af, "base": almacen.estado(), "fuentes": fuentes,
            "memoria": memoria,
            "consejo": ("Si alguna liga dice ok=false con 0 partidos, el plan "
                        "gratis no cubre esa temporada. Mientras tanto la página "
                        "sigue andando con AFA y 365scores.")}


ROUTES = {
    "/api/detalles": api_detalles,
    "/api/atleta": api_atleta,
    "/api/diagnostico": api_diagnostico,
    # Con el desglose por familia: sin eso, "202 MB" no dice qué hacer.
    "/api/base": lambda q: dict(almacen.estado(),
                                pesos=almacen.pesos(),
                                limpieza=almacen.leer("limpieza:ultima")[0],
                                cacheQueSobra=[almacen.familia(p + "/?")
                                               for p in CACHE_QUE_SOBRA],
                                diasDeCache=DIAS_DE_CACHE),
    "/api/home": api_home,
    "/api/clubes": api_clubes,
    "/api/buscar": api_buscar,
    "/api/ranking": api_ranking,
    "/api/recorrido": api_recorrido,
    "/api/club": api_club,
    "/api/club-info": api_club_info,
    "/api/competencias": api_competencias,
    "/api/contenido": api_contenido,
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
    # se resuelve al llamarla porque se define más abajo, junto al resto de
    # lo que tiene que ver con servir la página
    "/api/tiempos": lambda q: api_tiempos(q),
    "/api/visitas": lambda q: visitas.resumen(),
    # /api/visita —sin la ese— se atiende aparte, en `_responder`: necesita
    # los encabezados del pedido y acá sólo llegan los parámetros.
}


# ── Qué se contesta con lo último armado, y cada cuánto se renueva ───────
#
# Todas estas devuelven lo mismo para todos: la tabla de posiciones de la
# fecha 6 es la misma para vos que para cualquiera. Antes cada visita la
# calculaba de nuevo, y por eso cambiar de fecha tardaba 1,3 segundos y
# cambiar de torneo disparaba cuatro cuentas de medio segundo cada una.
#
# El número es cuántos segundos vale lo armado antes de mandar a rearmarlo
# por atrás. No es cuánto se espera: nadie espera. Es cada cuánto se hace
# el trabajo. Lo que se mueve con los partidos en curso va corto; lo que
# cambia una vez por fecha, largo.
#
# Las que no están acá se calculan en cada pedido, como siempre. Se suman a
# esta lista a propósito y de a una: entrar por descuido algo que tenga que
# ser fresco sí o sí es peor que una ruta lenta.
AL_TOQUE = {
    "/api/games": 8,          # los partidos de una fecha, con lo que va en vivo
    "/api/rounds": 20,        # qué fechas hay
    "/api/standings": 10,     # las tablas se mueven con los goles en curso
    "/api/annual": 20,
    "/api/promedios": 60,     # los promedios no se mueven en un partido
    "/api/scorers": 60,
    "/api/liga": 30,          # tabla y goleadores de otra liga
    "/api/liga/games": 10,
    "/api/club": 60,          # el último y el próximo de un club
    "/api/clubes": 600,       # la lista de clubes no cambia nunca
    "/api/ligas": 600,
}


# Las direcciones propias de cada club. Por ahora sólo la de prueba; se
# suman solas a medida que se cargue CLUBES_INFO.
def _slug(nombre):
    """
    El nombre del club convertido en dirección web.

    Los paréntesis se van: /estudiantes-lp se puede pegar en un mensaje,
    /estudiantes-(lp) se rompe apenas alguien lo codifica.
    """
    s = norm(nombre).replace("(", " ").replace(")", " ")
    return "-".join(s.split())


def _rutas_de_club():
    """
    Todas las direcciones que llevan a la página de un club.

    Además de la larga —/central-cordoba-sde— se registra la corta cuando no
    hay con quién confundirla: /central-cordoba llega igual. Pero
    /estudiantes no, porque hay dos en Primera y no sabríamos a cuál llevar.
    """
    rutas = {}
    cortas = {}
    for nombre in CLUBES_INFO:
        rutas[_slug(nombre)] = nombre
        base = _slug(re.sub(r"\s*\([^)]*\)", "", nombre))
        if base and base != _slug(nombre):
            cortas.setdefault(base, []).append(nombre)
    for corta, duenos in cortas.items():
        if len(duenos) == 1 and corta not in rutas:
            rutas[corta] = duenos[0]
    return rutas


RUTAS_CLUB = _rutas_de_club()


# ── Las direcciones de la página ─────────────────────────────────────────
#
# Hasta acá la página era una sola dirección: entrabas a hayvar.com.ar y
# todo lo que pasaba después —abrir un torneo, una fecha, un partido— no
# quedaba escrito en ningún lado. No se podía compartir el link de un
# partido, el botón de atrás del navegador te sacaba del sitio, y para
# Google todo el sitio era una página vacía.
#
# Ahora cada cosa tiene su dirección. La página sigue siendo un solo
# archivo: el servidor devuelve el mismo index.html para todas y adentro se
# decide qué mostrar. Lo único que cambia acá es el título y la
# descripción, que son los que se ven en la solapa del navegador, en el
# resultado de Google y en la vista previa cuando alguien pega el link.
#
# Ojo: esta lista está repetida en index.html, porque la página tiene que
# saber leer la dirección antes de hablar con el servidor. Hay una prueba
# que compara las dos y falla si alguien toca una sola.
RUTAS_LIGA = {
    "liga-profesional": "lpf",
    "primera-nacional": "nacional",
    "primera-b-metro": "pbm",
    "federal-a": "fa",
    "copa-argentina": "ca",
    "libertadores": "lib",
    "sudamericana": "sud",
    "champions-league": "champions",
    "europa-league": "europa",
    "laliga": "laliga",
    "premier-league": "premier",
    "serie-a": "seriea",
    "bundesliga": "bundesliga",
    "futbol-femenino": "fem",
}

TITULO_BASE = "HAYVAR"
LEMA = "Resultados en vivo, tablas y estadísticas del fútbol argentino y del mundo."

# La página ya armada para cada dirección, con y sin comprimir. Ver _pagina.
_PAGINAS = {}


# ── Cuánto tarda cada cosa ───────────────────────────────────────────────
#
# "La página está lenta" no se arregla adivinando. Acá se anota cuánto tardó
# cada ruta, cuántas veces se pidió y cuál fue la peor. Ocupa nada —una
# entrada por ruta, cuatro números— y se mira en /api/tiempos.
#
# Se mide el tiempo del servidor solamente: desde que llega el pedido hasta
# que se contesta. Lo que tarde el celular en dibujar no se ve desde acá,
# pero si el servidor contesta en 40 ms y la página igual tarda tres
# segundos, ya sabemos que el problema no está de este lado. Que es
# justamente lo que hay que saber antes de tocar nada.
_TIEMPOS = {}
_tiempos_lock = threading.Lock()


def anotar_tiempo(ruta, ms, bytes_=0):
    with _tiempos_lock:
        t = _TIEMPOS.get(ruta)
        if t is None:
            t = _TIEMPOS[ruta] = {"n": 0, "total": 0.0, "peor": 0.0,
                                  "ultima": 0.0, "bytes": 0}
        t["n"] += 1
        t["total"] += ms
        t["peor"] = max(t["peor"], ms)
        t["ultima"] = ms
        t["bytes"] = max(t["bytes"], bytes_)


def api_tiempos(q):
    """
    Dónde se van los segundos. /api/tiempos

    Ordenado por lo que más tiempo consumió en total, que no es lo mismo que
    lo más lento: una ruta de 20 ms que se pide mil veces pesa más que una
    de dos segundos que se pide una vez.
    """
    with _tiempos_lock:
        filas = [{"ruta": r, "veces": t["n"],
                  "promedio_ms": round(t["total"] / t["n"]),
                  "peor_ms": round(t["peor"]),
                  "ultima_ms": round(t["ultima"]),
                  "kb": round(t["bytes"] / 1024, 1),
                  "total_s": round(t["total"] / 1000, 1)}
                 for r, t in _TIEMPOS.items() if t["n"]]
    filas.sort(key=lambda x: -x["total_s"])
    return {"rutas": filas,
            "fondo": dict(_ESTADO_FONDO),
            "memoria": {"respuestas": len(_cache),
                        "megas": round(_cache_bytes / 1048576, 1),
                        "armadas": len(_VIVO),
                        "rearmando": sum(1 for v in _VIVO.values()
                                         if v["armando"])},
            "arriba_hace_s": round(time.time() - _ARRANCO),
            "como": ("promedio_ms es lo que tarda el servidor en armar la "
                     "respuesta. Si es chico y la página igual tarda, el "
                     "tiempo se va en la red o en el navegador.")}


_ARRANCO = time.time()
# Qué está haciendo el recolector de fondo ahora mismo. Sirve para saber si
# la lentitud es porque está bajando medio calendario mientras alguien mira.
_ESTADO_FONDO = {"vuelta": 0, "haciendo": "sin arrancar", "desde": None,
                 "historia_al_dia": False, "recorriendo": False}


# ── Contestar sin hacer esperar ──────────────────────────────────────────
#
# La portada tardaba 9,4 segundos de promedio. No porque hubiera mucha
# gente —eran 175 visitas en 41 horas— sino porque cada visita armaba todo
# de nuevo: once ligas, una tras otra, cada una con su viaje a AFA o a
# 365scores.
#
# La caché normal no alcanzaba, porque cuando se vence alguien tiene que
# pagar el rearmado completo, y ese alguien es una persona esperando.
#
# Acá se separa una cosa de la otra: se contesta SIEMPRE con lo último que
# se armó —al instante, sin mirar la hora— y si eso ya está viejo, se manda
# a rearmar en otro hilo para el que venga después. El único que espera de
# verdad es el primero de todos, cuando todavía no hay nada guardado.
#
# El precio es que se puede estar mostrando algo de unos segundos atrás.
# Para una portada que además se refresca sola cada veinte segundos, es un
# precio que no se nota. Para una tabla de posiciones tampoco. No se usaría
# para algo donde el dato viejo confunde.
_VIVO = {}
_vivo_lock = threading.Lock()


def al_toque(clave, armar, frescura=15):
    """
    Lo último armado, ya. Y si está viejo, se renueva por atrás.

    `frescura` puede ser un número de segundos o una función que mire lo
    último armado y decida. Eso último sirve para no rearmar cada diez
    segundos un día sin partidos en curso, donde no cambia nada.
    """
    with _vivo_lock:
        e = _VIVO.get(clave)
        ahora = time.time()
        if e and e["valor"] is not None:
            cuanto = frescura(e["valor"]) if callable(frescura) else frescura
            viejo = ahora - e["cuando"] > cuanto
            if viejo and not e["armando"]:
                e["armando"] = True
                threading.Thread(target=_rearmar, args=(clave, armar),
                                 daemon=True).start()
            return e["valor"]
        _VIVO[clave] = {"valor": None, "cuando": 0, "armando": True}

    # El primero arma sincrónico: no hay nada que mostrarle todavía.
    try:
        valor = armar()
    except Exception:
        with _vivo_lock:
            _VIVO.pop(clave, None)
        raise
    with _vivo_lock:
        _VIVO[clave] = {"valor": valor, "cuando": time.time(), "armando": False}
        _limpiar_vivo()
    return valor


# ── Servir la página sin la receta ───────────────────────────────────────
#
# index.html tiene casi cinco mil líneas de comentarios que explican cada
# decisión y cada error que costó encontrar. Eso es lo valioso del archivo,
# más que el código, y viajaba entero a cualquiera que abriera la página.
#
# Se quedan donde están —en el archivo, que es el que se edita y el que
# guarda git— y no se mandan. Nadie pierde nada: lo que se aligera es la
# copia que sale por el cable.
#
# Ojo con la parte difícil: sacar comentarios con una búsqueda simple rompe
# el javascript. Este archivo está lleno de "https://" adentro de textos,
# de expresiones regulares con barras, y de plantillas anidadas unas dentro
# de otras. Hay que leerlo distinguiendo código de texto, que es lo que
# hace `sin_comentarios_js`. Si algo sale mal, se manda el original.

# Después de estas palabras, una barra abre una expresión regular y no es
# una división. Sin esto, `return /x/.test(s)` se leía como una división.
_ANTES_DE_REGEX = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
}


def sin_comentarios_js(js):
    """
    El mismo javascript, sin los comentarios. Nada más se toca.

    Se recorre carácter por carácter llevando en una pila dónde estamos:
    en código, adentro de una plantilla, o adentro de un ${...} de una
    plantilla —que es código otra vez, y puede tener otra plantilla
    adentro—. Los textos y las expresiones regulares se copian tal cual,
    con lo que tengan adentro.

    Los saltos de línea de los comentarios se conservan, para que si alguna
    vez hay un error en el navegador el número de línea siga sirviendo.
    """
    salida = []
    i, n = 0, len(js)
    # cada nivel es ("codigo", llaves_abiertas) o ("plantilla",)
    pila = [["codigo", 0]]
    ultimo = ""            # último carácter significativo que emitimos
    palabra = ""           # y la última palabra, para el caso del return

    def emitir(t):
        salida.append(t)

    while i < n:
        if pila[-1][0] == "plantilla":
            # adentro del texto de una plantilla: se copia todo tal cual
            # hasta el cierre o hasta un ${, que vuelve a ser código
            j = i
            while j < n:
                c = js[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "`":
                    emitir(js[i:j + 1]); i = j + 1; pila.pop()
                    ultimo, palabra = "`", ""
                    break
                if c == "$" and js[j + 1:j + 2] == "{":
                    emitir(js[i:j + 2]); i = j + 2
                    pila.append(["codigo", 0])
                    ultimo, palabra = "{", ""
                    break
                j += 1
            else:
                emitir(js[i:]); i = n
            continue

        c = js[i]
        sig = js[i + 1] if i + 1 < n else ""

        # ── comentario de una línea ──
        if c == "/" and sig == "/":
            j = js.find("\n", i)
            i = n if j < 0 else j        # el salto se deja
            continue

        # ── comentario de varias líneas ──
        if c == "/" and sig == "*":
            j = js.find("*/", i + 2)
            fin = n if j < 0 else j + 2
            # Los que empiezan con /*! se quedan. Es la convención de toda
            # la vida para el aviso de derecho de autor: es justamente el
            # comentario que no tiene sentido borrar de la copia publicada.
            if js[i:i + 3] == "/*!":
                emitir(js[i:fin])
            else:
                emitir("\n" * js.count("\n", i, fin))
            i = fin
            continue

        # ── un texto entre comillas ──
        if c in "'\"":
            j = i + 1
            while j < n:
                if js[j] == "\\":
                    j += 2
                    continue
                if js[j] == c:
                    j += 1
                    break
                j += 1
            emitir(js[i:j]); i = j
            ultimo, palabra = c, ""
            continue

        # ── una plantilla ──
        if c == "`":
            emitir(c); i += 1
            pila.append(["plantilla"])
            continue

        # ── una expresión regular, o una división ──
        if c == "/":
            division = (ultimo in ")]}" or ultimo.isalnum()
                        or ultimo in "_$") and palabra not in _ANTES_DE_REGEX
            if not division:
                j, corchete = i + 1, False
                while j < n:
                    ch = js[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        corchete = True
                    elif ch == "]":
                        corchete = False
                    elif ch == "/" and not corchete:
                        j += 1
                        break
                    elif ch == "\n":
                        break        # no era una regex después de todo
                    j += 1
                emitir(js[i:j]); i = j
                ultimo, palabra = "/", ""
                continue

        # ── código común ──
        if c == "{":
            pila[-1][1] += 1
        elif c == "}":
            if pila[-1][1] == 0 and len(pila) > 1:
                # esta llave cierra el ${...} y vuelve a la plantilla
                emitir(c); i += 1; pila.pop()
                ultimo, palabra = "}", ""
                continue
            pila[-1][1] = max(0, pila[-1][1] - 1)

        emitir(c); i += 1
        if not c.isspace():
            ultimo = c
            palabra = (palabra + c) if (c.isalnum() or c in "_$") else ""
    return "".join(salida)


def _sin_comentarios_css(css):
    """Los estilos no tienen comentarios de línea: sólo /* … */."""
    fuera, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c in "'\"":
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == "\\" else 1
            fuera.append(css[i:j + 1]); i = j + 1
            continue
        if c == "/" and css[i + 1:i + 2] == "*":
            j = css.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        fuera.append(c); i += 1
    return "".join(fuera)


def aligerar(html):
    """
    La página lista para mandar: sin comentarios de HTML, de estilos ni de
    javascript. Si algo no cierra como esperábamos, se devuelve el original
    tal cual: preferimos mandar de más antes que mandar algo roto.
    """
    try:
        def js_de(m):
            return m.group(1) + sin_comentarios_js(m.group(2)) + m.group(3)

        def css_de(m):
            return m.group(1) + _sin_comentarios_css(m.group(2)) + m.group(3)

        salida = re.sub(r"(<script(?![^>]*\bsrc=)[^>]*>)(.*?)(</script>)",
                        js_de, html, flags=re.S)
        salida = re.sub(r"(<style[^>]*>)(.*?)(</style>)", css_de,
                        salida, flags=re.S)
        salida = re.sub(r"<!--(?!\[if).*?-->", "", salida, flags=re.S)

        # Red de seguridad. No prueba que el javascript sea válido —eso lo
        # hace la regresión, que lo pasa por el intérprete de verdad— pero
        # sí que no se haya comido medio archivo por un texto mal cerrado.
        anclas = ("App.init();", "const Rutas=", "function aplicar(",
                  "window.__ADELANTO__", "<div class=\"ov\" id=\"ov\"")
        if any(a not in salida for a in anclas):
            return html
        if salida.count("<script") != html.count("<script"):
            return html
        if len(salida) < len(html) * 0.45:
            return html
        return salida
    except Exception:
        return html


# ── Anotar quién entra ───────────────────────────────────────────────────
#
# El servidor sabe casi todo por los encabezados del pedido: de dónde vino,
# con qué navegador, en qué idioma. Lo único que no puede saber es el tamaño
# de la pantalla y cuánto se queda la persona: eso sólo lo sabe el navegador
# y lo avisa por /api/visita.
#
# Se anota la página, no las llamadas de la página: si se contara cada
# /api/ que hace el javascript, una visita parecerían veinte.
def liga_de_partido(gid):
    """
    De qué torneo es un partido, buscando por su id en lo que guardamos.

    No hay una tabla que lo diga: los partidos se guardan por torneo, así
    que se pregunta torneo por torneo. Son dieciséis lecturas de la base,
    que al lado de servir una página no es nada.

    Lo usa la página del partido para saber qué tabla de posiciones
    mostrar al costado, y el registro de visitas para saber a qué venía
    alguien que cayó ahí desde un buscador.
    """
    if not gid:
        return ""
    for lid in LIGAS:
        if almacen.leer("goles:%s:%s" % (lid, gid))[0] is not None:
            return lid
        if almacen.leer("tv:%s:%s" % (lid, gid))[0] is not None:
            return lid
    return ""


def que_venia_a_ver(ruta):
    """
    Qué torneo le interesa a quien aterrizó en esta página.

    Es el dato que puede ordenar la portada, así que vale la pena
    resolverlo bien y no sólo para las direcciones fáciles:

      /laliga                          → laliga, obvio
      /partido/barcelona-vs-madrid-99  → laliga, mirando de qué torneo es
                                         ese partido en la base
      /belgrano                        → lpf, porque es un club de Primera
      /                                → nada: el que entra por la puerta
                                         grande no dijo qué quiere

    El del medio es el que más importa: Google manda a la gente a partidos
    concretos, no a la portada. Cuesta unas pocas lecturas de la base, que
    al lado de servir una página no es nada.
    """
    partes = [p for p in (ruta or "").strip("/").split("/") if p]
    if not partes:
        return ""
    if partes[0] in RUTAS_LIGA:
        return RUTAS_LIGA[partes[0]]

    if partes[0] == "partido" and len(partes) == 2:
        m = re.search(r"(\d+)$", partes[1])
        return liga_de_partido(m.group(1)) if m else ""

    # Buscó un jugador por su nombre y cayó en su ficha. Es de los casos más
    # comunes que manda un buscador, y hasta acá lo estábamos tirando: el
    # torneo sale de dónde estuvo jugando, que es lo mismo que ya se usa
    # para armarle la ficha.
    if partes[0] == "jugador" and len(partes) == 2:
        nombre = re.sub(r"-\d+$", "", partes[1]).replace("-", " ")
        lid = liga_del_jugador(nombre)
        # `liga_del_jugador` cae en "lpf" cuando no sabe nada del jugador, y
        # eso acá sería inventar una intención que nadie expresó.
        return lid if almacen.leer("pj:%s:%s" % (lid, norm(nombre)))[0] else ""

    if len(partes) == 1 and partes[0] in RUTAS_CLUB:
        # los treinta de Primera son los que tienen ficha con colores
        return "lpf" if RUTAS_CLUB[partes[0]] in COLORES else ""
    return ""


def anotar_visita(handler, q):
    """
    Anota una visita juntando lo que sabe el servidor con lo que sabe el
    navegador.

    La anotación la dispara la página y no el pedido del HTML, por una
    razón concreta: el HTML se sirve desde una copia ya armada, la misma
    para todos, así que no hay dónde meterle un identificador propio a
    cada visitante. Además el navegador tiene tres datos que el servidor
    no puede ver —de dónde venía (`document.referrer`), el tamaño de la
    pantalla, y cuánto se queda— así que es el que tiene la foto completa.

    Lo que se paga: el que navega con javascript apagado o con un
    bloqueador agresivo no se cuenta. Le pasa igual a Google Analytics.
    Para tener la referencia, el total de páginas servidas está en
    /api/tiempos, en el renglón "(la página)": comparando los dos números
    se ve cuánto se está perdiendo.
    """
    ua = handler.headers.get("User-Agent") or ""
    if visitas.es_robot(ua):
        return {"ok": True, "robot": True}
    # Detrás de un hosting la IP del visitante viene en un encabezado: la
    # conexión de verdad es la del balanceador de Render.
    ip = ((handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
          or handler.client_address[0])
    ref = (q.get("ref") or [""])[0][:300]
    ruta = (q.get("r") or ["/"])[0][:120]
    zona = (q.get("tz") or [""])[0][:60]
    fuente, dominio = visitas.de_donde(ref, handler.headers.get("Host") or "")
    quiere = que_venia_a_ver(ruta)
    # La zona horaria manda sobre el idioma: el idioma lo cambia la gente,
    # la zona la pone el sistema. Si no vino zona —navegador viejo— se cae
    # al idioma, que es mejor que nada.
    pais = visitas.pais_de_zona(zona) or visitas.region(
        handler.headers.get("Accept-Language"))
    datos = {
        "huella": visitas.huella(ip, ua),
        "ruta": ruta,
        "fuente": fuente,
        "dominio": dominio,
        "busco": visitas.que_buscaba(ref),
        "dispositivo": visitas.dispositivo(ua),
        "sistema": visitas.sistema_de(ua),
        "navegador": visitas.navegador_de(ua),
        "region": pais,
        "pantalla": (q.get("p") or [""])[0][:12],
        "intencion": quiere,
    }
    vid = visitas.anotar(datos)
    # Lo que se le contesta a la página. Hoy no lo usa: es la semilla de la
    # portada dinámica, y encenderla es una decisión que no me corresponde
    # tomar a mí. Mientras tanto se puede ver en el administrador qué
    # habría sugerido para cada visita.
    return {"ok": True, "v": vid, "quiere": quiere,
            "region": pais, "continente": visitas.continente_de_zona(zona),
            "fuente": fuente}


def clave_de_ruta(path, q):
    """
    Con qué nombre se guarda la respuesta de una ruta.

    Lleva los parámetros adentro, y ordenados. Es lo que hace que la fecha
    5 y la fecha 6 sean dos respuestas distintas en vez de pisarse, y que
    ?id=lib&round=3 y ?round=3&id=lib sean la misma.
    """
    return "%s|%s" % (path, "&".join(
        "%s=%s" % (k, ",".join(v)) for k, v in sorted(q.items())))


def _rearmar(clave, armar):
    try:
        valor = armar()
    except Exception:
        valor = None
    with _vivo_lock:
        e = _VIVO.get(clave)
        if e is None:
            return
        e["armando"] = False
        if valor is not None:
            # si falló, se deja lo viejo: es mejor que una pantalla vacía,
            # y en la próxima vuelta se intenta de nuevo
            e["valor"], e["cuando"] = valor, time.time()


def _limpiar_vivo(tope=120):
    """
    Cada fecha, cada torneo y cada club guardan su respuesta armada. Con
    dieciséis torneos y sus fechas se juntan rápido, así que se pone tope y
    se tiran las más viejas. Se puede mirar cuántas hay en /api/tiempos.
    """
    if len(_VIVO) <= tope:
        return
    for k, _ in sorted(_VIVO.items(), key=lambda kv: kv[1]["cuando"])[:len(_VIVO) - tope]:
        if not _VIVO[k]["armando"]:
            _VIVO.pop(k, None)


def escapar(t):
    """
    Texto listo para meter adentro de un atributo HTML.

    Lo que entra acá sale de la dirección que pidió el visitante, así que
    hay que tratarlo como lo que es: algo que escribió un desconocido. Sin
    esto, alguien podría armar una dirección que cierre el atributo y meta
    su propio código en la página de cualquiera que abra el link.
    """
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _titulo_de_ruta(path):
    """
    Qué dice la solapa del navegador —y Google— en cada dirección.

    Devuelve (título, descripción) o None si la dirección no es nuestra.
    Es a propósito que sea texto fijo y no consulte nada: esto corre en
    cada visita y antes que cualquier otra cosa, así que no puede depender
    de que 365scores conteste.
    """
    partes = [p for p in path.strip("/").split("/") if p]
    if not partes:
        return ("%s — Fútbol en vivo" % TITULO_BASE, LEMA)

    def lindo(s):
        """De 'olimpia-vs-vasco-da-gama-4798160' a 'Olimpia vs Vasco Da Gama'."""
        s = re.sub(r"-\d+$", "", s).replace("-", " ").strip().title()
        return re.sub(r"\bVs\b", "vs", s)

    # el número del final es el id del partido: sin eso no hay nada que
    # abrir, así que tampoco es una dirección nuestra
    if partes[0] == "partido" and len(partes) == 2 and partes[1][-1:].isdigit():
        return ("%s — %s" % (lindo(partes[1]), TITULO_BASE),
                "Resultado, goles, formaciones y estadísticas del partido.")

    if partes[0] == "jugador" and len(partes) == 2:
        return ("%s — %s" % (lindo(partes[1]), TITULO_BASE),
                "Ficha del jugador: goles, partidos y por dónde pasó.")

    if partes[0] in RUTAS_LIGA:
        cfg = LIGAS.get(RUTAS_LIGA[partes[0]]) or {}
        nombre = cfg.get("nombre") or partes[0]
        torneo = cfg.get("torneo") or ""
        if len(partes) == 2 and partes[1].startswith("fecha-"):
            fecha = partes[1][6:]
            return ("%s fecha %s — %s" % (nombre, fecha, TITULO_BASE),
                    "Resultados y posiciones de la fecha %s de %s." % (fecha, nombre))
        if len(partes) == 3 and partes[1] == "llave":
            return ("%s — %s" % (nombre, TITULO_BASE),
                    "La llave, partido por partido, de %s." % nombre)
        if len(partes) == 1:
            return ("%s %s — %s" % (nombre, torneo, TITULO_BASE),
                    "Resultados en vivo, tabla de posiciones y goleadores "
                    "de %s." % nombre)
        return None

    if len(partes) == 1 and partes[0] in RUTAS_CLUB:
        club = RUTAS_CLUB[partes[0]]
        return ("%s — %s" % (club, TITULO_BASE),
                "%s: próximo partido, plantel, historial y cómo juega." % club)

    return None


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

    # Cuando alguien cierra la pestaña o cambia de pantalla, la conexión se
    # corta a mitad de la respuesta. Eso no es un error nuestro: es lo normal
    # en un navegador. Pero Python lo trata como excepción, y como el manejo
    # de errores intenta contestar por la misma conexión ya rota, se
    # encadenaban tres trazas de veinte líneas por cada persona que se iba.
    # El log terminaba siendo eso y nada más.
    SE_FUE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except self.SE_FUE:
            self.close_connection = True

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        body, enc = self._comprimir(body)
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            if enc:
                self.send_header("Content-Encoding", enc)
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._ultimo_tamano = len(body)
            self.wfile.write(body)
        except self.SE_FUE:
            self.close_connection = True

    def _texto(self, cuerpo, ctype, minutos=60):
        """
        Una respuesta de texto armada acá, sin archivo detrás.

        Con `minutos=0` se pide que no se guarde en ningún lado. No es lo
        mismo que guardarla cero segundos: la página de administración no
        tiene que quedar en la caché de un intermediario ni en el disco del
        navegador, aunque caduque enseguida.
        """
        body, enc = self._comprimir(cuerpo.encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control",
                         "private, no-store" if not minutos
                         else "public, max-age=%d" % (minutos * 60))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._ultimo_tamano = len(body)
        self.wfile.write(body)

    def _pagina(self, path):
        """
        index.html con el título y la descripción de esta dirección.

        Es lo único que el servidor cambia: adentro la página es la misma
        para todas las direcciones. Pero este pedacito importa más de lo
        que parece, porque es lo que ve el que no ejecuta el javascript —
        Google, y la vista previa de WhatsApp cuando alguien pega el link—.

        Cada respuesta se guarda ya armada y comprimida. Sin eso, cada
        visita leía 250 KB del disco, corría una expresión regular sobre
        todo el archivo y lo volvía a comprimir —y el resultado depende
        sólo de la dirección, así que era todo trabajo repetido—. Se
        rearma cuando index.html cambia de fecha, así que publicar una
        versión nueva se sigue viendo al recargar.
        """
        gz = self._acepta_gzip()
        try:
            archivo = os.path.join(HERE, "index.html")
            marca = os.path.getmtime(archivo)
            hecha = _PAGINAS.get((path, gz))
            if hecha and hecha[0] == marca:
                return self._enviar_pagina(hecha[1], hecha[2], marca)
            with open(archivo, encoding="utf-8") as f:
                html = f.read()
        except OSError:
            self.send_error(404)
            return
        cual = _titulo_de_ruta(path)
        if cual:
            titulo, desc = cual
            host = self.headers.get("Host") or "hayvar.com.ar"
            url = "https://%s%s" % (host, path)
            cabeza = "\n".join([
                "<title>%s</title>" % escapar(titulo),
                '<meta name="description" content="%s">' % escapar(desc),
                '<meta property="og:title" content="%s">' % escapar(titulo),
                '<meta property="og:description" content="%s">' % escapar(desc),
                '<meta property="og:type" content="website">',
                '<meta property="og:site_name" content="HAYVAR">',
                '<meta property="og:url" content="%s">' % escapar(url),
                '<link rel="canonical" href="%s">' % escapar(url),
            ])
            html = re.sub(r"<!--CABEZA-->.*?<!--/CABEZA-->",
                          lambda _: "<!--CABEZA-->\n%s\n<!--/CABEZA-->" % cabeza,
                          html, count=1, flags=re.S)
        # Los comentarios se quedan en el archivo y no viajan. Se hace acá,
        # una vez por dirección, y el resultado queda guardado: leer 274 KB
        # carácter por carácter en cada visita sería cambiar un problema
        # por otro.
        html = aligerar(html)
        body, enc = self._comprimir(html.encode("utf-8"))
        # Son 48 direcciones y dos variantes (con y sin comprimir): no hay
        # nada que vaciar, pero por si algún día aparece una dirección por
        # partido se le pone tope y se empieza de nuevo.
        if len(_PAGINAS) > 300:
            _PAGINAS.clear()
        _PAGINAS[(path, gz)] = (marca, body, enc)
        return self._enviar_pagina(body, enc, marca)

    def _enviar_pagina(self, body, enc, marca=0):
        """
        Manda la página, o dice "no cambió" si el visitante ya la tiene.

        Esto es lo que más se nota de todo lo que hay acá. La página pesa
        85 KB comprimida, y hasta ahora se mandaba entera en cada visita:
        se pedía revalidar pero no se le daba al navegador con qué
        compararla, así que la revalidación siempre terminaba en "tomá,
        todo de nuevo". Con la etiqueta, el navegador pregunta "¿sigue
        siendo ésta?" y la respuesta son doscientos bytes. Ochenta y cinco
        kilos menos por visita, en la conexión de un celular.

        Sigue revalidando en cada visita a propósito: si subís una versión
        nueva, la etiqueta cambia y se ve al recargar. No se cambia por un
        caché largo porque eso deja gente mirando una versión vieja
        durante horas, que es peor que un viaje de ida y vuelta corto.
        """
        etiqueta = '"%s-%x"' % (int(marca), len(body))
        if (self.headers.get("If-None-Match") or "").strip() == etiqueta:
            self.send_response(304)
            self.send_header("ETag", etiqueta)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self._ultimo_tamano = 0
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", etiqueta)
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._ultimo_tamano = len(body)
        self.wfile.write(body)

    def do_GET(self):
        arranque = time.time()
        try:
            return self._responder()
        finally:
            # Se anota siempre, aunque la respuesta haya fallado: un error
            # que tarda cuatro segundos es tan interesante como un acierto
            # que tarda cuatro segundos.
            ruta = urlparse(self.path).path.rstrip("/") or "/"
            if ruta.startswith("/img/"):
                ruta = "/img/…"            # son cientos, se cuentan juntos
            elif ruta.startswith("/partido/"):
                ruta = "/partido/…"
            elif ruta.startswith("/jugador/"):
                ruta = "/jugador/…"
            elif not ruta.startswith("/api/") and ruta != "/":
                ruta = "(la página)"
            anotar_tiempo(ruta, (time.time() - arranque) * 1000,
                          getattr(self, "_ultimo_tamano", 0))

    def _responder(self):
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
            self._ultimo_tamano = len(datos)
            self.wfile.write(datos)
            return

        # Las puertas de servicio, antes que nada. Va acá arriba a propósito:
        # si el control estuviera más abajo, alcanzaría con que alguien
        # agregue una ruta nueva en el lugar equivocado para saltearlo.
        if path in PRIVADAS and not con_llave(q, self.headers):
            return self._json(
                {"error": "Esta dirección no es pública.",
                 "porque": ("Borra datos, gasta cupo de las fuentes o cuenta "
                            "cómo está hecho el servidor por dentro."),
                 "comoEntrar": ("Agregá ?llave=… o mandá el encabezado "
                                "X-Llave. La llave se pone en la variable "
                                "HAYVAR_LLAVE del hosting."),
                 "configurada": bool(LLAVE)}, 403)

        # La página de adentro. Va aparte de las direcciones de la página
        # pública: no lleva título ni descripción para compartir —no se
        # comparte— y no se le sacan los comentarios, que ahí adentro son
        # para vos y no viajan a ningún desconocido.
        if path == "/admin":
            try:
                with open(os.path.join(HERE, "admin.html"), encoding="utf-8") as f:
                    return self._texto(f.read(), "text/html; charset=utf-8",
                                       minutos=0)
            except OSError:
                return self._json({"error": "falta admin.html"}, 404)

        # El aviso de la página: una visita nueva, o un latido diciendo que
        # la persona sigue leyendo. Va acá y no en la tabla de rutas porque
        # necesita los encabezados del pedido —de dónde viene, con qué
        # navegador, en qué idioma—, que ahí no llegan.
        #
        # Nunca puede romper una visita: si algo falla, se contesta que sí
        # y listo. Que no se anote alguien es un renglón menos en un
        # informe; que se rompa la página es otra cosa.
        if path == "/api/visita":
            try:
                v = (q.get("v") or [""])[0][:40]
                if v:
                    visitas.latir(v, (q.get("seg") or ["0"])[0])
                    return self._json({"ok": True})
                return self._json(anotar_visita(self, q))
            except Exception:
                return self._json({"ok": False})

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
                # Las que están en la tabla se contestan con lo último
                # armado y se renuevan por atrás. La clave lleva los
                # parámetros: la fecha 5 y la 6 son dos respuestas.
                seg = AL_TOQUE.get(path)
                if seg is None:
                    return self._json(fn(q))
                return self._json(al_toque(clave_de_ruta(path, q),
                                           lambda: fn(q), frescura=seg))
            except (HTTPError, URLError) as e:
                return self._json({"error": "no se pudo llegar a 365scores: %s" % e}, 502)
            except Exception as e:
                return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 500)

        # El mapa del sitio: la lista de direcciones para que Google las
        # encuentre sin tener que adivinar. Van los torneos y los clubes,
        # que son pocos y no cambian. Los partidos y los jugadores no: son
        # miles y se renuevan cada fecha, y Google llega igual siguiendo
        # los enlaces desde acá, que ahora son enlaces de verdad.
        if path in ("/sitemap.xml", "/robots.txt"):
            host = self.headers.get("Host") or "hayvar.com.ar"
            raiz = "https://%s" % host
            if path == "/robots.txt":
                # Las /api/ no son páginas: que las recorra un buscador no
                # le sirve a nadie y a nosotros nos cuesta. Ojo con lo que
                # esto es y lo que no: es un pedido, no una tranca. Lo que
                # de verdad no tiene que estar abierto está en PRIVADAS.
                cuerpo = ("User-agent: *\n"
                          "Allow: /\n"
                          "Disallow: /api/\n"
                          "Sitemap: %s/sitemap.xml\n" % raiz)
                return self._texto(cuerpo, "text/plain; charset=utf-8")
            rutas = ["/"] + ["/" + s for s in RUTAS_LIGA] \
                          + ["/" + s for s in sorted(RUTAS_CLUB)]
            cuerpo = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                      + "".join("  <url><loc>%s%s</loc></url>\n"
                                % (raiz, escapar(r)) for r in rutas)
                      + "</urlset>\n")
            return self._texto(cuerpo, "application/xml; charset=utf-8")

        # La página, comprimida. Todas las direcciones nuestras —un club, un
        # torneo, una fecha, un partido, un jugador— devuelven el mismo
        # index: la página es una sola y adentro decide qué mostrar mirando
        # la dirección. Lo único que cambia es el título, que lo pone
        # `_pagina`. Así el enlace se puede compartir, se puede abrir en una
        # pestaña nueva y Google lo puede indexar.
        if path in ("/", "/index.html") or _titulo_de_ruta(path):
            return self._pagina("/" if path == "/index.html" else path)
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
    ]

    # El resto se arma solo con las ligas que hay. Antes esta lista estaba
    # escrita a mano y quedó vieja: la Premier, la Serie A, la Bundesliga,
    # la Champions y el Federal A no se precalentaban, así que el primero
    # que entraba a cualquiera de ellas pagaba toda la espera.
    #
    # El orden importa: primero las de la portada, que es lo que se ve al
    # abrir la página, y después las demás.
    orden = ([l for l in HOME_LIGAS if l in LIGAS and l != "lpf"]
             + [l for l in LIGAS if l not in HOME_LIGAS and l != "lpf"])
    for lid in orden:
        tareas.append((LIGAS[lid]["nombre"],
                       lambda x=lid: api_liga_games({"id": [x]})))

    arranque_total = time.time()
    listas, fallidas = 0, 0
    for nombre, tarea in tareas:
        arranque = time.time()
        try:
            tarea()
            listas += 1
            print("  · %-22s listo en %.1fs" % (nombre, time.time() - arranque), flush=True)
        except Exception as e:
            fallidas += 1
            print("  · %-22s falló (%s), se reintenta al pedirlo"
                  % (nombre, type(e).__name__), flush=True)
    print("  Caché precalentado: %d de %d en %.0fs%s\n"
          % (listas, len(tareas), time.time() - arranque_total,
             "" if not fallidas else " (%d quedaron para después)" % fallidas),
          flush=True)


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
    #
    # Y no alcanza con que haya algo guardado: si lo leímos mientras se
    # jugaba, lo que hay es la mitad de los goles. Los partidos que quedaron
    # así también entran acá y se arreglan solos en las próximas vueltas.
    faltan = []
    for g in juegos:
        if g.get("status") != "FIN" or not g.get("liveId"):
            continue
        _, _, listo = detalle_al_dia(lid, g)
        if not listo:
            faltan.append(g)

    hechos = 0
    for g in faltan[:limite]:
        try:
            detalle_liviano(g["liveId"], en_juego=False, liga=lid)
            hechos += 1
        except Exception:
            continue
    return hechos


def juntar_stats(lid, limite=15):
    """Trae las estadísticas de los partidos que todavía no las tienen."""
    try:
        juegos = (all_games(ttl=600) if lid == "lpf"
                  else api_liga_games({"id": [lid]}).get("games", []))
    except Exception:
        return 0
    faltan = []
    for g in juegos:
        if g.get("status") != "FIN" or not g.get("liveId"):
            continue
        guardado, _ = almacen.leer("stats:%s:%s" % (lid, g["liveId"]))
        # Los guardados antes de que empezáramos a anotar los goles no
        # sirven para la efectividad ni la solidez: se vuelven a pedir.
        sin_goles = bool(guardado) and (guardado.get("h") or {}).get("gf") is None
        # Y los de antes de que guardáramos lo de cada jugador tampoco: sin
        # eso el gráfico de las fichas no se llenaba nunca, porque el
        # partido ya tenía estadísticas de equipo y no se volvía a mirar.
        sin_jugadores, _ = almacen.leer("jug:%s:%s" % (lid, g["liveId"]))
        if guardado is None or sin_goles or sin_jugadores is None:
            faltan.append(g)
    hechos = 0
    for g in faltan[:limite]:
        try:
            api_match({"id": [str(g["liveId"])], "liga": [lid]})
            hechos += 1
        except Exception:
            continue
    return hechos


# Lo último que dijo cada recorrido, para no repetir el mismo renglón.
_ULTIMO_CAMINO = {}


def rescatar_todo():
    """
    Va llenando la base en segundo plano, sin que nadie tenga que pedirlo.

    Recorre el calendario de cada torneo para los dos lados. Hacia atrás
    recupera lo que 365scores ya sacó de la ventana —la fase de grupos de la
    Libertadores, las rondas viejas de la Copa Argentina—; hacia adelante
    trae lo que todavía no entró, que es lo que le pasa a la Premier, la
    Serie A y la Bundesliga cuando arrancan: la ventana muestra dos fechas y
    el torneo tiene treinta y ocho.

    Después busca los goleadores de esos partidos. Cada vuelta guarda dónde
    quedó, así que si el servidor se reinicia sigue desde ahí.
    """
    time.sleep(20)          # que la página arranque tranquila primero
    # Primero lo primero: si hay que volver a recorrer todo, se reabre acá.
    try:
        reparar_recorridos()
    except Exception as e:
        print("  · no se pudo reparar el recorrido (%s)" % type(e).__name__,
              flush=True)
    # Las páginas viejas ya no se guardan: las que quedaron de antes ocupan
    # lugar al pedo. Se limpian una vez y listo.
    try:
        almacen.borrar_prefijo("pag:")
    except Exception:
        pass

    # Doce vueltas seguidas y después, si algo quedó pendiente, sigue de a
    # ratos. Antes cortaba en la doce y no volvía hasta el próximo arranque:
    # si la fuente se caía un par de veces —o si aparecía una fase nueva a
    # mitad de temporada— el hueco se quedaba ahí hasta el siguiente deploy.
    #
    # Y tampoco termina cuando se pone al día: se queda mirando cada cuarto
    # de hora. Antes se daba por cumplido y se iba, así que los partidos que
    # se jugaban después no los levantaba nadie hasta el próximo deploy —o
    # hasta que alguien los abriera a mano, que es peor: significa que la
    # base se llena sólo si hay visitas—. Una fecha entera son quince
    # partidos y entran en una sola pasada.
    #
    # Ojo con una cosa que ya me mordió: acá se juntan dos trabajos muy
    # distintos. Recorrer los calendarios es carísimo —cada página del
    # fixture de una copa son varios megas de JSON— y buscar los autores de
    # los goles es barato. Estaban atados al mismo semáforo: si quedaban
    # goles por buscar, el programa entendía que "falta historia" y se
    # ponía a recorrer todos los calendarios cada sesenta segundos. En una
    # máquina de medio procesador eso es todo el procesador, y la página se
    # arrastra para el que está mirándola. Ahora cada uno tiene su ritmo.
    limpieza_diaria()
    VUELTAS_SEGUIDAS = 12
    vuelta, historia_al_dia = 0, False
    while True:
        vuelta += 1
        pendientes, goles_pendientes = 0, 0
        # Mientras falte historia se recorre en cada vuelta; una vez
        # completa, basta con mirarlo de vez en cuando —lo que se juega
        # nuevo lo levantan igual los dos recolectores de abajo, que piden
        # el fixture ya resumido—.
        recorrer = (not historia_al_dia) or vuelta % 8 == 0
        _ESTADO_FONDO.update(vuelta=vuelta, recorriendo=recorrer,
                             historia_al_dia=historia_al_dia,
                             haciendo="recorriendo calendarios" if recorrer
                                      else "buscando goles",
                             desde=time.strftime("%H:%M:%S"))
        for lid, cfg in (LIGAS.items() if recorrer else ()):
          # las previas de la Champions son otra competencia: se recorren igual
          for comp in comps_de(cfg):
            for direccion, como in ((-1, "atrás"), (1, "adelante")):
                try:
                    # El paginado hacia atrás avanza de a siete partidos
                    # por página, no de a una fecha entera: con veinte
                    # páginas por vuelta una copa entera no llegaba nunca.
                    r = caminar_fixture(comp, direccion, paginas=40)
                    if not r.get("listo"):
                        pendientes += 1
                    # Se escribe la primera vuelta —para poder ver que
                    # corrió aunque no traiga nada— y después sólo cuando
                    # algo cambió. Si no, el log son cien renglones por
                    # minuto diciendo siempre lo mismo y no se lee nada.
                    firma = (r.get("total"), r.get("listo"))
                    if vuelta == 1 or firma != _ULTIMO_CAMINO.get((comp, direccion)):
                        print("  · %-18s %-8s %2d pág · +%-3d · total %-4d %-6s %s"
                              % (cfg["nombre"], como, r.get("paginas", 0),
                                 r.get("nuevos", 0), r.get("total", 0),
                                 "listo" if r.get("listo") else "sigue",
                                 r.get("motivo") or r.get("estado") or ""),
                              flush=True)
                    _ULTIMO_CAMINO[(comp, direccion)] = firma
                except Exception as e:
                    print("  · %-18s %-8s falló (%s)"
                          % (cfg["nombre"], como, type(e).__name__), flush=True)
                time.sleep(2)
            # cuántas fechas debería tener: si faltan, se avisa en el log
            # Cuántas fechas hay de las que debería haber. Se cuentan sobre
            # el calendario que la página sirve, no sobre el crudo de
            # 365scores: LaLiga arma el suyo con laliga.com y ahí el crudo
            # siempre va a estar corto, así que avisaba de un problema que
            # no existía.
            try:
                tope = fechas_del_torneo(cfg["sc"])
                if tope and not cfg.get("copa"):
                    servido = api_liga_games({"id": [lid]})
                    vistas = servido.get("rounds") or []
                    if vistas and len(vistas) < tope:
                        firma = ("fechas", len(vistas), tope)
                        if _ULTIMO_CAMINO.get(("fechas", lid)) != firma:
                            print("  · %-18s van %d de %d fechas"
                                  % (cfg["nombre"], len(vistas), tope), flush=True)
                        _ULTIMO_CAMINO[("fechas", lid)] = firma
            except Exception:
                pass
        for lid in LIGAS:
            try:
                n = juntar_goles(lid, limite=20)
                if n:
                    goles_pendientes += 1
                    print("  · %-18s goles de %d partidos" % (LIGAS[lid]["nombre"], n), flush=True)
            except Exception:
                pass
            time.sleep(2)

        # las estadísticas de la Liga Profesional, para el gráfico promedio
        try:
            n = juntar_stats("lpf", limite=15)
            if n:
                goles_pendientes += 1
                print("  · %-18s estadísticas de %d partidos"
                      % ("Liga Profesional", n), flush=True)
        except Exception:
            pass
        # Lo de los calendarios se decide sólo con los calendarios. Es la
        # línea que faltaba: antes un gol pendiente bastaba para que se
        # volvieran a recorrer todos, cada minuto, para siempre.
        if recorrer:
            if not pendientes and not historia_al_dia:
                print("  Historia completa: de acá en más miro los "
                      "calendarios cada tanto\n", flush=True)
            historia_al_dia = not pendientes
        _ESTADO_FONDO.update(historia_al_dia=historia_al_dia,
                             haciendo="esperando")

        # Y una vez por día, sacar la basura.
        try:
            limpieza_diaria()
        except Exception as e:
            print("  La limpieza falló: %s" % e, flush=True)

        # Y el ritmo: rápido sólo mientras falte historia, que es lo que
        # conviene apurar. Buscar goles es barato pero no urgente, y
        # hacerlo cada minuto le come el procesador al que está mirando la
        # página. Cada cinco alcanza.
        if not pendientes and not goles_pendientes:
            time.sleep(900)
        elif not pendientes:
            time.sleep(300)             # sólo quedan goles por buscar
        else:
            if vuelta == VUELTAS_SEGUIDAS:
                print("  Quedan %d recorridos sin terminar: sigo cada 15 "
                      "minutos\n" % pendientes, flush=True)
            time.sleep(60 if vuelta < VUELTAS_SEGUIDAS else 900)


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
    print("  Versión: %s" % VERSION_APP)
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
