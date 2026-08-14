# -*- coding: utf-8 -*-
"""
Cliente de API-Football (api-sports.io).

A diferencia de las fuentes anteriores, esta tiene licencia: la clave es tuya
y sus términos permiten uso público. La contra es el tope del plan gratis,
100 pedidos por día, que obliga a pensar cada llamada.

La estrategia:

  · Un pedido trae MUCHO. `/fixtures?league=128&season=2026` devuelve el
    torneo entero, las 16 fechas de una. No hace falta pedir fecha por fecha.
  · Todo pasa por el almacén: se guarda y se sirve de ahí.
  · Hay un presupuesto con reserva. Si se acaba, se sirve lo guardado en vez
    de romper.

Con eso, un día normal son unos 10 a 20 pedidos, no 100.
"""

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import almacen

BASE = "https://v3.football.api-sports.io"
TOPE_DIARIO = 100          # plan gratis
UA = "HAYVAR/1.0"

# Cuánto vale la pena guardar cada cosa antes de volver a preguntar.
FRESCURA = {
    "fixtures": 60 * 60 * 6,      # el fixture cambia poco
    "standings": 60 * 30,         # las tablas, tras cada fecha
    "topscorers": 60 * 60 * 12,
    "live": 25,                   # lo único que se pide seguido
    "status": 60 * 60,
}


class SinPresupuesto(Exception):
    """Se acabaron los pedidos del día."""


class SinClave(Exception):
    """No hay clave configurada."""


def _pedir(clave_api, camino, params):
    if not clave_api:
        raise SinClave("no hay clave de API-Football configurada")
    url = "%s/%s?%s" % (BASE, camino.strip("/"), urlencode(params))
    req = Request(url, headers={"x-apisports-key": clave_api,
                                "Accept": "application/json",
                                "User-Agent": UA})
    with urlopen(req, timeout=20) as r:
        cuerpo = json.loads(r.read().decode("utf-8"))
    almacen.contar_pedido()

    # La API responde 200 aunque haya error: viene en el cuerpo.
    errores = cuerpo.get("errors")
    if errores and (isinstance(errores, dict) and errores or
                    isinstance(errores, list) and errores):
        detalle = (list(errores.values())[0] if isinstance(errores, dict)
                   else errores[0])
        raise RuntimeError(str(detalle))
    return cuerpo.get("response", [])


def traer(clave_api, camino, params, frescura=None, forzar=False):
    """Pide con caché y presupuesto. Devuelve (datos, info)."""
    etiqueta = camino.strip("/").replace("/", "-")
    clave = "af:%s:%s" % (etiqueta, urlencode(sorted(params.items())))
    edad_max = frescura if frescura is not None else FRESCURA.get(etiqueta, 60 * 60)

    if not forzar:
        valor, edad = almacen.leer(clave, edad_max)
        if valor is not None:
            return valor, {"origen": "cache", "edad": round(edad)}

    if not almacen.hay_presupuesto(TOPE_DIARIO):
        viejo, edad = almacen.leer(clave)
        if viejo is not None:
            return viejo, {"origen": "cache-vieja", "edad": round(edad or 0),
                           "motivo": "se agotó el presupuesto del día"}
        raise SinPresupuesto("se agotaron los %d pedidos de hoy" % TOPE_DIARIO)

    try:
        datos = _pedir(clave_api, camino, params)
    except Exception as e:
        viejo, edad = almacen.leer(clave)
        if viejo is not None:
            return viejo, {"origen": "cache-vieja", "edad": round(edad or 0),
                           "error": str(e)}
        raise

    almacen.guardar(clave, datos)
    return datos, {"origen": "fuente", "edad": 0}


# ── Traducción al modelo interno ─────────────────────────────────────────
ESTADOS = {
    "1H": "LIVE", "2H": "LIVE", "HT": "LIVE", "ET": "LIVE", "BT": "LIVE",
    "P": "LIVE", "LIVE": "LIVE", "INT": "LIVE",
    "FT": "FIN", "AET": "FIN", "PEN": "FIN", "AWD": "FIN", "WO": "FIN",
    "NS": "PROG", "TBD": "PROG",
    "PST": "SUSP", "CANC": "SUSP", "ABD": "SUSP", "SUSP": "SUSP",
}


def _equipo(t):
    return {"id": t.get("id"), "name": t.get("name") or "", "canon": None,
            "short": "", "logo": t.get("logo"), "score": None, "site": None}


def mapear_partido(f):
    fx, eq, gol = f.get("fixture", {}), f.get("teams", {}), f.get("goals", {})
    lg, st = f.get("league", {}), (fx.get("status") or {})
    estado = ESTADOS.get(st.get("short"), "PROG")
    ronda = None
    m = lg.get("round") or ""
    for pedazo in m.replace("-", " ").split():
        if pedazo.isdigit():
            ronda = int(pedazo)
    casa, visita = _equipo(eq.get("home") or {}), _equipo(eq.get("away") or {})
    casa["score"], visita["score"] = gol.get("home"), gol.get("away")
    return {
        "id": "af-%s" % fx.get("id"), "liveId": fx.get("id"),
        "round": ronda, "zone": None, "interzonal": False,
        "stage": lg.get("round") or "", "start": fx.get("date"),
        "status": estado, "statusText": st.get("long") or "",
        "minute": st.get("elapsed") if estado == "LIVE" else None,
        "referee": fx.get("referee") or "",
        "home": casa, "away": visita,
        "gh": gol.get("home"), "ga": gol.get("away"),
        "venue": (fx.get("venue") or {}).get("name") or "",
    }


def partidos(clave_api, liga, temporada, **extra):
    params = {"league": liga, "season": temporada}
    params.update(extra)
    datos, info = traer(clave_api, "fixtures", params)
    return [mapear_partido(f) for f in datos], info


def en_vivo(clave_api, liga):
    datos, info = traer(clave_api, "fixtures", {"league": liga, "live": "all"},
                        frescura=FRESCURA["live"])
    return [mapear_partido(f) for f in datos], info


def posiciones(clave_api, liga, temporada):
    datos, info = traer(clave_api, "standings",
                        {"league": liga, "season": temporada})
    zonas = []
    for entrada in datos:
        grupos = ((entrada.get("league") or {}).get("standings") or [])
        for grupo in grupos:
            filas = []
            for r in grupo:
                todos = r.get("all") or {}
                gf = (todos.get("goals") or {}).get("for") or 0
                gc = (todos.get("goals") or {}).get("against") or 0
                filas.append({
                    "team": {"name": (r.get("team") or {}).get("name") or "",
                             "short": "", "logo": (r.get("team") or {}).get("logo"),
                             "site": None},
                    "pts": r.get("points") or 0, "pj": todos.get("played") or 0,
                    "g": todos.get("win") or 0, "e": todos.get("draw") or 0,
                    "p": todos.get("lose") or 0,
                    "gf": gf, "gc": gc, "dif": gf - gc,
                    "form": [{"W": "G", "D": "E", "L": "P"}.get(c, "E")
                             for c in (r.get("form") or "")[-5:]],
                    "live": False, "pos": r.get("rank"),
                    "grupo": r.get("group") or "",
                })
            if filas:
                zonas.append({"name": filas[0]["grupo"] or "Tabla", "rows": filas})
    return zonas, info


def goleadores(clave_api, liga, temporada):
    datos, info = traer(clave_api, "players/topscorers",
                        {"league": liga, "season": temporada})
    filas = []
    for i, p in enumerate(datos, 1):
        est = (p.get("statistics") or [{}])[0]
        goles = (est.get("goals") or {})
        filas.append({
            "rank": i, "name": (p.get("player") or {}).get("name") or "",
            "team": {"name": (est.get("team") or {}).get("name") or "", "short": "",
                     "logo": (est.get("team") or {}).get("logo"), "site": None},
            "goals": goles.get("total") or 0,
            "pens": (est.get("penalty") or {}).get("scored") or 0,
            # API-Football no discrimina de jugada / cabeza / tiro libre
            "jugada": None, "cabeza": None, "tiroLibre": None,
        })
    return filas, info


def diagnostico(clave_api, ligas_temporadas):
    """
    Prueba la clave y averigua qué cubre el plan. Devuelve un informe sin
    exponer nunca la clave.
    """
    informe = {"clave_configurada": bool(clave_api),
               "pedidos_hoy": almacen.pedidos_hoy(), "tope": TOPE_DIARIO,
               "ligas": [], "cuenta": None, "error": None}
    if not clave_api:
        informe["error"] = "No hay clave: creá clave.txt o definí APIFOOTBALL_KEY."
        return informe

    try:
        estado, _ = traer(clave_api, "status", {}, frescura=FRESCURA["status"])
        if isinstance(estado, dict):
            sub = estado.get("subscription") or {}
            req = estado.get("requests") or {}
            informe["cuenta"] = {
                "plan": sub.get("plan"), "activa": sub.get("active"),
                "vence": sub.get("end"),
                "usados_hoy": req.get("current"), "limite_diario": req.get("limit_day"),
            }
    except Exception as e:
        informe["error"] = "La clave no fue aceptada: %s" % e
        return informe

    for nombre, liga, temporada in ligas_temporadas:
        item = {"nombre": nombre, "liga": liga, "temporada": temporada}
        try:
            datos, info = traer(clave_api, "fixtures",
                                {"league": liga, "season": temporada})
            item["partidos"] = len(datos)
            item["origen"] = info.get("origen")
            item["ok"] = len(datos) > 0
            if not datos:
                item["nota"] = ("Sin partidos. En el plan gratis las temporadas "
                                "recientes suelen estar bloqueadas.")
        except Exception as e:
            item["ok"] = False
            item["error"] = str(e)
        informe["ligas"].append(item)
    return informe
