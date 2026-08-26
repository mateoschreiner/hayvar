# -*- coding: utf-8 -*-
"""
Regresión de HAYVAR. Se corre con:  python3 _pruebas.py

No pega contra 365scores: las respuestas de la fuente se simulan. Lo que
prueba es lo nuestro —cómo se ordena, se filtra y se cuenta— que es donde
estuvieron todos los errores.
"""
import itertools
import json, os, random, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
os.environ["HAYVAR_DB"] = "/tmp/hayvar_pruebas.db"
for _e in ("", "-wal", "-shm"):
    try: os.remove("/tmp/hayvar_pruebas.db" + _e)
    except OSError: pass
sys.path.insert(0, AQUI)
import server

# Casi todas las pruebas del recorrido le cambian el fetch_ruta a server por
# uno de mentira. El de verdad se guarda acá, antes de que nadie lo pise.
FETCH_RUTA_REAL = server.fetch_ruta

HTML = open(os.path.join(AQUI, "index.html"), encoding="utf-8").read()
fallas = []
def chequear(titulo, cond, detalle=""):
    print("  %s %s%s" % ("✓" if cond else "✗", titulo,
                         "" if cond else "  <- " + str(detalle)))
    if not cond:
        fallas.append(titulo)



# ── un 365scores de mentira, fiel en lo que importa ─────────────────────
# Los números de partido no siguen el calendario. Cualquier prueba del
# recorrido que use ids ordenados se miente a sí misma.
import datetime as _dtu, random as _rndu
def universo(comp, cuantos, desde=4700000, temporada=69, semilla=1):
    _rndu.seed(semilla)
    ids = list(range(desde, desde + cuantos)); _rndu.shuffle(ids)
    cuando = {i: _dtu.datetime(2026, 2, 1) + _dtu.timedelta(days=k * 3)
              for k, i in enumerate(ids)}
    orden = sorted(cuando, key=lambda i: cuando[i])
    def crudo(i):
        return {"id": i, "competitionId": comp, "seasonNum": temporada,
                "roundNum": None, "stageName": "Fase de grupos",
                "startTime": cuando[i].isoformat(), "statusGroup": 4,
                "statusText": "Finalizado", "gameTime": 90,
                "homeCompetitor": {"id": 1, "name": "A", "score": 1},
                "awayCompetitor": {"id": 2, "name": "B", "score": 0}}
    def guardado(i):
        return {"id": i, "comp": comp, "temporada": temporada, "round": None,
                "start": cuando[i].isoformat(), "stage": "Fase de grupos"}
    def haciaAtras(ruta):
        d = int(re.search(r"aftergame=(\d+)", ruta).group(1))
        pos = orden.index(d) if d in orden else 0
        return {"games": [crudo(i) for i in orden[max(0, pos - 7):pos]],
                "paging": {}}
    return orden, guardado, haciaAtras


print("\n── camisetas ──")
SABE = set(re.findall(r"k\.patron\s*===?\s*'(\w+)'", HTML)) | {"liso"}
# Todas las camisetas de todos los clubes, no sólo las dos primeras: un club
# puede tener tercera y esa también hay que saber dibujarla.
TODAS = [(n, c, k) for n, d in server.CLUBES_INFO.items()
         for c, k in d["camisetas"].items()]
malos = [(n, c) for n, c, k in TODAS if k["patron"] not in SABE]
chequear("los 30 clubes tienen ficha", len(server.CLUBES_INFO) == 30,
         len(server.CLUBES_INFO))
chequear("todos los patrones se saben dibujar", not malos, malos)
chequear("nadie quedó sin sitio oficial",
         all(d.get("sitio") for d in server.CLUBES_INFO.values()))

# Lo que el diseño de una camiseta pide y el dibujo tiene que entender. Es
# el mismo error de siempre: se agrega una opción en la configuración y el
# que dibuja no se entera, así que la camiseta sale sin eso y nadie avisa.
ABECEDARIOS = {"didona", "angulosa", "sistema"}
chequear("el dibujo conoce los abecedarios de las leyendas",
         all(("'%s'" % a) in HTML for a in ABECEDARIOS - {"didona"})
         and "const DIDONA" in HTML)
letras = {(k.get("leyenda") or {}).get("letra") for _, _, k in TODAS}
chequear("y ninguna leyenda pide una letra que no existe",
         not (letras - ABECEDARIOS - {None}), letras)
# Las leyendas que van dibujadas letra por letra sólo pueden usar letras
# que estén en el abecedario. Con la del sistema no hace falta: esa la pone
# el navegador.
falta_glifo = sorted({c for _, _, k in TODAS
                      if (k.get("leyenda") or {}).get("letra") in
                      ("didona", "angulosa")
                      for c in k["leyenda"]["texto"].upper()
                      if c != " " and not re.search(
                          r"'%s':\s*\{av:" % re.escape(c), HTML)})
chequear("y toda letra dibujada tiene su glifo", not falta_glifo, falta_glifo)
chequear("y el dibujo sabe hacer la trama de agua",
         "k.agua" in HTML and "feTurbulence" in HTML)
chequear("Aldosivi tiene las tres",
         list(server.CLUBES_INFO["Aldosivi"]["camisetas"]) ==
         ["titular", "suplente", "tercera"])
chequear("y Argentinos también",
         list(server.CLUBES_INFO["Argentinos Juniors"]["camisetas"]) ==
         ["titular", "suplente", "tercera"])
# El escudo se enlaza, no se copia: es la misma imagen que la página ya usa
# al lado del nombre. Y va sólo en el frente.
chequear("el escudo va enlazado y sólo en el frente",
         "function camisetaSVG(k0, atras, escudo)" in HTML
         and "${!atras && escudo && !k.sinEscudo ?" in HTML
         and "camisetaSVG(kits[nom],false,d.escudo)" in HTML)
# Hoy no la usa ninguna —la tercera de Argentinos terminó llevándolo—
# pero la puerta queda abierta para la camiseta que lleve un escudo
# especial que no podamos enlazar.
chequear("y una camiseta puede pedir que no se lo pongan",
         "!k.sinEscudo" in HTML)
# Lo que dice el cuello por dentro tiene que caer sobre la cinta, y la
# cinta se mueve con el escote: si el número fuera fijo, quedaría flotando.
# Una costura es un doblez: sombra de un lado, luz del otro. Con una sola
# línea se veía pintada encima.
chequear("las costuras van en dos líneas y no en una",
         HTML.count('stroke="rgba(255,255,255,.17)"') >= 3
         and 'stroke="rgba(0,0,0,.22)"' in HTML)
# El borde de la manga que va contra el cuerpo no es silueta sino costura:
# trazarlo como los demás dejaba una raya oscura y recta cruzando el costado.
# Ni el borde de la manga contra el cuerpo ni las dos sisas son silueta:
# los tapa la otra pieza. Trazarlos dejaba rayas negras y rectas.
chequear("el contorno del cuerpo no traza las sisas",
         'd="${CUERPO}" fill="none" stroke="rgba(0,0,0,.32)"' not in HTML
         and 'd="M78 28 L${ESCOTE} L152 28" fill="none"' in HTML)
chequear("el contorno de la manga no traza la costura contra el cuerpo",
         'd="${MANGA_I}" fill="none" stroke="rgba(0,0,0,.30)"' not in HTML
         and 'd="M78 28 Q58 33 48 46 Q38 62 37 88 Q50 96 64 98" fill="none"'
         in HTML)
chequear("y los vivos de Argentinos los corta la costura, no una altura fija",
         'clip-path="url(#ragl${u})"' in HTML
         and '<clipPath id="ragl${u}">' in HTML)
# La ranglan no es la misma de los dos lados: adelante cae casi a plomo
# desde el cuello y atrás baja mucho más tendida. Son dos piezas distintas
# de la camiseta.
chequear("la ranglan de adelante no es la de atrás",
         "const RANGLAN_I = atras" in HTML
         and HTML.count("'102 34 Q86 36 78 55 Q70 70 67 84'") == 1
         and HTML.count("'97 36 Q86 37 79 47 Q70 55 66 66 L65 84'") == 1)
chequear("y el panel de la blanca se traza sobre esa misma línea",
         'd="M${RANGLAN_I}" fill="none" stroke="${PANEL}"' in HTML)
chequear("lo del cuello de atrás se ubica con el escote",
         "y=\"${(HUNDE + GRUESO_CUELLO / 2 - 1.1).toFixed(1)}\"" in HTML)


print("\n── la tienda oficial ──")
ajenas = ("mercadolibre", "dexter", "opensports", "solodeporte", "instagram",
          "facebook", "adidas.", "puma.", "kappa", "umbro", "nike.")
chequear("todas las tiendas son de un club de Primera",
         not (set(server.TIENDAS) - set(server.CLUBES_INFO)),
         set(server.TIENDAS) - set(server.CLUBES_INFO))
chequear("y ninguna es de un tercero",
         not [n for n, u in server.TIENDAS.items()
              if any(a in u.lower() for a in ajenas)],
         [n for n, u in server.TIENDAS.items()
          if any(a in u.lower() for a in ajenas)])
chequear("y todas van por https",
         all(u.startswith("https://") for u in server.TIENDAS.values()))
# El club que no tiene tienda propia no muestra la tarjeta: es preferible
# eso a mandar a alguien a un link que no es del club.
chequear("el que no tiene tienda no muestra el botón",
         "d.tienda?`<a href=" in HTML and "d.sitio||d.tienda?" in HTML)


print("\n── direcciones de club ──")
import unicodedata
def slug_js(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"['´`]", "", s)).strip("-")
mal = [n for n in server.CLUBES_INFO if server.RUTAS_CLUB.get(slug_js(n)) != n]
chequear("la dirección que arma el navegador es la que entiende el servidor",
         not mal, mal)
chequear("ninguna lleva paréntesis",
         not [r for r in server.RUTAS_CLUB if "(" in r])


print("\n── fases de las copas ──")
for lid, fases in server.FASES_COPA.items():
    rangos = [server.rango_etapa(f) for f in fases]
    chequear("%s: las fases no se cruzan" % lid, rangos == sorted(rangos),
             list(zip(fases, rangos)))
chequear("el repechaje de acceso va antes de la fase de liga",
         server.rango_etapa("Repechaje de acceso") < server.rango_etapa("Fase de liga"))
chequear("y el play-off de febrero, después",
         server.rango_etapa("Fase de liga") < server.rango_etapa("Play-offs"))
chequear("Playoff de la clasificación -> Repechaje de acceso",
         server.nombre_de_previa("Playoff") == "Repechaje de acceso")
chequear("3rd Qualifying Round -> Fase previa 3",
         server.nombre_de_previa("3rd Qualifying Round") == "Fase previa 3")


print("\n── la clasificación europea numera sus temporadas aparte ──")
EL, PREV = 573, 596
server.almacen.guardar("temporada:%d" % EL, 61)
server.almacen.guardar("temporada:%d" % PREV, 11)
def juego(gid, comp, temp, etapa, grupo=None, fin=False):
    return {"id": gid, "competitionId": comp, "seasonNum": temp, "stageNum": 4,
            "groupNum": grupo, "stageName": etapa, "roundNum": 1,
            "startTime": "2026-08-20T15:00:00+00:00",
            "statusGroup": 4 if fin else 2,
            "statusText": "Finalizado" if fin else "Prog.",
            "gameTime": 90 if fin else -1,
            "homeCompetitor": {"id": 1, "name": "A%d" % gid, "score": 2 if fin else -1},
            "awayCompetitor": {"id": 2, "name": "B%d" % gid, "score": 1 if fin else -1}}
CRUDOS = ([juego(100 + i, PREV, 11, "Playoff", grupo=i + 1) for i in range(12)]
          + [juego(200 + i, EL, 60, "Fase de liga") for i in range(4)])
def falso_fetch(path, params, ttl=15):
    if path == "competitions":
        c = params.get("competitions")
        return {"competitions": [{"id": c, "currentSeasonNum": 61 if c == EL else 11}]}
    return {"games": CRUDOS, "competitions": [{"id": EL, "currentSeasonNum": 61}]}
server.fetch = falso_fetch
quedan = server._sc_fixture(EL)
chequear("se quedan los 12 de la clasificación de ahora", len(quedan) == 12, len(quedan))
chequear("se van los 4 de la temporada pasada",
         all(m["comp"] == PREV for m in quedan))
cfg = server.LIGAS["europa"]
todos = server.fixture_de_liga(cfg)
chequear("quedan marcados como previa", all(m.get("previa") for m in todos))
chequear("y con número de llave, para armar el cuadro",
         all(m.get("slot") for m in todos))
chequear("la clasificación no cuenta como 'el torneo arrancó'",
         server.arranco_el_torneo(cfg) is False)


print("\n── la migración no puede borrar nada ──")
C2 = 5078
viejos = [{"id": i, "round": 1, "temporada": 3} for i in range(1, 381)]
server.almacen.guardar("fixture:%d" % C2, viejos)
server.almacen.guardar("hist:%d" % C2, {"listo": True})
server.migrar_fixture(C2)
tras, _ = server.almacen.leer("fixture:%d" % C2)
chequear("los 380 partidos siguen ahí", len(tras) == 380, len(tras))
chequear("y el recorrido quedó reabierto",
         server.almacen.leer("hist:%d" % C2)[0] == {})


print("\n── el recorrido se autorepara ──")
# El caso que se dio en Render: el calendario quedó corto pero los
# marcadores decían "ya recorrí todo", así que nadie lo volvía a bajar.
C3 = 7
server.almacen.guardar("fechas:%d" % C3, 38)
server.almacen.guardar("fixture:%d" % C3,
    [{"id": i, "round": i, "comp": C3, "temporada": 132} for i in (1, 2)])
server.almacen.guardar("hist:%d" % C3, {"listo": True})
server.almacen.guardar("fut:%d" % C3, {"listo": True})
server.reabrir_si_falta(C3)
chequear("2 de 38 fechas y 'listo' -> reabre el recorrido",
         server.almacen.leer("hist:%d" % C3)[0] == {}
         and server.almacen.leer("fut:%d" % C3)[0] == {})
chequear("y no borra los partidos",
         len(server.almacen.leer("fixture:%d" % C3)[0]) == 2)
server.almacen.guardar("hist:%d" % C3, {"listo": True})
server.reabrir_si_falta(C3)
chequear("no insiste más de una vez por día",
         server.almacen.leer("hist:%d" % C3)[0] == {"listo": True})
C4 = 25
server.almacen.guardar("fechas:%d" % C4, 34)
server.almacen.guardar("fixture:%d" % C4,
    [{"id": i, "round": i % 34 + 1, "comp": C4} for i in range(400)])
server.almacen.guardar("hist:%d" % C4, {"listo": True})
server.reabrir_si_falta(C4)
chequear("un calendario completo lo deja en paz",
         server.almacen.leer("hist:%d" % C4)[0]["listo"] is True)


print("\n── reparación de todos los recorridos ──")
# Los partidos guardados y el marcador de por dónde iba el recorrido son
# dos cosas distintas, y pueden quedar peleadas: sin esto, un calendario
# que se perdió no se recupera nunca porque el marcador dice "ya está".
for _cfg in server.LIGAS.values():
    for _c in server.comps_de(_cfg):
        server.almacen.guardar("hist:%s" % _c, {"listo": True})
        server.almacen.guardar("fut:%s" % _c, {"listo": True})
        server.almacen.guardar("fixture:%s" % _c, [{"id": 1, "round": 1, "comp": _c}])
_comps = sorted({c for f in server.LIGAS.values() for c in server.comps_de(f)})
server.reparar_recorridos()      # ahora sólo informa, no toca nada
chequear("informar no borra ni un partido",
         all(len(server.almacen.leer("fixture:%s" % c)[0] or []) == 1 for c in _comps))
chequear("ni reescribe los marcadores",
         all((server.almacen.leer("hist:%s" % c)[0] or {}).get("listo")
             for c in _comps))
_src = open(os.path.join(AQUI, "server.py"), encoding="utf-8").read()
chequear("el cliente que se va no ensucia el log",
         "except self.SE_FUE:" in _src and "def handle_one_request" in _src)


print("\n── qué fecha se abre ──")
import datetime as _dt
def _g(dias, fin):
    # Anclado al dia LOCAL y no a la hora UTC. `fecha_actual` compara contra
    # `date.today()`, que es local: contando desde la hora UTC, un partido de
    # "ayer" caia en el dia de hoy cada vez que la prueba se corria despues
    # de la medianoche de Londres, y la prueba fallaba sola de madrugada.
    d = _dt.date.today() + _dt.timedelta(days=dias)
    t = _dt.datetime.combine(d, _dt.time(15, 0), _dt.timezone.utc)
    return {"start": t.isoformat(), "status": "FIN" if fin else "PROG"}
for _titulo, _pf, _esp in [
    ("una fecha en curso gana sobre la siguiente",
     {1: [_g(-1, True), _g(1, False)], 2: [_g(6, False)]}, 1),
    ("si hay partidos hoy, esa",
     {2: [_g(-3, True)], 3: [_g(0, False)], 4: [_g(7, False)]}, 3),
    ("un suspendido viejo no clava la página",
     {1: [_g(-70, True), _g(-70, False)], 2: [_g(-1, True)], 3: [_g(3, False)]}, 3),
    ("torneo terminado: la última",
     {1: [_g(-40, True)], 2: [_g(-30, True)]}, 2)]:
    chequear(_titulo, server.fecha_actual(sorted(_pf), _pf) == _esp,
             server.fecha_actual(sorted(_pf), _pf))


print("\n── esconder no es borrar ──")
_C = 25
server.almacen.guardar("temporada:%d" % _C, 118)
server.almacen.guardar("fixture:%d" % _C,
    [{"id": 900 + i, "round": 34, "comp": _C, "temporada": 117,
      "start": "2026-05-22T10:30:00-03:00", "stage": "Descenso/Ascenso"} for i in range(9)]
  + [{"id": 100 + i, "round": 1, "comp": _C, "temporada": 118,
      "start": "2026-08-28T15:30:00-03:00", "stage": "Fase 1"} for i in range(9)])
_guardado = server.fetch
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C, "currentSeasonNum": 118}]} if p == "competitions"
    else {"games": [], "competitions": [{"id": _C, "currentSeasonNum": 118}]})
_serv = server._sc_fixture(_C)
chequear("la temporada pasada no se muestra", len(_serv) == 9, len(_serv))
chequear("pero sigue guardada en la base",
         len(server.almacen.leer("fixture:%d" % _C)[0]) == 18)
chequear("y su fase desaparece del selector",
         "Descenso/Ascenso" not in {m.get("stage") for m in _serv})
server.fetch = _guardado


print("\n── el recorrido aguanta una página de otra temporada ──")
_C2 = 102
server.almacen.guardar("temporada:%d" % _C2, 40)
server.almacen.guardar("fixture:%d" % _C2, [])
server.almacen.guardar("hist:%d" % _C2, {})
_paso = {"n": 0}
def _ruta(ruta):
    _paso["n"] += 1
    _otra = _paso["n"] == 2          # la segunda página es de otra temporada
    return {"games": [{"id": 1000 + _paso["n"], "competitionId": _C2,
                       "seasonNum": 39 if _otra else 40, "roundNum": 1,
                       "startTime": "2026-04-01T16:00:00-03:00",
                       "statusGroup": 4, "statusText": "Finalizado", "gameTime": 90,
                       "homeCompetitor": {"id": 1, "name": "A", "score": 1},
                       "awayCompetitor": {"id": 2, "name": "B", "score": 0}}],
            "paging": {"previousPage": "/p%d" % (_paso["n"] + 1)}}
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C2, "currentSeasonNum": 40}]} if p == "competitions"
    else {"games": [], "paging": {"previousPage": "/p1"}})
server.fetch_ruta = _ruta
server.time.sleep = lambda s: None
_r = server.caminar_fixture(_C2, -1, paginas=5)
chequear("no corta en la página filtrada", _r["paginas"] >= 4, _r["paginas"])
chequear("y trae los de las páginas buenas", _r["nuevos"] >= 4, _r["nuevos"])
_C3 = 6224
server.almacen.guardar("fixture:%d" % _C3, [])
server.almacen.guardar("hist:%d" % _C3, {})
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C3, "currentSeasonNum": 5}]} if p == "competitions"
    else {"games": [], "paging": {}})
chequear("sin paginado se marca terminado, no 'sigue' eterno",
         server.caminar_fixture(_C3, -1, paginas=9)["listo"] is True)
server.fetch = _guardado


print("\n── el recorrido dice por qué se detuvo ──")
# Sin esto, un recorrido que se corta antes de tiempo es indistinguible de
# uno que terminó bien: los dos decían "listo" y había que adivinar.
server.time.sleep = lambda s: None
def _armar(comp, paginas_buenas):
    server.almacen.guardar("temporada:%d" % comp, 40)
    server.almacen.guardar("fixture:%d" % comp, [])
    server.almacen.guardar("hist:%d" % comp, {})
    server.almacen.guardar("migrado2:%d" % comp, True)
    server.almacen.guardar("reabierto:%d" % comp, True)
    server.fetch = lambda p, q, ttl=15, c=comp: (
        {"competitions": [{"id": c, "currentSeasonNum": 40}]} if p == "competitions"
        else {"games": [], "paging": {"previousPage": "/p1"}})
    _n = {"i": 0}
    def _ruta(r):
        _n["i"] += 1
        # despues de `paginas_buenas` no hay ni partidos ni paginado
        vacia = _n["i"] > paginas_buenas
        return {"games": [] if vacia else [
                    {"id": comp * 1000 + _n["i"], "competitionId": comp,
                     "seasonNum": 40, "roundNum": 1,
                     "startTime": "2026-04-%02dT16:00:00-03:00" % (28 - _n["i"]),
                     "statusGroup": 4, "statusText": "Finalizado",
                     "gameTime": 90,
                     "homeCompetitor": {"id": 1, "name": "A", "score": 1},
                     "awayCompetitor": {"id": 2, "name": "B", "score": 0}}],
                "paging": {"previousPage": "/p%d" % (_n["i"] + 1)} if not vacia else {}}
    server.fetch_ruta = _ruta
_armar(9001, 3)
_r = server.caminar_fixture(9001, -1, paginas=20)
# Que la fuente deje de dar paginado ya no termina el recorrido: el cursor se
# arma solo. Termina cuando de verdad no hay mas partidos.
chequear("termina cuando no quedan partidos, y lo explica",
         _r["listo"] and "sin partidos" in (_r.get("motivo") or ""),
         _r.get("motivo"))
_armar(9002, 99)
_r2 = server.caminar_fixture(9002, -1, paginas=3)
chequear("si se corta por el presupuesto, lo dice y sigue después",
         not _r2["listo"] and "límite" in (_r2.get("motivo") or ""),
         _r2.get("motivo"))
chequear("el motivo queda guardado para /api/recorrido",
         server.almacen.leer("hist:9002")[0].get("motivo") == _r2["motivo"])
def _explota(r): raise OSError("timeout")
server.fetch_ruta = _explota
_armar(9003, 1)
server.fetch_ruta = _explota
_r3 = server.caminar_fixture(9003, -1, paginas=5)
chequear("un error de la fuente no se disfraza de 'listo'",
         not _r3["listo"] and "falló" in (_r3.get("motivo") or ""),
         _r3.get("motivo"))
server.fetch = _guardado

# Un tropiezo de la fuente no cuesta una pagina: corta la vuelta entera y lo
# que venia atras queda sin bajar. A la Primera Nacional le faltaba septiembre
# por eso: las dos direcciones murieron en un TimeoutError.
class _Respuesta:
    def __init__(s, d): s.d = json.dumps(d).encode()
    def read(s): return s.d
    def __enter__(s): return s
    def __exit__(s, *a): return False
_veces = {"n": 0}
def _flojo(req, timeout=20):
    _veces["n"] += 1
    if _veces["n"] < 3:
        raise TimeoutError("timed out")
    return _Respuesta({"games": [], "paging": {}})
_urlopen, _dormir = server.urlopen, server.time.sleep
_falso_fr, server.fetch_ruta = server.fetch_ruta, FETCH_RUTA_REAL
server.urlopen, server.time.sleep = _flojo, lambda s: None
try:
    _ok = server.fetch_ruta("/web/games/?x=1")
    chequear("dos timeouts seguidos no cortan el recorrido: reintenta",
             _ok == {"games": [], "paging": {}} and _veces["n"] == 3, _veces["n"])
    _veces["n"] = 0
    def _siempre(req, timeout=20): raise TimeoutError("timed out")
    server.urlopen = _siempre
    try:
        server.fetch_ruta("/web/games/?x=1")
        _murio = False
    except TimeoutError:
        _murio = True
    chequear("pero si la fuente esta caida no insiste para siempre",
             _murio and server.INTENTOS_PAGINA == 3)
finally:
    server.urlopen, server.time.sleep = _urlopen, _dormir
    server.fetch_ruta = _falso_fr


print("\n── un marcador de otra version no se le cree ──")
# Tres veces seguidas la reparacion corrio con el recorrido todavia roto y
# dejo todo sellado en "listo". Ahora la version va adentro del marcador.
_C5 = 3102
_orden5, _guardado5, _atras5 = universo(_C5, 60, 4728100, semilla=5)
for _k, _v in (("temporada:%d" % _C5, 69), ("migrado2:%d" % _C5, True),
               ("reabierto:%d" % _C5, True)):
    server.almacen.guardar(_k, _v)
server.almacen.guardar("fixture:%d" % _C5, [_guardado5(i) for i in _orden5[-16:]])
server.almacen.guardar("hist:%d" % _C5,      # sin "v": version anterior
    {"listo": True, "total": 16, "motivo": "la fuente no ofrece mas paginas"})
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C5, "currentSeasonNum": 69}]} if p == "competitions"
    else {"games": [], "paging": {}})
server.fetch_ruta = _atras5
_r7 = server.caminar_fixture(_C5, -1, paginas=30)
chequear("un marcador de otra version se rehace", _r7["paginas"] > 3, _r7["paginas"])
chequear("y trae lo que faltaba", _r7["total"] == 60, _r7["total"])
chequear("el marcador nuevo guarda su version",
         server.almacen.leer("hist:%d" % _C5)[0].get("v") == server.VERSION_RECORRIDO)
chequear("y no se repite",
         server.caminar_fixture(_C5, -1, paginas=30).get("paginas", 0) == 0)
_vieja = server.VERSION_RECORRIDO
server.VERSION_RECORRIDO += 1
chequear("subir la version alcanza para rehacer todo",
         server.caminar_fixture(_C5, -1, paginas=30).get("paginas", 0) > 0)
server.VERSION_RECORRIDO = _vieja
server.almacen.guardar("fut:%d" % _C5,
    {"listo": True, "total": 60, "motivo": "listo", "ultimo": "/u",
     "v": server.VERSION_RECORRIDO})
_rf = server.caminar_fixture(_C5, 1, paginas=40)
chequear("hacia adelante rechequea pero no rehace todo",
         _rf.get("paginas", 0) <= 3, _rf.get("paginas"))
server.fetch = _guardado

print("\n── reconstruir guarda copia y se puede deshacer ──")
_C8 = 4102
for _k, _v in (("temporada:%d" % _C8, 69), ("migrado2:%d" % _C8, True),
               ("reabierto:%d" % _C8, True)):
    server.almacen.guardar(_k, _v)
server.almacen.guardar("fixture:%d" % _C8,
    [{"id": 900 + i, "comp": _C8, "temporada": 69, "round": 5} for i in range(16)])
_LIB = server.LIGAS["lib"]["sc"]
server.LIGAS["lib"]["sc"] = _C8
chequear("sin confirmar no borra nada",
         "error" in server.api_recorrido({"reconstruir": ["lib"]})
         and len(server.almacen.leer("fixture:%d" % _C8)[0]) == 16)
server.fetch_ruta = lambda r: {"games": [], "paging": {}}
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C8, "currentSeasonNum": 69}]} if p == "competitions"
    else {"games": [], "competitions": [{"id": _C8, "currentSeasonNum": 69}],
          "paging": {}})
_d8 = server.api_recorrido({"reconstruir": ["lib"], "confirmar": ["si"]})
chequear("al reconstruir guarda una copia",
         (_d8["rehecho"]["respaldo"] or {}).get("competencias") == [_C8])
chequear("y se puede volver atrás",
         len(server.api_recorrido({"restaurar": ["lib"], "confirmar": ["si"]})
             ["restaurado"]) == 1
         and len(server.almacen.leer("fixture:%d" % _C8)[0]) == 16)
server.LIGAS["lib"]["sc"] = _LIB
server.fetch = _guardado


print("\n── el cuadro de las previas va aparte ──")
# Las eliminatorias para entrar al torneo son otro torneo: los que las ganan
# recién aparecen en la fase de grupos. Colgadas del cuadro grande daban
# ramas que no se conectan con nada.
def _pp(gid, etapa, slot, a, b, ga, gb, comp=596):
    return {"id": gid, "liveId": gid, "comp": comp, "temporada": 11,
            "stage": etapa, "slot": slot, "legNum": 1,
            "stageNum": -10 + server.rango_etapa(etapa),
            "start": "2026-07-10T16:00:00-03:00", "status": "FIN",
            "gh": ga, "ga": gb, "round": None, "zone": None, "interzonal": False,
            "home": {"name": a, "canon": a, "short": a[:3], "logo": None,
                     "pasa": ga > gb},
            "away": {"name": b, "canon": b, "short": b[:3], "logo": None,
                     "pasa": gb > ga}}
_juegos = [_pp(1, "Fase previa 2", 1, "Egnatia", "Lillestrom", 2, 0),
           _pp(2, "Fase previa 2", 2, "Thun", "Omonia", 1, 0),
           _pp(3, "Fase previa 3", 1, "Egnatia", "Thun", 3, 1),
           _pp(10, "Octavos de final", 1, "Benfica", "Aarhus", 2, 1, comp=573)]
_fx, _st, _gl = server.fixture_de_liga, server._sc_standings, server._sc_goleadores
server.fixture_de_liga = lambda cfg, ttl=120: _juegos
server._sc_standings = lambda comp, ttl=25: []
server._sc_goleadores = lambda comp, escudos=None: []
server.fetch = lambda p_, q, ttl=15: {"games": []}
_rl = server.api_liga_games({"id": ["europa"]})
_prev = [b["etapa"] for b in (_rl.get("llavesPrevia") or []) if b["llaves"]]
_prin = [b["etapa"] for b in (_rl.get("llaves") or []) if b["llaves"]]
chequear("las previas tienen su propio cuadro",
         _prev == ["Fase previa 2", "Fase previa 3"], _prev)
chequear("y no se cuelan en el del torneo",
         "Fase previa 2" not in _prin and "Octavos de final" in _prin, _prin)
chequear("un torneo sin previas no inventa la pestaña",
         "llavesPrevia" not in server.api_liga_games({"id": ["ca"]}))
server.fixture_de_liga, server._sc_standings, server._sc_goleadores = _fx, _st, _gl
server.fetch = _guardado
chequear("la pestaña Previa existe en la página",
         "['previa','Previa']" in HTML and "cuadroLlaves(S.llavesPrevia)" in HTML)


print("\n── qué es una previa y qué no ──")
# Una previa es la de una competencia declarada en sc_extra. Tomar
# "cualquier competencia que no sea la principal" hacía que a la
# Sudamericana le renombraran el pre octavos como "Fase previa 1".
def _sd(gid, etapa, comp):
    return {"id": gid, "liveId": gid, "comp": comp, "temporada": 30,
            "stage": etapa, "etapaFuente": etapa, "stageNum": 4, "round": None,
            "slot": 1, "start": "2026-08-05T21:30:00-03:00", "status": "FIN",
            "gh": 2, "ga": 0, "zone": None, "interzonal": False,
            "home": {"name": "Lanús", "canon": "Lanús", "short": "LAN",
                     "logo": None, "pasa": True},
            "away": {"name": "Cienciano", "canon": "Cienciano", "short": "CIE",
                     "logo": None, "pasa": False}}
_sf = server._sc_fixture
server._sc_fixture = lambda comp, ttl=120: (
    [_sd(1, "Pre octavos", 9999), _sd(2, "Fase de grupos", 389)] if comp == 389 else [])
_rs = server.fixture_de_liga(server.LIGAS["sud"])
chequear("el pre octavos de la Sudamericana no es previa",
         not any(m.get("previa") for m in _rs)
         and "Pre octavos" in {m["stage"] for m in _rs},
         sorted({m["stage"] for m in _rs}))
server._sc_fixture = lambda comp, ttl=120: (
    [dict(_sd(10, "Playoff", 332))] if comp == 332 else [])
_rc2 = server.fixture_de_liga(server.LIGAS["champions"])
chequear("la clasificación de la Champions sí lo es",
         _rc2 and _rc2[0].get("previa")
         and _rc2[0]["stage"] == "Repechaje de acceso")
server._sc_fixture = _sf


print("\n── una fase necesita varias fechas para tener pestaña ──")
import datetime as _dtt
def _bg(gid, ronda, etapa, sn, cuando):
    return {"id": gid, "liveId": gid, "comp": 25, "temporada": 118,
            "stage": etapa, "stageNum": sn, "round": ronda, "slot": None,
            "start": cuando.isoformat(), "status": "PROG", "gh": None, "ga": None,
            "zone": None, "interzonal": False,
            "home": {"name": "A%d" % gid, "canon": "A%d" % gid, "short": "A", "logo": None},
            "away": {"name": "B%d" % gid, "canon": "B%d" % gid, "short": "B", "logo": None}}
_ini = _dtt.datetime(2026, 8, 28, 15, 30)
_bund = [_bg(r * 10 + k, r, "", 1, _ini + _dtt.timedelta(days=7 * (r - 1)))
         for r in range(1, 35) for k in range(9)]
_bund += [_bg(900 + i, 35, "Descenso/Ascenso", 2, _dtt.datetime(2027, 5, 20 + i, 15, 30))
          for i in range(2)]
_fx2, _st2, _gl2 = server.fixture_de_liga, server._sc_standings, server._sc_goleadores
server.fixture_de_liga = lambda cfg, ttl=120: _bund
server._sc_standings = lambda comp, ttl=25: []
server._sc_goleadores = lambda comp, escudos=None: []
server.fetch = lambda p_, q, ttl=15: {"games": []}
_rb = server.api_liga_games({"id": ["bundesliga"]})
chequear("un repechaje de dos partidos no arma pestaña",
         _rb["fasesLiga"] == [], _rb["fasesLiga"])
chequear("y la liga abre en la fecha 1", _rb["current"] == 1, _rb["current"])
_fed = [_bg(r * 10 + k, r, "Primera Fase", 1,
            _dtt.datetime(2026, 3, 1) + _dtt.timedelta(days=7 * r))
        for r in range(1, 14) for k in range(9)]
_fed += [_bg(5000 + r * 10 + k, r, "Segunda Fase", 2,
             _dtt.datetime(2026, 7, 1) + _dtt.timedelta(days=7 * r))
         for r in range(1, 10) for k in range(9)]
server.fixture_de_liga = lambda cfg, ttl=120: _fed
chequear("dos fases de verdad sí lo hacen",
         len(server.api_liga_games({"id": ["fa"]})["fasesLiga"]) == 2)
server.fixture_de_liga, server._sc_standings, server._sc_goleadores = _fx2, _st2, _gl2
server.fetch = _guardado
chequear("la fase por defecto es la de la fecha en curso, no la última",
         "f.rounds.includes(S.current)" in HTML)


print("\n── el cursor se ancla en la fecha, no en el número ──")
# Los números de partido de 365scores no siguen el calendario: pidiendo los
# anteriores al 4728058 devuelve el 4728053 pero también el 4728065. Anclando
# en el número más chico el cursor no se movía y el recorrido moría en la
# primera vuelta — media Copa Argentina sin bajar.
import datetime as _dt3, random as _rnd
_C9 = 9640
server.almacen.guardar("temporada:%d" % _C9, 16)
server.almacen.guardar("migrado2:%d" % _C9, True)
server.almacen.guardar("reabierto:%d" % _C9, True)
server.almacen.guardar("hist:%d" % _C9, {})
_rnd.seed(5)
_ids = list(range(4648800, 4648860)); _rnd.shuffle(_ids)
_cuando = {i: _dt3.datetime(2026, 3, 1) + _dt3.timedelta(days=k * 3)
           for k, i in enumerate(_ids)}
_porFecha = sorted(_cuando, key=lambda i: _cuando[i])
server.almacen.guardar("fixture:%d" % _C9,
    [{"id": i, "comp": _C9, "temporada": 16, "round": None,
      "start": _cuando[i].isoformat(), "stage": "32avos de final"}
     for i in _porFecha[-19:]])
chequear("el borde por fecha no es el número más chico",
         server._borde(server.almacen.leer("fixture:%d" % _C9)[0], _C9, -1)
         != min(_porFecha[-19:]))
def _cr9(i):
    return {"id": i, "competitionId": _C9, "seasonNum": 16, "roundNum": None,
            "stageName": "32avos de final", "startTime": _cuando[i].isoformat(),
            "statusGroup": 4, "statusText": "Finalizado", "gameTime": 90,
            "homeCompetitor": {"id": 1, "name": "A", "score": 1},
            "awayCompetitor": {"id": 2, "name": "B", "score": 0}}
server.fetch_ruta = lambda r: {"games": [
    _cr9(i) for i in _porFecha[max(0, _porFecha.index(
        int(re.search(r"aftergame=(\d+)", r).group(1))) - 7):
        _porFecha.index(int(re.search(r"aftergame=(\d+)", r).group(1)))]],
    "paging": {}}
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C9, "currentSeasonNum": 16}]} if p == "competitions"
    else {"games": [], "paging": {}})
server.time.sleep = lambda s: None
_r9 = server.caminar_fixture(_C9, -1, paginas=30)
chequear("y con ese ancla el recorrido llega hasta el final",
         _r9["total"] == 60, _r9["total"])
server.fetch = _guardado


print("\n── enganchar el fixture de AFA con 365scores ──")
# Sin ese enganche un partido no se puede abrir: no hay goles, ni formaciones,
# ni canal. En la Primera Nacional las fechas 23 y 24 tenian seis de dieciocho
# porque los partidos se postergaron: AFA sigue publicando la fecha original
# y 365scores la real, y al no coincidir se rendia.
def _afa(gid, a, b, dia, ronda):
    return {"id": gid, "round": ronda,
            "start": (dia + "T15:00:00-03:00") if dia else None,
            "status": "FIN", "gh": 1, "ga": 0, "zone": None, "interzonal": False,
            "stage": "", "liveId": None, "venue": "",
            "home": {"name": a, "canon": a, "short": a[:3], "logo": None},
            "away": {"name": b, "canon": b, "short": b[:3], "logo": None}}
def _sc(gid, a, b, dia):
    return {"id": gid, "liveId": gid, "comp": 419, "temporada": 46,
            "start": (dia + "T15:00:00-03:00") if dia else None, "status": "FIN",
            "gh": 1, "ga": 0, "round": None, "stage": "", "zone": None,
            "interzonal": False,
            "home": {"name": a, "canon": a, "short": a[:3], "logo": None},
            "away": {"name": b, "canon": b, "short": b[:3], "logo": None}}
_dfg, _fxg = server.df_fixture_generico, server.fixture_de_liga
_stg, _glg = server._sc_standings, server._sc_goleadores
server._sc_standings = lambda comp, ttl=25: []
server._sc_goleadores = lambda comp, escudos=None: []
server.fetch = lambda p, q, ttl=15: {"games": []}
def _enganche(afas, scs):
    server.df_fixture_generico = lambda lid, _a=afas: [dict(g) for g in _a]
    server.fixture_de_liga = lambda cfg, ttl=120, _s=scs: _s
    return {m["id"]: m.get("liveId")
            for m in server.api_liga_games({"id": ["nacional"]})["games"]}
chequear("un partido postergado engancha con el mas cercano",
         _enganche([_afa(1, "Colon", "San Telmo", "2026-07-05", 23),
                    _afa(2, "Colon", "San Telmo", "2026-11-20", 34)],
                   [_sc(9001, "Colon", "San Telmo", "2026-07-12"),
                    _sc(9002, "Colon", "San Telmo", "2026-11-20")])
         == {1: 9001, 2: 9002})
chequear("y la otra rueda no se roba el de una fecha ajena",
         _enganche([_afa(1, "Colon", "San Telmo", "2026-07-05", 23),
                    _afa(2, "Colon", "San Telmo", "2026-11-20", 34)],
                   [_sc(9101, "Colon", "San Telmo", "2026-11-20")])
         == {1: None, 2: 9101})
chequear("sin fecha de un lado vale el unico candidato",
         _enganche([_afa(4, "Ferro", "All Boys", None, 23)],
                   [_sc(9004, "Ferro", "All Boys", "2026-07-05")]) == {4: 9004})
chequear("un partido de 365scores no se reparte entre dos",
         _enganche([_afa(5, "Ferro", "All Boys", "2026-07-05", 23),
                    _afa(6, "Ferro", "All Boys", "2026-07-06", 24)],
                   [_sc(9005, "Ferro", "All Boys", "2026-07-05")])
         == {5: 9005, 6: None})

# El marcador que AFA no cargo. La fecha 21 de la Primera Nacional quedo con
# nueve resultados de dieciocho, con los dieciocho jugados y enganchados.
def _marcador(afas, scs):
    server.df_fixture_generico = lambda lid, _a=afas: [dict(g) for g in _a]
    server.fixture_de_liga = lambda cfg, ttl=120, _s=scs: _s
    return {m["id"]: (m.get("gh"), m.get("ga"), m.get("status"))
            for m in server.api_liga_games({"id": ["nacional"]})["games"]}
_sinR = _afa(7, "Quilmes", "Atlanta", "2026-07-19", 21)
_sinR.update({"gh": None, "ga": None, "status": "PROG", "statusText": ""})
_con3 = _sc(9007, "Quilmes", "Atlanta", "2026-07-19"); _con3.update({"gh": 3, "ga": 1})
chequear("si AFA no cargo el resultado, lo completa 365scores",
         _marcador([_sinR], [_con3])[7] == (3, 1, "FIN"))
_yaR = _afa(8, "Quilmes", "Atlanta", "2026-07-19", 21)   # AFA dice 1-0
_otro = _sc(9008, "Quilmes", "Atlanta", "2026-07-19"); _otro.update({"gh": 5, "ga": 5})
chequear("pero un resultado de AFA no se pisa",
         _marcador([_yaR], [_otro])[8] == (1, 0, "FIN"))
_pend = _afa(9, "Quilmes", "Atlanta", "2026-09-19", 29)
_pend.update({"gh": None, "ga": None, "status": "PROG", "statusText": ""})
_nojug = _sc(9009, "Quilmes", "Atlanta", "2026-09-19")
_nojug.update({"gh": None, "ga": None, "status": "PROG"})
chequear("y un partido que no se jugo no se inventa",
         _marcador([_pend], [_nojug])[9] == (None, None, "PROG"))
server.df_fixture_generico, server.fixture_de_liga = _dfg, _fxg
server._sc_standings, server._sc_goleadores = _stg, _glg
server.fetch = _guardado


print("\n── las dos fases del Federal A ──")
# El Federal A juega una Primera Fase y una Segunda, y las dos empiezan en la
# fecha 1. 365scores manda los partidos sin nombre de fase, asi que las dos
# fechas 1 se sumaban en una sola: 34 partidos donde son 17.
_ZONA1 = ["Douglas Haig", "Sp. Belgrano", "Def. de Belgrano", "9 de Julio"]
_ZONA2 = ["Olimpo", "Villa Mitre", "Cipolletti", "Alvarado"]
_CRUCES = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]

def _fa(gid, a, b, dia, ronda, gh=1, ga=0):
    return {"id": gid, "round": ronda, "start": dia + "T15:30:00-03:00",
            "status": "FIN", "gh": gh, "ga": ga, "stage": "", "stageNum": 1,
            "slot": None, "zone": None, "interzonal": False, "liveId": gid,
            "venue": "", "minute": None, "statusText": "Finalizado",
            "home": {"name": a, "canon": a, "short": a[:3], "logo": None},
            "away": {"name": b, "canon": b, "short": b[:3], "logo": None}}

def _torneo_fa():
    """Primera Fase de marzo a mayo y Segunda en agosto, las dos desde la 1."""
    juegos, gid = [], 7000
    for ronda, (i, j) in enumerate(_CRUCES, 1):
        dia = "2026-03-%02d" % (7 + ronda * 3)          # marzo/abril
        for z in (_ZONA1, _ZONA2):
            juegos.append(_fa(gid, z[i], z[j], dia, ronda)); gid += 1
    for ronda, (i, j) in enumerate(_CRUCES[:3], 1):
        dia = "2026-08-%02d" % (1 + ronda * 7)          # agosto
        for z in (_ZONA1, _ZONA2):
            juegos.append(_fa(gid, z[i], z[j], dia, ronda)); gid += 1
    return juegos

_j = _torneo_fa()
_hubo = server.marcar_fases_por_calendario(_j, ["Primera Fase", "Segunda Fase"])
_deFase = {}
for _g in _j:
    _deFase.setdefault(_g["stage"], set()).add(_g["round"])
chequear("las dos fases se separan por el calendario", _hubo)
chequear("la Primera Fase se queda con sus seis fechas",
         _deFase.get("Primera Fase") == {1, 2, 3, 4, 5, 6}, _deFase)
chequear("y la Segunda con las tres suyas",
         _deFase.get("Segunda Fase") == {1, 2, 3}, _deFase)

# Un partido postergado se juega mucho despues pero sigue siendo de su fecha.
# Si alcanzara para abrir una fase, cada suspension inventaria una.
_post = _torneo_fa()
next(_g for _g in _post
     if _g["round"] == 2 and _g["start"].startswith("2026-03"))\
    ["start"] = "2026-05-10T15:30:00-03:00"
server.marcar_fases_por_calendario(_post, ["Primera Fase", "Segunda Fase"])
chequear("un postergado suelto no inventa una fase",
         next(g["stage"] for g in _post if g["start"].startswith("2026-05-10"))
         == "Primera Fase")
chequear("y las fases siguen siendo dos",
         {g["stage"] for g in _post} == {"Primera Fase", "Segunda Fase"})

# Las zonas salen de quien jugo contra quien: nadie cruza de grupo.
_zonas = server.zonas_por_rivales([g for g in _j if g["stage"] == "Primera Fase"])
chequear("cada zona sale de quienes se enfrentaron",
         len(set(_zonas.values())) == 2
         and len({_zonas[e] for e in _ZONA1}) == 1
         and len({_zonas[e] for e in _ZONA2}) == 1, _zonas)
_tab = server.tablas_por_resultados(
    [g for g in _j if g["stage"] == "Primera Fase"], "Primera Fase")
chequear("y la tabla se arma sin que la fuente mande el grupo",
         len(_tab) == 2 and all(len(t["rows"]) == 4 for t in _tab),
         [(t["name"], len(t["rows"])) for t in _tab])

# Cada zona reparte cosas distintas: en la Fase Campeonato se pelea el
# ascenso y en la Revalida, no descender. Pintarlas igual seria decir que
# el puntero de la Revalida asciende.
def _zona(nombre, n, pts=None):
    return {"name": nombre, "num": 1,
            "rows": [{"team": {"name": "%s%d" % (nombre[-1:], i)}, "pos": i,
                      "pts": (pts[i - 1] if pts else 30 - i),
                      "pj": 16, "gf": 0, "gc": 0, "dif": 0}
                     for i in range(1, n + 1)]}
#
# Ojo con el nombre: 365scores llama "Segunda Fase" a la de Campeonato, así
# que sus zonas quedan como "Segunda Fase - Zona A" y no dicen "Campeonato"
# por ningún lado. Con la regla atada a esa palabra no se pintaba nada y
# sólo aparecían los descensos, que son los únicos que sí dicen "Reválida".
_zs = [_zona("Primera Fase - Zona 1", 10), _zona("Primera Fase - Zona 2", 9),
       _zona("Segunda Fase - Zona A", 9),
       _zona("Segunda Fase - Campeonato B", 9),
       _zona("Segunda Fase - Reválida B", 10)]
server.marcar_destinos(_zs, server.LIGAS["fa"]["zonas_de"])
_dest = {z["name"]: [r["destino"] for r in z["rows"]] for z in _zs}
chequear("de una zona de diez pasan cinco",
         _dest["Primera Fase - Zona 1"][:5] == ["campeonato"] * 5
         and _dest["Primera Fase - Zona 1"][5:] == ["revalida"] * 5)
chequear("y de una de nueve, cuatro",
         _dest["Primera Fase - Zona 2"][:4] == ["campeonato"] * 4)
chequear("los que no pasan quedan marcados como Reválida",
         _dest["Primera Fase - Zona 2"][4:] == ["revalida"] * 5)
chequear("en la Segunda Fase los cuatro primeros van a la Tercera",
         _dest["Segunda Fase - Zona A"][:4] == ["tercera"] * 4)
chequear("el quinto suma la Copa Argentina",
         _dest["Segunda Fase - Zona A"][4] == "copaarg")
chequear("y del sexto al noveno, a la segunda etapa de la Reválida",
         _dest["Segunda Fase - Zona A"][5:] == ["revalida2"] * 4)
chequear("da igual que la zona diga 'Campeonato' o no",
         _dest["Segunda Fase - Campeonato B"] == _dest["Segunda Fase - Zona A"])
chequear("en la Reválida pasan los cinco primeros",
         _dest["Segunda Fase - Reválida B"][:5] == ["revalida2"] * 5)
chequear("y ahi no se marca ningun descenso: esa cuenta va aparte",
         "desciende" not in _dest["Segunda Fase - Reválida B"])

# El mejor quinto de las zonas de nueve tambien pasa. Es lo unico que no se
# puede decidir mirando una tabla sola: hay que comparar zonas entre si.
_nueves = [_zona("Primera Fase - Zona A", 9, [30, 28, 26, 24, 20, 9, 8, 7, 6]),
           _zona("Primera Fase - Zona B", 9, [30, 28, 26, 24, 23, 9, 8, 7, 6]),
           _zona("Primera Fase - Zona C", 9, [30, 28, 26, 24, 21, 9, 8, 7, 6])]
server.marcar_destinos(_nueves, server.LIGAS["fa"]["zonas_de"])
server.marcar_mejor_puesto(_nueves, server.LIGAS["fa"]["mejor_puesto"])
chequear("el mejor quinto de las zonas de nueve tambien pasa",
         {z["name"][-1:]: z["rows"][4]["destino"] for z in _nueves}
         == {"A": "revalida", "B": "campeonato", "C": "revalida"},
         {z["name"][-1:]: z["rows"][4]["destino"] for z in _nueves})
_diez = [_zona("Primera Fase - Zona 1", 10, [99] * 10)] + [
    _zona("Primera Fase - Zona A", 9, [30, 28, 26, 24, 20, 9, 8, 7, 6]),
    _zona("Primera Fase - Zona B", 9, [30, 28, 26, 24, 23, 9, 8, 7, 6])]
server.marcar_destinos(_diez, server.LIGAS["fa"]["zonas_de"])
server.marcar_mejor_puesto(_diez, server.LIGAS["fa"]["mejor_puesto"])
chequear("y el quinto de la zona de diez no le compite ese lugar",
         _diez[1]["rows"][4]["destino"] == "revalida"
         and _diez[2]["rows"][4]["destino"] == "campeonato",
         [z["rows"][4]["destino"] for z in _diez])
# El descenso no sale de ninguna tabla que se vea: se suma la Primera Fase
# con la Revalida. La Zona A se promedia por partido jugado y la B se suma
# derecho, asi que un mismo equipo puede salvarse en una y descender en la
# otra. Eso es lo que se prueba: que el criterio de cada zona sea el suyo.
def _revalida(letra, equipos):
    return {"name": "Segunda Fase - Reválida %s" % letra, "num": letra,
            "rows": [{"team": {"name": n}, "pos": i, "pts": p, "pj": j,
                      "gf": 0, "gc": 0, "dif": 0}
                     for i, (n, p, j) in enumerate(equipos, 1)]}
def _pf(gid, a, b, gh, ga):
    return {"id": gid, "round": 1, "start": "2026-04-11T15:30:00-03:00",
            "status": "FIN", "gh": gh, "ga": ga, "stage": "Primera Fase",
            "slot": None,
            "home": {"name": a, "canon": a}, "away": {"name": b, "canon": b}}
# Viejo hizo mas puntos pero en mas partidos; Nuevo jugo pocos y los gano.
# Por puntos va arriba Viejo (9 en 5 partidos), por promedio Nuevo (6 en 2).
_pfj = [_pf(1, "Viejo", "R1", 1, 0), _pf(2, "Viejo", "R2", 1, 0),
        _pf(3, "Viejo", "R3", 0, 0), _pf(4, "Viejo", "R4", 0, 0),
        _pf(5, "Viejo", "R5", 0, 0),
        _pf(6, "Nuevo", "R6", 1, 0), _pf(7, "Nuevo", "R7", 1, 0),
        _pf(8, "R7", "R8", 0, 1)]
_lista = [("Viejo", 0, 1), ("Nuevo", 0, 1), ("Otro1", 15, 1), ("Otro2", 15, 1)]
_rev = [_revalida("A", _lista), _revalida("B", _lista)]
_desc = server.tablas_de_descenso(_rev, _pfj, server.LIGAS["fa"]["descenso"])
chequear("se arma una tabla de descenso por cada zona de la Reválida",
         [z["name"] for z in _desc] == ["Descenso - Zona A", "Descenso - Zona B"],
         [z["name"] for z in _desc])
chequear("la Zona A se ordena por promedio",
         all("prom" in r for r in _desc[0]["rows"])
         and _desc[0]["rows"][2]["team"]["name"] == "Nuevo",
         [(r["team"]["name"], r.get("prom")) for r in _desc[0]["rows"]])
chequear("y la Zona B por puntos, sin promediar",
         all("prom" not in r for r in _desc[1]["rows"])
         and _desc[1]["rows"][2]["team"]["name"] == "Viejo",
         [(r["team"]["name"], r["pts"]) for r in _desc[1]["rows"]])
chequear("suma los puntos de la Primera Fase a los de la Reválida",
         {r["team"]["name"]: (r["pts"], r["pj"])
          for r in _desc[1]["rows"]}["Viejo"] == (9, 6),
         {r["team"]["name"]: (r["pts"], r["pj"]) for r in _desc[1]["rows"]})
server.marcar_destinos(_desc, server.LIGAS["fa"]["zonas_de"])
chequear("y descienden los dos ultimos de cada una",
         all([r["destino"] for r in z["rows"]][-2:] == ["desciende"] * 2
             for z in _desc),
         [[r["destino"] for r in z["rows"]] for z in _desc])

chequear("ninguna tabla queda sin destinos",
         all(any(r["destino"] for r in z["rows"]) for z in _zs),
         [z["name"] for z in _zs if not any(r["destino"] for r in z["rows"])])
# Los colores estaban escritos a mano en la pantalla y un destino nuevo nacia
# sin color: se marcaba en la tabla y no se veia nada.
_claves = {c for b in server.LIGAS["fa"]["zonas_de"] for c in b["reglas"]}
chequear("todo destino del Federal A tiene su color en la leyenda",
         _claves <= {x["clave"] for x in server.LEYENDA_DESTINOS},
         _claves - {x["clave"] for x in server.LEYENDA_DESTINOS})
_COLORES = set(re.findall(r"'(#[0-9a-f]{6})':\[", HTML))
chequear("y la pantalla sabe pintar ese color",
         {x["color"] for x in server.LEYENDA_DESTINOS
          if x["clave"] in _claves} <= _COLORES,
         {x["color"] for x in server.LEYENDA_DESTINOS
          if x["clave"] in _claves} - _COLORES)

# La Fase Campeonato y la Revalida se juegan a la vez: una sola pestana.
def _bloque(fase, grupo, equipos):
    return {"name": fase,
            "groups": [{"num": grupo, "name": "Zona %s" % grupo}],
            "rows": [{"competitor": {"id": i, "name": e}, "points": 0,
                      "gamePlayed": 0, "for": 0, "against": 0,
                      "groupNum": grupo}
                     for i, e in enumerate(equipos, 1)]}
server.fetch = lambda p, q, ttl=25: {"standings": [
    _bloque("Segunda Fase", "A", ["Olimpo", "Alvarado"]),
    _bloque("Reválida", "A", ["Germinal", "Sol de Mayo"])]}
_juntas = server._sc_standings(5078, juntar=server.LIGAS["fa"]["fases_juntas"])
chequear("Campeonato y Reválida quedan bajo el mismo titulo",
         all(z["name"].startswith("Segunda Fase - ") for z in _juntas),
         [z["name"] for z in _juntas])
chequear("pero no se funden en una sola tabla",
         len(_juntas) == 2 and all(len(z["rows"]) == 2 for z in _juntas))
chequear("y se sigue sabiendo cual es la Reválida",
         any("Reválida" in z["name"] for z in _juntas),
         [z["name"] for z in _juntas])
server.fetch = _guardado

# Y todo junto: la fecha 1 tiene que dejar de tener el doble de partidos.
_stg2, _glg2, _fxg2 = server._sc_standings, server._sc_goleadores, server.fixture_de_liga
server._sc_standings = lambda comp, ttl=25, juntar=None: []
server._sc_goleadores = lambda comp, escudos=None: []
server.fixture_de_liga = lambda cfg, ttl=120: [dict(g) for g in _torneo_fa()]
server.fetch = lambda p, q, ttl=15: {"games": []}
_r = server.api_liga_games({"id": ["fa"]})
_porFecha = {}
for _g in _r["games"]:
    _porFecha[_g["round"]] = _porFecha.get(_g["round"], 0) + 1
# La zona salia de en que tabla esta hoy cada equipo, y en la fase vieja los
# equipos ya estan repartidos de otra manera: casi toda la Primera Fase
# aparecia como "Interzonal", que es justo lo que no era.
chequear("ningun partido de la fase vieja queda como interzonal",
         not any(g["interzonal"] for g in _r["games"]),
         sum(1 for g in _r["games"] if g["interzonal"]))
chequear("y cada fase agrupa por sus propias zonas",
         len({g["zone"] for g in _r["games"] if g["round"] <= 6}) == 2,
         sorted({g["zone"] for g in _r["games"] if g["round"] <= 6}))

# La fase vieja tambien llega rotulada: con la zona donde esta HOY cada
# equipo, que no es la de entonces. Quedarse con ese rotulo ponia
# "Zona Reválida - A" arriba de una fecha de abril.
_marzo = _torneo_fa()
for _g in _marzo:                       # como si vinieran de las tablas de hoy
    _g["zone"] = "Reválida A" if _g["home"]["name"] in _ZONA1 else "Reválida B"
server.marcar_fases_por_calendario(_marzo, ["Primera Fase", "Segunda Fase"])
server.zonas_de_cada_fase(_marzo)
_vieja = {g["zone"] for g in _marzo if g["stage"] == "Primera Fase"}
chequear("la fase vieja no se queda con los rotulos de la de ahora",
         not any("Reválida" in z for z in _vieja), sorted(_vieja))
chequear("pero la fase que se juega si conserva los suyos",
         {g["zone"] for g in _marzo if g["stage"] == "Segunda Fase"}
         == {"Reválida A", "Reválida B"},
         sorted({g["zone"] for g in _marzo if g["stage"] == "Segunda Fase"}))
chequear("ninguna fecha queda con el doble de partidos",
         set(_porFecha.values()) == {2}, _porFecha)
chequear("las fechas de la Segunda Fase no pisan a las de la Primera",
         sorted(_porFecha) == list(range(1, 10)), sorted(_porFecha))
_fl = _r["fasesLiga"]
chequear("quedan las dos fases para elegir",
         [f["nombre"] for f in _fl] == ["Primera Fase", "Segunda Fase"],
         [f["nombre"] for f in _fl])
chequear("y cada una sabe desde que numero corre, para rotular su fecha 1",
         [f["desde"] for f in _fl] == [1, 7], [f.get("desde") for f in _fl])
chequear("la fecha que se abre es una de la fase que se esta jugando",
         _r["current"] in _fl[1]["rounds"], (_r["current"], _fl[1]["rounds"]))
server._sc_standings, server._sc_goleadores = _stg2, _glg2
server.fixture_de_liga = _fxg2
server.fetch = _guardado

chequear("sin desglose de goles no se muestran las columnas",
         not server.hay_desglose_de_goles(
             [{"name": "X", "goals": 7, "jugada": 0, "cabeza": 0,
               "tiroLibre": 0, "pens": 0}]))
chequear("con desglose si",
         server.hay_desglose_de_goles(
             [{"name": "X", "goals": 7, "jugada": 5, "cabeza": 2}]))


print("\n── un tramo de otra temporada en el medio no corta ──")
# El cursor de respaldo se anclaba en lo guardado. Si una pagina venia entera
# de otra temporada no se guardaba nada, el ancla no se movia y el cursor
# salia igual al anterior: el recorrido saltaba ese tramo. A la Primera
# Nacional le faltaban dos ventanas de dias enteras en el medio del torneo.
_C10 = 5419
_rndu.seed(3)
_idsH = list(range(4643000, 4643104)); _rndu.shuffle(_idsH)
_cuandoH = {i: _dtu.datetime(2026, 2, 1) + _dtu.timedelta(days=k * 2)
            for k, i in enumerate(_idsH)}
_ordenH = sorted(_cuandoH, key=lambda i: _cuandoH[i])
_viejaH = set(_ordenH[40:47]) | set(_ordenH[70:77])
def _crudoH(i):
    return {"id": i, "competitionId": _C10, "seasonNum": 45 if i in _viejaH else 46,
            "roundNum": None, "stageName": "", "startTime": _cuandoH[i].isoformat(),
            "statusGroup": 4, "statusText": "Finalizado", "gameTime": 90,
            "homeCompetitor": {"id": 1, "name": "A", "score": 1},
            "awayCompetitor": {"id": 2, "name": "B", "score": 0}}
for _k, _v in (("temporada:%d" % _C10, 46), ("migrado2:%d" % _C10, True),
               ("reabierto:%d" % _C10, True), ("hist:%d" % _C10, {})):
    server.almacen.guardar(_k, _v)
server.almacen.guardar("fixture:%d" % _C10,
    [{"id": i, "comp": _C10, "temporada": 46, "round": None,
      "start": _cuandoH[i].isoformat(), "stage": ""} for i in _ordenH[-7:]])
server.fetch = lambda p, q, ttl=15: (
    {"competitions": [{"id": _C10, "currentSeasonNum": 46}]} if p == "competitions"
    else {"games": [], "paging": {}})
server.fetch_ruta = lambda r: {"games": [
    _crudoH(i) for i in _ordenH[max(0, (_ordenH.index(
        int(re.search(r"aftergame=(\d+)", r).group(1)))
        if int(re.search(r"aftergame=(\d+)", r).group(1)) in _ordenH
        else len(_ordenH)) - 7):(_ordenH.index(
        int(re.search(r"aftergame=(\d+)", r).group(1)))
        if int(re.search(r"aftergame=(\d+)", r).group(1)) in _ordenH
        else len(_ordenH))]], "paging": {}}
server.time.sleep = lambda s: None
_rh2 = server.caminar_fixture(_C10, -1, paginas=40)
_deberia = len([i for i in _ordenH if i not in _viejaH])
chequear("atraviesa los tramos de otra temporada sin perder el medio",
         _rh2["total"] == _deberia, "%d de %d" % (_rh2["total"], _deberia))
server.fetch = _guardado


print("\n── partidazo del día ──")
server.api_annual = lambda q: {"rows": [
    {"team": {"name": "River Plate"}, "canon": "River Plate", "pos": 1},
    {"team": {"name": "Belgrano"}, "canon": "Belgrano", "pos": 4},
    {"team": {"name": "Huracán"}, "canon": "Huracán", "pos": 20}]}
def pj(gid, a, b, inter=False, pa=None, pb=None, ra=0, rb=0):
    return {"id": gid, "interzonal": inter,
            "home": {"name": a, "canon": a, "pais": pa, "rank": ra},
            "away": {"name": b, "canon": b, "pais": pb, "rank": rb}}
chequear("gana el interzonal que es clásico",
         server.partidazo_del_dia([{"liga": "lpf", "games": [
             pj(1, "River Plate", "Belgrano"),
             pj(2, "Boca Juniors", "River Plate", inter=True)]}]) == 2)
chequear("un interzonal que no es clásico no gana por serlo",
         server.partidazo_del_dia([{"liga": "lpf", "games": [
             pj(3, "Huracán", "Belgrano", inter=True),
             pj(4, "River Plate", "Huracán")]}]) == 4)
chequear("Belgrano-Talleres es clásico",
         server.es_clasico_ar("Belgrano", "Talleres (C)"))
chequear("Belgrano-River no", not server.es_clasico_ar("Belgrano", "River Plate"))


print("\n── gráfico y listas de jugadores ──")
random.seed(11)
BASE = {"goles": .35, "total remates": 2.4, "goles esperados": .3,
        "pases claves": 1.0, "regates": 1.4}
plantel = [("Delantero %02d" % i, 1.7 - i * .03) for i in range(40)]
for g in range(1, 8):
    server.anotar_jugadores("lpf", g, [
        {"n": n, "eq": "Club %d" % (i % 12), "p": "Centrodelantero",
         "r": round(6.2 * f, 2),
         "v": {k: round(x * f * random.uniform(.92, 1.08), 3)
               for k, x in BASE.items()}}
        for i, (n, f) in enumerate(plantel)])
rad = server.radar_jugador("lpf", "Delantero 25")
chequear("el delantero se compara contra delanteros", rad["grupo"] == "delantero")
coinciden = True
for e in rad["ejes"]:
    t = server.ranking_jugadores("lpf", "delantero", e["eje"])
    mia = next(f for f in t["filas"] if f["name"] == "Delantero 25")
    if (e["puesto"], e["de"]) != (mia["pos"], t["total"]):
        coinciden = False
chequear("el puesto del gráfico y el de la lista son el mismo", coinciden)
chequear("un arquero no recibe ejes de delantero",
         "Goles" not in [e["eje"] for e in server.EJES_JUGADOR["arquero"]])
chequear("Volante central se reconoce como volante",
         server.grupo_puesto("Volante central") == "volante")
chequear("Lateral izquierdo, como defensor",
         server.grupo_puesto("Lateral izquierdo") == "defensor")
chequear("un jugador sin datos devuelve None, no rompe",
         server.radar_jugador("lpf", "Fulanito") is None)


print("\n── buscador ──")
r = server.api_buscar({"q": ["velez"]})
chequear("buscar 'velez' encuentra a Vélez",
         r["clubes"] and r["clubes"][0]["name"] == "Vélez Sarsfield")
chequear("buscar 'delantero 2' encuentra jugadores",
         bool(server.api_buscar({"q": ["delantero 2"]})["jugadores"]))
chequear("una sola letra no busca nada",
         server.api_buscar({"q": ["v"]})["clubes"] == [])


print("\n── el club que juega es el que juega ──")
# En una copa internacional hay clubes que se llaman igual: Nacional es el de
# Uruguay y tambien el de Potosi, y hay una Universidad Catolica en Chile y
# otra en Ecuador. El calendario de 365scores trae el escudo y el nombre de
# cada partido; ir igual a la tabla de posiciones a emparejar por nombre los
# cambiaba por los del otro club.
chequear("'juniors' no alcanza para confundir dos clubes",
         server.emparejar("Argentinos Juniors", {"boca juniors": 1}) is None,
         server.emparejar("Argentinos Juniors", {"boca juniors": 1}))
chequear("pero el club sigue apareciendo cuando de verdad es el mismo",
         server.emparejar("Argentinos Jrs", {"argentinos juniors": 1})
         == "argentinos juniors")
chequear("y Boca no deja de ser Boca",
         server.emparejar("Boca Jrs", {"boca juniors": 1, "argentinos juniors": 1})
         == "boca juniors")

def _cop(gid, a, b, la, lb):
    return {"id": gid, "liveId": gid, "comp": 102, "temporada": 69, "round": 2,
            "start": "2026-03-04T21:30:00-03:00", "status": "FIN",
            "gh": 1, "ga": 0, "stage": "Segunda Fase", "stageNum": 2,
            "slot": 1, "zone": None, "interzonal": False,
            "home": {"name": a, "canon": a, "short": a[:3], "logo": la},
            "away": {"name": b, "canon": b, "short": b[:3], "logo": lb}}
_stg3, _glg3, _fxg3 = server._sc_standings, server._sc_goleadores, server.fixture_de_liga
# En la tabla estan los de Uruguay y Chile; en la previa juegan los otros dos.
server._sc_standings = lambda comp, ttl=25, juntar=None: [
    {"name": "Grupo A", "num": 1, "rows": [
        {"team": {"name": "Nacional", "short": "NAC", "logo": "uruguay.png",
                  "site": None}, "pos": 1, "pts": 9, "pj": 3},
        {"team": {"name": "Universidad Católica", "short": "UCA",
                  "logo": "chile.png", "site": None}, "pos": 2, "pts": 6, "pj": 3}]}]
server._sc_goleadores = lambda comp, escudos=None: []
server.fixture_de_liga = lambda cfg, ttl=120: [
    _cop(1, "Nacional Potosí", "Universidad Católica", "potosi.png", "ecuador.png")]
server.fetch = lambda p, q, ttl=15: {"games": []}
_g = server.api_liga_games({"id": ["lib"]})["games"][0]
chequear("el escudo del partido no lo pisa el de un club homónimo",
         (_g["home"]["logo"], _g["away"]["logo"]) == ("potosi.png", "ecuador.png"),
         (_g["home"]["logo"], _g["away"]["logo"]))
chequear("ni el nombre",
         (_g["home"]["name"], _g["away"]["name"])
         == ("Nacional Potosí", "Universidad Católica"),
         (_g["home"]["name"], _g["away"]["name"]))
server._sc_standings, server._sc_goleadores = _stg3, _glg3
server.fixture_de_liga = _fxg3
server.fetch = _guardado


print("\n── una edición que ya terminó no es la de ahora ──")
# 365scores tarda en mover el numero de temporada entre una edicion y la
# otra. En agosto seguia diciendo que la Europa League corria la 61, la que
# termino en mayo, y la pagina mostraba esa fase de liga con su tabla como si
# fuera la de ahora.
_CE = 573
_hoy = _dtu.date.today()
def _vieja(gid, dias):
    d = _hoy - _dtu.timedelta(days=dias)
    return {"id": gid, "comp": _CE, "temporada": 61, "round": 5,
            "start": d.isoformat() + "T16:00:00-03:00", "status": "FIN",
            "gh": 1, "ga": 0, "stage": "Fase de liga", "slot": None,
            "home": {"name": "A", "canon": "A"}, "away": {"name": "B", "canon": "B"}}
def _clasi(gid, dias):
    d = _hoy - _dtu.timedelta(days=dias)
    return {"id": gid, "comp": 596, "temporada": 11, "round": 1,
            "start": d.isoformat() + "T16:00:00-03:00", "status": "FIN",
            "gh": 2, "ga": 1, "stage": "Primera Ronda", "slot": None,
            "home": {"name": "C", "canon": "C"}, "away": {"name": "D", "canon": "D"}}

def _servido(juegos, temporadas):
    server.almacen.guardar("fixture:%d" % _CE, juegos)
    for molde in ("hist:%d", "fut:%d"):
        server.almacen.guardar(molde % _CE, {"listo": True, "v": server.VERSION_RECORRIDO})
    for c, t in temporadas.items():
        server.almacen.guardar("temporada:%d" % c, t)
    server.almacen.guardar("migrado2:%d" % _CE, True)
    server.almacen.guardar("reabierto:%d" % _CE, True)
    server.fetch = lambda p, q, ttl=15: {"games": [], "competitions": []}
    return server._sc_fixture(_CE, ttl=0)

_r = _servido([_vieja(1, 100), _vieja(2, 95), _clasi(3, 10), _clasi(4, 8)],
              {573: 61, 596: 11})
chequear("la edición terminada no se muestra",
         not any(m["id"] in (1, 2) for m in _r), [m["id"] for m in _r])
chequear("pero la clasificación que se está jugando sí",
         {m["id"] for m in _r} == {3, 4}, [m["id"] for m in _r])
chequear("y nada de eso se borra de la base",
         len(server.almacen.leer("fixture:%d" % _CE)[0]) == 4)
# La tabla es tan vieja como el calendario: tambien tiene que irse.
_stg4 = server._sc_standings
server._sc_standings = lambda comp, ttl=25, juntar=None: [
    {"name": "Fase de liga", "num": 1,
     "rows": [{"team": {"name": "Lyon"}, "pos": 1, "pts": 21, "pj": 8}]}]
_liga = server.api_liga({"id": ["europa"]})
chequear("la tabla de la edición terminada tampoco se muestra",
         _liga["zonas"] == [], _liga["zonas"])
chequear("y se dice por qué, en vez de dejar el panel vacío",
         "todavía no empezó" in (_liga.get("zonasNota") or ""),
         _liga.get("zonasNota"))
server._sc_standings = _stg4

# Sin nada mas nuevo guardado, la ultima edicion se sigue mostrando: si no,
# la Copa Argentina desapareceria cada enero hasta que arranque la siguiente.
_r2 = _servido([_vieja(1, 100), _vieja(2, 95)], {573: 61})
chequear("si no hay nada más nuevo, la última edición se sigue mostrando",
         len(_r2) == 2, [m["id"] for m in _r2])
# Y una edicion en curso no se toca ni aunque le falten fechas por jugar.
_enCurso = [_vieja(1, 100), _vieja(2, 95), _clasi(3, 10)]
_enCurso[1]["status"] = "PROG"
_r3 = _servido(_enCurso, {573: 61, 596: 11})
chequear("una edición con partidos por jugar no se da por terminada",
         {m["id"] for m in _r3} == {1, 2, 3}, [m["id"] for m in _r3])
server.fetch = _guardado


print("\n── las dos copas de Conmebol ──")
import inspect
# La clasificacion previa de la Sudamericana se juega a partido unico: son
# dieciseis partidos sueltos, no un cuadro. Dibujarlos como llaves
# encadenadas es inventar un camino que no existe.
chequear("la Sudamericana no arma cuadro de previa",
         server.LIGAS["sud"].get("sin_cuadro_previa") is True)
chequear("pero la Libertadores sí, que la juega a ida y vuelta",
         not server.LIGAS["lib"].get("sin_cuadro_previa"))
chequear("el cuadro de previa se saltea cuando la liga lo pide",
         "if previas and not cfg.get(\"sin_cuadro_previa\"):"
         in inspect.getsource(server.api_liga_games))
# El tercero de cada grupo de la Libertadores no queda afuera: se va a los
# pre octavos de la Sudamericana.
_grupo = [{"name": "Grupo A", "num": 1,
           "rows": [{"team": {"name": "E%d" % i}, "pos": i} for i in range(1, 5)]}]
server.marcar_destinos(_grupo, server.LIGAS["lib"]["zonas_de"])
chequear("en los grupos de la Libertadores se marca al tercero",
         [r["destino"] for r in _grupo[0]["rows"]]
         == ["avanza", "avanza", "sudamericana", ""],
         [r["destino"] for r in _grupo[0]["rows"]])
chequear("y ese destino tiene color en la leyenda",
         "sudamericana" in {x["clave"] for x in server.LEYENDA_DESTINOS})
chequear("que la pantalla sabe pintar",
         next(x["color"] for x in server.LEYENDA_DESTINOS
              if x["clave"] == "sudamericana") in _COLORES)


print("\n── el pop-up ──")
# De un partido se entra a un jugador y de una serie a un partido. Esto
# llevaba su propia pila de por dónde se pasó; ahora la pila es el historial
# del navegador, porque cada pantalla tiene su dirección. El "‹" del pop-up y
# la flecha de atrás del navegador tienen que hacer lo mismo.
chequear("volver es ir para atrás en el historial",
         "volverModal(){" in HTML and "history.back()" in HTML
         and "S.pila" not in HTML)
chequear("y si se entró directo por el link, lleva a la pantalla de abajo",
         "else Rutas.ir(S.fondo||{t:'home'});" in HTML)
chequear("cerrar un pop-up con dirección propia también vuelve",
         "if(S.modal) return api.volverModal();" in HTML)
chequear("el botón de volver aparece sólo si hay a dónde volver",
         "const botonesModal=()=>`${S.pasos>0" in HTML)
# Las fichas que son también página escriben `${comoPagina?'':botonesModal()}`:
# de página no llevan cruz ni "‹", porque para eso está el navegador.
chequear("ninguna cruz quedó suelta fuera del botón compartido",
         'class="x" onclick="App.closeModal()">×' not in HTML
         and HTML.count("botonesModal()}") >= 5)
# El encabezado no se pega con `sticky` sino que se arma en tres piezas y el
# unico que se desplaza es el cuerpo. Con sticky se declaraba fijo y no lo
# era: la cancha de las formaciones se le asomaba por arriba.
chequear("el pop-up se arma en tres piezas y sólo se desplaza el cuerpo",
         "display:flex;flex-direction:column;max-height:calc(100vh - 52px)" in HTML
         and ".mhead{background:var(--nav);color:#fff;padding:16px;flex:none}" in HTML
         and ".modal>.tabs{flex:none" in HTML)
chequear("el cuerpo se deja achicar, si no el scroll se lo lleva la página",
         ".mbody{padding:14px;min-height:0;flex:1;overflow-y:auto" in HTML)
# El pop-up no se sostiene con sticky sino con el flex de tres piezas: se
# declaraba fijo y no lo era, y la cancha de las formaciones se le asomaba
# por arriba. La página del partido sí usa sticky, pero es otra cosa —no
# tiene alto máximo, se desplaza con la página— y por eso ahí sí funciona.
_STICKY = [l for l in HTML.splitlines() if "position:sticky" in l
           and "/*" not in l and "position:sticky de todo" not in l]
chequear("el pop-up sigue sin depender de sticky",
         not any(".modal" in l or l.strip().startswith(".mhead")
                 or l.strip().startswith(".mbody") for l in _STICKY),
         _STICKY)
chequear("y lo único que se fija en el partido es su página",
         sum(1 for l in _STICKY if ".ficha-pagina" in l) == 2, _STICKY)
# La barra lateral arrancaba catorce pixeles mas abajo que las otras dos
# columnas: el encabezado mide 56 sin la barrita de estado y 84 con ella, y
# el tope estaba clavado en 84.
chequear("la barra lateral arranca a la misma altura que las otras columnas",
         "top:calc(var(--enc,56px) + 14px)" in HTML
         and "setProperty('--enc'" in HTML)
chequear("y se mueve por su cuenta sin arrastrar la página",
         "overscroll-behavior:contain" in HTML
         and "max-height:calc(100vh - var(--enc,56px) - 28px)" in HTML)
chequear("la cruz es un botón redondo y no un signo suelto",
         ".mhead .x,.mhead .volver{width:32px;height:32px" in HTML)
chequear("y el fondo de atrás es más oscuro",
         "background:rgba(6,9,18,.80)" in HTML)


print("\n── el grito de gol ──")
# Apagado de fabrica, y el sonido se cambia dejando un archivo: nadie deberia
# tener que tocar el codigo para cambiar un mp3.
chequear("viene apagado de fábrica",
         "localStorage.getItem(CLAVE)==='1'" in HTML
         and "let activo=false" in HTML)
chequear("y queda prendido entre visitas",
         "localStorage.setItem(CLAVE,activo?'1':'0')" in HTML)
# Un relato tiene entrada y bajada: lo que sirve para un aviso es el grito
# del medio. Los dos numeros van juntos y arriba para poder cambiarlos.
chequear("del archivo se reproduce sólo el pedazo que sirve",
         "const DESDE=4, HASTA=12, ESFUMA=.35" in HTML
         and "s.start(0,desde,dura)" in HTML)
chequear("y un archivo más corto de lo pedido no rompe nada",
         "const desde=p.duration>DESDE?DESDE:0;" in HTML
         and "Math.max(.2,Math.min(HASTA,p.duration)-desde)" in HTML)
chequear("el final se baja en vez de cortarse seco",
         "linearRampToValueAtTime(.0001,t+dura)" in HTML)
chequear("suena el archivo si está, y si no el propio",
         "const CLAVE='hayvar.gol', ARCHIVO='/sonidos/gol.mp3'" in HTML
         and "if(p){" in HTML and "} else propio();" in HTML)
# Los navegadores no dejan sonar nada hasta que la persona toca algo, asi que
# el interruptor tiene que sonar en el mismo clic que lo activa.
chequear("el interruptor destraba el audio en el mismo clic",
         "if(activo) await sonar();" in HTML)
chequear("y el gol lo dispara el mismo contador que ya existía",
         "if(goles) Gol.gritar();" in HTML)
chequear("el botón está en la barra de arriba",
         'id="golBtn" onclick="App.sonido()"' in HTML)


print("\n── el celular ──")
# Todo esto va adentro del @media del celular: la pantalla grande no se toca.
_MOVIL = HTML[HTML.index("@media(max-width:900px)"):
              HTML.index("@media(max-width:400px)")]
# La altura de cada renglon del cuadro estaba clavada en 22px y la caja se
# achica con el zoom: en 2x la caja mide 38 y los dos renglones 44, y en 3x
# mide 30 contra los mismos 44. El nombre quedaba cortado por la mitad.
chequear("el renglón del cuadro no tiene la altura clavada",
         "height:22px" not in _MOVIL and "--fila" in HTML)
chequear("y en el celular las cajas no se achican tanto con el zoom",
         "{an:112,alto:44,hueco:8, sep:20,corto:true}" in HTML
         and "{an:94, alto:40,hueco:6, sep:16,corto:true}" in HTML)
chequear("la letra del cuadro nunca baja de 10.5 en el celular",
         "(nivel===2?10.5:nivel===1?11:11.5)" in HTML)
chequear("las dos formaciones van una al lado de la otra",
         ".xi{grid-template-columns:1fr 1fr" in _MOVIL)
chequear("y el porcentaje del gráfico se va contra el margen",
         ".cmp-vals{display:grid;grid-template-columns:auto 1fr auto" in _MOVIL)
_ESCRITORIO = HTML[:HTML.index("@media(max-width:1180px)")]
chequear("la versión de escritorio queda como estaba",
         ".xi{display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:12px}"
         in _ESCRITORIO
         and ".cmp-vals{display:flex;align-items:baseline;gap:9px" in _ESCRITORIO)


print("\n── pantalla ──")
chequear("el escudo sólo lleva al club donde corresponde",
         "DONDE_SE_ENTRA='#modalBox, table, .carrera, .cl-plantel'" in HTML)
chequear("no quedó el cursor de mano en toda la página",
         re.search(r"^\[data-club\]\{cursor:pointer\}", HTML, re.M) is None)
chequear("el radar comprime la escala arriba del promedio",
         "0.25+x/100*0.75" in HTML)
chequear("el resumen del partido va del final para atrás",
         ".slice().reverse()" in HTML)
chequear("Champions y Europa están en Internacional",
         "['champions','Champions League',1],['europa','Europa League',1]" in HTML)
import inspect
chequear("el precalentado recorre todas las ligas",
         "HOME_LIGAS" in inspect.getsource(server.precalentar))

# El cuadro de la clasificacion previa no parte al medio: tres llaves, despues
# ocho, despues cuatro. Deducir el tamano dividiendo daba 4, 2 y 1.
chequear("el cuadro toma el tamaño de las llaves cuando el nombre no lo dice",
         "porNombre(b.etapa)||porDatos(b)" in HTML)
chequear("y encadena por equipo cuando no es una escalera",
         "const hijoDe=" in HTML and "hijoDe[c][i]" in HTML)
chequear("la línea sale hacia el cruce que dice el encadenado",
         "const destino=hijoDe[c][i];" in HTML)
chequear("el cuadro cuelga de la última ronda, no de la más ancha",
         "const base=cupos.length-1;" in HTML)
chequear("y dos cruces que caen a la misma altura se separan",
         "fila[i]<piso+paso" in HTML)
# Si los cruces de la derecha estan mas juntos que el lugar que necesitan sus
# llaves, la de abajo de un grupo cae encima de la de arriba del siguiente y
# el corrimiento se arrastra hacia abajo de a un renglon por grupo. Eso
# descolocaba la Previa 1 y 2 de la Champions.
chequear("si las llaves no entran, se estira el cuadro en vez de amontonarlo",
         "const factor=cuantas*paso/juntos;" in HTML)
# Repartir cada ronda pareja a lo alto queda prolijo y equivocado: los cruces
# terminan lejos de las llaves que los alimentan. Que queden espacios en
# blanco es preferible; el blanco dice la verdad y la prolijidad, no.
chequear("y no se reparte pareja ignorando de dónde viene cada cruce",
         "const H=Math.max(...cupos)*paso;" not in HTML)
# Las dos llaves que se juntan en un mismo cruce tienen que quedar pegadas.
# En la Previa 1 de la Champions quedaban separadas por una tercera que va a
# otro lado, y las tres lineas se cruzaban.
chequear("las llaves que van al mismo cruce quedan juntas",
         "const donde=new Map();" in HTML
         and "pa[0]-pb[0]||pa[1]-pb[1]||a-b" in HTML)
chequear("y la cuenta de 'uno a uno' sólo se usa donde el cuadro parte al medio",
         "if(escalera) for(let c=slots.length-2;c>=0;c--){" in HTML)
# La Copa Argentina se juega a partido unico: abrir "la serie" de un partido
# solo es un rodeo, muestra una pantalla intermedia para llegar al mismo lado.
chequear("una llave de un solo partido abre el partido, no la serie",
         "const solo=k.partidos.length===1?k.partidos[0]:null;" in HTML
         and "const r=solo?rutaPartido(solo):rutaSerie(k);" in HTML)
# Los cuartos se sortean cuando terminan los octavos: la etapa existe antes
# de tener partidos, y ahi lo que uno quiere ver es quienes van clasificando.
chequear("la etapa de una copa aparece aunque todavía no tenga partidos",
         'if cfg.get("copa") and etapas:' in
         inspect.getsource(server.api_liga_games))
# Estas copas no sortean: el cuadro esta armado de entrada, asi que los
# cruces de la ronda que viene ya se saben. Se emparejan por numero de llave
# y no por posicion en la lista: si falta alguna, se correria todo el cuadro.
chequear("los cruces de la etapa que viene se arman solos",
         "for(let s=1;s+1<=tope;s+=2)" in HTML and "porSlot[k.slot]=k" in HTML)
_CON_FINAL = ("lib", "sud", "ca", "champions", "europa")
chequear("y la final trae fecha y sede aunque no tenga equipos",
         all(server.LIGAS[x].get("final", {}).get("cuando") for x in _CON_FINAL),
         {x: server.LIGAS[x].get("final") for x in _CON_FINAL})
# La fase de liga no cruza a nadie: son 36 equipos en una tabla. Lo que se
# puede mostrar antes del sorteo son los que vienen ganando la clasificacion.
chequear("en una fase de liga se muestran los que entraron, no cruces",
         "const esTabla=etapa&&/grupo|liga/i.test(etapa);" in HTML
         and "Entraron desde la clasificación" in HTML)
# La fase de liga se sortea en agosto: hasta entonces la etapa no existe para
# la fuente y el boton no aparecia, justo la semana en que uno quiere mirar
# quien se va metiendo.
chequear("la fase de liga está en la lista de etapas de Champions y Europa",
         all("Fase de liga" in server.LIGAS[x]["etapas_extra"]
             for x in ("champions", "europa")))
chequear("y va antes que los octavos",
         all(server.LIGAS[x]["etapas_extra"]
             == sorted(server.LIGAS[x]["etapas_extra"], key=server.rango_etapa)
             for x in ("champions", "europa")))
chequear("la de la Copa Argentina dice que la cancha no está confirmada",
         server.LIGAS["ca"]["final"]["sede"] is None
         and "no se confirmó" in server.LIGAS["ca"]["final"]["nota"])
chequear("y la fecha no se corre un día por la zona horaria",
         "const d=new Date(+p[0],+p[1]-1,+p[2]);" in HTML)
chequear("cuando no hay tabla se dice por qué en vez de 'Sin datos'",
         "const sinTabla=()=>" in HTML and "d.zonasNota" in HTML)
chequear("y no se pone 'Por definir' donde no va a haber cruce",
         re.search(r"if\(escalera\)\s*\n\s*cajas\+=`<div class=\"brk vacia\"", HTML)
         is not None)
# En una copa lo que uno abre es el cuadro, pero el orden de las pestañas
# sigue el del torneo: previa, grupos y recién ahí el cuadro.
chequear("las pestañas van previa, grupos y cuadro",
         HTML.index("hayPrevia?[['previa','Previa']]")
         < HTML.index("hayCuadro?[['cuadro','Cuadro']]:[]),\n                ...(d.conAnual"))
chequear("pero una copa se abre en el cuadro",
         "S.tab=hayCuadro?'cuadro':faseQueSeJuega(tabs);" in HTML)


print("\n── el radar compara contra los que están jugando ──")
# El índice de estadísticas guarda los últimos quinientos partidos de la
# competencia y eso pasa de largo la temporada: quedan adentro los que se
# fueron al descenso, y cualquier nombre que no reconocemos entra como si
# fuera un club más. Así se llegaba a "48º de 53" en un torneo de treinta.
_EJE = server.EJES_RADAR[0]["eje"]
_CLAVE = server.EJES_RADAR[0]["claves"][0]


def _partido(gid, local, visita, vl, vv):
    server.almacen.guardar("stats:radar:%s" % gid,
                           {"h": {"eq": local, "v": {_CLAVE: vl}, "gf": 1, "gc": 0},
                            "a": {"eq": visita, "v": {_CLAVE: vv}, "gf": 0, "gc": 1}})


_hoy = ["Belgrano", "Boca Juniors", "River Plate", "Racing", "Talleres (C)"]
_ids = []
for _i in range(4):                     # dos partidos por club, que es el mínimo
    for _a, _b in ((0, 1), (2, 3)):
        _partido(9000 + len(_ids), _hoy[_a], _hoy[_b], 10 + _i, 8 + _i)
        _ids.append(str(9000 + len(_ids)))
for _i in range(2):                     # y un par de intrusos
    _partido(9500 + _i, "Belgrano", "Equipo Que Ya No Juega", 10, 40)
    _ids.append(str(9500 + _i))
    _partido(9600 + _i, "Talleres (C)", "Otro Fantasma", 10, 40)
    _ids.append(str(9600 + _i))
server.almacen.guardar("statsidx:radar", _ids)

_libre = server.radar_promedio("radar", "Belgrano")
_acotado = server.radar_promedio("radar", "Belgrano", set(server.COLORES))
chequear("sin lista se cuelan los que no son de la liga",
         _libre and _libre["clubes"] > 4, _libre and _libre["clubes"])
chequear("con la lista se compara sólo contra ésos",
         _acotado and _acotado["clubes"] == len(_hoy),
         _acotado and _acotado["clubes"])
# Y no es sólo el puesto: el promedio de la liga también se ensuciaba,
# porque los intrusos entraban a la cuenta.
chequear("y el promedio de la liga también deja de contarlos",
         _acotado["ejes"][0]["liga"] < _libre["ejes"][0]["liga"],
         (_libre["ejes"][0]["liga"], _acotado["ejes"][0]["liga"]))
_SRV = open(os.path.join(AQUI, "server.py"), encoding="utf-8").read()
chequear("la ficha del club pasa los treinta de Primera",
         "radar_promedio(\"lpf\", canon, set(COLORES) | {canon},\n"
         "                                del_torneo())" in _SRV)

# Y el otro filtro: sólo los partidos del torneo que se está jugando. El
# Apertura se juega con otro plantel y a veces con otro técnico, así que
# mezclarlo con el Clausura da un promedio que no es de nadie.
_del_torneo = set(_ids[:8])            # los del round robin, sin los intrusos
_torneo = server.radar_promedio("radar", "Belgrano", set(server.COLORES),
                                _del_torneo)
chequear("se puede acotar a los partidos de un solo torneo",
         _torneo and _torneo["partidos"] == 4, _torneo and _torneo["partidos"])
chequear("y el resto del historial sigue guardado",
         len(server.almacen.leer("statsidx:radar")[0]) == len(_ids))
chequear("si el torneo todavía no tiene nada cargado, no se inventa",
         server.radar_promedio("radar", "Belgrano", None, {"999999"}) is None)
chequear("y el gráfico dice de qué torneo habla",
         _torneo["torneo"] is None and _libre["torneo"] is None
         and "r.torneo?'del '+esc(r.torneo)" in HTML)


print("\n── el caché de memoria se mide en bytes ──")
# Contar respuestas era contar peras: la tabla de posiciones ocupa dos kilos
# y una página del fixture de una copa puede ocupar cinco megas. Con
# trescientas entradas permitidas, el proceso se comía la memoria del
# hosting y lo reiniciaban.
server._cache.clear()
server._cache_bytes = 0
server._guardar_en_cache("chico", {"a": 1}, 2 * 1024)
chequear("una respuesta chica entra", "chico" in server._cache)
server._guardar_en_cache("enorme", {"a": 1}, 5 * 1024 * 1024)
chequear("y una de cinco megas no", "enorme" not in server._cache)
for _i in range(60):
    server._guardar_en_cache("u%d" % _i, {"a": _i}, 200 * 1024)
chequear("el total nunca pasa el tope",
         server._cache_bytes <= server._CACHE_MAX_BYTES,
         server._cache_bytes)
chequear("y lo que se descarta es lo más viejo",
         "u59" in server._cache and "u0" not in server._cache)
chequear("la cuenta de bytes coincide con lo guardado",
         server._cache_bytes == sum(v[2] for v in server._cache.values()),
         (server._cache_bytes, sum(v[2] for v in server._cache.values())))
server._cache.clear(); server._cache_bytes = 0

# Y el que llama sin decir el tamaño también tiene que andar. Esto no es
# teórico: al cambiar la firma de esta función quedaron rotas las cuatro
# llamadas de AFA y la página mostró el error en pantalla durante horas.
# La prueba anterior no lo agarró porque llamaba a la función directo, con
# todos los argumentos. Así que además de probarla, se revisan todas las
# llamadas que hay en el archivo.
server._guardar_en_cache("sinTamano", {"a": 1})
chequear("se puede guardar sin decir cuánto ocupa",
         "sinTamano" in server._cache and server._cache_bytes > 0)

import ast as _ast, inspect as _insp
_arbol = _ast.parse(_SRV)
_firma = _insp.signature(server._guardar_en_cache)
_minimo = sum(1 for p in _firma.parameters.values() if p.default is p.empty)
_malas = [n.lineno for n in _ast.walk(_arbol)
          if isinstance(n, _ast.Call) and getattr(n.func, "id", "")
          == "_guardar_en_cache" and len(n.args) < _minimo]
chequear("y todas las llamadas del archivo le pasan lo que pide",
         not _malas, _malas)
server._cache.clear(); server._cache_bytes = 0

# Recorrer el calendario entero es lo caro. Una vez al día, alcanza con
# mirarlo de vez en cuando.
chequear("el rescate deja de recorrer el calendario cuando está al día",
         "recorrer = (not historia_al_dia) or vuelta % 8 == 0" in _SRV)


print("\n── las estadísticas se juntan solas ──")
# El promedio no puede depender de que alguien abra los partidos a mano: si
# nadie entra, la base no se llena y el gráfico queda a medias para siempre.
_juegos = [{"status": "FIN", "liveId": 7001},
           {"status": "FIN", "liveId": 7002},
           {"status": "SOON", "liveId": 7003},     # todavía no se jugó
           {"status": "FIN", "liveId": None}]      # sin id no se puede pedir
server.almacen.guardar("stats:lpf:7001", {"h": {"gf": 1}, "a": {"gf": 0}})
server.almacen.guardar("jug:lpf:7001", {})
_abiertos = []
_all_real, _match_real = server.all_games, server.api_match
server.all_games = lambda ttl=25: _juegos
server.api_match = lambda q: _abiertos.append(q["id"][0])
_hechos = server.juntar_stats("lpf", limite=15)
server.all_games, server.api_match = _all_real, _match_real
chequear("va a buscar los partidos terminados que no tienen estadísticas",
         _abiertos == ["7002"], _abiertos)
chequear("y no vuelve a pedir los que ya están", _hechos == 1, _hechos)
# Puesto al día, el recolector no se corta: sigue durmiendo y volviendo.
# La rama puede hacer algo antes de dormir —ahí es donde completa las
# formaciones viejas— pero tiene que terminar en el sueño de siempre.
_rama = _SRV.split("if not pendientes and not goles_pendientes:")[1]
_rama = _rama.split("elif not pendientes:")[0]
chequear("el rescate no se va cuando se pone al día",
         "Historia completa: no queda nada por traer" not in _SRV
         and _rama.rstrip().endswith("time.sleep(900)"), _rama.rstrip()[-40:])


print("\n── la bandera del plantel ──")
# Treinta jugadores no pueden ser treinta pedidos. La fuente acepta varios
# atletas en la misma dirección, así que van todos juntos; y se guarda por
# jugador, que es lo que no cambia cuando cambia de club.
_pedidos = []
_falso_atletas = {"athletes": [
    {"id": 111, "nationalityName": "Argentina", "nationalityId": 10},
    {"id": 222, "nationalityName": "Uruguay", "nationalityId": 15},
    {"id": 333, "nationalityName": "Colombia", "nationalityId": 26},
]}
_fetch_real = server.fetch
server.fetch = lambda path, params, ttl=15: (
    _pedidos.append(params) or _falso_atletas)
_n1 = server.nacionalidades([111, 222, 333])
chequear("el plantel entero se pide de una vez", len(_pedidos) == 1, _pedidos)
chequear("y en el mismo pedido van todos los jugadores",
         sorted(_pedidos[0]["athletes"].split(",")) == ["111", "222", "333"],
         _pedidos)
chequear("cada uno vuelve con su país y su bandera",
         _n1["222"]["pais"] == "Uruguay" and "Countries/Round/15"
         in _n1["222"]["bandera"], _n1.get("222"))
_pedidos.clear()
server.nacionalidades([111, 222, 333])
chequear("y no se vuelve a pedir lo que ya está guardado", not _pedidos, _pedidos)
server.fetch = lambda path, params, ttl=15: (_ for _ in ()).throw(OSError("caída"))
chequear("si la fuente se cae, el plantel sigue saliendo",
         server.nacionalidades([444]) == {})
server.fetch = _fetch_real
chequear("y en la página va la bandera y no el contador de titularidades",
         'class="pais"' in HTML and "tit.</span>" not in HTML)


print("\n── los goles de la lista no se congelan a mitad del partido ──")
# El error: alcanzaba con que hubiera *algo* guardado para no volver a
# pedirlo nunca. Un partido leído a los cuarenta minutos quedaba con los
# goles de ese momento, y uno leído antes de empezar quedaba sin ninguno.
# Olimpia 1-4 Vasco se mostró toda la noche sin goles en la lista mientras
# la ficha del partido —que pide el detalle por otro lado— los tenía todos.
_p_vivo = {"liveId": 8101, "status": "LIVE", "gh": 1, "ga": 0}
_p_fin = {"liveId": 8102, "status": "FIN", "gh": 1, "ga": 4}
_p_por_jugar = {"liveId": 8103, "status": "SOON", "gh": None, "ga": None}

server.anotar_goles("cp", 8101, [{"player": "Uno", "min": 20, "side": "h"}], False)
chequear("un partido en juego se vuelve a pedir siempre",
         server.detalle_al_dia("cp", _p_vivo)[2] is False)

# leído antes de empezar: cero goles y el partido termina 1-4
server.anotar_goles("cp", 8102, [], False)
chequear("lo leído antes del pitazo inicial no se da por bueno",
         server.detalle_al_dia("cp", _p_fin)[2] is False)

# ahora sí, ya terminado
server.anotar_goles("cp", 8102, [
    {"player": "Matus", "min": 15, "side": "h"},
    {"player": "Mendes", "min": 29, "side": "a"},
    {"player": "David", "min": 36, "side": "a"},
    {"player": "Adson", "min": 70, "side": "a"},
    {"player": "Spinelli", "min": 84, "side": "a"},
    {"player": "Sandoval", "min": 79, "side": "h", "anulado": True},
], True)
_lista, _tv, _listo = server.detalle_al_dia("cp", _p_fin)
chequear("una vez terminado queda como definitivo", _listo is True)
chequear("y están los cinco goles, sin el anulado",
         len(_lista) == 5, len(_lista))

# El caso que hay que dejar cerrado: si la fuente nunca dice quién hizo un
# gol, el partido no puede quedar pidiéndose para siempre. Se lee una vez
# más y queda marcado, aunque la cuenta no cierre.
server.anotar_goles("cp", 8104, [{"player": "", "min": 30, "side": "h"}], True)
chequear("un partido incompleto pero ya releído no se pide de nuevo",
         server.detalle_al_dia("cp", {"liveId": 8104, "status": "FIN",
                                     "gh": 2, "ga": 0})[2] is True)
chequear("el gol sin autor se guarda igual, con el minuto",
         server.leer_goles("cp", 8104)[0] == [{"j": "", "e": "", "m": 30,
                                               "s": "h"}],
         server.leer_goles("cp", 8104)[0])

# lo guardado con el formato viejo —una lista pelada— se sigue entendiendo
server.almacen.guardar("goles:cp:8105", [{"j": "Viejo", "m": 10, "s": "h"}])
chequear("lo guardado antes se sigue leyendo",
         server.leer_goles("cp", 8105)[0][0]["j"] == "Viejo")
chequear("y si la cantidad coincide con el resultado se da por bueno",
         server.detalle_al_dia("cp", {"liveId": 8105, "status": "FIN",
                                     "gh": 1, "ga": 0})[2] is True)
chequear("pero si faltan goles se vuelve a pedir",
         server.detalle_al_dia("cp", {"liveId": 8105, "status": "FIN",
                                     "gh": 3, "ga": 1})[2] is False)
# El que todavía no empezó: mientras no tengamos el canal se sigue
# mirando, y una vez que lo tenemos se deja en paz. Éste es el error que
# dejó a los tres partidos del lunes sin canal en pantalla.
_p_por_jugar["start"] = (_dtu.datetime.now(_dtu.timezone.utc)
                         + _dtu.timedelta(hours=3)).isoformat()
server.anotar_goles("cp", 8103, [], False)
chequear("sin canal, un partido que ya viene se sigue mirando",
         server.detalle_al_dia("cp", _p_por_jugar)[2] is False)
server.almacen.guardar("tv:cp:8103", ["TNT Sports"])
chequear("y con el canal ya guardado se deja de preguntar",
         server.detalle_al_dia("cp", _p_por_jugar)[2] is True)
_lejos = dict(_p_por_jugar, liveId=8107,
              start=(_dtu.datetime.now(_dtu.timezone.utc)
                     + _dtu.timedelta(days=5)).isoformat())
server.anotar_goles("cp", 8107, [], False)
chequear("pero si falta una semana no se molesta a la fuente todavía",
         server.detalle_al_dia("cp", _lejos)[2] is True)

# La tabla de goleadores propia no puede contar los goles sin autor.
server.almacen.guardar("golesidx:cp", ["8102", "8104"])
_tabla = server.goleadores_propios("cp")
chequear("la tabla de goleadores ignora los goles sin autor",
         len(_tabla) == 5 and all(r["name"] for r in _tabla),
         [r["name"] for r in _tabla])

# Y el rescate de fondo tiene que ir a buscar justamente esos.
_j2 = [{"status": "FIN", "liveId": 8102},      # definitivo
       {"status": "FIN", "liveId": 8105},      # formato viejo, completo
       {"status": "FIN", "liveId": 8106}]      # nunca leído
_j2[1].update(gh=1, ga=0); _j2[0].update(gh=1, ga=4); _j2[2].update(gh=0, ga=0)
_pedidos2 = []
_lg_real, _det_real = server.api_liga_games, server.detalle_liviano
server.api_liga_games = lambda q: {"games": _j2}
server.detalle_liviano = lambda gid, **kw: _pedidos2.append(gid)
server.LIGAS["cp"] = {"nombre": "de prueba"}
server.juntar_goles("cp", limite=10)
server.api_liga_games, server.detalle_liviano = _lg_real, _det_real
del server.LIGAS["cp"]
chequear("el rescate sólo va a buscar lo que falta",
         _pedidos2 == [8106], _pedidos2)

# La otra mitad del error estaba en la caché: el detalle se guardaba doce
# horas, así que el intento de arreglarlo volvía a caer en la misma foto.
chequear("el detalle del partido ya no se cachea doce horas",
         "ttl = 30 if en_juego else 300" in _SRV)
chequear("y la lista mira si lo guardado está al día, no si existe",
         "guardado, tv, listo = detalle_al_dia(x, g)" in _SRV
         and 'guardado, _ = almacen.leer("goles:%s:%s"' not in _SRV)
# Y la prueba de verdad: la lista de partidos, entera. Es la que reproduce
# lo que se vio en pantalla el jueves.
server.anotar_goles("lpf", 8201, [{"player": "Arrascaeta", "min": 35,
                                   "side": "h"}], False)
server.anotar_goles("lpf", 8202, [{"player": "Conechny", "min": 4,
                                   "side": "h"}], True)
_lista_j = [{"id": "A", "liveId": 8201, "status": "FIN", "gh": 2, "ga": 1,
             "start": "2026-08-19T21:30:00-03:00"},
            {"id": "B", "liveId": 8202, "status": "FIN", "gh": 1, "ga": 0,
             "start": "2026-08-19T19:15:00-03:00"}]
_releidos = []
_all_real3, _det_real3 = server.all_games, server.detalle_liviano
server.all_games = lambda ttl=25: _lista_j
server.detalle_liviano = lambda gid, **kw: (_releidos.append(gid)
                                            or {"tv": [], "goles": [],
                                                "penales": None})
_res = server.api_detalles({"id": ["lpf"]})
server.all_games, server.detalle_liviano = _all_real3, _det_real3
chequear("el 2-1 con un solo gol guardado se vuelve a pedir",
         _releidos == [8201], _releidos)
chequear("y el 1-0 que ya estaba completo se sirve de la base",
         len(_res["detalles"]["B"]["goles"]) == 1
         and _res["detalles"]["B"]["goles"][0]["player"] == "Conechny",
         _res["detalles"].get("B"))

chequear("el gol sin autor se muestra como el minuto solo",
         HTML.count("quien?quien+' ':''") + HTML.count("q?q+' ':''") == 2,
         HTML.count("quien?quien+' ':''") + HTML.count("q?q+' ':''"))


print("\n── cada cosa tiene su dirección ──")
# El servidor y la página tienen que estar de acuerdo en cómo se llama cada
# torneo en la dirección. Están escritos dos veces —la página necesita leer
# la dirección antes de hablar con el servidor— así que esto es lo que
# impide que se separen sin que nadie se entere.
_m = re.search(r"const LIGA_RUTA=\{(.*?)\};", HTML, re.S)
_pagina = dict(re.findall(r"(\w+):'([a-z0-9-]+)'", _m.group(1) if _m else ""))
chequear("el servidor y la página nombran igual a cada torneo",
         _pagina == {v: k for k, v in server.RUTAS_LIGA.items()},
         set(_pagina.items()) ^ set((v, k) for k, v in server.RUTAS_LIGA.items()))
chequear("y no falta ninguno de los que existen",
         set(server.RUTAS_LIGA.values()) == set(server.LIGAS),
         set(server.RUTAS_LIGA.values()) ^ set(server.LIGAS))

# El servidor devuelve la página para todas las direcciones nuestras y para
# ninguna otra. Si dijera que sí a cualquier cosa, un archivo que falta
# devolvería la página entera con código 200 en vez de un 404.
_nuestras = ["/", "/liga-profesional", "/liga-profesional/fecha-5",
             "/libertadores/llave/river-vs-boca",
             "/partido/aldosivi-vs-union-4728056",
             "/jugador/enzo-fernandez-8167", "/belgrano", "/estudiantes-lp"]
_ajenas = ["/favicon.svg", "/no-existe", "/liga-profesional/cualquiera",
           "/partido", "/partido/a/b", "/jugador", "/partido/sin-numero"]
chequear("todas las direcciones nuestras devuelven la página",
         all(server._titulo_de_ruta(r) for r in _nuestras),
         [r for r in _nuestras if not server._titulo_de_ruta(r)])
chequear("y las que no son nuestras siguen siendo un archivo o un 404",
         not any(server._titulo_de_ruta(r) for r in _ajenas),
         [r for r in _ajenas if server._titulo_de_ruta(r)])
chequear("el título dice qué se está mirando",
         server._titulo_de_ruta("/partido/olimpia-vs-vasco-da-gama-4798160")[0]
         == "Olimpia vs Vasco Da Gama — HAYVAR",
         server._titulo_de_ruta("/partido/olimpia-vs-vasco-da-gama-4798160"))
chequear("y el de un club usa su nombre de verdad, con paréntesis y todo",
         server._titulo_de_ruta("/estudiantes-lp")[0].startswith("Estudiantes (LP)"))

# La dirección la escribe el visitante: no puede entrar cruda en el HTML.
_veneno = '/partido/x" onmouseover="alert(1)-9'
chequear("lo que viene de la dirección se escapa antes de escribirlo",
         '"' not in server.escapar(server._titulo_de_ruta(_veneno)[0]),
         server.escapar(server._titulo_de_ruta(_veneno)[0]))
chequear("y el bloque que reemplaza está marcado en la página",
         "<!--CABEZA-->" in HTML and "<!--/CABEZA-->" in HTML)

# Tener direcciones y no decirle a Google cuáles son sería la mitad del
# trabajo. Van los torneos y los clubes; los partidos no, que son miles y
# cambian todas las fechas.
chequear("hay mapa del sitio y aviso para los buscadores",
         '"/sitemap.xml", "/robots.txt"' in _SRV
         and "Sitemap: %s/sitemap.xml" in _SRV)
chequear("y el mapa lleva todos los torneos y todos los clubes",
         '["/"] + ["/" + s for s in RUTAS_LIGA]' in _SRV
         and '["/" + s for s in sorted(RUTAS_CLUB)]' in _SRV)

# Enlaces de verdad, que es lo que permite abrir en una pestaña nueva. Si
# alguno vuelve a ser un div con onclick, ctrl+clic deja de funcionar ahí y
# nadie se da cuenta hasta que lo prueba.
chequear("la fila de un partido es un enlace",
         "const abre=r ? ` href=\"${esc(Rutas.url(r))}\" data-ir`" in HTML)
chequear("los torneos del menú son enlaces",
         'href="${esc(Rutas.url(id===\'home\'?{t:\'home\'}:{t:\'liga\',id}))}" data-ir' in HTML)
chequear("y los jugadores también",
         "const enlaceJugador=(nombre,atletaId,equipo,clase,estilo)=>" in HTML
         and HTML.count("data-ir") >= 12, HTML.count("data-ir"))
chequear("el clic con ctrl, con command o con el del medio no se ataja",
         "e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey" in HTML)
chequear("y el enlace no queda azul y subrayado adentro de la tabla",
         "a.match,a.brk,a.serie-p{display:block;color:inherit;text-decoration:none}" in HTML)

# El que llega por el link no tiene nada atrás, así que el partido no es un
# pop-up sobre nada: es una página, con el menú a la izquierda y la tabla
# del torneo a la derecha.
chequear("lo que decide es si hay algo atrás, no si tenemos el partido a mano",
         "const comoPagina=!S.fondo;" in HTML)
# La ficha no lleva la barra de fechas: no es una fecha, es un partido. La
# lista de modos que la saltean puede crecer —las secciones del torneo
# tampoco la llevan— pero la ficha tiene que seguir estando.
chequear("como página usa el armazón de tres columnas del resto del sitio",
         "shell(false,'ficha'); drawSide();" in HTML
         and "quiere==='club'||quiere==='ficha'" in HTML
         and "quiere==='ficha'\n            /* El partido no va adentro" in HTML)
chequear("y el mismo dibujante sirve para el pop-up y para la página",
         "let mTab='res', mData=null, mBase=null, dondeVaLaFicha='#modalBox';" in HTML
         and "$(dondeVaLaFicha).innerHTML=`" in HTML)
# Uno baja a leer los goles y el marcador se le iba de pantalla, que es
# justo el dato que quiere tener a la vista todo el tiempo.
# El marcador no se fijaba, y el motivo no era la regla de sticky sino que
# .card tiene overflow:hidden, que se lo anula a todo lo que tenga adentro.
# Por eso el partido no va adentro de una caja: se arma la suya.
chequear("el partido no va adentro de .card, que anularía el fijado",
         ".card{" in HTML and "overflow:hidden" in HTML
         and "? `<div class=\"ficha-pagina\" id=\"matches\"></div>`" in HTML
         and ".ficha-pagina{background:var(--card)" in HTML)
chequear("el marcador y las pestañas quedan fijos al desplazarse",
         ".ficha-pagina > .mhead{position:sticky;top:var(--enc,56px)" in HTML
         and ".ficha-pagina > .tabs{position:sticky" in HTML)
# La altura del marcador no es fija: cambia con el minuto en un partido en
# curso y en el celular es otra. Se mide en vez de clavar un número.
chequear("y las pestañas se pegan a la altura de verdad del marcador",
         "top:calc(var(--enc,56px) + var(--cab,118px))" in HTML
         and "function medirCabecera()" in HTML
         and "new ResizeObserver(poner)" in HTML)

# La ficha de un jugador abierta por el link llega sin el nombre: sólo con
# el slug. El servidor tiene que poder devolver el nombre bien escrito.
server.almacen.guardar("jugidx:lpf", None)
_real = server._nombre_de_slug("no-existe-nadie", "lpf")
chequear("un slug desconocido igual sirve para buscar",
         server.norm(_real) == "no existe nadie", _real)
# Y se lee como un nombre: "enzo fernandez" en el título de una ficha
# parece un error de la página, no el nombre de una persona.
chequear("y se escribe con las iniciales en mayúscula",
         _real == "No Existe Nadie"
         and server._nombre_de_slug("enzo-fernandez", "lpf") == "Enzo Fernandez",
         _real)
chequear("y api_atleta acepta el slug de la dirección",
         "slug = (q.get(\"slug\") or [\"\"])[0].strip()" in _SRV)

# El enrutador de la página se prueba corriéndolo de verdad, no mirando el
# texto. Se saca el bloque tal cual está en index.html y se lo hace leer y
# escribir cada dirección: leer y volver a escribir tiene que devolver lo
# mismo, porque si no, entrar por un link y después tocar algo te cambiaría
# la dirección sin motivo.
import shutil as _sh, subprocess as _sub, tempfile as _tmp
_DOMSITO = os.path.join(AQUI, "_domsito.js")
if _sh.which("node") and os.path.exists(_DOMSITO):
    _i = HTML.index("  const LIGA_RUTA=")
    _j = HTML.index("  /* La única puerta de entrada")
    _casos = ["/", "/liga-profesional", "/liga-profesional/fecha-5",
              "/libertadores/llave/river-plate-vs-boca-juniors",
              "/partido/aldosivi-vs-union-4728056",
              "/jugador/enzo-fernandez-8167", "/jugador/di-maria",
              "/belgrano", "/estudiantes-lp"]
    _guion = HTML[_i:_j] + ("""
const casos=%s, salida=[];
for(const c of casos){ const d=Rutas.leer(c); salida.push(d?Rutas.url(d):null); }
salida.push(Rutas.leer('/no/es/nuestra'), Rutas.leer('/partido/sin-numero'));
salida.push(slugTexto("Newell's Old Boys"), slugTexto("Estudiantes (LP)"));
console.log(JSON.stringify(salida));
""" % json.dumps(_casos))
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_guion); _ruta = _f.name
    _r = _sub.run(["node", _ruta], capture_output=True, text=True,
                     timeout=60)
    os.unlink(_ruta)
    _out = json.loads(_r.stdout) if _r.returncode == 0 else None
    chequear("el enrutador de la página corre", _out is not None, _r.stderr[:200])
    if _out:
        chequear("leer una dirección y volver a escribirla da la misma",
                 _out[:len(_casos)] == _casos,
                 [(a, b) for a, b in zip(_casos, _out) if a != b])
        chequear("y una dirección que no es nuestra no se la traga",
                 _out[len(_casos)] is None and _out[len(_casos) + 1] is None,
                 _out[len(_casos):len(_casos) + 2])
        chequear("el slug de la página es el mismo que el del servidor",
                 [_out[-2], _out[-1]]
                 == [server._slug("Newell's Old Boys"),
                     server._slug("Estudiantes (LP)")],
                 [_out[-2], _out[-1]])
    # Y todas las direcciones que la página sabe escribir, el servidor las
    # tiene que reconocer. Si no, abrir una en una pestaña nueva daría 404.
    chequear("todo lo que la página escribe, el servidor lo entiende",
             all(server._titulo_de_ruta(u) for u in _casos if u),
             [u for u in _casos if not server._titulo_de_ruta(u)])

    # Lo anterior prueba las dos funciones sueltas. Esto prueba el paseo
    # entero: se carga la página en un DOM de mentira y se la hace navegar
    # como navegaría una persona, mirando qué dice la dirección en cada
    # paso y si el botón de atrás la deja donde corresponde. Es lo único
    # que agarra un error de cableado entre `aplicar`, `Rutas.ir` y
    # `popstate`, que es donde puede romperse esto sin que se note.
    _app = re.sub(r"^App\.init\(\);$", "", HTML.split("<script>")[-1]
                  .split("</script>")[0], flags=re.M)
    _paseo = """
const salida=[];
const paso=q=>salida.push([q, loc.pathname]);
paso('arranque');
App.liga('lpf');                            paso('entra a un torneo');
App.pick(7);                                paso('cambia de fecha');
App.liga('lib');                            paso('entra a otro torneo');
historial.back();                           paso('atrás');
historial.back();                           paso('atrás');
App.club('Estudiantes (LP)');               paso('entra a un club');
App.player('Enzo Fernández','River',8167);  paso('abre un jugador');
historial.back();                           paso('atrás');
console.log(JSON.stringify(salida));
"""
    _guion2 = (open(_DOMSITO, encoding="utf-8").read()
               + "\nglobalThis.document=doc; globalThis.window=win;"
                 "\nglobalThis.location=loc; globalThis.history=historial;"
                 "\nglobalThis.localStorage=almacenLocal;"
                 "\nglobalThis.MutationObserver=MutationObserver;"
                 "\nglobalThis.URL=URL2; globalThis.fetch=fetchFalso;"
                 "\nglobalThis.requestAnimationFrame=f=>0;"
                 "\nglobalThis.setTimeout=(f,t)=>0; globalThis.clearTimeout=()=>{};"
                 "\nglobalThis.setInterval=()=>0; globalThis.clearInterval=()=>{};"
                 "\nlet App;\n"
               + _app.replace("const App=(()=>{", "App=(()=>{") + _paseo)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_guion2); _ruta2 = _f.name
    _r2 = _sub.run(["node", _ruta2], capture_output=True, text=True,
                     timeout=60)
    os.unlink(_ruta2)
    _paso = json.loads(_r2.stdout) if _r2.returncode == 0 else None
    chequear("la página entera arranca y se puede navegar",
             _paso is not None, _r2.stderr.strip().splitlines()[:3])
    if _paso:
        _esperado = [
            ["arranque", "/"],
            ["entra a un torneo", "/liga-profesional"],
            ["cambia de fecha", "/liga-profesional/fecha-7"],
            ["entra a otro torneo", "/libertadores"],
            ["atrás", "/liga-profesional/fecha-7"],
            ["atrás", "/liga-profesional"],
            ["entra a un club", "/estudiantes-lp"],
            ["abre un jugador", "/jugador/enzo-fernandez-8167"],
            ["atrás", "/estudiantes-lp"],
        ]
        chequear("la dirección acompaña a cada paso, y el atrás también",
                 _paso == _esperado,
                 [(a, b) for a, b in zip(_esperado, _paso) if a != b])

    # El otro camino: el que llega por el link, sin nada atrás. El partido
    # tiene que ocupar la página, y cerrarlo tiene que llevarlo a la
    # portada en vez de sacarlo del sitio.
    def _correr(js_extra):
        _g = (open(_DOMSITO, encoding="utf-8").read()
              + "\nglobalThis.document=doc; globalThis.window=win;"
                "\nglobalThis.location=loc; globalThis.history=historial;"
                "\nglobalThis.localStorage=almacenLocal;"
                "\nglobalThis.MutationObserver=MutationObserver;"
                "\nglobalThis.URL=URL2; globalThis.fetch=fetchFalso;"
                "\nglobalThis.requestAnimationFrame=f=>0;"
                "\nglobalThis.setTimeout=(f,t)=>0; globalThis.clearTimeout=()=>{};"
                 "\nglobalThis.setInterval=()=>0; globalThis.clearInterval=()=>{};"
                "\nprocess.on('unhandledRejection',()=>{});\nlet App;\n"
              + _app.replace("const App=(()=>{", "App=(()=>{") + js_extra)
        with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as _h:
            _h.write(_g); _p = _h.name
        _s = _sub.run(["node", _p], capture_output=True, text=True,
                     timeout=60)
        os.unlink(_p)
        return json.loads(_s.stdout) if _s.returncode == 0 and _s.stdout else None

    _frio = _correr("""
loc.pathname='/partido/olimpia-vs-vasco-4798160';
App.init();
// como página, el partido va en la columna del medio y el pop-up
// queda sin usar; y el menú del costado tiene que estar dibujado
const salida={enLaPagina: (doc.querySelector('#matches').innerHTML||'').includes('mhead'),
              enElPopUp:  (doc.querySelector('#modalBox').innerHTML||'').includes('mhead'),
              hayMenu:    (doc.querySelector('#side').innerHTML||'').includes('Liga Profesional')};
App.closeModal();
salida.alCerrar=loc.pathname;
console.log(JSON.stringify(salida));
""")
    chequear("entrando por el link, el partido se dibuja como página",
             _frio and _frio["enLaPagina"] and not _frio["enElPopUp"], _frio)
    chequear("y con el menú del sitio al costado",
             _frio and _frio["hayMenu"], _frio)
    chequear("cerrarlo lleva a la portada, no fuera del sitio",
             _frio and _frio["alCerrar"] == "/", _frio)

    # Lo que de verdad demuestra que el recorte no rompió nada: hacer
    # navegar la versión aligerada y comprobar que da paso por paso lo
    # mismo que la original. Sintaxis válida no alcanza —un texto mal
    # cortado puede compilar y hacer otra cosa—.
    _sin = re.sub(r"^App\.init\(\);$", "",
                  server.aligerar(HTML).split("<script>")[-1]
                  .split("</script>")[0], flags=re.M)
    _guion3 = (open(_DOMSITO, encoding="utf-8").read()
               + "\nglobalThis.document=doc; globalThis.window=win;"
                 "\nglobalThis.location=loc; globalThis.history=historial;"
                 "\nglobalThis.localStorage=almacenLocal;"
                 "\nglobalThis.MutationObserver=MutationObserver;"
                 "\nglobalThis.URL=URL2; globalThis.fetch=fetchFalso;"
                 "\nglobalThis.requestAnimationFrame=f=>0;"
                 "\nglobalThis.setTimeout=(f,t)=>0; globalThis.clearTimeout=()=>{};"
                 "\nglobalThis.setInterval=()=>0; globalThis.clearInterval=()=>{};"
                 "\nprocess.on('unhandledRejection',()=>{});\nlet App;\n"
               + _sin.replace("const App=(()=>{", "App=(()=>{") + _paseo)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_guion3); _ruta3 = _f.name
    _r3 = _sub.run(["node", _ruta3], capture_output=True, text=True,
                     timeout=60)
    os.unlink(_ruta3)
    _sinpaso = json.loads(_r3.stdout) if _r3.returncode == 0 else None
    chequear("la página sin comentarios navega igual que la original",
             _sinpaso == _paso, (_r3.stderr.strip().splitlines()[:2]
                                 if _sinpaso is None else _sinpaso))

    _tibio = _correr("""
loc.pathname='/liga-profesional';
App.init();
App.S.games=[{id:'a', liveId:4798160, home:{name:'Olimpia'}, away:{name:'Vasco'},
          status:'FIN', gh:1, ga:4}];
App.openMatch('a');
console.log(JSON.stringify({ruta:loc.pathname,
  enElPopUp: (doc.querySelector('#modalBox').innerHTML||'').includes('mhead')}));
""")
    chequear("y desde adentro el mismo partido es un pop-up, no la página",
             _tibio and _tibio["ruta"] == "/partido/olimpia-vs-vasco-4798160"
             and _tibio["enElPopUp"], _tibio)
else:
    print("  · sin node: el enrutador de la página no se probó")


print("\n── que no tarde ──")
# "La página está lenta" no se arregla adivinando. Estas tres son las que
# cambian de verdad cuánto se espera.
server._TIEMPOS.clear()
server.anotar_tiempo("/api/x", 120.0, 4096)
server.anotar_tiempo("/api/x", 80.0, 2048)
_t = server.api_tiempos({})["rutas"][0]
chequear("se anota cuánto tarda cada ruta",
         _t["veces"] == 2 and _t["promedio_ms"] == 100 and _t["peor_ms"] == 120,
         _t)
chequear("y se puede ver qué está haciendo el recolector de fondo",
         "fondo" in server.api_tiempos({}))
server._TIEMPOS.clear()

# Lo que más se nota: la página pesa 85 KB comprimida y se mandaba entera en
# cada visita, porque se pedía revalidar sin dar con qué comparar.
chequear("la página lleva etiqueta, para que el navegador no la baje dos veces",
         'etiqueta = \'"%s-%x"\' % (int(marca), len(body))' in _SRV
         and 'If-None-Match' in _SRV and "self.send_response(304)" in _SRV)
chequear("y se guarda ya armada en vez de releerla y recomprimirla",
         "_PAGINAS[(path, gz)] = (marca, body, enc)" in _SRV
         and "if hecha and hecha[0] == marca:" in _SRV)

# El error que casi seguro estaba frenando el sitio: un gol pendiente hacía
# que el recolector creyera que faltaba historia, y se ponía a bajar todos
# los calendarios cada sesenta segundos.
chequear("los goles pendientes ya no despiertan al recorredor de calendarios",
         "historia_al_dia = not pendientes" in _SRV
         and "recorrer = (not historia_al_dia) or vuelta % 8 == 0" in _SRV)
chequear("y buscar goles solo va cada cinco minutos, no cada uno",
         "elif not pendientes:" in _SRV and "time.sleep(300)" in _SRV)


print("\n── la ficha del jugador es la misma se entre por donde se entre ──")
# El mismo jugador abierto desde la formación de un partido salía completo, y
# abierto desde el plantel del club salía sin partidos, sin goles y sin
# gráfico. La página manda el torneo que uno está mirando, y desde la ficha
# de un club eso es "club", que no es un torneo: todas las búsquedas de
# abajo se hacían contra una liga que no existe.
server.almacen.guardar("pj:lpf:enzo perez", {"n": 7, "ids": ["1"] * 7})
chequear("desde la ficha de un club se resuelve el torneo de verdad",
         server.liga_del_jugador("Enzo Pérez", "club") == "lpf")
chequear("y desde la portada también",
         server.liga_del_jugador("Enzo Pérez", "home") == "lpf")
chequear("si mandan un torneo de verdad, ese manda",
         server.liga_del_jugador("Enzo Pérez", "nacional") == "nacional")
chequear("y de un desconocido no se inventa nada raro",
         server.liga_del_jugador("Nadie Conocido", "club") == "lpf")
# el que jugó en dos: gana donde más jugó
server.almacen.guardar("pj:lpf:juan viaja", {"n": 2, "ids": ["1", "2"]})
server.almacen.guardar("pj:nacional:juan viaja", {"n": 9, "ids": ["1"] * 9})
chequear("el que jugó en dos torneos se busca donde más jugó",
         server.liga_del_jugador("Juan Viaja", "club") == "nacional")

# Y la prueba que importa: las dos puertas tienen que dar lo mismo.
_fetch_real2 = server.fetch
server.fetch = lambda *a, **k: (_ for _ in ()).throw(OSError("sin fuente"))
_desde_club = server.api_atleta({"name": ["Enzo Pérez"], "liga": ["club"]})
_desde_part = server.api_atleta({"name": ["Enzo Pérez"], "liga": ["lpf"]})
server.fetch = _fetch_real2
chequear("los partidos jugados ya no dependen de por dónde entraste",
         _desde_club.get("pj") == _desde_part.get("pj") == 7,
         (_desde_club.get("pj"), _desde_part.get("pj")))
chequear("y la ficha dice de qué torneo salieron los números",
         _desde_club.get("liga") == "lpf", _desde_club.get("liga"))


print("\n── la portada no hace esperar ──")
# Medía 9,4 segundos de promedio y 40 el peor caso. La causa: cada visita
# armaba todo de nuevo, once ligas una tras otra. Dos cambios: se piden a la
# vez, y se contesta con lo último armado mientras se rearma por atrás.
import threading as _th
server._VIVO.clear()
# Ojo: acá arriba las pruebas anularon time.sleep para no tardar, así que
# no se puede medir con el reloj. Se usa una señal, que además es la forma
# correcta de esperar a otro hilo.
_armados, _rearmado = [0], _th.Event()
def _contar():
    _armados[0] += 1
    if _armados[0] > 1:
        _rearmado.set()
    return {"n": _armados[0], "live": 0}

_v1 = server.al_toque("prueba", _contar, frescura=0)
chequear("el primero de todos lo arma y se lo lleva",
         _v1 == {"n": 1, "live": 0}, _v1)

_v2 = server.al_toque("prueba", _contar, frescura=0)
chequear("el que viene después se lleva lo que ya estaba, sin esperar",
         _v2["n"] == 1, _v2)
chequear("y mientras tanto se rearmó por atrás",
         _rearmado.wait(5) and _armados[0] == 2, _armados)

# Si la fuente se cae, se sigue mostrando lo último bueno en vez de romper.
_fallo = _th.Event()
def _rota():
    _fallo.set()
    raise OSError("se cayó la fuente")
server.al_toque("prueba", _rota, frescura=0)
_fallo.wait(5)
chequear("si la fuente falla, se sigue mostrando lo último que anduvo",
         server.al_toque("prueba", _contar, frescura=9999)["n"] == 2,
         server._VIVO.get("prueba"))
server._VIVO.clear()

# Y las once ligas se piden a la vez, no una tras otra.
chequear("las ligas de la portada se piden todas juntas",
         "with ThreadPoolExecutor(max_workers=min(8, len(cuales))) as pool:" in _SRV
         and "traido = dict(pool.map(de, cuales))" in _SRV)

# La ficha de un club tardaba 7,8 s: trece ligas en fila y, a cada una, su
# tabla de posiciones aparte. Veintiséis esperas para dibujar una página.
chequear("las trece ligas de la ficha del club también",
         "traido = dict(pool.map(de_liga, cuales))" in _SRV
         and "cuales = [l for l in LIGAS if l != \"fem\"]" in _SRV)
chequear("y el orden sale de LIGAS, no de cuál contestó primero",
         "orden = [l for l in cuales if traido.get(l)]" in _SRV)

server._VIVO.clear()
_veces = [0]
_armar_real = server.armar_club_info
server.armar_club_info = lambda canon: (_veces.__setitem__(0, _veces[0] + 1)
                                        or {"club": canon})
_c1 = server.api_club_info({"name": ["Belgrano"]})
_c2 = server.api_club_info({"name": ["Belgrano"]})
server.armar_club_info = _armar_real
chequear("la ficha del club se arma una vez y se sirve muchas",
         _veces[0] == 1 and _c1 == _c2 == {"club": "Belgrano"},
         (_veces[0], _c1))
chequear("los goleadores y canales de la fecha, igual",
         "return al_toque(\"det:%s:%s:%s\" % (fecha or \"\", lid, rnd or \"\")," in _SRV)
server._VIVO.clear()

# Cambiar de fecha tardaba 1,3 s y cambiar de torneo disparaba cuatro
# cuentas de medio segundo cada una. Son todas iguales para todo el mundo.
chequear("las tablas y el fixture también se sirven al toque",
         set(server.AL_TOQUE) >= {"/api/games", "/api/rounds", "/api/standings",
                                  "/api/annual", "/api/promedios",
                                  "/api/scorers", "/api/liga",
                                  "/api/liga/games"},
         sorted(server.AL_TOQUE))
chequear("y ninguna de esas se calcula dos veces por la misma pregunta",
         "al_toque(clave_de_ruta(path, q)," in _SRV)
# La clave es lo único que separa una fecha de otra. Si se pisan, cambiás
# de fecha y ves los partidos de la anterior, que sería mucho peor que
# tardar 1,3 segundos.
_k = server.clave_de_ruta
chequear("la fecha 5 y la fecha 6 no se pisan",
         _k("/api/games", {"round": ["5"]}) != _k("/api/games", {"round": ["6"]}))
chequear("ni dos torneos distintos",
         _k("/api/liga", {"id": ["lib"]}) != _k("/api/liga", {"id": ["sud"]}))
chequear("pero el mismo pedido escrito al revés sí es el mismo",
         _k("/api/liga/games", {"id": ["lib"], "round": ["3"]})
         == _k("/api/liga/games", {"round": ["3"], "id": ["lib"]}))
chequear("y una ruta sin parámetros tiene su clave igual",
         _k("/api/scorers", {}) == "/api/scorers|")
# Lo que puede tener efectos —rehacer un recorrido, vaciar la base— no
# puede entrar acá por descuido: se contestaría con una respuesta vieja.
chequear("lo que cambia cosas no se sirve de lo guardado",
         not ({"/api/recorrido", "/api/contenido", "/api/raw", "/api/diagnostico"}
              & set(server.AL_TOQUE)))
chequear("la clave lleva los parámetros, así la fecha 5 y la 6 son distintas",
         "for k, v in sorted(q.items())" in _SRV)
chequear("cada partido se copia antes de etiquetarlo",
         "return [dict(g) for g in games" in _SRV)
chequear("un día que ya pasó no se rearma cada diez segundos",
         "if not hoy:\n            return 600" in _SRV)


print("\n── la página viaja sin la receta ──")
# index.html tiene casi 5.000 líneas de comentarios explicando cada
# decisión. Eso vale más que el código y viajaba entero a cualquiera que
# abriera la página. Se quedan en el archivo; lo que se aligera es la copia
# que sale por el cable.
_ALIG = server.aligerar(HTML)
# Que nadie "ayude" borrándolos del archivo: ahí es donde tienen que estar.
_UNA_FRASE = "oficial manda siempre, aunque nos falte el autor"
chequear("los comentarios se quedan en el archivo",
         HTML.count("/* ──") > 20 and _UNA_FRASE in HTML,
         HTML.count("/* ──"))
chequear("y no viajan",
         len(_ALIG) < len(HTML) * 0.85 and _UNA_FRASE not in _ALIG,
         "%.0f%% del original" % (100 * len(_ALIG) / len(HTML)))
chequear("pero el bloque que reemplaza el servidor sobrevive al recorte",
         "<title>" in _ALIG and "og:title" in _ALIG)
# El único comentario que sí tiene que viajar es el del derecho de autor:
# borrarlo de la copia publicada sería borrarlo justo de donde sirve.
chequear("el aviso de derecho de autor viaja con la página",
         "/*! HAYVAR" in _ALIG and "Todos los derechos reservados" in _ALIG
         and "© 2026 HAYVAR" in _ALIG)
chequear("y los términos completos están en su archivo",
         os.path.exists(os.path.join(AQUI, "licencia.txt")))
chequear("los buscadores no tienen por qué recorrer las /api/",
         "Disallow: /api/" in _SRV)

# Lo delicado: una barra adentro de un texto o de una expresión regular no
# es un comentario. Este archivo está lleno de https:// y de regex.
_casos = [
    ("var u='http://x//y'; // afuera", "var u='http://x//y'; "),
    ('var r=/a\\/\\/b/; // afuera', 'var r=/a\\/\\/b/; '),
    ("var t=`no // es comentario`; // sí", "var t=`no // es comentario`; "),
    ("var t=`a${ `b${c}d` }e`; // anidada", "var t=`a${ `b${c}d` }e`; "),
    ("return /x/.test(s); // regex después de return",
     "return /x/.test(s); "),
    ("var d=a/b; var e=c/d; // división, no regex", "var d=a/b; var e=c/d; "),
    ("var s='no /* toques */ esto'; /* esto sí */",
     "var s='no /* toques */ esto'; "),
    ('var q="comilla \\" adentro"; // afuera', 'var q="comilla \\" adentro"; '),
]
_mal = [(a, server.sin_comentarios_js(a)) for a, b in _casos
        if server.sin_comentarios_js(a) != b]
chequear("una barra adentro de un texto o de una regex no es un comentario",
         not _mal, _mal)

# Y la red de seguridad: si el recorte sale raro, se manda el original.
chequear("si el recorte se come el archivo, se manda el original",
         server.aligerar("<script>var a='sin cerrar</script>")
         == "<script>var a='sin cerrar</script>")


print("\n── las puertas de servicio están cerradas ──")
# /api/recorrido?reconstruir=todo&confirmar=si borra los partidos de los
# dieciséis torneos. Y se autodocumenta: el que la abría de curioso leía en
# la respuesta cómo hacerlo. Antes de publicar la página hay que cerrarla.
chequear("lo que borra o gasta está en la lista de privadas",
         server.PRIVADAS == {"/api/recorrido", "/api/raw", "/api/contenido",
                             "/api/diagnostico", "/api/tiempos",
                             "/api/base", "/api/visitas", "/admin"},
         sorted(server.PRIVADAS))
chequear("el control va antes de resolver la ruta, no después",
         _SRV.index("if path in PRIVADAS and not con_llave(q, self.headers):")
         < _SRV.index('if path == "/api/raw":'))
chequear("y la llave no está escrita en el código",
         'os.environ.get("HAYVAR_LLAVE"' in _SRV
         and "llave.txt" in open(os.path.join(AQUI, ".gitignore"),
                                 encoding="utf-8").read())

# En la compu de uno quedan abiertas; publicado, cerradas.
_casa, _llave = server.EN_CASA, server.LLAVE
server.EN_CASA = True
chequear("en la compu de uno se puede entrar sin llave",
         server.con_llave({}) is True)
server.EN_CASA, server.LLAVE = False, "abracadabra"
chequear("publicado, sin llave no se entra",
         server.con_llave({}) is False)
chequear("con la llave equivocada tampoco",
         server.con_llave({"llave": ["abracadabr"]}) is False)
chequear("con la llave correcta sí",
         server.con_llave({"llave": ["abracadabra"]}) is True)
chequear("y también sirve mandarla como encabezado",
         server.con_llave({}, {"X-Llave": "abracadabra"}) is True)
# Fallar cerrado: si nadie configuró la llave, no se abre igual.
server.LLAVE = ""
chequear("si se olvidaron de poner la llave, queda cerrado y no abierto",
         server.con_llave({"llave": [""]}) is False
         and server.con_llave({}) is False)
server.EN_CASA, server.LLAVE = _casa, _llave

# Y lo que sí es público tiene que seguir siéndolo, o la página se cae.
chequear("las rutas que usa la página siguen abiertas",
         not (server.PRIVADAS & {"/api/home", "/api/games", "/api/rounds",
                                 "/api/standings", "/api/annual",
                                 "/api/promedios", "/api/scorers",
                                 "/api/liga", "/api/liga/games", "/api/match",
                                 "/api/detalles", "/api/club", "/api/clubes",
                                 "/api/club-info", "/api/atleta",
                                 "/api/buscar", "/api/ligas"}))
chequear("y el chequeo de salud de Render también",
         "/api/ligas" not in server.PRIVADAS)
# /api/base cuenta dónde vive el archivo de la base, cuánto pesa y cuántas
# entradas tiene. Se me había quedado abierta.
chequear("la base tampoco cuenta dónde vive a cualquiera",
         "/api/base" in server.PRIVADAS)


print("\n── quién entra, sin guardar quién es nadie ──")
import visitas
_IPH = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari")
_WIN = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

# Lo más importante de todo esto: contar personas sin poder identificarlas.
_h1 = visitas.huella("200.1.2.3", _IPH)
chequear("la huella no deja ver la IP",
         "200.1.2.3" not in _h1 and len(_h1) == 16, _h1)
chequear("la misma persona da la misma huella el mismo día",
         visitas.huella("200.1.2.3", _IPH) == _h1)
chequear("y dos personas distintas dan huellas distintas",
         visitas.huella("200.1.2.4", _IPH) != _h1)
chequear("mañana la misma persona ya no se puede reconocer",
         visitas.huella("200.1.2.3", _IPH, dia="2030-01-01") != _h1)

chequear("a los robots no se los cuenta como visitas",
         visitas.es_robot(_BOT) and not visitas.es_robot(_IPH))
chequear("se distingue el teléfono de la computadora",
         visitas.dispositivo(_IPH) == "móvil"
         and visitas.dispositivo(_WIN) == "escritorio")
chequear("y el sistema y el navegador",
         (visitas.sistema_de(_IPH), visitas.navegador_de(_IPH)) == ("iOS", "Safari")
         and (visitas.sistema_de(_WIN), visitas.navegador_de(_WIN)) == ("Windows", "Chrome"),
         (visitas.sistema_de(_WIN), visitas.navegador_de(_WIN)))

# De dónde viene: del referente sólo el dominio, nunca la dirección entera,
# que puede llevar cosas privadas de la otra página.
_casos_fuente = [
    ("https://www.google.com/search?q=secreto", "Google"),
    ("https://l.instagram.com/?u=algo", "Instagram"),
    ("https://t.co/abc", "X / Twitter"),
    ("https://hayvar.com.ar/laliga", "interno"),
    ("", "directo"),
]
_malf = [(r, visitas.de_donde(r, "hayvar.com.ar")[0]) for r, e in _casos_fuente
         if visitas.de_donde(r, "hayvar.com.ar")[0] != e]
chequear("se reconoce de dónde llegó cada visita", not _malf, _malf)
chequear("y no se guarda la dirección completa del referente",
         "secreto" not in json.dumps(
             visitas.de_donde("https://www.google.com/search?q=secreto",
                              "hayvar.com.ar")))
chequear("los términos de búsqueda se guardan cuando el buscador los manda",
         visitas.que_buscaba("https://duckduckgo.com/?q=aldosivi+union")
         == "aldosivi union")
chequear("y no se inventan cuando Google no los manda",
         visitas.que_buscaba("https://www.google.com/") == "")
chequear("el idioma sirve de respaldo para el país",
         visitas.region("es-AR,es;q=0.9") == "AR"
         and visitas.region("en-US") == "US" and visitas.region("") == "")

# Pero el idioma solo no alcanza, y éste es el error que se habría comido a
# los argentinos: media Argentina tiene el teléfono en inglés, manda en-US,
# y con eso les poníamos la Libertadores antes que la Liga Profesional. La
# zona horaria no la configura nadie a mano y no se equivoca.
chequear("la zona horaria dice el país mejor que el idioma",
         visitas.pais_de_zona("America/Argentina/Buenos_Aires") == "AR"
         and visitas.pais_de_zona("America/Argentina/Cordoba") == "AR"
         and visitas.pais_de_zona("Europe/Madrid") == "ES"
         and visitas.pais_de_zona("Europe/London") == "GB"
         and visitas.pais_de_zona("Asia/Tokyo") == "")
chequear("y el continente sale casi siempre",
         visitas.continente_de_zona("America/Santiago") == "america"
         and visitas.continente_de_zona("Europe/Paris") == "europa"
         and visitas.continente_de_zona("Atlantic/Canary") == "europa"
         and visitas.continente_de_zona("Asia/Tokyo") == ""
         and visitas.continente_de_zona("") == "")
chequear("el argentino con el teléfono en inglés sigue siendo argentino",
         (visitas.pais_de_zona("America/Argentina/Buenos_Aires")
          or visitas.region("en-US")) == "AR")
chequear("la página manda la zona horaria",
         "Intl.DateTimeFormat().resolvedOptions().timeZone" in HTML
         and "&tz='+encodeURIComponent(zona)" in HTML)
chequear("y el servidor la prefiere al idioma",
         "visitas.pais_de_zona(zona) or visitas.region(" in _SRV)

# Contar de verdad, con la base.
server.almacen.borrar_prefijo("vis:")
def _v(ip, ruta, ua=_IPH, ref=""):
    f, d = visitas.de_donde(ref, "hayvar.com.ar")
    return visitas.anotar({"huella": visitas.huella(ip, ua), "ruta": ruta,
        "fuente": f, "dominio": d, "busco": visitas.que_buscaba(ref),
        "dispositivo": visitas.dispositivo(ua), "sistema": visitas.sistema_de(ua),
        "navegador": visitas.navegador_de(ua), "region": "AR",
        "pantalla": "390x844", "intencion": ""})
_a = _v("1.1.1.1", "/")
_b = _v("2.2.2.2", "/laliga")
_v("1.1.1.1", "/aldosivi")          # el mismo de antes, otra página
_r = visitas.resumen()
chequear("dos personas y tres páginas vistas",
         (_r["hoy"]["gente"], _r["hoy"]["vistas"]) == (2, 3), _r["hoy"])

# Los identificadores llevan azar: con la hora en milisegundos, dos
# personas que entraran a la vez compartían identificador y el tiempo de
# una se le sumaba a la otra.
chequear("dos visitas simultáneas no comparten identificador", _a != _b)
visitas.latir(_a, 45)
visitas.latir(_a, 120)
visitas.latir(_a, 90)               # llega tarde y desordenado
visitas.latir(_b, 30)
_r = visitas.resumen()
chequear("el tiempo se suma bien y no va para atrás",
         _r["hoy"]["segundos"] == 150, _r["hoy"]["segundos"])
chequear("y cada tiempo queda en la visita que corresponde",
         sorted(u["seg"] for u in _r["ultimas"]) == [0, 30, 120],
         [u["seg"] for u in _r["ultimas"]])

# Que no crezca sin freno: el disco es de 1 GB y ya hay 202 MB adentro.
for _i in range(500):
    _v("9.9.9.%d" % (_i % 120), "/partido/x-%d" % _i)
_dia = server.almacen.leer("vis:dia:%s" % visitas.hoy())[0]
chequear("las últimas visitas tienen tope",
         len(server.almacen.leer("vis:ultimas")[0]) == visitas.ULTIMAS)
chequear("y el resumen del día no crece con el tráfico",
         len(_dia["paginas"]) <= 81 and len(json.dumps(_dia)) < 60000,
         (len(_dia["paginas"]), len(json.dumps(_dia)) // 1024))
chequear("en lo guardado no hay ninguna IP",
         not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                       json.dumps(_dia) + json.dumps(
                           server.almacen.leer("vis:ultimas")[0])))
server.almacen.borrar_prefijo("vis:")

# Qué venía a ver. Es el dato que más pesa de todos, porque es lo único que
# la persona dijo: el buscador la mandó justo ahí. Las palabras exactas no
# llegan —Google las borra— pero el destino dice lo mismo.
server.almacen.guardar("tv:lib:4798160", ["ESPN 2"])
server.almacen.guardar("pj:laliga:enzo fernandez", {"n": 12, "ids": ["1"] * 12})
chequear("de un torneo se deduce el torneo",
         server.que_venia_a_ver("/laliga") == "laliga")
chequear("de una fecha suelta, también",
         server.que_venia_a_ver("/liga-profesional/fecha-6") == "lpf")
chequear("de un partido, mirando de cuál torneo es",
         server.que_venia_a_ver("/partido/olimpia-vs-vasco-4798160") == "lib")
chequear("de un club de Primera, la Liga Profesional",
         server.que_venia_a_ver("/belgrano") == "lpf")
chequear("y de un jugador, el torneo donde estuvo jugando",
         server.que_venia_a_ver("/jugador/enzo-fernandez") == "laliga")
chequear("de un jugador del que no sabemos nada, no se inventa",
         server.que_venia_a_ver("/jugador/nadie-conocido") == "")
chequear("y de la portada, nada: no dijo qué quiere",
         server.que_venia_a_ver("/") == ""
         and server.que_venia_a_ver("/partido/no-existe-999") == "")

# Lo más cerca que se puede estar de saber qué escribieron en el buscador.
server.almacen.borrar_prefijo("vis:")
def _vb(ruta, ref):
    f, d = visitas.de_donde(ref, "hayvar.com.ar")
    visitas.anotar({"huella": visitas.huella(ruta, ref), "ruta": ruta,
        "fuente": f, "dominio": d, "busco": "", "dispositivo": "móvil",
        "sistema": "iOS", "navegador": "Safari", "region": "AR",
        "pantalla": "390x844", "intencion": ""})
_vb("/partido/aldosivi-vs-union-4728056", "https://www.google.com/")
_vb("/partido/aldosivi-vs-union-4728056", "https://www.google.com/")
_vb("/jugador/enzo-fernandez", "https://www.bing.com/")
_vb("/laliga", "https://www.instagram.com/")     # una red social no es búsqueda
_vb("/", "")                                     # ni el que escribió la dirección
_at = {x["que"]: x["cuantas"] for x in visitas.resumen()["aterrizajes"]}
chequear("se ve a qué página llega el que viene de un buscador",
         _at == {"/partido/aldosivi-vs-union-4728056": 2,
                 "/jugador/enzo-fernandez": 1}, _at)
server.almacen.borrar_prefijo("vis:")

# La que anota tiene que estar abierta —la usa la propia página— y la que
# muestra lo juntado, cerrada.
chequear("la que anota está abierta y la que muestra está cerrada",
         "/api/visita" not in server.PRIVADAS
         and "/api/visitas" in server.PRIVADAS)
chequear("anotar nunca puede romper una visita",
         'return self._json({"ok": False})' in _SRV)
chequear("la página avisa el tamaño de pantalla y de dónde venía",
         "screen.width+'x'+screen.height" in HTML
         and "document.referrer" in HTML)
chequear("y el tiempo va por latidos, no por el evento de cerrar",
         "setInterval(latir, 30000)" in HTML
         and "if(document.hidden) latir();" in HTML)


print("\n── la portada se ordena según quién entra ──")
# La pregunta difícil no es qué hacer con el que llega buscando algo: es qué
# hacer con el que entra por la puerta grande sin decir nada, que son casi
# todos. Cuatro señales más, con puntaje, y sin ninguna queda el orden de
# siempre. Se prueba corriendo la función tal cual está en la página.
if _sh.which("node"):
    _i = HTML.index("  // El interruptor. En false")
    _j = HTML.index("  async function loadHome(){")
    _orden = ("let S={};\nclass URLSearchParams{constructor(s){this.s=s||''}"
              "get(k){const m=new RegExp('[?&]'+k+'=([^&]*)').exec(this.s);"
              "return m?m[1]:null}}\nconst location={search:''};\n"
              + HTML[_i:_j].replace("const PORTADA_SEGUN_VISITA = true;",
                                    "let PORTADA_SEGUN_VISITA = true;") + """
const L=(l,v)=>({liga:l, games: v?[{status:'LIVE'}]:[{status:'FIN'}]});
const orden=b=>b.map(x=>x.liga).join(' ');
const out={};
// un día cargado, con partidos de todos los torneos
const todo=(v)=>['lpf','nacional','ca','lib','sud','champions','europa',
  'laliga','premier','seriea','bundesliga'].map(l=>L(l,(v||[]).includes(l)));
function caso(n, visita, club, bloques, search){
  S={visita:visita||{}, club:club?{name:'x'}:null};
  location.search=search||'';
  const b=bloques||todo(); ordenarPortada(b); out[n]=orden(b);
}
caso('argentina', {region:'AR'});
caso('america', {region:'CL'});
caso('europaConLiga', {region:'ES'});
caso('europaSinLiga', {region:'FR'});
caso('europaMasClub', {region:'ES'}, true);
caso('restoDelMundo', {region:'JP'});
caso('sinPais', {});
caso('quiereGana', {region:'ES', quiere:'premier'});
// el orden de prioridades, con las tres señales a la vez
caso('buscoLuegoClubLuegoPais', {region:'ES', quiere:'premier'}, true);
caso('vivoDesempata', {region:'FR'}, false, todo(['seriea']));
caso('vivoNoPisaLaPropia', {region:'ES'}, false, todo(['premier','seriea']));
caso('vivoNoSubeSolo', {region:'AR'}, false, todo(['laliga']));
caso('noSubeUnoQueNoJuega', {region:'ES'}, false,
     [L('lpf'),L('nacional'),L('lib')]);
// La Sudamericana nunca arriba de la Libertadores. Se le da vuelta a
// propósito el orden con que llegan, y de un visitante del que no sabemos
// nada, que es el caso donde no se reordena nada más.
caso('sudNuncaArriba', {region:'JP'}, false, [L('sud'),L('lib'),L('lpf')]);
caso('sudNuncaArribaSinPais', {}, false, [L('sud'),L('lib')]);
caso('sudNuncaArribaEnEuropa', {region:'ES'}, false, [L('sud'),L('lib')]);
// salvo que haya venido justamente a ver la Sudamericana
caso('sudGanaSiVinoPorElla', {region:'AR', quiere:'sud'}, false,
     [L('lib'),L('sud'),L('lpf')]);
PORTADA_SEGUN_VISITA=false;
caso('apagado', {region:'ES', quiere:'premier'});
caso('forzado', {}, false, todo(), '?ver=premier');
console.log(JSON.stringify(out));
""")
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_orden); _ro = _f.name
    _po = _sub.run(["node", _ro], capture_output=True, text=True,
                   timeout=60)
    os.unlink(_ro)
    _o = json.loads(_po.stdout) if _po.returncode == 0 else None
    chequear("la función de ordenar corre", _o is not None,
             _po.stderr.strip().splitlines()[:2])
    if _o:
        _T = "ca sud europa laliga premier seriea bundesliga"   # la cola
        _esperado = {
            # las cuatro reglas, tal como quedaron dichas
            "argentina":     "lpf lib sud champions nacional ca europa laliga premier seriea bundesliga",
            "america":       "lib sud lpf champions nacional ca europa laliga premier seriea bundesliga",
            "europaConLiga": "laliga champions lib sud lpf nacional ca europa premier seriea bundesliga",
            # sin país europeo identificado, Primera Nacional se va al final
            "europaSinLiga": "champions lpf lib sud ca europa laliga premier seriea bundesliga nacional",
            # el club elegido manda aunque esté leyendo desde Madrid
            "europaMasClub": "lpf laliga champions lib sud nacional ca europa premier seriea bundesliga",
            # de donde no sabemos, el orden de siempre
            "restoDelMundo": "lpf nacional ca lib sud champions europa laliga premier seriea bundesliga",
            "sinPais":       "lpf nacional ca lib sud champions europa laliga premier seriea bundesliga",
            # lo que vino a ver le gana a de dónde es. Ojo con la cola: sin
            # nada en vivo, las europeas que sobran quedan en el orden de
            # siempre y no se reacomodan.
            "quiereGana":    "premier laliga champions lib sud lpf nacional ca europa seriea bundesliga",
            # y con las tres juntas: lo que buscó, después el club que
            # eligió, y recién después la lista de su región
            "buscoLuegoClubLuegoPais":
                "premier lpf laliga champions lib sud nacional ca europa seriea bundesliga",
            # el "en vivo" sólo desempata entre europeas, sin mover al grupo
            "vivoDesempata": "champions lpf lib sud ca seriea europa laliga premier bundesliga nacional",
            # y nunca le pisa el puesto a la liga del propio visitante
            "vivoNoPisaLaPropia": "laliga champions lib sud lpf nacional ca premier seriea europa bundesliga",
            # ni sube un torneo a la cabeza sólo por estar rodando
            "vivoNoSubeSolo": "lpf lib sud champions nacional ca laliga europa premier seriea bundesliga",
            # Un español un día sin LaLiga ni Champions: las dos primeras de
            # su lista no existen, así que no se inventan. Baja a la
            # siguiente que sí está —Libertadores— y después la Liga
            # Profesional, que es lo que su lista dice.
            "noSubeUnoQueNoJuega": "lib lpf nacional",
            # La Sudamericana es el hermano menor de la Libertadores y va
            # abajo siempre, aunque lleguen al revés y aunque del visitante
            # no sepamos nada.
            "sudNuncaArriba":        "lib sud lpf",
            "sudNuncaArribaSinPais": "lib sud",
            "sudNuncaArribaEnEuropa": "lib sud",
            # salvo que haya venido a ver justamente la Sudamericana: lo que
            # la persona vino a ver le gana a cualquier jerarquía nuestra
            "sudGanaSiVinoPorElla":  "sud lpf lib",
            # con el interruptor apagado la portada es igual para todos
            "apagado":       "lpf nacional ca lib sud champions europa laliga premier seriea bundesliga",
            # pero ?ver= anda igual, para poder probarlo sin encenderlo
            "forzado":       "premier lpf nacional ca lib sud champions europa laliga seriea bundesliga",
        }
        _malos = {k: (v, _o.get(k)) for k, v in _esperado.items()
                  if _o.get(k) != v}
        chequear("la portada se ordena como quedó dicho, caso por caso",
                 not _malos, _malos)
# Y el partidazo del día acompaña: no puede quedar uno de un torneo que
# esta persona no vino a ver, con su torneo puesto arriba.
chequear("el servidor manda un partidazo por torneo",
         '"partidazos": {b["liga"]: partidazo_del_dia([b])' in _SRV)
chequear("y la página elige el del torneo que quedó primero",
         "const suyo=(h.partidazos||{})[arriba];" in HTML
         and "const elegido=suyo||h.partidazo;" in HTML)
# Elegir el partidazo de un solo torneo es un uso nuevo de una función que
# hasta ahora siempre recibía la portada entera: hay que probar que no se
# rompa ni devuelva cualquier cosa con un bloque suelto o vacío.
def _pd(i, h, a, liga, **kw):
    d = {"id": i, "liga": liga, "home": {"name": h, "canon": h},
         "away": {"name": a, "canon": a}, "status": "FIN", "gh": 1, "ga": 0,
         "start": "2026-08-24T20:00:00-03:00", "interzonal": False, "round": 6}
    d.update(kw)
    return d
_bl = [{"liga": "lpf", "nombre": "Liga Profesional", "games": [
            _pd("1", "Boca Juniors", "River Plate", "lpf", interzonal=True),
            _pd("2", "Aldosivi", "Unión", "lpf")]},
       {"liga": "laliga", "nombre": "LaLiga", "games": [
            _pd("3", "Real Madrid", "Barcelona", "laliga"),
            _pd("4", "Getafe", "Osasuna", "laliga")]}]
chequear("cada torneo elige su propio partidazo",
         [server.partidazo_del_dia([b]) for b in _bl] == ["1", "3"],
         [server.partidazo_del_dia([b]) for b in _bl])
chequear("y con un bloque vacío no se rompe ni inventa",
         server.partidazo_del_dia([{"liga": "x", "games": []}]) is None
         and server.partidazo_del_dia([]) is None)
chequear("el interruptor está encendido y se puede apagar en una línea",
         "const PORTADA_SEGUN_VISITA = true;" in HTML)
chequear("y se puede probar sin encenderlo",
         "new URLSearchParams(location.search).get('ver')" in HTML)
chequear("si el aviso llega tarde, se reordena sin quedar dando vueltas",
         "if(S.liga==='home' && S.home && ordenarPortada(S.home.bloques))" in HTML
         and "loadHome();" in HTML)


print("\n── la columna del torneo en la página de un partido ──")
# El servidor tiene que decir de qué torneo es el partido: la página lo
# necesita para saber qué tabla poner al costado, y el que entra por el
# link no puede saberlo solo.
server.almacen.guardar("tv:champions:5551111", ["ESPN"])
chequear("el servidor sabe de qué torneo es un partido",
         server.liga_de_partido("5551111") == "champions"
         and server.liga_de_partido("999999") == ""
         and server.liga_de_partido("") == "")
chequear("y se lo manda a la página con el partido",
         'out["liga"] = liga_id' in _SRV
         and 'out["ligaNombre"]' in _SRV and 'out["torneo"]' in _SRV)
# Y esto estaba mal desde antes: sin torneo, `api_match` daba "lpf" por
# defecto, así que cada visita en frío a un partido de la Champions anotaba
# a sus jugadores como si hubieran jugado en la Liga Profesional.
chequear("y ya no se anota a cualquiera como jugador de Primera",
         'liga_id = pedida if pedida in LIGAS else (liga_de_partido(str(gid)) or "lpf")'
         in _SRV)
chequear("la columna elige qué mostrar según la competencia",
         "if(lid==='lpf'){" in HTML and "async function panelDelTorneo(m)" in HTML)
chequear("en la Liga Profesional van la zona, el anual y los promedios",
         "['anual','Anual'],\n                              ['prom','Promedios']" in HTML)
chequear("y si es eliminación directa lo dice, en vez de mostrar una tabla vacía",
         "está en eliminación directa" in HTML)
chequear("los dos equipos del partido van resaltados en la tabla",
         "const suyo=(destacar||[]).some(n=>mismoNombre(n,nom));" in HTML)
# El encabezado decía "Clausura 2026" en todos los partidos, también en un
# Bayern-Inter.
chequear("el encabezado dice el torneo de verdad y no siempre el Clausura",
         "const dondeJuega=[" in HTML
         and "'Clausura 2026 · Fecha '" not in HTML
         and "[m.ligaNombre, m.torneo].filter(Boolean).join(' ')" in HTML)


print("\n── en una copa, la instancia que se juega ──")
# 365scores escribe la fase de cada partido a su manera y cambiando de
# torneo. Estos son los nombres tal como estaban guardados en la base el
# 25/8/26: si la fuente los cambia, esta prueba lo avisa antes que el sitio.
_CRUDOS = {
    "champions": ["Primera Ronda", "Segunda Ronda", "Tercera Ronda", "Playoff"],
    "europa":    ["Primera Ronda", "Segunda Ronda", "Tercera Ronda", "Playoff"],
    "lib":       ["Primera Fase", "Segunda Fase", "Tercera Fase",
                  "Octavos de Final", "Cuartos de Final", "Semifinales", "Final"],
    "sud":       ["Primera Fase", "Octavos de Final", "Cuartos de Final",
                  "Semifinales", "Final"],
    "ca":        ["32avos de final", "16avos de final", "Octavos de Final",
                  "Cuartos de Final", "Semifinales", "Final"],
}
_perdidos = [(lid, s) for lid, sts in _CRUDOS.items() for s in sts
             if not server.etapa_de_copa(lid, s)]
chequear("cada fase que manda la fuente encaja en una del torneo", not _perdidos,
         _perdidos)
# Las clasificatorias de agosto llegan como "Primera/Segunda/Tercera Ronda".
# No encajaban en ninguna fase y `api_liga_games` descarta lo que no encaja:
# de los 83 partidos de la Champions se veían 7, y de los 68 de la Europa, 12.
chequear("las rondas previas de Champions y Europa ya no se descartan",
         server.etapa_de_copa("champions", "Primera Ronda") == "Fase previa 1"
         and server.etapa_de_copa("champions", "Segunda Ronda") == "Fase previa 2"
         and server.etapa_de_copa("europa", "Tercera Ronda") == "Fase previa 3")
# Y "Tercera Ronda" era peor que no encajar: caía en `tercer` —el partido por
# el tercer puesto— y se ordenaba entre la semifinal y la final.
chequear("y la tercera ronda no se confunde con el partido por el tercer puesto",
         server.rango_etapa("Tercera Ronda") < server.rango_etapa("Fase de grupos")
         and sorted(server.FASES_COPA["champions"], key=server.rango_etapa)
             == server.FASES_COPA["champions"])
# En la fase de grupos la fuente no manda el nombre de la fase: manda el
# número de fecha y nada más. Es la única fase de una copa que numera fechas.
chequear("la fase de grupos se deduce de que tenga fecha numerada",
         server.etapa_de_copa("lib", "", 4) == "Fase de grupos"
         and server.etapa_de_copa("sud", "", 2) == "Fase de grupos"
         and server.etapa_de_copa("champions", "", 3) == "Fase de liga")
chequear("sin fase y sin fecha no se inventa ninguna",
         server.etapa_de_copa("lib", "", None) == "")

# Los dos "play-off" de la Champions. UEFA juega dos rondas con ese nombre y
# no son la misma cosa: la de agosto es el último escalón de la
# clasificación —el que la gana entra a la fase de liga— y la de febrero es
# la que da entrada a los octavos. 365scores manda "Playoff" en las dos.
# En el calendario de este año los de la Champions son el 18 y 19 de agosto
# y los de la Europa el 20, y salían rotulados como los de febrero.
_pl = lambda lid, cuando: server.etapa_de_copa(lid, "Playoff", None, cuando)
chequear("el play-off de agosto es el de clasificación",
         _pl("champions", "2026-08-18T21:00:00Z") == "Repechaje de acceso"
         and _pl("europa", "2026-08-20T21:00:00Z") == "Repechaje de acceso",
         (_pl("champions", "2026-08-18T21:00:00Z"),
          _pl("europa", "2026-08-20T21:00:00Z")))
chequear("y el de febrero, el que da entrada a los octavos",
         _pl("champions", "2027-02-17T21:00:00Z") == "Play-offs"
         and _pl("europa", "2027-02-18T21:00:00Z") == "Play-offs",
         (_pl("champions", "2027-02-17T21:00:00Z"),
          _pl("europa", "2027-02-18T21:00:00Z")))
# Sin fecha no hay con qué decidir, y adivinar sería peor: se deja el que
# viene, que es el que la fuente nombra.
chequear("sin fecha no adivina", _pl("champions", "") == "Play-offs")
# La Libertadores y la Sudamericana tienen un solo play-off —los pre
# octavos— y ahí no hay nada que desempatar: agosto es su fecha real.
chequear("y donde hay un solo play-off no se mete",
         server.etapa_de_copa("lib", "Pre octavos", None,
                              "2026-08-18T21:00:00Z") == "Pre octavos"
         and server.etapa_de_copa("sud", "Pre octavos", None,
                                  "2026-08-18T21:00:00Z") == "Pre octavos")
# El partido lleva su fecha a la función, que es de dónde sale el desempate.
chequear("la página del partido le pasa la fecha",
         'etapa_de_copa(liga_id, out.get("stage"), out.get("round"),\n'
         '                                 out.get("start"))' in _SRV)
chequear("y el calendario también, que es donde se arma el cuadro",
         "desempatar_playoff(canonizar_fase(et, fases), fases," in _SRV)
# Con el desempate puesto, el orden del torneo tiene que seguir siendo el
# real: el repechaje de acceso antes de la fase de liga, y el otro después.
chequear("el repechaje queda antes de la fase de liga y los play-offs después",
         server.rango_etapa("Repechaje de acceso")
         < server.rango_etapa("Fase de liga") < server.rango_etapa("Play-offs")
         < server.rango_etapa("Octavos de final"))
# Un torneo que no es copa tiene fechas y no instancias: la etapa va vacía y
# el encabezado queda exactamente como estaba.
chequear("en las ligas no cambia nada",
         all(server.etapa_de_copa(l, "", 5) == "" and server.etapa_de_copa(l, "Clausura", 5) == ""
             for l in ("lpf", "laliga", "premier", "seriea", "nacional")))
chequear("y el partido la lleva puesta",
         'out["etapa"] = etapa_de_copa(' in _SRV)
# Pedir el calendario entero de la Libertadores —163 partidos— para dibujar
# ocho cajitas al costado es gastarle la conexión al que mira desde el celular.
chequear("las llaves se piden solas, sin el calendario entero",
         '(q.get("solo") or [""])[0] == "llaves"' in _SRV
         and "'&solo=llaves'" in HTML)

# Y la prueba que vale: abrir un partido de octavos de la Libertadores y
# mirar qué quedó dibujado al costado.
if _sh.which("node"):
    _LLAVES = """{nombre:'Copa Libertadores', copa:true,
  etapas:['Fase de grupos','Octavos de final','Cuartos de final'],
  llaves:[
   {etapa:'Octavos de final', previa:false, llaves:[
     {slot:1, penales:null, cerrada:false,
      equipos:[{team:{name:'Boca Juniors',canon:'Boca Juniors'},goles:2,pasa:false},
               {team:{name:'Flamengo',canon:'Flamengo'},goles:1,pasa:false}],
      partidos:[{id:'99', liveId:'99', start:'2026-08-25T21:30:00Z', tramo:'Ida',
                 status:'FIN', gh:2, ga:1,
                 home:{name:'Boca Juniors',canon:'Boca Juniors'},
                 away:{name:'Flamengo',canon:'Flamengo'}}]},
     {slot:2, penales:[4,2], cerrada:true,
      equipos:[{team:{name:'River Plate',canon:'River Plate'},goles:1,pasa:true},
               {team:{name:'Palmeiras',canon:'Palmeiras'},goles:1,pasa:false}],
      partidos:[{id:'100', liveId:'100', start:'2026-08-26T21:30:00Z', tramo:'Ida',
                 status:'FIN', gh:1, ga:1,
                 home:{name:'River Plate',canon:'River Plate'},
                 away:{name:'Palmeiras',canon:'Palmeiras'}}]}]},
   {etapa:'Cuartos de final', previa:false, llaves:[]}]}"""

    def _copa(match):
        _js = ("""
process.on('unhandledRejection',()=>{});
const RESP={
 '/api/match': %s,
 '/api/liga/games': %s,
 '/api/liga': {id:'lib', nombre:'Copa Libertadores', zonas:[{name:'Grupo C',
   rows:[{pos:1, canon:'Flamengo',
          team:{name:'Flamengo',canon:'Flamengo'}, pts:12, pj:6, dif:5},
         {pos:2, canon:'Boca Juniors',
          team:{name:'Boca Juniors',canon:'Boca Juniors'}, pts:9, pj:6, dif:2}]}]}};
const pedidos=[];
globalThis.fetch=async(u)=>{
  pedidos.push(u);
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};
};
loc.pathname='/partido/boca-juniors-vs-flamengo-99';
App.init();
(async()=>{
  for(let i=0;i<80;i++) await new Promise(r=>setImmediate(r));
  const medio=doc.querySelector('#matches').innerHTML||'';
  const der=doc.querySelector('#right').innerHTML||'';
  const enc=(medio.match(/<span>([^<]*Libertadores[^<]*)<\\/span>/)||[])[1]||'';
  console.log(JSON.stringify({
    encabezado: enc.trim().replace(/\\s+/g,' '),
    cajas: (der.match(/brk-lado/g)||[]).length,
    marcada: (der.match(/brk-suya/g)||[]).length,
    hayTabla: der.includes('<table'),
    penales: der.includes('(4)'),
    linkAlOtro: der.includes('river-plate-vs-palmeiras-100'),
    soloLlaves: pedidos.some(u=>u.indexOf('solo=llaves')>=0),
    calendarioEntero: pedidos.some(u=>u.indexOf('/api/liga/games')===0
                                    && u.indexOf('solo=llaves')<0)}));
})();
""" % (match, _LLAVES))
        _gg = (open(_DOMSITO, encoding="utf-8").read()
               + "\nglobalThis.document=doc; globalThis.window=win;"
                 "\nglobalThis.location=loc; globalThis.history=historial;"
                 "\nglobalThis.localStorage=almacenLocal;"
                 "\nglobalThis.MutationObserver=MutationObserver;"
                 "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
                 "\nglobalThis.setInterval=()=>0;\nlet App;\n"
               + _app.replace("const App=(()=>{", "App=(()=>{") + _js)
        with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as _f:
            _f.write(_gg); _rc = _f.name
        _pc = _sub.run(["node", _rc], capture_output=True, text=True, timeout=60)
        os.unlink(_rc)
        return json.loads(_pc.stdout) if _pc.returncode == 0 and _pc.stdout else None

    _OCT = """{id:'99', liveId:'99', liga:'lib', ligaNombre:'Copa Libertadores',
  torneo:'2026', etapa:'Octavos de final', stage:'Octavos de Final', round:null,
  start:'2026-08-25T21:30:00Z', status:'FIN', gh:2, ga:1,
  home:{name:'Boca Juniors',canon:'Boca Juniors'},
  away:{name:'Flamengo',canon:'Flamengo'},
  events:[], stats:[], lineups:{home:[],away:[]}, banco:{home:[],away:[]},
  confirmada:{}, bancoReal:{}, formation:{}, tv:[]}"""
    _oct = _copa(_OCT)
    _gru = _copa(_OCT.replace("etapa:'Octavos de final'", "etapa:'Fase de grupos'")
                     .replace("stage:'Octavos de Final'", "stage:''")
                     .replace("round:null", "round:3"))
    chequear("la página de un partido de copa se arma entera", _oct is not None)
    if _oct:
        chequear("el encabezado dice la instancia y no una fecha",
                 _oct["encabezado"] == "Copa Libertadores 2026 · Octavos de final",
                 _oct["encabezado"])
        # En octavos la tabla del grupo ya no dice nada: esa fase terminó.
        chequear("al costado van los cruces de la instancia, no la tabla",
                 _oct["cajas"] == 2 and not _oct["hayTabla"], _oct)
        chequear("con el cruce de este partido marcado", _oct["marcada"] == 1,
                 _oct["marcada"])
        chequear("y la tanda de penales al lado del global", _oct["penales"],
                 _oct)
        # El link de la serie no sirve en frío —se registra recién al dibujar
        # el cuadro—, así que cada caja lleva al partido que se juega.
        chequear("cada cruce lleva a su partido", _oct["linkAlOtro"], _oct)
        chequear("y se pidió sólo las llaves, no el calendario entero",
                 _oct["soloLlaves"] and not _oct["calendarioEntero"], _oct)
    print("\n── de dónde es cada uno ──")
    # La nacionalidad ya se pedía para el plantel de un club: se piden todos
    # juntos y se guardan por jugador para siempre. Acá se engancha lo mismo
    # a las formaciones, así que un partido cuesta un pedido la primera vez
    # y ninguno después.
    chequear("las formaciones piden la nacionalidad en una sola tanda",
             "paises = nacionalidades(todos)" in _SRV
             and "for f in lineups[k] + banco[k]:" in _SRV)
    chequear("y si la fuente no contesta, la formación se muestra igual",
             _SRV.count("except Exception:\n        pass\n\n    ofic =") == 1)
    # La bandera del club va sólo donde dice algo. En la Liga Profesional
    # los treinta son argentinos y sería una columna de banderas iguales.
    chequear("el torneo internacional está marcado, y sólo los cuatro",
             [l for l in server.LIGAS if server.LIGAS[l].get("internacional")]
             == ["champions", "europa", "lib", "sud"],
             [l for l in server.LIGAS if server.LIGAS[l].get("internacional")])

    _BAND = ("https://imagecache.365scores.com/image/upload/"
             "v1/Countries/Round/")
    _XI = ("lineups:{home:[{n:1,name:'Sergio Romero',id:'1',pais:'Argentina',"
           "bandera:'%s10'},{n:5,name:'Ander Herrera',id:'2',pais:'España',"
           "bandera:'%s3'},{n:9,name:'Sin Bandera',id:'3'}],"
           "away:[{n:1,name:'Rossi',id:'4',pais:'Brasil',bandera:'%s21'}]},"
           "banco:{home:[],away:[]}, confirmada:{home:true,away:true},"
           "bancoReal:{home:true,away:true},"
           "formation:{home:'4-3-3',away:'4-4-2'}") % (_BAND, _BAND, _BAND)

    def _banderas(match):
        _js = ("""
process.on('unhandledRejection',()=>{});
const RESP={'/api/match': %s,
 '/api/liga/games': {llaves:[]}, '/api/liga': {id:'lib', nombre:'x', zonas:[]}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/partido/boca-juniors-vs-flamengo-99';
App.init();
(async()=>{
  for(let i=0;i<70;i++) await new Promise(r=>setImmediate(r));
  App.mtab('xi');
  for(let i=0;i<20;i++) await new Promise(r=>setImmediate(r));
  const m=doc.querySelector('#matches').innerHTML||'';
  console.log(JSON.stringify({
    lugares:(m.match(/xi-pais/g)||[]).length,
    conBandera:(m.match(/xi-pais"><img/g)||[]).length,
    club:(m.match(/club-pais/g)||[]).length}));
})();
""" % match)
        _gg = (open(_DOMSITO, encoding="utf-8").read()
               + "\nglobalThis.document=doc; globalThis.window=win;"
                 "\nglobalThis.location=loc; globalThis.history=historial;"
                 "\nglobalThis.localStorage=almacenLocal;"
                 "\nglobalThis.MutationObserver=MutationObserver;"
                 "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
                 "\nglobalThis.setInterval=()=>0;\nlet App;\n"
               + _app.replace("const App=(()=>{", "App=(()=>{") + _js)
        with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as _f:
            _f.write(_gg); _rb = _f.name
        _pb = _sub.run(["node", _rb], capture_output=True, text=True, timeout=60)
        os.unlink(_rb)
        return json.loads(_pb.stdout) if _pb.returncode == 0 and _pb.stdout else None

    _int = _banderas("""{id:'99', liveId:'99', liga:'lib',
  ligaNombre:'Copa Libertadores', torneo:'2026', etapa:'Octavos de final',
  round:null, status:'FIN', gh:2, ga:1, start:'2026-08-25T21:30:00Z',
  events:[], stats:[], tv:[],
  home:{name:'Boca Juniors',canon:'Boca Juniors',pais:11,bandera:'%s11'},
  away:{name:'Flamengo',canon:'Flamengo',pais:21,bandera:'%s21'}, %s}"""
                      % (_BAND, _BAND, _XI))
    _loc = _banderas("""{id:'99', liveId:'99', liga:'lpf',
  ligaNombre:'Liga Profesional', torneo:'Clausura 2026', round:5,
  status:'FIN', gh:2, ga:1, start:'2026-08-25T21:30:00Z',
  events:[], stats:[], tv:[],
  home:{name:'Boca Juniors',canon:'Boca Juniors'},
  away:{name:'River Plate',canon:'River Plate'}, %s}""" % _XI)
    chequear("en la formación va la bandera de cada jugador",
             _int and _int["conBandera"] == 3, _int)
    # El que no la tiene igual ocupa el lugar: sin eso los nombres bailan
    # entre el que tiene bandera y el que no.
    chequear("y el que no la tiene ocupa el lugar igual",
             _int and _int["lugares"] == 4, _int)
    chequear("en un torneo internacional, la bandera del país de cada club",
             _int and _int["club"] == 2, _int)
    # En la Liga Profesional los treinta son argentinos: serían treinta
    # banderas iguales diciendo nada.
    chequear("y en uno local no aparece ninguna",
             _loc and _loc["club"] == 0 and _loc["conBandera"] == 3, _loc)

    # El país del club no está donde uno lo buscaría. Los calendarios
    # guardados de la Libertadores y la Sudamericana no lo traen —se
    # guardaron antes de que el campo existiera, y de un partido ya
    # guardado sólo se refrescan la fase y la zona— y los de la Champions y
    # la Europa sí. Leyendo nada más el calendario, la bandera saldría en
    # dos torneos y en los otros dos no.
    import copy

    def _eq(n, cid, pais=None):
        d = {"id": cid, "name": n, "canon": n}
        if pais is not None:
            d["pais"] = pais
        return d

    _vivos = [{"home": _eq("Estudiantes", 100, 10),
               "away": _eq("Flamengo", 200, 21)}]
    _tabla = server.recordar_paises(_vivos)
    chequear("de la ventana en vivo se aprende de qué país es cada club",
             _tabla.get("100") == 10 and _tabla.get("200") == 21, _tabla)

    _guardado = [{"id": "9", "home": _eq("Estudiantes", 100),
                  "away": _eq("Flamengo", 200)}]
    _copia = copy.deepcopy(_guardado)
    _conb = server.con_banderas(_guardado, "lib")
    chequear("y con eso se completa el calendario que no lo trae",
             _conb[0]["home"].get("bandera", "").endswith("/10")
             and _conb[0]["away"].get("bandera", "").endswith("/21"), _conb[0])
    # La lista que llega es la que está guardada en la base: sin copiar, la
    # bandera se colaba en el calendario en el próximo `guardar`.
    chequear("sin escribirle nada al calendario guardado",
             _guardado == _copia, _guardado)
    chequear("en un torneo local no se toca ni un partido",
             server.con_banderas(_guardado, "lpf") is _guardado)
    # Inventar la bandera de un club que nunca vimos sería poner una
    # bandera equivocada, que es peor que no poner ninguna.
    _raro = [{"id": "7", "home": _eq("Club Nuevo", 999),
              "away": _eq("Otro", 998)}]
    _sr = server.con_banderas(_raro, "lib")
    chequear("y a un club que nunca vimos no se le inventa una",
             "bandera" not in _sr[0]["home"] and "bandera" not in _sr[0]["away"])
    chequear("el fixture de un torneo internacional sale con banderas",
             "games = con_banderas(games, lid)" in _SRV)
    chequear("y la portada las hereda de ahí, sin pedir nada más",
             'api_liga_games({"id": [lid]}).get("games", [])' in _SRV)
    # Y la prueba que vale: dibujar la portada con un partido de un torneo
    # internacional al lado de uno local, y mirar la fila que quedó.
    _pt = ("""
process.on('unhandledRejection',()=>{});
const eq=(n,p)=>p?{name:n,canon:n,pais:'X',bandera:'/Countries/Round/'+p}
                 :{name:n,canon:n};
const pg=(i,h,a,p)=>({id:i, liveId:i, start:'2026-08-25T21:30:00Z',
  status:'FIN', gh:1, ga:0, round:3, interzonal:false,
  home:eq(h,p&&11), away:eq(a,p&&21)});
const RESP={
 '/api/home': {date:'2026-08-25', total:2, live:0, partidazo:null, partidazos:{},
   bloques:[
    {liga:'lib', nombre:'Copa Libertadores', torneo:'2026',
     games:[pg('1','Boca Juniors','Flamengo',true)]},
    {liga:'lpf', nombre:'Liga Profesional', torneo:'Clausura',
     games:[pg('2','Aldosivi','Unión',false)]}]},
 '/api/detalles': {}, '/api/ligas':{ligas:[]}, '/api/clubes':{clubes:[]},
 '/api/visita':{}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/';
App.init();
(async()=>{
  for(let i=0;i<70;i++) await new Promise(r=>setImmediate(r));
  const p=doc.querySelector('#matches').innerHTML||'';
  const filas=p.split('class="match').slice(1);
  const inter=filas.find(f=>f.indexOf('Boca')>=0)||'';
  const local=filas.find(f=>f.indexOf('Aldosivi')>=0)||'';
  // en cada mitad, ¿la bandera va antes o después del nombre?
  const mitad=inter.indexOf('m-score');
  const izq=inter.slice(0,mitad), der=inter.slice(mitad);
  console.log(JSON.stringify({
    filas: filas.length,
    banderas: (inter.match(/club-pais/g)||[]).length,
    enElLocal: (local.match(/club-pais/g)||[]).length,
    localBanderaDespues: izq.indexOf('Boca Juniors') < izq.indexOf('club-pais'),
    visitaBanderaAntes:  der.indexOf('club-pais') < der.indexOf('Flamengo')}));
})();
""")
    _gp = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{") + _pt)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gp); _rp2 = _f.name
    _pp2 = _sub.run(["node", _rp2], capture_output=True, text=True, timeout=60)
    os.unlink(_rp2)
    _por = json.loads(_pp2.stdout) if _pp2.returncode == 0 and _pp2.stdout else None
    chequear("la portada dibuja las banderas del torneo internacional",
             _por and _por["filas"] == 2 and _por["banderas"] == 2, _por)
    chequear("y en la fila del torneo local no pone ninguna",
             _por and _por["enElLocal"] == 0, _por)
    # La fila es un espejo: si las dos banderas van antes del nombre, la del
    # local queda pegada al escudo y la del visitante suelta en el medio.
    chequear("la fila queda en espejo: local nombre–bandera, visitante bandera–nombre",
             _por and _por["localBanderaDespues"] and _por["visitaBanderaAntes"],
             _por)

    if _gru:
        chequear("en la fase de grupos sigue yendo la tabla del grupo",
                 _gru["hayTabla"] and _gru["cajas"] == 0, _gru)
        chequear("y ahí ni se piden las llaves, que no existen",
                 not _gru["soloLlaves"], _gru)
        chequear("con la fase y la fecha juntas en el encabezado",
                 _gru["encabezado"]
                 == "Copa Libertadores 2026 · Fase de grupos · Fecha 3",
                 _gru["encabezado"])

# Y la prueba que vale: abrir el link de un partido de la Champions con el
# navegador de mentira y mirar qué quedó dibujado en cada columna.
if _sh.which("node"):
    _pg = ("""
process.on('unhandledRejection',()=>{});
const eq=n=>({name:n, canon:n, logo:null, short:''});
const RESP={
 '/api/match': {id:4738312, liga:'champions', ligaNombre:'Champions League',
   torneo:'Temporada 2026-27', stage:'Fase de liga', round:null, zone:null,
   home:eq('Bayern'), away:eq('Inter'), gh:2, ga:1, status:'FIN',
   start:'2026-08-24T21:00:00-03:00', events:[], stats:[],
   lineups:{home:[],away:[]}, banco:{home:[],away:[]}},
 '/api/liga': {id:'champions', nombre:'Champions League', zonas:[
   {name:'Fase de liga', rows:[
     {pos:1, team:eq('Inter'),  pts:9, pj:4, dif:5},
     {pos:2, team:eq('Bayern'), pts:7, pj:4, dif:3},
     {pos:3, team:eq('Arsenal'),pts:4, pj:4, dif:0}]}]}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).find(x=>u.startsWith(x));
  if(!k) throw new Error('sin ruta');
  return {ok:true, status:200, json:async()=>RESP[k]};
};
loc.pathname='/partido/bayern-vs-inter-4738312';
App.init();
(async()=>{
  // se esperan unas vueltas del bucle para que terminen los pedidos; el
  // setTimeout del DOM de mentira no sirve acá porque está anulado
  for(let i=0;i<40;i++) await new Promise(r=>setImmediate(r));
  const medio=doc.querySelector('#matches').innerHTML||'';
  const der=doc.querySelector('#right').innerHTML||'';
  const menu=doc.querySelector('#side').innerHTML||'';
  const m=medio.match(/<span>([^<]*Champions[^<]*)<\\/span>/);
  console.log(JSON.stringify({
    encabezado: m?m[1].trim():'',
    marcador: medio.includes('2 - 1'),
    hayMenu: menu.includes('Liga Profesional'),
    tabla: der.includes('Arsenal'),
    resaltados: (der.match(/fila-destacada/g)||[]).length}));
})();
""")
    _g = (open(_DOMSITO, encoding="utf-8").read()
          + "\nglobalThis.document=doc; globalThis.window=win;"
            "\nglobalThis.location=loc; globalThis.history=historial;"
            "\nglobalThis.localStorage=almacenLocal;"
            "\nglobalThis.MutationObserver=MutationObserver;"
            "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
            "\nglobalThis.setInterval=()=>0;\nlet App;\n"
          + _app.replace("const App=(()=>{", "App=(()=>{") + _pg)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_g); _rp = _f.name
    _pp = _sub.run(["node", _rp], capture_output=True, text=True, timeout=60)
    os.unlink(_rp)
    _pag = json.loads(_pp.stdout) if _pp.returncode == 0 and _pp.stdout else None
    chequear("la página de un partido se arma entera", _pag is not None,
             _pp.stderr.strip().splitlines()[:2])
    if _pag:
        chequear("el encabezado dice de qué torneo y de qué etapa es",
                 _pag["encabezado"] == "Champions League Temporada 2026-27 · Fase de liga",
                 _pag["encabezado"])
        chequear("el marcador está donde tiene que estar",
                 _pag["marcador"] is True)
        chequear("el menú del sitio queda a la izquierda", _pag["hayMenu"] is True)
        chequear("y la tabla del torneo a la derecha", _pag["tabla"] is True)
        chequear("con los dos equipos del partido resaltados",
                 _pag["resaltados"] == 2, _pag["resaltados"])

    # La carrera que rompía todo: al arrancar se piden varias cosas a la
    # vez, y la lista de clubes —que llega tarde— redibujaba la portada
    # encima de lo que estuviera en pantalla. Abrías el link de un partido
    # en una pestaña nueva, veías la portada, y el partido aparecía recién
    # si lo volvías a elegir de la lista.
    _tarde = ("""
process.on('unhandledRejection',()=>{});
const eq=n=>({name:n, canon:n, logo:null, short:''});
const demora=n=>new Promise(r=>{ let i=0;
  const t=()=>{ if(++i>n) r(); else setImmediate(t); }; t(); });
const RESP={
 '/api/match': {id:4633355, liga:'lpf', ligaNombre:'Liga Profesional',
   torneo:'Clausura 2026', round:6, interzonal:true, zone:null,
   home:eq('Talleres (C)'), away:eq('Rosario Central'), gh:2, ga:2,
   status:'FIN', start:'2026-08-24T21:15:00-03:00', events:[], stats:[],
   lineups:{home:[],away:[]}, banco:{home:[],away:[]}},
 '/api/standings': {zones:[{name:'Zona A', rows:[{pos:15,
    canon:'Talleres (C)', team:eq('Talleres (C)'), pts:4, pj:6, dif:-4}]}]},
 '/api/annual': {rows:[]}, '/api/promedios': {rows:[]}, '/api/ligas': {ligas:[]},
 '/api/clubes': {clubes:[{name:'Talleres (C)', primary:'#fff', accent:'#000'}]},
 '/api/home': {total:1, live:0, bloques:[{liga:'lpf', nombre:'Liga Profesional',
    games:[{id:'z', status:'FIN', home:eq('A'), away:eq('B'), gh:0, ga:0}]}]}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).find(x=>u.startsWith(x));
  if(!k) throw new Error('sin ruta');
  if(k==='/api/clubes') await demora(25);   // llega tarde, como en la vida real
  return {ok:true, status:200, json:async()=>RESP[k]};
};
loc.pathname='/partido/talleres-c-vs-rosario-central-4633355';
App.init();
(async()=>{
  for(let i=0;i<80;i++) await new Promise(r=>setImmediate(r));
  const medio=doc.querySelector('#matches').innerHTML||'';
  console.log(JSON.stringify({partido: medio.includes('2 - 2'),
    tapado: medio.includes('ver torneo'),
    calendario: !!doc.querySelector('#days')}));
})();
""")
    _g2 = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{") + _tarde)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_g2); _rt = _f.name
    _pt = _sub.run(["node", _rt], capture_output=True, text=True, timeout=60)
    os.unlink(_rt)
    _tr = json.loads(_pt.stdout) if _pt.returncode == 0 and _pt.stdout else None
    chequear("abrir el link en una pestaña nueva muestra el partido",
             _tr and _tr["partido"] is True,
             _tr or _pt.stderr.strip().splitlines()[:4])
    chequear("y no se lo tapa la portada cuando llega la lista de clubes",
             _tr and _tr["tapado"] is False and _tr["calendario"] is False, _tr)

    # Las cuatro pestañas del panel derecho, y la marca de los dos equipos.
    _lpf = ("""
process.on('unhandledRejection',()=>{});
const eq=n=>({name:n, canon:n, logo:null, short:''});
const fila=(pos,n,extra)=>Object.assign({pos, canon:n, team:eq(n), pts:10-pos,
  pj:6, g:3, e:1, p:2, gf:8, gc:6, dif:2, form:['G','P'], live:false},
  extra||{});
const RESP={
 '/api/match': {id:4633355, liga:'lpf', ligaNombre:'Liga Profesional',
   torneo:'Clausura 2026', round:6, interzonal:true, zone:null,
   home:eq('Talleres (C)'), away:eq('Rosario Central'), gh:2, ga:2,
   status:'FIN', start:'2026-08-24T21:15:00-03:00', events:[], stats:[],
   lineups:{home:[],away:[]}, banco:{home:[],away:[]}},
 '/api/standings': {zones:[
   {name:'Zona A', rows:[fila(1,'Instituto'), fila(15,'Talleres (C)')]},
   {name:'Zona B', rows:[fila(1,'Boca Juniors')]}]},
 '/api/annual': {rows:[fila(1,'Instituto',{copa:'libertadores'}),
                       fila(20,'Talleres (C)',{copa:null})]},
 '/api/promedios': {rows:[
   fila(1,'Instituto',{prom:1.9, promMin:1.9, descendiendo:false,
     enRiesgo:false, restantes:0, p2024:60, p2025:55, p2026:12}),
   fila(28,'Talleres (C)',{prom:0.9, promMin:0.9, descendiendo:true,
     enRiesgo:false, restantes:0, p2024:30, p2025:28, p2026:4})]},
 '/api/ligas': {ligas:[]}, '/api/clubes': {clubes:[]}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).find(x=>u.startsWith(x));
  if(!k) throw new Error('sin ruta');
  return {ok:true, status:200, json:async()=>RESP[k]};
};
loc.pathname='/partido/talleres-c-vs-rosario-central-4633355';
App.init();
const ver=()=>doc.querySelector('#right').innerHTML||'';
const esperar=async()=>{ for(let i=0;i<30;i++) await new Promise(r=>setImmediate(r)); };
(async()=>{
  await esperar();
  const out={zona:(doc.querySelector('#tabs').innerHTML
                    .match(/data-t="(\\w+)" class="on"/)||[])[1],
             zonaMarca:/fila-destacada/.test(ver())&&ver().includes('Talleres')};
  App.tab('anual'); await esperar();
  out.anual=ver().includes('Instituto'); out.anualMarca=/fila-destacada/.test(ver());
  App.tab('prom');  await esperar();
  out.prom=ver().includes('Instituto');  out.promMarca=/fila-destacada/.test(ver());
  App.tab('B');     await esperar();
  out.zonaB=ver().includes('Boca'); out.zonaBsinMarca=!/fila-destacada/.test(ver());
  console.log(JSON.stringify(out));
})();
""")
    _g3 = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{") + _lpf)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_g3); _rl2 = _f.name
    _pl2 = _sub.run(["node", _rl2], capture_output=True, text=True, timeout=60)
    os.unlink(_rl2)
    _lp = json.loads(_pl2.stdout) if _pl2.returncode == 0 and _pl2.stdout else None
    chequear("el panel de la Liga Profesional se arma", _lp is not None,
             _pl2.stderr.strip().splitlines()[:2])
    if _lp:
        chequear("abre en la zona donde juegan, no en la primera",
                 _lp["zona"] == "A" and _lp["zonaMarca"] is True, _lp)
        chequear("la pestaña de Anual responde y marca a los dos",
                 _lp["anual"] and _lp["anualMarca"], _lp)
        chequear("la de Promedios también",
                 _lp["prom"] and _lp["promMarca"], _lp)
        chequear("y en la zona donde no juegan no marca a nadie",
                 _lp["zonaB"] and _lp["zonaBsinMarca"], _lp)

    # La ficha de un jugador, con la misma idea: página cuando se llega por
    # el link, y al costado la tabla donde uno lo buscaría.
    def _jugador(quien, ruta):
        _js = ("""
process.on('unhandledRejection',()=>{});
const eq=n=>({name:n, canon:n, logo:null, short:''});
const fila=(pos,n)=>({pos, canon:n, team:eq(n), pts:10-pos, pj:6, g:3, e:1,
  p:2, gf:8, gc:6, dif:2, form:['G'], live:false});
const RESP={
 '/api/atleta': %s,
 '/api/scorers': {rows:[
   {rank:1, name:'Adrián Martínez', team:eq('Racing'), goals:9},
   {rank:2, name:'Enzo Fernandez',  team:eq('River Plate'), goals:7}]},
 '/api/standings': {zones:[{name:'Zona A', rows:[fila(1,'Instituto'),
   fila(7,'River Plate')]}]},
 '/api/ligas':{ligas:[]}, '/api/clubes':{clubes:[]}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).find(x=>u.startsWith(x));
  if(!k) throw new Error('sin ruta');
  return {ok:true, status:200, json:async()=>RESP[k]};
};
loc.pathname='%s';
App.init();
(async()=>{
  for(let i=0;i<60;i++) await new Promise(r=>setImmediate(r));
  const medio=doc.querySelector('#matches').innerHTML||'';
  const der=doc.querySelector('#right').innerHTML||'';
  console.log(JSON.stringify({
    enLaPagina: medio.includes('Ficha de jugador'),
    enElPopUp: (doc.querySelector('#modalBox').innerHTML||'').includes('Ficha'),
    hayMenu: (doc.querySelector('#side').innerHTML||'').includes('Liga Profesional'),
    panel: der.includes('Goleadores') ? 'goleadores'
         : der.includes('Zona A') ? 'posiciones' : '',
    marcados: (der.match(/fila-destacada/g)||[]).length}));
})();
""" % (quien, ruta))
        _gg = (open(_DOMSITO, encoding="utf-8").read()
               + "\nglobalThis.document=doc; globalThis.window=win;"
                 "\nglobalThis.location=loc; globalThis.history=historial;"
                 "\nglobalThis.localStorage=almacenLocal;"
                 "\nglobalThis.MutationObserver=MutationObserver;"
                 "\nglobalThis.URL=URL2; globalThis.requestAnimationFrame=f=>0;"
                 "\nglobalThis.setInterval=()=>0;\nlet App;\n"
               + _app.replace("const App=(()=>{", "App=(()=>{") + _js)
        with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as _f:
            _f.write(_gg); _rj = _f.name
        _pj2 = _sub.run(["node", _rj], capture_output=True, text=True, timeout=60)
        os.unlink(_rj)
        return json.loads(_pj2.stdout) if _pj2.returncode == 0 and _pj2.stdout else None

    _gol = _jugador("{name:'Enzo Fernandez', liga:'lpf', team:'River Plate',"
                    " goals:7, rank:2, pj:12, carrera:[], transfermarkt:'http://x'}",
                    "/jugador/enzo-fernandez")
    _def = _jugador("{name:'Marcos Rojo', liga:'lpf', team:'River Plate',"
                    " pj:12, carrera:[], transfermarkt:'http://x'}",
                    "/jugador/marcos-rojo")
    chequear("la ficha de un jugador también se arma como página",
             _gol and _gol["enLaPagina"] and not _gol["enElPopUp"]
             and _gol["hayMenu"], _gol)
    chequear("al goleador se le pone la tabla de goleadores, con él marcado",
             _gol and _gol["panel"] == "goleadores" and _gol["marcados"] == 1,
             _gol)
    # Un defensor sin goles en la tabla de goleadores no dice nada; su club
    # en la tabla de posiciones, sí.
    chequear("y al que no convirtió, la de posiciones con su club marcado",
             _def and _def["panel"] == "posiciones" and _def["marcados"] == 1,
             _def)
# La página también arma el nombre desde la dirección mientras espera la
# respuesta, así que tiene que escribirlo igual que el servidor.
chequear("y la página lo escribe igual mientras espera la respuesta",
         "const nombreDeSlug=s=>" in HTML
         and "p.charAt(0).toUpperCase()+p.slice(1)" in HTML
         and "d.nombre||nombreDeSlug(d.slug)" in HTML)


print("\n── \"lo que viene\" no es la lista de al lado otra vez ──")
# Mostraba los seis primeros partidos del día: a las diez de la mañana, eso
# es todo lo que va a pasar hasta la noche. Ahora es una ventana de dos
# horas con piso y techo, porque ninguna de las dos reglas sola sirve.
if _sh.which("node"):
    _i = HTML.index("  const VENTANA_HORAS =")
    _j = HTML.index("  // Panel derecho de la portada")
    _lv = ("let S={};const hhmm=s=>new Date(s).toISOString().slice(11,16);\n"
           + HTML[_i:_j] + """
const T0=Date.parse('2026-08-24T18:00:00Z');
const p=m=>({status:'PROG', start:new Date(T0+m*60000).toISOString()});
const out={};
const caso=(n,mins)=>{ S={games:mins.map(p)};
  out[n]=loQueViene(T0).map(m=>faltaPara(m.start,T0)); };
caso('sabadoCargado', [5,20,35,50,65,80,95,240]);
caso('martesTranquilo', [200,300,420]);
caso('unoSolo', [180]);
caso('todoEmpezado', []);
caso('bordeDeLaVentana', [119,121,400]);
caso('inminente', [3,45,300]);
console.log(JSON.stringify(out));
""")
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_lv); _rl = _f.name
    _pl = _sub.run(["node", _rl], capture_output=True, text=True, timeout=60)
    os.unlink(_rl)
    _lq = json.loads(_pl.stdout) if _pl.returncode == 0 else None
    chequear("la selección corre", _lq is not None,
             _pl.stderr.strip().splitlines()[:2])
    if _lq:
        chequear("un sábado cargado no llena la columna: cinco y basta",
                 len(_lq["sabadoCargado"]) == 5, _lq["sabadoCargado"])
        chequear("un martes sin nada cerca igual muestra los que siguen",
                 len(_lq["martesTranquilo"]) == 2
                 and all(":" in x for x in _lq["martesTranquilo"]),
                 _lq["martesTranquilo"])
        chequear("con un solo partido en el día, ése",
                 len(_lq["unoSolo"]) == 1, _lq["unoSolo"])
        chequear("y si ya empezaron todos, la sección no aparece",
                 _lq["todoEmpezado"] == [], _lq["todoEmpezado"])
        chequear("el piso alcanza al que quedó justo afuera de la ventana",
                 len(_lq["bordeDeLaVentana"]) == 2, _lq["bordeDeLaVentana"])
        # Lo que le da sentido a la sección: no hay que hacer la cuenta.
        chequear("lo que está por empezar dice cuánto falta, no la hora",
                 _lq["inminente"][0] == "en 3 min"
                 and _lq["inminente"][1] == "en 45 min", _lq["inminente"])
        chequear("y lo lejano vuelve al reloj, que se lee mejor",
                 ":" in _lq["martesTranquilo"][0], _lq["martesTranquilo"])
chequear("la ventana y los topes están a la vista para cambiarlos",
         "const VENTANA_HORAS = 2, VIENEN_MINIMO = 2, VIENEN_MAXIMO = 5;" in HTML)
# En el partidazo y en "lo que viene" los partidos vienen sueltos, mezclados
# de todas las competencias: sin decir de cuál es, uno lee "Sabah – Hapoel
# Beer Sheva" y no sabe qué está mirando.
chequear("el partidazo y lo que viene dicen de qué competencia son",
         "const deQueTorneo = m => m && m.ligaNombre" in HTML
         and "${deQueTorneo(golazo)}" in HTML
         and "${m.ligaNombre?`<div style=\"font-size:10px" in HTML)


print("\n── el filtro de \"en vivo\" en la portada ──")
# Apretar "en vivo" en la portada llamaba al dibujante de un torneo, que
# agrupa por zonas: quedaban los partidos correctos con los títulos de otra
# cosa —"Interzonal" arriba de la Europa League—.
chequear("cada pantalla usa su propio dibujante",
         "if(S.liga==='home') pintarPortada(); else drawMatches();" in HTML)
if _sh.which("node"):
    _i = HTML.index("  function pintarPortada(){")
    _j = HTML.index("  async function loadHome(){")
    _fv = ("let S={onlyLive:false, home:null};\nconst pintado={};\n"
           "const esc=s=>String(s==null?'':s);\n"
           "const matchRow=m=>'[fila '+m.id+']';\n"
           "const Rutas={url:()=>'/x'};\n"
           "const $=sel=>({set innerHTML(v){pintado[sel]=v;},"
           " get innerHTML(){return pintado[sel]||'';},"
           " set textContent(v){}, classList:{toggle(){}}});\n"
           + HTML[_i:_j] + """
const B=(liga,nombre,vivos,otros)=>({liga,nombre,games:
  [].concat(Array.from({length:vivos},(_,k)=>({id:liga+'v'+k,status:'LIVE'})),
            Array.from({length:otros},(_,k)=>({id:liga+'f'+k,status:'FIN'})))});
S.home={total:9, live:2, bloques:[B('lpf','Liga Profesional',0,3),
  B('europa','Europa League',2,2), B('lib','Copa Libertadores',0,2)]};
const titulos=()=>(pintado['#matches'].match(/class="nm">([^<]+)/g)||[])
  .map(s=>s.replace(/.*">/,''));
S.onlyLive=false; pintarPortada(); const todos=titulos();
S.onlyLive=true;  pintarPortada(); const soloVivo=titulos();
S.home.bloques.forEach(b=>b.games=b.games.filter(m=>m.status!=='LIVE'));
pintarPortada();
console.log(JSON.stringify({todos, soloVivo,
  cartel: pintado['#matches'].includes('No hay partidos en vivo')}));
""")
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_fv); _rf = _f.name
    _pf = _sub.run(["node", _rf], capture_output=True, text=True, timeout=60)
    os.unlink(_rf)
    _fq = json.loads(_pf.stdout) if _pf.returncode == 0 else None
    chequear("la portada se dibuja con el filtro puesto", _fq is not None,
             _pf.stderr.strip().splitlines()[:2])
    if _fq:
        chequear("los títulos son de torneo y no de zona",
                 _fq["todos"] == ["Liga Profesional", "Europa League",
                                  "Copa Libertadores"], _fq["todos"])
        chequear("con el filtro puesto queda sólo el torneo que tiene algo rodando",
                 _fq["soloVivo"] == ["Europa League"], _fq["soloVivo"])
        chequear("y si no hay ninguno, lo dice en vez de quedar en blanco",
                 _fq["cartel"] is True)


print("\n── la página de administración ──")
_ADM = open(os.path.join(AQUI, "admin.html"), encoding="utf-8").read()
chequear("no es pública", "/admin" in server.PRIVADAS)
chequear("y no se guarda en la caché de nadie",
         'minutos=0' in _SRV and '"private, no-store" if not minutos' in _SRV)
chequear("no se enlaza desde el sitio ni se deja indexar",
         'content="noindex, nofollow"' in _ADM
         and "/admin" not in HTML)
chequear("junta las cinco direcciones en un solo pedido paralelo",
         all(("pedir('%s')" % r) in _ADM for r in
             ("/api/tiempos", "/api/base", "/api/contenido",
              "/api/recorrido", "/api/diagnostico")))
chequear("la llave no queda guardada en el navegador",
         "localStorage" not in _ADM and "sessionStorage" not in _ADM)
chequear("y si la llave está mal, lo dice en criollo",
         "Esa llave no es" in _ADM)
# Lo que tiene que saltar solo, sin leer números: el disco llenándose es
# la falla que rompe feo y de madrugada.
chequear("el disco llenándose se pinta antes de ser un problema",
         "pc > 85 ? 'mal' : pc > 60 ? 'mirar' : 'ok'" in _ADM)
chequear("y una base que no sobrevive a las publicaciones también",
         "sobrevive_al_deploy === false" in _ADM)


print("\n── abrir de cero: los dos viajes se superponen ──")
# Abrir la página era: bajar el HTML, leer 220 KB de javascript, y RECIÉN
# AHÍ pedir los partidos. Dos esperas en fila con la lectura en el medio.
# Ahora el pedido sale en la primera línea del HTML, antes del programa.
chequear("el pedido arranca antes de leer el programa",
         "window.__ADELANTO__" in HTML
         and HTML.index("window.__ADELANTO__") < HTML.index("<style>"))
chequear("y sólo adivina las dos puertas por las que entra casi todo el mundo",
         "'/api/home?date=' + d" in HTML and "'/api/rounds'" in HTML
         and "return null;" in HTML)
chequear("el que pide después usa esa respuesta en vez de pedirla de nuevo",
         "if(a && a.url===path && a.promesa){" in HTML
         and "a.promesa=null;" in HTML)
chequear("y si algo falla, se pide como siempre",
         "}catch(e){ return null; }" in HTML)
# La dirección que arma el adelanto tiene que ser idéntica a la que después
# pide la página; si no, se hacen dos pedidos en vez de uno.
_m = re.search(r"const ymd=d=>`([^`]+)`", HTML)
chequear("la fecha del adelanto se escribe igual que la de la página",
         _m and _m.group(1) == "${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}"
         and "String(hoy.getMonth()+1).padStart(2,'0')" in HTML,
         _m and _m.group(1))


print("\n── el marcador y los goles cuentan lo mismo ──")
# El marcador sale de la lista de partidos y los goles del detalle de cada
# uno, y no se piden al mismo tiempo. Cuando entra un gol, el detalle se
# entera primero: la fila de Newell's decía 0-0 con "Cóccaro 51'" escrito
# abajo. Los dos datos eran ciertos; mostrarlos juntos era el error.
if _sh.which("node"):
    # se saca la función tal cual está en la página y se la corre con un S
    # de mentira: prueba la cuenta de verdad, no el texto del código
    _d = HTML.index("  function marcadorVivo(m){")
    _h = HTML.index("  const claseLado=(m,local)=>{")
    _js = ("const S={detalles:{}};\n" + HTML[_d:_h] + """
const gol=(side,anulado)=>({side, min:51, player:'Cóccaro', anulado,
                            penales:false});
const vivo={id:'x', status:'LIVE', gh:0, ga:0};
S.detalles={x:{goles:[gol('h',false)]}};
const conGol=marcadorVivo(vivo);
S.detalles={x:{goles:[gol('h',true)]}};       // el VAR lo anula
const anulado=marcadorVivo(vivo);
S.detalles={x:{goles:[{side:'h',min:10,player:'',anulado:false,penales:false}]}};
const terminado=marcadorVivo({id:'x', status:'FIN', gh:2, ga:3});
console.log(JSON.stringify({conGol, anulado, terminado,
  pinta:htmlMarcador(vivo).indexOf('0-0')}));
""")
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_js); _rr = _f.name
    _s = _sub.run(["node", _rr], capture_output=True, text=True,
                     timeout=60)
    os.unlink(_rr)
    _marc = json.loads(_s.stdout) if _s.returncode == 0 else None
    chequear("la cuenta del marcador corre", _marc is not None,
             _s.stderr.strip().splitlines()[:2])
    if _marc:
        chequear("un gol que todavía no llegó al marcador igual se cuenta",
                 _marc["conGol"] == {"gh": 1, "ga": 0}, _marc["conGol"])
        chequear("y si lo anulan, vuelve a mandar el marcador oficial",
                 _marc["anulado"] == {"gh": 0, "ga": 0}, _marc["anulado"])
        chequear("terminado el partido manda siempre el oficial",
                 _marc["terminado"] == {"gh": 2, "ga": 3}, _marc["terminado"])
        chequear("y la fila ya no puede decir 0-0 con un gol escrito abajo",
                 _marc["pinta"] == -1, _marc["pinta"])
chequear("el marcador nunca va para atrás",
         "Math.max(m.gh??0, cuantos('h'))" in HTML)
chequear("y al llegar los goles se repinta la fila, no sólo el pie",
         "if(m.status==='LIVE') actualizarFila(fila,m);" in HTML)


print("\n── sacar la basura sin llevarse lo que sirve ──")
# La base sólo crecía. Había dos funciones escritas para limpiarla y a
# ninguna la llamaba nadie — y con razón: `almacen.limpiar` borraba por
# fecha sin mirar qué era cada fila, así que se llevaba puesto justo lo que
# no caduca. Ahora el prefijo es obligatorio.
try:
    server.almacen.limpiar("", 60)
    _obligatorio = False
except ValueError:
    _obligatorio = True
chequear("borrar por fecha a secas ya no se puede", _obligatorio)

# La prueba de fondo se corre contra una base aparte: acá se borra de
# verdad, y no es cosa de hacerlo sobre la del proyecto.
import subprocess as _sb2, tempfile as _tp2, textwrap as _tw2
_guion = _tw2.dedent("""
    import os, time, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import almacen, server
    VIEJO = time.time() - 60*60*24*200
    gordo = {"x": "y"*40000}
    B = "sc:https://webws.365scores.com/web/"
    # basura: caché que nadie pide hace doscientos días
    for p in ("standings", "games/current", "games/fixtures",
              "games/results", "athletes", "stats"):
        almacen.guardar(B+p+"/?a=1", gordo)
    # el detalle de un partido, de los mismos doscientos días
    almacen.guardar(B+"game/?gameId=123", gordo)
    # y lo que no caduca nunca
    for k in ("carrera:messi", "pj:lpf:messi", "fixture:102", "goles:lpf:99",
              "hist:lpf", "plantel:boca", "nac:110543"):
        almacen.guardar(k, gordo)
    with almacen._lock:
        c = almacen._con()
        c.execute("UPDATE datos SET guardado=?", (VIEJO,)); c.commit()
    # y una de la misma familia pero de recién: se está usando
    almacen.guardar(B+"standings/?a=2", gordo)
    antes_bytes = almacen.estado()["bytes"]
    antes = set(almacen.claves())
    r = server.limpieza_diaria()
    quedan = set(almacen.claves())
    print(json.dumps({
        "borradas": sorted(k[:60] for k in antes - quedan),
        "elPartidoSigue": (B+"game/?gameId=123") in quedan,
        "laFrescaSigue": (B+"standings/?a=2") in quedan,
        "loQueNoCaduca": sorted(k for k in quedan if not k.startswith("sc:")),
        "dijoFilas": r["filas"],
        "achico": antes_bytes - almacen.estado()["bytes"],
        "dosVecesNoHaceNada": server.limpieza_diaria() is None,
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion); _gp3 = _f.name
_dbtmp = os.path.join(_tp2.gettempdir(), "hayvar_limpieza_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_dbtmp + _ext):
        os.unlink(_dbtmp + _ext)
_pl = _sb2.run([sys.executable, _gp3, _dbtmp, AQUI],
               capture_output=True, text=True, timeout=120)
os.unlink(_gp3)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_dbtmp + _ext):
        os.unlink(_dbtmp + _ext)
_lim = None
for _linea in _pl.stdout.splitlines():
    if _linea.startswith("{"):
        _lim = json.loads(_linea)
chequear("la limpieza corre entera", _lim is not None,
         (_pl.stdout[-200:], _pl.stderr[-300:]))
if _lim:
    chequear("se lleva las seis familias de caché que ya nadie pide",
             len(_lim["borradas"]) == 6, _lim["borradas"])
    # Lo que pidió Mateo, y es la regla: los partidos y los jugadores no se
    # tocan. Alguien puede querer ver un partido viejo, y las comparaciones
    # entre temporadas se hacen justamente con eso.
    chequear("el detalle de un partido viejo se queda", _lim["elPartidoSigue"])
    chequear("y las carreras, los planteles y los calendarios también",
             _lim["loQueNoCaduca"] ==
             ["carrera:messi", "fixture:102", "goles:lpf:99", "hist:lpf",
              "limpieza:ultima", "nac:110543", "pj:lpf:messi", "plantel:boca"],
             _lim["loQueNoCaduca"])
    # Lo que se sigue usando se reescribe solo cada vez que vence: por eso
    # mirar la última escritura alcanza para saber si alguien lo pide.
    chequear("una entrada de esta semana no se toca aunque sea de la misma familia",
             _lim["laFrescaSigue"])
    # Sin el VACUUM, SQLite marca el espacio libre y no devuelve un mega.
    chequear("y el archivo achica de verdad, no sólo la tabla",
             _lim["achico"] > 100000, _lim["achico"])
    chequear("corre una vez por día y no en cada vuelta",
             _lim["dosVecesNoHaceNada"])
# El administrador tiene que decir qué está ocupando el disco: "202 MB" solo
# no dice qué hacer.
chequear("el administrador muestra el peso de cada familia",
         "pesos=almacen.pesos()" in _SRV and "def pesos():" in open(os.path.join(AQUI, "almacen.py"),
                               encoding="utf-8").read())
chequear("y qué familias se limpian y cada cuánto",
         "cacheQueSobra=" in _SRV and "diasDeCache=" in _SRV)
# La familia más pesada es el detalle de los partidos, y es justo la que no
# se toca: que no se cuele en la lista por descuido.
chequear("el detalle de los partidos no está en la lista de lo que se tira",
         not any("web/game" in p and "games" not in p
                 for p in server.CACHE_QUE_SOBRA),
         server.CACHE_QUE_SOBRA)
chequear("las visitas viejas también se van, que no son de nadie",
         'hecho["visitas"] = visitas.limpiar()' in _SRV)

# Y que el administrador lo muestre de verdad: se corre la función tal cual
# está en admin.html con una base de mentira, y se mira qué dibujó.
if _sh.which("node"):
    _base_falsa = json.dumps({
        "bytes": 12000000, "entradas": 45, "sobrevive_al_deploy": True,
        "pesos": [{"familia": "sc:game", "filas": 30, "bytes": 9000000, "dias": 40},
                  {"familia": "sc:standings", "filas": 10, "bytes": 2000000, "dias": 40},
                  {"familia": "carrera", "filas": 5, "bytes": 900000, "dias": 40}],
        "cacheQueSobra": ["sc:standings", "sc:games/current", "sc:athletes"],
        "diasDeCache": 30})
    _jsadm = re.findall(r"<script>(.*?)</script>", _ADM, re.S)[-1]
    _jsadm = _jsadm.split("/* ── armar todo")[0]
    _cola = ("""
const base = __BASE__;
const s = queOcupa(base);
console.log(JSON.stringify({
  filas: (s.match(/<tr>/g)||[]).length,
  seQueda: (s.match(/se queda/g)||[]).length,
  seTira: (s.match(/se tira a los 30/g)||[]).length,
  elPartidoSeQueda: s.indexOf('sc:game<') >= 0
                    && s.split('sc:game<')[1].indexOf('se queda')
                       < s.split('sc:game<')[1].indexOf('se tira'),
  diceElPrecio: s.indexOf('25 centavos') >= 0}));
""").replace("__BASE__", _base_falsa)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write("globalThis.location={search:'',hash:''};\n" + _jsadm + _cola)
        _ra = _f.name
    _pa = _sub.run(["node", _ra], capture_output=True, text=True, timeout=60)
    os.unlink(_ra)
    _adm = json.loads(_pa.stdout) if _pa.returncode == 0 and _pa.stdout else None
    chequear("el administrador dibuja el desglose del disco", _adm is not None,
             _pa.stderr.strip().splitlines()[:2])
    if _adm:
        chequear("con una fila por familia", _adm["filas"] == 4, _adm)
        chequear("diciendo cuál se tira y cuál se queda",
                 _adm["seTira"] == 1 and _adm["seQueda"] == 2, _adm)
        # La familia más pesada es el detalle de los partidos: tiene que
        # quedar dicho ahí mismo que ésa no se toca.
        chequear("y que el detalle de los partidos se queda",
                 _adm["elPartidoSeQueda"], _adm)
        # Porque si el disco molesta, la salida es agrandarlo, no borrar
        # partidos: son 25 centavos de dólar por giga por mes.
        chequear("con el precio del disco a la vista", _adm["diceElPrecio"])

print("\n── no guardar lo que nadie va a volver a leer ──")
# El 84% del disco eran 2.638 respuestas crudas de partidos, 161 MB, y no
# las dejaba la gente abriendo partidos: las dejaba nuestro propio buscador
# de goles, que recorre todos los calendarios y pide el detalle de cada uno
# para sacar quién convirtió. De ahí salen los goles, quiénes jugaron y el
# canal —todo guardado aparte— y el crudo de sesenta kilobytes queda por el
# solo hecho de que `fetch` cachea todo lo que pide.
_guion2 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import almacen, server

    ev = lambda pid, mn, cid: {"playerId": pid, "gameTime": mn,
                               "eventType": {"id": 1, "name": "Gol"},
                               "competitorId": cid, "subType": {"name": ""}}
    P = {"game": {"id": 99, "statusText": "Finalizado",
        "gameTimeAndStatusDisplayType": 2,
        "homeCompetitor": {"id": 1, "name": "Boca Juniors", "score": 2,
            "lineups": {"members": [{"id": 10, "jerseyNumber": 9, "status": 1}]}},
        "awayCompetitor": {"id": 2, "name": "River Plate", "score": 1,
            "lineups": {"members": [{"id": 20, "jerseyNumber": 7, "status": 1}]}},
        "members": [{"id": 10, "name": "Miguel Merentiel"},
                    {"id": 20, "name": "Facundo Colidio"}],
        "events": [ev(10, 23, 1), ev(10, 55, 1), ev(20, 70, 2)],
        "tvNetworks": [{"name": "ESPN"}]}}

    class F:
        def read(self): return json.dumps(P).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    n = [0]
    def falso(req, timeout=None):
        n[0] += 1
        return F()
    server.urlopen = falso
    sc = lambda: len([k for k in almacen.claves() if k.startswith("sc:")])

    # el recolector, con el partido ya terminado
    d = server.detalle_liviano("99", en_juego=False, liga="lpf")
    crudoTerminado = sc()
    guardado = sorted(k for k in almacen.claves() if not k.startswith("sc:"))
    # el mismo pedido otra vez: tiene que salir de memoria, no de la fuente
    server.detalle_liviano("99", en_juego=False, liga="lpf")
    pedidosTrasRepetir = n[0]
    # y un partido en juego sí se guarda: ahí el respaldo vale
    server.detalle_liviano("77", en_juego=True, liga="lpf")
    crudoEnJuego = sc()

    # Y la pregunta que importa: un partido viejo, sin nada cacheado,
    # ¿sigue mostrando todo en su página?
    n[0] = 0
    m = server.api_match({"id": ["99"], "liga": ["lpf"]})
    print(json.dumps({
        "crudoTerminado": crudoTerminado,
        "crudoEnJuego": crudoEnJuego,
        "pedidosTrasRepetir": pedidosTrasRepetir,
        "goles": [(g["min"], g["player"]) for g in (d.get("goles") or [])],
        "guardado": guardado,
        "pedidosDeLaPagina": n[0],
        "marcador": [m.get("gh"), m.get("ga")],
        "formaciones": len(m["lineups"]["home"]) + len(m["lineups"]["away"]),
        "eventos": len(m.get("events") or []),
        "canal": m.get("tv"),
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion2); _gp4 = _f.name
_db2 = os.path.join(_tp2.gettempdir(), "hayvar_fetch_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db2 + _ext):
        os.unlink(_db2 + _ext)
_pf = _sb2.run([sys.executable, _gp4, _db2, AQUI],
               capture_output=True, text=True, timeout=120)
os.unlink(_gp4)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db2 + _ext):
        os.unlink(_db2 + _ext)
_fe = None
for _linea in _pf.stdout.splitlines():
    if _linea.startswith("{"):
        _fe = json.loads(_linea)
chequear("el recolector corre entero", _fe is not None,
         (_pf.stdout[-200:], _pf.stderr[-400:]))
if _fe:
    chequear("un partido terminado no deja el crudo en la base",
             _fe["crudoTerminado"] == 0, _fe["crudoTerminado"])
    # Mientras se juega sí: ahí tener lo último bueno vale algo si la fuente
    # se cae, y son unas pocas decenas de partidos a la vez, no miles.
    chequear("uno en juego sí, que es cuando el respaldo sirve",
             _fe["crudoEnJuego"] == 1, _fe["crudoEnJuego"])
    # No guardar en la base no significa pedirlo de nuevo cada vez: la
    # memoria lo sigue cacheando, así que no cuesta un pedido más.
    chequear("y no se pide dos veces: la memoria lo sigue cacheando",
             _fe["pedidosTrasRepetir"] == 1, _fe["pedidosTrasRepetir"])
    # Lo que hacía falta del partido ya salió y quedó guardado aparte: eso
    # es lo que hace que tirar el crudo no pierda nada.
    chequear("los goles salen igual",
             _fe["goles"] == [[23, "Miguel Merentiel"], [55, "Miguel Merentiel"],
                              [70, "Facundo Colidio"]], _fe["goles"])
    chequear("y quedan guardados los goles, las carreras, los planteles y el canal",
             _fe["guardado"] == ["carrera:facundo colidio",
                                 "carrera:miguel merentiel", "goles:lpf:99",
                                 "golesidx:lpf", "pj:lpf:facundo colidio",
                                 "pj:lpf:miguel merentiel", "plantel:boca juniors",
                                 "plantel:river plate", "tv:lpf:99"],
             _fe["guardado"])
    # La pregunta de Mateo: sin el crudo guardado, ¿la página de un partido
    # viejo sigue mostrando todo? La página pide el partido por su cuenta.
    chequear("y la página de un partido viejo sigue mostrando todo",
             _fe["marcador"] == [2, 1] and _fe["formaciones"] == 2
             and _fe["eventos"] == 3 and _fe["canal"] == ["ESPN"], _fe)
    chequear("con un solo pedido, igual que antes",
             _fe["pedidosDeLaPagina"] == 1, _fe["pedidosDeLaPagina"])

print("\n── qué miraron, no sólo por dónde entraron ──")
# La página no recarga al cambiar de pantalla: cada torneo, cada partido y
# cada jugador tienen su dirección pero es el mismo documento. Así que si el
# navegador no avisa, lo único que queda anotado es la puerta de entrada.
_guion3 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import almacen, visitas

    vid = visitas.anotar({"huella": "abc", "ruta": "/partido/boca-vs-river-99",
                          "fuente": "Google", "intencion": "lpf"})
    v0 = [x for x in almacen.leer("vis:ultimas")[0] if x["id"] == vid][0]

    # la de entrada ya está anotada: avisarla de nuevo no suma
    repetida = visitas.mirar(vid, "/partido/boca-vs-river-99")
    # el recorrido de verdad
    for r in ["/lpf", "/laliga", "/jugador/enzo-fernandez", "/lpf"]:
        visitas.mirar(vid, r)
    # dos veces la misma seguida: no es una pantalla nueva
    seguida = visitas.mirar(vid, "/lpf")
    # y una visita que ya no está en el anillo
    fantasma = visitas.mirar("2020-01-01-nadie", "/lpf")

    v = [x for x in almacen.leer("vis:ultimas")[0] if x["id"] == vid][0]
    dia = almacen.leer("vis:dia:%s" % visitas.hoy())[0]

    # el tope del detalle: veinte pantallas más, y el camino no crece
    for i in range(20):
        visitas.mirar(vid, "/torneo-%d" % i)
    v2 = [x for x in almacen.leer("vis:ultimas")[0] if x["id"] == vid][0]

    print(json.dumps({
        "alEntrar": {"vistas": v0.get("vistas"), "vio": v0.get("vio")},
        "repetida": repetida, "seguida": seguida, "fantasma": fantasma,
        "camino": v.get("vio"), "vistas": v.get("vistas"),
        "delDia": dia.get("paginasVistas"),
        "visitasDelDia": dia.get("vistas"),
        "paginasDelDia": sorted(dia.get("paginas", {})),
        "tope": len(v2.get("vio")), "cuentaIgual": v2.get("vistas"),
        "empiezaPorDondeAnduvo": (v2.get("vio") or [None])[0],
        "resumen": {k: visitas.resumen(2)["hoy"][k]
                    for k in ("vistas", "paginas", "paginasPorVisita")},
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion3); _gp5 = _f.name
_db3 = os.path.join(_tp2.gettempdir(), "hayvar_vis_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db3 + _ext):
        os.unlink(_db3 + _ext)
_pv = _sb2.run([sys.executable, _gp5, _db3, AQUI],
               capture_output=True, text=True, timeout=120)
os.unlink(_gp5)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db3 + _ext):
        os.unlink(_db3 + _ext)
_vi = None
for _linea in _pv.stdout.splitlines():
    if _linea.startswith("{"):
        _vi = json.loads(_linea)
chequear("el registro de recorrido corre entero", _vi is not None,
         (_pv.stdout[-200:], _pv.stderr[-400:]))
if _vi:
    chequear("una visita nace con su pantalla de entrada contada",
             _vi["alEntrar"] == {"vistas": 1, "vio": []}, _vi["alEntrar"])
    chequear("y queda el camino que hizo, en orden",
             _vi["camino"] == ["/lpf", "/laliga", "/jugador/enzo-fernandez",
                               "/lpf"], _vi["camino"])
    # Volver a la misma pantalla en la que ya estás pasa seguido con el
    # botón de atrás, y no es una pantalla nueva. Pero ir a un partido y
    # volver al torneo sí: por eso se miran sólo las consecutivas.
    chequear("avisar dos veces seguidas la misma no suma", _vi["seguida"] is False)
    chequear("ni avisar de nuevo la de entrada", _vi["repetida"] is False)
    chequear("pero volver a una donde ya estuviste, sí",
             _vi["camino"].count("/lpf") == 2, _vi["camino"])
    chequear("la cuenta de la visita suma la de entrada y las demás",
             _vi["vistas"] == 5, _vi["vistas"])
    chequear("el día cuenta páginas y visitas por separado",
             _vi["delDia"] == 5 and _vi["visitasDelDia"] == 1, _vi)
    chequear("y las páginas del día son todas las que se miraron",
             _vi["paginasDelDia"] == ["/jugador/enzo-fernandez", "/laliga",
                                      "/lpf", "/partido/boca-vs-river-99"],
             _vi["paginasDelDia"])
    # El detalle del camino tiene tope: es lo único que podría crecer sin
    # freno. El total se sigue contando, para poder distinguir una visita
    # de treinta pantallas de una de doce.
    chequear("el camino guardado tiene tope",
             _vi["tope"] == visitas.PANTALLAS_POR_VISITA, _vi["tope"])
    chequear("pero la cuenta sigue subiendo igual",
             _vi["cuentaIgual"] == 25, _vi["cuentaIgual"])
    # Se guardan las primeras, no las últimas: lo que interesa es por dónde
    # empezó a moverse, no dónde terminó.
    chequear("y guarda por dónde empezó, no dónde terminó",
             _vi["empiezaPorDondeAnduvo"] == "/lpf",
             _vi["empiezaPorDondeAnduvo"])
    chequear("una visita que ya se cayó del anillo no rompe nada",
             _vi["fantasma"] is False)
    chequear("el administrador recibe las dos cuentas",
             _vi["resumen"] == {"vistas": 1, "paginas": 25,
                                "paginasPorVisita": 25.0}, _vi["resumen"])
# Los dos datos llegan por el mismo pedido: al cambiar de pantalla se
# aprovecha el viaje para actualizar el reloj.
chequear("la página avisa la pantalla y el reloj en el mismo viaje",
         "'v='+encodeURIComponent(vid)+'&r='+encodeURIComponent(ruta)" in HTML
         and "+'&seg='+contar()" in HTML)
chequear("y el servidor los atiende a los dos",
         "visitas.mirar(v, ruta)" in _SRV and 'if q.get("seg"):' in _SRV)

# Y la prueba que vale: navegar de verdad con el navegador de mentira,
# entrando por un partido y pasando por seis pantallas.
if _sh.which("node"):
    _nav = ("""
process.on('unhandledRejection',()=>{});
const avisos=[]; const eq=n=>({name:n, canon:n});
const RESP={
 '/api/visita': {v:'2026-08-25-abc123', quiere:'lpf', region:'AR'},
 '/api/match': {id:'99', liveId:'99', liga:'lpf', ligaNombre:'Liga Profesional',
   torneo:'Clausura', round:5, status:'FIN', gh:2, ga:1, events:[], stats:[],
   tv:[], start:'2026-08-25T21:30:00Z', home:eq('Boca'), away:eq('River'),
   lineups:{home:[],away:[]}, banco:{home:[],away:[]}, confirmada:{},
   bancoReal:{}, formation:{}},
 '/api/atleta': {name:'Enzo Fernandez', liga:'lpf', team:'River', pj:5,
   carrera:[]},
 '/api/home': {date:'2026-08-25', total:0, live:0, bloques:[], partidazos:{}},
 '/api/liga/games': {games:[], rounds:[], llaves:[]},
 '/api/liga': {zonas:[], anual:[], goleadores:[]},
 '/api/scorers': {rows:[]}, '/api/standings': {zones:[]}, '/api/detalles': {},
 '/api/ligas': {ligas:[]}, '/api/clubes': {clubes:[]}};
globalThis.fetch=async(u)=>{
  if(u.indexOf('/api/visita?')===0){
    avisos.push(u);
    // el aviso de la visita tarda: mientras tanto la persona ya navegó
    if(u.indexOf('v=')<0)
      for(let i=0;i<40;i++) await new Promise(r=>setImmediate(r));
  }
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/partido/boca-vs-river-99';
App.init();
(async()=>{
  const esperar=async n=>{for(let i=0;i<n;i++) await new Promise(r=>setImmediate(r));};
  await esperar(5);
  // dos pantallas ANTES de que llegue el identificador
  for(const r of ['/lpf','/laliga']){
    loc.pathname=r; Rutas.ir(Rutas.leer(r)); await esperar(3); }
  await esperar(80);
  for(const r of ['/jugador/enzo-fernandez','/laliga','/laliga','/lpf','/']){
    loc.pathname=r; Rutas.ir(Rutas.leer(r)); await esperar(15); }
  await esperar(20);
  const conRuta=avisos.filter(u=>u.indexOf('&r=')>0);
  console.log(JSON.stringify({
    pantallas: conRuta.map(u=>decodeURIComponent(
      (u.match(/[?&]r=([^&]*)/)||[])[1]||'')),
    avisoDeEntrada: avisos.filter(u=>u.indexOf('v=')<0).length,
    mismoId: conRuta.every(u=>u.indexOf('v=2026-08-25-abc123')>0),
    conReloj: conRuta.every(u=>u.indexOf('&seg=')>0)}));
})();
""")
    _gn = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
             "\nglobalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App, Rutas;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{")
                 .replace("  const Rutas={", "  Rutas={") + _nav)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gn); _rn = _f.name
    _pn = _sub.run(["node", _rn], capture_output=True, text=True, timeout=60)
    os.unlink(_rn)
    _na = json.loads(_pn.stdout) if _pn.returncode == 0 and _pn.stdout else None
    chequear("la página navega y avisa", _na is not None,
             _pn.stderr.strip().splitlines()[:2])
    if _na:
        # La de entrada no está: ésa la anota el aviso de la visita.
        chequear("avisa cada pantalla por la que pasa, y no la de entrada",
                 _na["pantallas"] == ["/lpf", "/laliga",
                                      "/jugador/enzo-fernandez", "/laliga",
                                      "/lpf", "/"], _na["pantallas"])
        # Las dos primeras pasaron antes de que llegara el identificador:
        # se guardan y salen después, o se perderían las de quien entra y
        # toca un partido en el primer segundo.
        chequear("incluidas las que pasaron antes de tener identificador",
                 _na["pantallas"][:2] == ["/lpf", "/laliga"], _na["pantallas"])
        chequear("todas contra la misma visita", _na["mismoId"])
        chequear("y aprovechan el viaje para el reloj", _na["conReloj"])
        chequear("el aviso de la visita sigue siendo uno solo",
                 _na["avisoDeEntrada"] == 1, _na["avisoDeEntrada"])

    # Y el administrador, corriendo su propio código con visitas de mentira.
    _vfalsa = json.dumps({
        "hoy": {"gente": 40, "vistas": 52, "paginas": 137, "porPersona": 95,
                "vistasPorPersona": 1.3, "paginasPorVisita": 2.6},
        "ultimas": [
            {"t": 1756150000, "ruta": "/partido/boca-vs-river-99",
             "fuente": "Google", "region": "AR", "busco": "", "disp": "móvil",
             "so": "Android", "pantalla": "390x844", "seg": 210, "vistas": 5,
             "vio": ["/lpf", "/laliga", "/jugador/enzo-fernandez"]},
            {"t": 1756149000, "ruta": "/", "fuente": "directo", "region": "ES",
             "busco": "", "disp": "escritorio", "so": "macOS",
             "pantalla": "1440x900", "seg": 12, "vistas": 1, "vio": []},
            {"t": 1756148000, "ruta": "/lpf", "fuente": "X / Twitter",
             "region": "AR", "busco": "", "disp": "móvil", "so": "iOS",
             "pantalla": "430x932", "seg": 600, "vistas": 30,
             "vio": ["/a", "/b", "/c", "/d", "/e", "/f", "/g", "/h", "/i",
                     "/j", "/k", "/l"]}]})
    _cola = ("""
const v = __V__;
const hoy = visitasHoy(v), ult = ultimas(v);
console.log(JSON.stringify({
  dosCajas: hoy.indexOf('Visitas') >= 0 && hoy.indexOf('Páginas vistas') >= 0,
  visitas: hoy.indexOf('>52<') >= 0,
  paginas: hoy.indexOf('>137<') >= 0,
  porVisita: hoy.indexOf('2.6 por visita') >= 0,
  pasos: (ult.match(/class="paso"/g) || []).length,
  seFueDeAhi: ult.indexOf('se fue de ahí') >= 0,
  loQueNoEntro: ult.indexOf('+17') >= 0}));
""").replace("__V__", _vfalsa)
    _jadm = re.findall(r"<script>(.*?)</script>", _ADM, re.S)[-1]
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write("globalThis.location={search:'',hash:''};\n"
                 + _jadm.split("/* ── armar todo")[0] + _cola)
        _rv = _f.name
    _pv2 = _sub.run(["node", _rv], capture_output=True, text=True, timeout=60)
    os.unlink(_rv)
    _av = json.loads(_pv2.stdout) if _pv2.returncode == 0 and _pv2.stdout else None
    chequear("el administrador dibuja las visitas", _av is not None,
             _pv2.stderr.strip().splitlines()[:2])
    if _av:
        # Antes había un solo número y decía las dos cosas mal.
        chequear("visitas y páginas son dos números distintos",
                 _av["dosCajas"] and _av["visitas"] and _av["paginas"]
                 and _av["porVisita"], _av)
        # Doce pasos de la larga, tres de la primera, ninguno de la que se fue.
        chequear("y debajo de cada visita, por dónde siguió",
                 _av["pasos"] == 15, _av["pasos"])
        chequear("el que se fue de la primera pantalla se nota",
                 _av["seFueDeAhi"])
        # 30 páginas y 12 guardadas: quedan 17 sin detalle, pero contadas.
        chequear("y las que no entraron en el detalle igual se cuentan",
                 _av["loQueNoEntro"], _av)

print("\n── los partidos, uno por fila ──")
# El almacén guarda un torneo entero como un bloque de JSON: sirve para
# mandar una pantalla, pero no se le puede preguntar nada. `fixture:11` son
# 753 partidos en 463 KB, y para mirar uno hay que parsear los 753.
_guion4 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import almacen, tablas

    def pg(i, comp, loc, lid, vis, vid, dia, gh=None, ga=None, temp=1, ronda=1):
        return {"id": i, "comp": comp, "temporada": temp, "round": ronda,
                "start": dia + "T20:00:00-03:00", "status": "FIN",
                "home": {"id": lid, "canon": loc, "name": loc, "score": gh},
                "away": {"id": vid, "canon": vis, "name": vis, "score": ga},
                "gh": gh, "ga": ga, "venue": "La Bombonera", "stage": ""}

    tablas.iniciar()
    # el torneo, por su competencia principal
    tablas.guardar("champions", 572, [
        pg(1, 572, "Bayern", 10, "Inter", 20, "2026-09-15", 2, 1),
        pg(2, 572, "Inter", 20, "Bayern", 10, "2026-11-04", 0, 0),
        # y una clasificatoria, que también está en la otra competencia
        pg(9, 572, "Celje", 30, "Ararat", 40, "2026-08-04", 3, 1)],
        principal=True)
    # ahora la misma clasificatoria, por la competencia de la previa
    tablas.guardar("champions", 332, [
        pg(9, 332, "Celje", 30, "Ararat", 40, "2026-08-04", 3, 1)],
        principal=False)
    # y la temporada anterior del mismo torneo
    tablas.guardar("champions", 572, [
        pg(3, 572, "Bayern", 10, "Inter", 20, "2025-10-01", 1, 3, temp=0)],
        principal=True)

    e = tablas.estado()
    fila9 = tablas._filas("SELECT liga, comp, principal FROM partidos WHERE id=9")
    # volver a pasar lo mismo no duplica: la clave es el partido
    tablas.guardar("champions", 572, [
        pg(1, 572, "Bayern", 10, "Inter", 20, "2026-09-15", 2, 1)],
        principal=True)
    despues = tablas.estado()["partidos"]
    # y un resultado que cambia sí se actualiza
    tablas.guardar("champions", 572, [
        pg(1, 572, "Bayern", 10, "Inter", 20, "2026-09-15", 4, 1)],
        principal=True)
    marcador = tablas._filas("SELECT gh, ga FROM partidos WHERE id=1")[0]

    print(json.dumps({
        "filas": e["partidos"], "equipos": e["equipos"],
        "porLiga": e["porLiga"],
        "elRepetido": fila9,
        "trasRepasar": despues,
        "marcador": [marcador["gh"], marcador["ga"]],
        "cruces": [(m["dia"], m["gh"], m["ga"]) for m in tablas.entre(10, 20)],
        "delEquipo": len(tablas.del_equipo(10)),
        "deUnaTemporada": len(tablas.del_equipo(10, temporada=1)),
        "temporadas": tablas.temporadas("champions"),

        # ── quién jugó qué, y los goles ──
        "part": tablas.guardar_participaciones(
            [("bayern uno", 1), ("bayern uno", 2), ("inter uno", 1),
             # el mismo par otra vez: no es una participación nueva
             ("bayern uno", 1)]),
        "gol": tablas.guardar_goles([
            (1, "bayern uno", 12, "Bayern", "h"),
            (1, "bayern uno", 70, "Bayern", "h"),   # dos del mismo, dos goles
            (1, "inter uno", 55, "Inter", "a"),
            (1, "bayern uno", 12, "Bayern", "h"),   # repetido: es el mismo gol
            (2, "bayern uno", None, "Bayern", "h")]),  # sin minuto
        "carrera": [(m["dia"], m["liga"], m["goles"])
                    for m in tablas.carrera_de("bayern uno")],
        "goleadores": [(g["jugador"], g["goles"])
                       for g in tablas.goleadores(tope=5)],
        "goleadoresDeUnaTemporada": [
            (g["jugador"], g["goles"])
            for g in tablas.goleadores(liga="champions", temporada=1)],
        "cuentas": {k: tablas.estado()[k]
                    for k in ("participaciones", "jugadores", "goles")},

        "borradas": tablas.borrar_liga("champions"),
        "quedan": tablas.estado()["partidos"],
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion4); _gp6 = _f.name
_db4 = os.path.join(_tp2.gettempdir(), "hayvar_tab_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db4 + _ext):
        os.unlink(_db4 + _ext)
_pt2 = _sb2.run([sys.executable, _gp6, _db4, AQUI],
                capture_output=True, text=True, timeout=120)
os.unlink(_gp6)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db4 + _ext):
        os.unlink(_db4 + _ext)
_tb = None
for _linea in _pt2.stdout.splitlines():
    if _linea.startswith("{"):
        _tb = json.loads(_linea)
chequear("la tabla de partidos corre entera", _tb is not None,
         (_pt2.stdout[-200:], _pt2.stderr[-400:]))
if _tb:
    # Cuatro partidos distintos: dos de la fase de liga, uno de la
    # clasificación y uno de la temporada anterior. El de la clasificación
    # llegó dos veces, por sus dos competencias.
    chequear("cada partido es una fila y nada más que una",
             _tb["filas"] == 4, _tb["filas"])
    # Éste es EL error que había que evitar. Las clasificatorias de la
    # Champions y la Europa están guardadas en dos competencias: son 151
    # partidos con el mismo identificador en dos bloques. Con la clave
    # equivocada se contaban dos veces y las tablas quedaban mal armadas
    # para siempre.
    chequear("el partido que está en dos competencias no se cuenta dos veces",
             len(_tb["elRepetido"]) == 1, _tb["elRepetido"])
    # Y queda con el torneo, no con el número interno de la previa.
    chequear("y queda con la competencia principal, no con la de la previa",
             _tb["elRepetido"][0]["comp"] == 572
             and _tb["elRepetido"][0]["principal"] == 1, _tb["elRepetido"])
    chequear("volver a pasar los mismos partidos no los duplica",
             _tb["trasRepasar"] == 4, _tb["trasRepasar"])
    chequear("pero un resultado que cambió sí se actualiza",
             _tb["marcador"] == [4, 1], _tb["marcador"])
    # La pregunta que con bloques no se podía hacer: los cruces entre dos
    # equipos, de cualquier torneo y de cualquier temporada, ordenados.
    chequear("se puede preguntar el historial entre dos equipos",
             _tb["cruces"] == [["2026-11-04", 0, 0], ["2026-09-15", 4, 1],
                               ["2025-10-01", 1, 3]], _tb["cruces"])
    chequear("y todos los partidos de un equipo, de local y de visitante",
             _tb["delEquipo"] == 3, _tb["delEquipo"])
    chequear("acotados a una temporada", _tb["deUnaTemporada"] == 2,
             _tb["deUnaTemporada"])
    chequear("y qué temporadas hay de cada torneo",
             [t["temporada"] for t in _tb["temporadas"]] == [1, 0],
             _tb["temporadas"])
    # ── quién jugó qué ──
    # Cuatro pares mandados, tres distintos: el par jugador–partido es lo
    # que de verdad no se puede repetir.
    chequear("una participación es un jugador y un partido, una sola vez",
             _tb["cuentas"]["participaciones"] == 3
             and _tb["cuentas"]["jugadores"] == 2, _tb["cuentas"])
    # Cinco goles mandados: uno era el mismo repetido. Los otros dos del
    # mismo jugador en el mismo partido son dos goles distintos, y eso hay
    # que respetarlo o los goleadores salen mal.
    chequear("dos goles del mismo jugador en un partido son dos goles",
             _tb["cuentas"]["goles"] == 4, _tb["cuentas"])
    # La carrera sale de cruzar las dos tablas: los partidos que jugó, con
    # el torneo y la fecha del partido y sus goles contados.
    chequear("la carrera de un jugador sale de cruzar las dos tablas",
             _tb["carrera"] == [["2026-09-15", "champions", 2],
                                ["2026-11-04", "champions", 1]]
             or _tb["carrera"] == [["2026-11-04", "champions", 1],
                                   ["2026-09-15", "champions", 2]],
             _tb["carrera"])
    chequear("y la tabla de goleadores se calcula, no se guarda",
             _tb["goleadores"] == [["bayern uno", 3], ["inter uno", 1]],
             _tb["goleadores"])
    chequear("acotada a un torneo y una temporada",
             _tb["goleadoresDeUnaTemporada"] == [["bayern uno", 3],
                                                 ["inter uno", 1]],
             _tb["goleadoresDeUnaTemporada"])
    # Si sale mal, se borra y se rearma: por eso esto no puede perder nada.
    chequear("un torneo se puede borrar entero para rearmarlo",
             _tb["borradas"] == 4 and _tb["quedan"] == 0, _tb)
# La tabla se arma leyendo lo que ya está guardado. Si le pidiera algo a la
# fuente, rearmarla costaría plata y no se podría hacer a la ligera.
chequear("se arma de los bloques guardados, sin pedirle nada a la fuente",
         'almacen.leer("fixture:%s" % comp)' in _SRV
         and "fetch(" not in _SRV.split("def sincronizar_tablas")[1].split("\ndef ")[0])
# Primero las principales y después las previas: si fuera al revés, los 151
# quedarían con el número interno de la clasificación.
# El orden no cambia el resultado —la condición del ON CONFLICT ya deja
# ganar a la principal llegue cuando llegue— pero leerlo en ese orden dice
# cuál manda, y no depende de acordarse de la condición.
chequear("y primero las competencias principales",
         "for principal in (True, False):" in _SRV)
# El administrador tiene que poder mostrarla: si los números no cuadran con
# los torneos, la tabla está mal armada y hay que verlo antes de usarla.
if _sh.which("node"):
    _bt = json.dumps({
        "bytes": 1000, "entradas": 5, "sobrevive_al_deploy": True, "pesos": [],
        "tablas": {"partidos": 4206, "equipos": 378, "porLiga": [
            {"liga": "laliga", "partidos": 753, "temporadas": 2, "jugados": 379,
             "desde": "2025-08-17", "hasta": "2027-05-30"},
            {"liga": "champions", "partidos": 83, "temporadas": 1, "jugados": 83,
             "desde": "2026-07-07", "hasta": "2026-08-19"}]},
        "tablasCuando": {"cuando": "2026-08-25T20:00:00", "leidos": 4357,
                         "filas": 4206}})
    _colat = ("""
const base = __B__;
const s = tablaDePartidos(base);
console.log(JSON.stringify({
  filas: (s.match(/<tr>/g) || []).length,
  total: s.indexOf('>4.206<') >= 0 || s.indexOf('>4206<') >= 0,
  avisaRepetidos: s.indexOf('repetidos, unificados') >= 0,
  nombraTorneos: s.indexOf('laliga') >= 0 && s.indexOf('champions') >= 0}));
""").replace("__B__", _bt)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write("globalThis.location={search:'',hash:''};\n"
                 + re.findall(r"<script>(.*?)</script>", _ADM, re.S)[-1]
                   .split("/* ── armar todo")[0] + _colat)
        _rt2 = _f.name
    _pt3 = _sub.run(["node", _rt2], capture_output=True, text=True, timeout=60)
    os.unlink(_rt2)
    _at = json.loads(_pt3.stdout) if _pt3.returncode == 0 and _pt3.stdout else None
    chequear("el administrador dibuja la tabla de partidos", _at is not None,
             _pt3.stderr.strip().splitlines()[:2])
    if _at:
        chequear("con una fila por torneo",
                 _at["filas"] == 3 and _at["nombraTorneos"], _at)
        # 4.357 leídos y 4.206 filas: la diferencia son los 151 que están
        # en dos competencias. Que se vea, y no parezca que se perdieron.
        chequear("y avisa cuántos venían repetidos", _at["avisaRepetidos"], _at)
# La tabla se rehacía sólo cuando el recolector recorría los calendarios, y
# eso, con la historia completa, es una vez cada ocho vueltas: un gol de
# ahora tardaba hasta dos horas en llegar. Se engancha donde se guarda el
# calendario, que es el instante exacto en que hay un resultado nuevo.
chequear("el calendario que se guarda va a la tabla en ese momento",
         "guardados = list(acumulado.values())" in _SRV
         and "tablas.guardar(lid, comp, guardados, principal=principal)" in _SRV)
chequear("y para eso se sabe de qué torneo es cada competencia",
         "def liga_de_comp(comp):" in _SRV)
_ALM = open(os.path.join(AQUI, "almacen.py"), encoding="utf-8").read()
# Leer once mil claves de a una son once mil consultas con su candado.
chequear("las claves de una familia se leen de pocas pasadas, no de a una",
         "def leer_prefijo(" in _ALM and "clave IN (%s)" in _ALM)
# Y si una página del archivo está dañada, la consulta entera se cae: antes
# eso devolvía una lista vacía y parecía que no había datos.
chequear("y una página dañada no se lleva puesta a toda la familia",
         "for clave in grupo:" in _ALM
         and "la tanda tiene una página rota" in _ALM)
chequear("el almacén presta su conexión en vez de abrir otra",
         "def conexion():" in open(os.path.join(AQUI, "almacen.py"),
                                   encoding="utf-8").read()
         and "with almacen.conexion() as c:" in open(
             os.path.join(AQUI, "tablas.py"), encoding="utf-8").read())

print("\n── las formaciones y las estadísticas, de los diez que se miran ──")
# El detalle de cada partido ya se pide para buscarle los goles, y hasta
# ahora lo único que se sacaba de ahí eran los goles. Las formaciones y las
# estadísticas vienen en el mismo paquete: sacarlas no cuesta un pedido más.
chequear("son los diez torneos elegidos, ni uno más",
         sorted(server.LIGAS_EN_DETALLE) ==
         sorted(["lpf", "ca", "lib", "sud", "champions", "europa",
                 "laliga", "premier", "seriea", "bundesliga"]),
         server.LIGAS_EN_DETALLE)
# Los que quedan afuera son los de ascenso y el femenino: son treinta filas
# por partido y cuatro mil partidos por temporada.
chequear("y los que quedan afuera quedan afuera",
         not (set(server.LIGAS_EN_DETALLE)
              & {"nacional", "pbm", "fa", "fem"}))
chequear("se sacan del partido que ya está abierto, sin pedir de nuevo",
         "anotar_formacion(liga, game_id, g)" in _SRV
         and "fetch(" not in _SRV.split("def anotar_formacion")[1]
                                 .split("\ndef ")[0])

_guion5 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import server, tablas

    def m(i, st, pos, dor, rank=None, stats=None, x=None, y=None):
        d = {"id": i, "status": st, "jerseyNumber": dor,
             "position": {"name": pos}, "ranking": rank,
             "yardFormation": {"fieldSide": x, "fieldLine": y}}
        if stats:
            d["stats"] = [{"name": k, "value": v} for k, v in stats.items()]
        return d

    G = {"game": {"id": 99, "statusText": "Finalizado",
        "gameTimeAndStatusDisplayType": 2, "startTime": "2026-08-25T20:00:00",
        "members": [{"id": 10, "name": "Sergio Romero"},
                    {"id": 11, "name": "Marcos Rojo"},
                    {"id": 12, "name": "Miguel Merentiel"},
                    {"id": 13, "name": "Suplente Uno"},
                    {"id": 14, "name": "Miguel Russo"},
                    {"id": 20, "name": "Franco Armani"}],
        "homeCompetitor": {"id": 1, "name": "Boca Juniors", "score": 2,
          "lineups": {"formation": "4-3-3", "members": [
            m(10, 1, "Arquero", 1, 7.2, {"Atajadas": "4", "Toques": "31"}, 50, 5),
            m(11, 1, "Defensor central", 6, 6.8, {"Despejes": "7"}, 35, 20),
            m(12, 1, "Centrodelantero", 9, 8.1, {"Goles": "2", "Remates": "5"}, 50, 85),
            m(13, 2, "Volante central", 23),
            m(14, None, "", -1)]}},
        "awayCompetitor": {"id": 2, "name": "River Plate", "score": 1,
          "lineups": {"formation": "4-4-2", "members": [
            m(20, 1, "Arquero", 1, 6.5, {"Atajadas": "2"}, 50, 5)]}},
        "events": [], "tvNetworks": []}}

    class F:
        def read(self): return json.dumps(G).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    n = [0]
    server.urlopen = lambda req, timeout=None: (n.__setitem__(0, n[0] + 1), F())[1]

    server.detalle_liviano("99", en_juego=False, liga="lpf")
    pedidos = n[0]
    e1 = tablas.estado()
    once = tablas.once_de(99, "h")
    # volver a pasar el mismo partido no puede duplicar nada
    server.detalle_liviano("99", en_juego=False, liga="lpf")
    e2 = tablas.estado()
    # y uno de un torneo que no está en la lista
    G["game"]["id"] = 100
    server.detalle_liviano("100", en_juego=False, liga="fa")
    e3 = tablas.estado()

    print(json.dumps({
        "pedidos": pedidos,
        "formaciones": e1["formaciones"], "conDibujo": e1["conFormacion"],
        "estadisticas": e1["estadisticas"],
        "dibujo": once["dibujo"], "confirmada": once["confirmada"],
        "roles": [(p["jugador"], p["rol"], p["puesto"], p["dorsal"],
                   p["puntaje"]) for p in once["gente"]],
        "trasRepetir": [e2["formaciones"], e2["estadisticas"]],
        "trasElDeAfuera": [e3["formaciones"], e3["estadisticas"]],
        "comoJuega": tablas.como_juega("Miguel Merentiel"),
        "remates": tablas.promedio_de("Miguel Merentiel", "remates"),
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion5); _gp7 = _f.name
_db5 = os.path.join(_tp2.gettempdir(), "hayvar_form_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db5 + _ext):
        os.unlink(_db5 + _ext)
_pf2 = _sb2.run([sys.executable, _gp7, _db5, AQUI],
                capture_output=True, text=True, timeout=120)
os.unlink(_gp7)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db5 + _ext):
        os.unlink(_db5 + _ext)
_fo = None
for _linea in _pf2.stdout.splitlines():
    if _linea.startswith("{"):
        _fo = json.loads(_linea)
chequear("la extracción corre entera", _fo is not None,
         (_pf2.stdout[-200:], _pf2.stderr[-400:]))
if _fo:
    # Lo importante: el mismo pedido de siempre. Si esto costara uno más,
    # multiplicaría la cuenta de la fuente por dos.
    chequear("no cuesta ni un pedido más a la fuente", _fo["pedidos"] == 1,
             _fo["pedidos"])
    chequear("queda el dibujo de cada equipo",
             _fo["dibujo"] == "4-3-3" and _fo["conDibujo"] == 1, _fo)
    # Cinco de Boca y uno de River. El técnico también: 365scores le pone
    # el dorsal -1 y es parte de la formación.
    chequear("y quién estuvo, con su rol y su puesto",
             _fo["formaciones"] == 6, _fo["formaciones"])
    chequear("el titular, el suplente y el técnico se distinguen",
             [r[1] for r in _fo["roles"]] ==
             ["titular", "titular", "titular", "suplente", "dt"], _fo["roles"])
    # Con cuatro titulares de once, la formación no está confirmada: la
    # fuente manda el plantel entero hasta poco antes del partido.
    chequear("y una formación a medias no se da por confirmada",
             _fo["confirmada"] is False)
    chequear("las estadísticas quedan una por fila",
             _fo["estadisticas"] == 6, _fo["estadisticas"])
    chequear("volver a pasar el mismo partido no duplica nada",
             _fo["trasRepetir"] == [6, 6], _fo["trasRepetir"])
    # La regla que pidió Mateo: sólo los diez torneos que se miran.
    chequear("y un torneo que no está en la lista no deja nada",
             _fo["trasElDeAfuera"] == [6, 6], _fo["trasElDeAfuera"])
    # De qué juega alguien sale de sus formaciones, no de su ficha: la
    # ficha dice un puesto solo aunque haya jugado en tres.
    chequear("se puede preguntar de qué juega alguien",
             _fo["comoJuega"] == [{"puesto": "Centrodelantero",
                                   "rol": "titular", "veces": 1,
                                   "puntaje": 8.1}], _fo["comoJuega"])
    chequear("y cuánto promedia en una estadística",
             _fo["remates"]["promedio"] == 5 and _fo["remates"]["partidos"] == 1,
             _fo["remates"])
# El recolector no vuelve a abrir un partido cuyos goles ya resolvió, así
# que sólo con él las formaciones de todo lo ya jugado no se capturaban
# nunca. La ficha de un partido pide el mismo paquete: que también deje las
# suyas, y así cada partido que alguien mira queda guardado — que además es
# el criterio correcto, porque son justo los que a alguien le importan.
chequear("la ficha de un partido también deja su formación",
         "anotar_formacion(liga_id, gid, g)" in _SRV)
chequear("y las dos puertas usan la misma función",
         _SRV.count("anotar_formacion(") == 3)   # la definición y las dos

print("\n── completar la historia vieja, sin apurarse ──")
# Novecientos partidos ya jugados sin formación, dos pedidos cada uno.
# Hacerlos de golpe son mil ochocientos pedidos en ráfaga desde una sola IP
# contra una API privada de la que depende el sitio entero.
chequear("se hacen de a poco y con pausa entre uno y otro",
         server.POR_VUELTA <= 10 and server.PAUSA_ENTRE >= 1,
         (server.POR_VUELTA, server.PAUSA_ENTRE))
# Y sólo cuando no hay nada mejor que hacer: mientras falte algo de hoy,
# eso manda.
# Y engancharlo donde corresponde: en la rama del recolector que sólo se
# alcanza cuando no quedó nada del día, y en ninguna otra.
_ramaLibre = _SRV.split("if not pendientes and not goles_pendientes:")[1] \
                 .split("elif not pendientes:")[0]
chequear("y sólo cuando el recolector no tiene nada que hacer",
         "rellenar_formaciones()" in _ramaLibre
         and _SRV.count("rellenar_formaciones(") == 2,   # la definición y ésta
         _SRV.count("rellenar_formaciones("))

_guion6 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import almacen, server, tablas
    server.PAUSA_ENTRE = 0        # en la prueba no se espera de verdad

    # un torneo de mentira con seis partidos jugados
    pg = lambda i: {"id": i, "temporada": 1, "round": 1, "gh": 1, "ga": 0,
                    "start": "2026-05-0%dT20:00:00" % (i % 9 + 1),
                    "status": "FIN",
                    "home": {"id": 1, "canon": "A"}, "away": {"id": 2, "canon": "B"}}
    tablas.guardar("lpf", 7, [pg(i) for i in range(1, 7)])

    CON = {"formation": "4-3-3", "members": [
        {"id": 10, "status": 1, "jerseyNumber": 1,
         "position": {"name": "Arquero"}, "ranking": 7.0,
         "stats": [{"name": "Atajadas", "value": "3"}]}]}

    class F:
        def __init__(s, d): s.d = d
        def read(s): return json.dumps(s.d).encode()
        def __enter__(s): return s
        def __exit__(s, *a): pass

    n = [0]
    vacios = set()
    def falso(req, timeout=None):
        n[0] += 1
        gid = req.full_url.split("gameId=")[1].split("&")[0]
        lu = {"members": []} if gid in vacios else CON
        return F({"game": {"id": int(gid), "statusText": "Finalizado",
            "gameTimeAndStatusDisplayType": 2, "startTime": "2026-05-01T20:00:00",
            "members": [{"id": 10, "name": "Un Arquero"}],
            "homeCompetitor": {"id": 1, "name": "A", "score": 1, "lineups": lu},
            "awayCompetitor": {"id": 2, "name": "B", "score": 0,
                               "lineups": {"members": []}},
            "events": [], "tvNetworks": []}})
    server.urlopen = falso

    faltan0 = tablas.cuantos_sin_formacion(["lpf"])
    r1 = server.rellenar_formaciones(2)
    pedidos1 = n[0]
    # los dos que siguen no tienen formación en la fuente
    vacios.update(str(p["id"]) for p in tablas.sin_formacion(["lpf"], 2))
    r2 = server.rellenar_formaciones(2)
    descartados = list(almacen.leer("formaciones:sinsuerte")[0] or [])
    # y no vuelven a aparecer nunca más
    quedan = [p["id"] for p in tablas.sin_formacion(["lpf"], 9, descartados)]
    print(json.dumps({
        "faltanAlEmpezar": faltan0,
        "primera": r1, "pedidosPrimera": pedidos1,
        "segunda": r2, "descartados": len(descartados),
        "losDescartadosNoVuelven": not (set(descartados) & set(quedan)),
        "quedan": len(quedan),
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion6); _gp8 = _f.name
_db6 = os.path.join(_tp2.gettempdir(), "hayvar_rel_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db6 + _ext):
        os.unlink(_db6 + _ext)
_pr2 = _sb2.run([sys.executable, _gp8, _db6, AQUI],
                capture_output=True, text=True, timeout=120)
os.unlink(_gp8)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db6 + _ext):
        os.unlink(_db6 + _ext)
_re = None
for _linea in _pr2.stdout.splitlines():
    if _linea.startswith("{"):
        _re = json.loads(_linea)
chequear("el relleno corre entero", _re is not None,
         (_pr2.stdout[-200:], _pr2.stderr[-400:]))
if _re:
    chequear("sabe cuántos le faltan", _re["faltanAlEmpezar"] == 6,
             _re["faltanAlEmpezar"])
    chequear("hace los que se le piden y ni uno más",
             _re["primera"]["hechos"] == 2 and _re["pedidosPrimera"] == 2,
             (_re["primera"], _re["pedidosPrimera"]))
    chequear("y va descontando", _re["primera"]["faltan"] == 4,
             _re["primera"]["faltan"])
    # Un partido viejo que la fuente ya no detalla no se puede completar
    # nunca: sin anotarlo, se pediría de nuevo en cada vuelta para siempre.
    chequear("al que la fuente no detalla lo anota y no lo repite",
             _re["segunda"]["hechos"] == 0 and _re["segunda"]["sin"] == 2
             and _re["descartados"] == 2 and _re["losDescartadosNoVuelven"],
             _re)
    chequear("y sigue con los que quedan", _re["quedan"] == 2, _re["quedan"])
chequear("el administrador muestra cuánto falta",
         "faltanFormaciones=tablas.cuantos_sin_formacion(" in _SRV
         and "Historia por completar" in _ADM)

print("\n── cómo les fue las veces anteriores ──")
# Es la primera pregunta que contesta la tabla de partidos y que con los
# bloques no se podía hacer: los cruces entre dos equipos están repartidos
# entre los dieciséis calendarios y hay que atravesarlos todos.
_guion7 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import server, tablas

    # A es el local de HOY. En estos partidos jugó de los dos lados.
    def pg(i, loc, lid, vis, vid, dia, gh, ga, liga="lpf"):
        return {"id": i, "temporada": 1, "round": 1, "start": dia + "T20:00:00",
                "status": "FIN", "gh": gh, "ga": ga,
                "home": {"id": lid, "canon": loc}, "away": {"id": vid, "canon": vis}}
    # Ojo con estos datos: tres de las cuatro victorias de A son de
    # visitante, a propósito. Con un reparto simétrico, contar "desde el
    # local de hoy" y contar "desde el local de cada partido" dan el mismo
    # número por casualidad, y la prueba no prueba nada.
    tablas.guardar("lpf", 7, [
        pg(1, "A", 1, "B", 2, "2026-05-11", 2, 0),     # A ganó de local
        pg(2, "B", 2, "A", 1, "2025-11-02", 0, 1),     # A ganó de visitante
        pg(3, "A", 1, "B", 2, "2025-09-21", 1, 1),     # empate
        pg(4, "B", 2, "A", 1, "2025-04-10", 0, 2),     # A ganó de visitante
        pg(9, "A", 1, "B", 2, "2026-08-25", None, None)])  # todavía no se jugó
    tablas.guardar("ca", 640, [
        pg(5, "A", 1, "B", 2, "2025-02-02", 0, 2, "ca")])  # ganó B, otro torneo

    h = server.historial_entre(1, 2)
    sinHoy = server.historial_entre(1, 2, excluir=1)

    # El partido que se está mirando: cuenta si ya terminó, no si está en
    # curso o sin jugar. Y se lo reconoce por su fecha además de por su
    # identificador —el de la ficha es el de 365scores y el de la tabla
    # sale del calendario—, así que esto no depende de que coincidan.
    def conElDeHoy(estado, gh, ga, ident=9):
        tablas.borrar_liga("hoy")
        tablas.guardar("hoy", 8, [dict(
            pg(ident, "A", 1, "B", 2, "2026-08-26", gh, ga), status=estado)])
        r = server.historial_entre(1, 2, excluir=9, dia="2026-08-26T21:00:00Z")
        marcado = [x for x in r["partidos"] if x.get("este")]
        return [r["jugados"], r["gano"], bool(marcado)]
    terminado = conElDeHoy("FIN", 3, 0)
    enCurso = conElDeHoy("LIVE", 1, 0)
    sinJugar = conElDeHoy("SCH", None, None)
    otroId = conElDeHoy("FIN", 3, 0, ident=777)
    tablas.borrar_liga("hoy")
    print(json.dumps({
        "resumen": [h["gano"], h["empates"], h["perdio"], h["jugados"]],
        "cuantos": len(h["partidos"]),
        "orden": [p["dia"] for p in h["partidos"]],
        "torneos": sorted({p["liga"] for p in h["partidos"]}),
        "nombraElTorneo": h["partidos"][0]["ligaNombre"],
        "sinJugarNoCuenta": all(p["gh"] is not None for p in h["partidos"]),
        "elDeHoy": [sinHoy["jugados"],
                    [p.get("este", False) for p in sinHoy["partidos"]
                     if p["id"] == 1]],
        "nuncaSeCruzaron": server.historial_entre(1, 999),
        "sinEquipo": server.historial_entre(None, 2),
        "terminado": terminado, "enCurso": enCurso, "sinJugar": sinJugar,
        "otroId": otroId,
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion7); _gp9 = _f.name
_db7 = os.path.join(_tp2.gettempdir(), "hayvar_hist_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db7 + _ext):
        os.unlink(_db7 + _ext)
_ph = _sb2.run([sys.executable, _gp9, _db7, AQUI],
               capture_output=True, text=True, timeout=120)
os.unlink(_gp9)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db7 + _ext):
        os.unlink(_db7 + _ext)
_hi = None
for _linea in _ph.stdout.splitlines():
    if _linea.startswith("{"):
        _hi = json.loads(_linea)
chequear("el historial corre entero", _hi is not None,
         (_ph.stdout[-200:], _ph.stderr[-400:]))
if _hi:
    # A ganó dos —una de local y una de visitante—, un empate, y B ganó dos.
    # La cuenta se lee parada en esta página: el primer número es del que
    # HOY es local, sin importar de qué lado jugó cada una de esas veces.
    # A ganó tres —una de local y dos de visitante—, un empate, y B ganó
    # una. La cuenta se lee parada en esta página: el primer número es del
    # que HOY es local, sin importar de qué lado jugó cada una de esas veces.
    chequear("cuenta desde el lado del local de hoy, jugara donde jugara",
             _hi["resumen"] == [3, 1, 1, 5], _hi["resumen"])
    chequear("y junta los cruces de todos los torneos",
             _hi["torneos"] == ["ca", "lpf"], _hi["torneos"])
    chequear("del más nuevo al más viejo",
             _hi["orden"] == sorted(_hi["orden"], reverse=True), _hi["orden"])
    # Un partido que todavía no se jugó no dice nada de cómo les fue.
    chequear("los que no se jugaron no entran", _hi["sinJugarNoCuenta"])
    chequear("con el nombre del torneo de cada uno",
             _hi["nombraElTorneo"] == "Liga Profesional", _hi["nombraElTorneo"])
    # El que se está mirando aparece y va marcado, para que se vea de
    # dónde sale la cuenta. Y no se enlaza a sí mismo.
    chequear("el partido de hoy aparece marcado, no escondido",
             _hi["elDeHoy"] == [5, [True]], _hi["elDeHoy"])
    # Dos que nunca se cruzaron no muestran una caja vacía: no muestran nada.
    chequear("si nunca se cruzaron, no se muestra nada",
             _hi["nuncaSeCruzaron"] is None and _hi["sinEquipo"] is None)
    # Abrir un partido ya terminado: forma parte del historial como
    # cualquier otro, así que cuenta. Antes lo sacaba siempre.
    chequear("un partido terminado cuenta en su propio historial",
             _hi["terminado"] == [6, 4, True], _hi["terminado"])
    # Uno en curso o sin jugar todavía no dijo nada.
    chequear("pero uno en curso no", _hi["enCurso"] == [5, 3, False],
             _hi["enCurso"])
    chequear("ni uno que no se jugó", _hi["sinJugar"] == [5, 3, False],
             _hi["sinJugar"])
    # Y se lo reconoce por la fecha, no sólo por el identificador: dos
    # equipos no se cruzan dos veces el mismo día.
    chequear("y se lo reconoce por la fecha aunque el id no coincida",
             _hi["otroId"] == [6, 4, True], _hi["otroId"])
chequear("el partido lo lleva puesto, sin un pedido más",
         'out["historial"] = historial_entre(' in _SRV)
# Va después de la tabla del torneo y aparte: si una tarda o falla, la otra
# se ve igual.
chequear("y la página lo cuelga abajo de lo que ya está",
         "function historialAlCostado(m)" in HTML
         and "insertAdjacentHTML('beforeend'" in HTML
         and ".then(()=>historialAlCostado(current())," in HTML)

# Y dibujándolo de verdad, que es donde se ve si la cuenta quedó de qué lado.
if _sh.which("node"):
    _mh = json.dumps({
        "id": "99", "liveId": "99", "liga": "lpf",
        "ligaNombre": "Liga Profesional", "torneo": "Clausura", "round": 5,
        "status": "FIN", "gh": 2, "ga": 1, "start": "2026-08-25T21:30:00Z",
        "events": [], "stats": [], "tv": [],
        "home": {"name": "Boca Juniors", "canon": "Boca Juniors"},
        "away": {"name": "River Plate", "canon": "River Plate"},
        "lineups": {"home": [], "away": []}, "banco": {"home": [], "away": []},
        "confirmada": {}, "bancoReal": {}, "formation": {},
        "historial": {"gano": 3, "empates": 1, "perdio": 2, "jugados": 6,
          "partidos": [
            {"id": 91, "dia": "2026-05-11", "liga": "lpf",
             "local": "River Plate", "visita": "Boca Juniors", "gh": 1, "ga": 2},
            {"id": 92, "dia": "2025-11-02", "liga": "ca",
             "local": "Boca Juniors", "visita": "River Plate", "gh": 0, "ga": 0},
            {"id": 93, "dia": "2025-09-21", "liga": "lpf",
             "local": "Boca Juniors", "visita": "River Plate", "gh": 2,
             "ga": 3}]}}, ensure_ascii=False)
    _jh = ("""
process.on('unhandledRejection',()=>{});
const RESP={'/api/match': __M__, '/api/liga/games':{llaves:[]},
  '/api/liga':{zonas:[],anual:[],goleadores:[]}, '/api/standings':{zones:[]},
  '/api/annual':{rows:[]}, '/api/promedios':{rows:[]},
  '/api/ligas':{ligas:[]}, '/api/clubes':{clubes:[]}, '/api/visita':{v:'x'}};
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/partido/boca-juniors-vs-river-plate-99';
App.init();
(async()=>{
  for(let i=0;i<90;i++) await new Promise(r=>setImmediate(r));
  const d=doc.querySelector('#right').innerHTML||'';
  console.log(JSON.stringify({
    hay: d.indexOf('Cómo les fue') >= 0,
    cuantos: d.indexOf('6 partidos') >= 0,
    cuenta: (d.match(/<b>\\d<\\/b> (?:Boca Juniors|empates|River Plate)/g) || []),
    filas: (d.match(/class="hist-p"/g) || []).length,
    marcados: (d.match(/eq[^"]*gano/g) || []).length,
    linkea: d.indexOf('river-plate-vs-boca-juniors-91') >= 0}));
})();
""").replace("__M__", _mh)
    _gh2 = (open(_DOMSITO, encoding="utf-8").read()
            + "\nglobalThis.document=doc; globalThis.window=win;"
              "\nglobalThis.location=loc; globalThis.history=historial;"
              "\nglobalThis.localStorage=almacenLocal;"
              "\nglobalThis.MutationObserver=MutationObserver;"
              "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
              "\nglobalThis.requestAnimationFrame=f=>0;"
              "\nglobalThis.setInterval=()=>0;\nlet App;\n"
            + _app.replace("const App=(()=>{", "App=(()=>{") + _jh)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gh2); _rh = _f.name
    _phh = _sub.run(["node", _rh], capture_output=True, text=True, timeout=60)
    os.unlink(_rh)
    _hd = json.loads(_phh.stdout) if _phh.returncode == 0 and _phh.stdout else None
    chequear("la página dibuja el historial", _hd is not None,
             _phh.stderr.strip().splitlines()[:2])
    if _hd:
        chequear("con cuántos se cruzaron", _hd["hay"] and _hd["cuantos"], _hd)
        # El orden de la cuenta importa: primero el local de hoy.
        chequear("y la cuenta del lado que corresponde",
                 _hd["cuenta"] == ["<b>3</b> Boca Juniors", "<b>1</b> empates",
                                   "<b>2</b> River Plate"], _hd["cuenta"])
        chequear("un renglón por cruce", _hd["filas"] == 3, _hd["filas"])
        # Los dos que ganó River; el empate no marca a nadie.
        chequear("con el que ganó cada uno resaltado", _hd["marcados"] == 2,
                 _hd["marcados"])
        chequear("y cada cruce lleva a su partido", _hd["linkea"], _hd)

    # El bug que encontró Mateo: al cambiar de zona o pasar a la anual, el
    # panel se rehace entero y el historial desaparecía para no volver
    # hasta recargar la página. Colgarlo una sola vez no alcanza.
    _eq = lambda n: {"name": n, "canon": n, "logo": None, "short": ""}
    _fl = lambda p, n: {"pos": p, "canon": n, "team": _eq(n), "pts": 10 - p,
                        "pj": 6, "g": 3, "e": 1, "p": 2, "gf": 8, "gc": 6,
                        "dif": 2, "form": ["G"], "live": False}
    _pr = lambda p, n: dict(_fl(p, n), prom=1.5, promMin=1.2, restantes=5,
                            descendiendo=False, enRiesgo=False)
    _resp = json.dumps({
        "/api/match": json.loads(_mh), "/api/liga/games": {"llaves": []},
        "/api/standings": {"zones": [
            {"name": "Zona A", "rows": [_fl(1, "Boca Juniors")]},
            {"name": "Zona B", "rows": [_fl(2, "River Plate")]}]},
        "/api/annual": {"rows": [_fl(1, "Boca Juniors")]},
        "/api/promedios": {"rows": [_pr(1, "Boca Juniors")]},
        "/api/liga": {"zonas": [], "anual": [], "goleadores": []},
        "/api/ligas": {"ligas": []}, "/api/clubes": {"clubes": []},
        "/api/visita": {"v": "x"}}, ensure_ascii=False)
    _jt = ("""
process.on('unhandledRejection',()=>{});
const RESP=__R__;
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/partido/boca-juniors-vs-river-plate-99';
App.init();
(async()=>{
  const esperar=async n=>{for(let i=0;i<n;i++) await new Promise(r=>setImmediate(r));};
  await esperar(90);
  const der=()=>doc.querySelector('#right').innerHTML||'';
  const hay=()=>der().indexOf('Cómo les fue')>=0;
  const paso=[hay()];
  for(const t of ['B','anual','prom','A']){
    App.tab(t); await esperar(10); paso.push(hay());
  }
  console.log(JSON.stringify({paso,
    copias: (der().match(/class="hist"/g) || []).length,
    sigueLaTabla: der().indexOf('Boca Juniors') >= 0}));
})();
""").replace("__R__", _resp)
    _gt = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
             "\nglobalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{") + _jt)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gt); _rt3 = _f.name
    _pt4 = _sub.run(["node", _rt3], capture_output=True, text=True, timeout=60)
    os.unlink(_rt3)
    _tb2 = json.loads(_pt4.stdout) if _pt4.returncode == 0 and _pt4.stdout else None
    chequear("las pestañas del panel corren", _tb2 is not None,
             _pt4.stderr.strip().splitlines()[:2])
    if _tb2:
        chequear("el historial sobrevive a cambiar de zona, anual y promedios",
                 _tb2["paso"] == [True] * 5, _tb2["paso"])
        # Y no se pega de nuevo encima del que ya estaba.
        chequear("y queda una sola copia", _tb2["copias"] == 1, _tb2["copias"])
        chequear("con la tabla nueva arriba", _tb2["sigueLaTabla"], _tb2)

print("\n── los colores de la barra ──")
# Cada pedazo del color de su club. Tiene dos trampas: hay clubes con el
# principal casi blanco —Argentinos— que sobre la tarjeta blanca
# desaparecen, y hay pares con colores parecidos —dos verdes— donde la
# barra no dice nada y conviene el azul y rojo de siempre.
if _sh.which("node"):
    _frag = HTML[HTML.index("  const _rgb=c=>{"):
                 HTML.index("  function historialAlCostado(m){")]
    _pares = json.dumps([[a, list(server.COLORES[a]), b, list(server.COLORES[b])]
                         for a, b in itertools.combinations(
                             sorted(server.COLORES), 2)])
    _jc = ("const esc=s=>String(s==null?'':s);\n" + _frag + """
let conColor=0, sinColor=0, seePierden=0;
for(const [na,ca,nb,cb] of __P__){
  const r=coloresDelHistorial({home:{colores:ca}, away:{colores:cb}});
  if(!r) sinColor++;
  else { conColor++; if(_claro(r.local)||_claro(r.visita)) seePierden++; }
}
const arg=coloresDelHistorial({home:{colores:['#f2f2f2','#c8102e']},
                               away:{colores:['#0a2472','#f2c94c']}});
console.log(JSON.stringify({conColor, sinColor, seePierden,
  casiBlanco: arg && arg.local,
  sinColores: coloresDelHistorial({home:{}, away:{}})}));
""").replace("__P__", _pares)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_jc); _rc2 = _f.name
    _pc2 = _sub.run(["node", _rc2], capture_output=True, text=True, timeout=60)
    os.unlink(_rc2)
    _co = json.loads(_pc2.stdout) if _pc2.returncode == 0 and _pc2.stdout else None
    chequear("los colores se eligen", _co is not None,
             _pc2.stderr.strip().splitlines()[:2])
    if _co:
        # De los 435 pares posibles entre los treinta de Primera, la
        # mayoría se distingue y el resto cae al azul y rojo de siempre.
        chequear("la mayoría de los pares se pinta con sus colores",
                 _co["conColor"] > _co["sinColor"] * 2, _co)
        # Ninguna barra puede quedar tan clara que se pierda en la tarjeta.
        chequear("y ninguna barra se pierde en el fondo blanco",
                 _co["seePierden"] == 0, _co["seePierden"])
        # Argentinos es casi blanco y tiene que usar su segundo color.
        chequear("un club de camiseta casi blanca usa su segundo color",
                 _co["casiBlanco"] == "#c8102e", _co["casiBlanco"])
        chequear("y sin colores cargados queda el de siempre",
                 _co["sinColores"] is None)
# Dos verdes parecidos no se distinguen, y una barra que no se distingue no
# dice nada: ahí es mejor el par de siempre.
chequear("dos clubes de colores parecidos caen al par de siempre",
         "if(!a||!b||!_lejos(a,b)) return null;" in HTML)
# El empate no es de nadie: se llama sin color y se queda con el gris.
chequear("y el empate va en gris, no en el color de nadie",
         "barra(h.empates,'e')}" in HTML
         and ".hist-barra .e{background:var(--txt3)}" in HTML)


print("\n── el historial del club, contra cada rival ──")
# Una fila por rival y no un partido por renglón: contra veinte equipos y
# dos temporadas serían ochenta renglones y no se lee nada.
_guion8 = _tw2.dedent("""
    import os, json, sys
    os.environ["HAYVAR_DB"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2])
    import server, tablas

    def pg(i, loc, lid, vis, vid, dia, gh, ga, liga="lpf", comp=7):
        return {"id": i, "temporada": 1, "round": 1, "start": dia + "T20:00:00",
                "status": "FIN", "gh": gh, "ga": ga,
                "home": {"id": lid, "canon": loc}, "away": {"id": vid, "canon": vis}}
    # El club es A. Contra B jugó tres veces —una de local ganando, una de
    # visitante ganando y un empate— y contra C una sola, perdiendo.
    tablas.guardar("lpf", 7, [
        pg(1, "A", 1, "B", 2, "2026-05-11", 2, 0),
        pg(2, "B", 2, "A", 1, "2025-11-02", 0, 1),
        pg(3, "A", 1, "B", 2, "2025-09-21", 1, 1),
        pg(4, "C", 3, "A", 1, "2025-08-01", 3, 0),
        pg(8, "A", 1, "B", 2, "2026-09-01", None, None),   # sin jugar
        pg(9, "B", 2, "C", 3, "2025-07-01", 1, 0)])        # sin A: no va
    # y un partido suyo en otro torneo, que no cuenta acá
    tablas.guardar("lib", 102, [pg(5, "A", 1, "Z", 9, "2026-03-01", 4, 0, "lib")])

    h = server.historial_del_club(1, "lpf")
    porRival = {r["rival"]: r for r in h}
    print(json.dumps({
        "rivales": [r["rival"] for r in h],
        "contraB": [porRival["B"]["pj"], porRival["B"]["g"], porRival["B"]["e"],
                    porRival["B"]["p"], porRival["B"]["gf"], porRival["B"]["gc"]],
        "contraC": [porRival["C"]["pj"], porRival["C"]["g"], porRival["C"]["e"],
                    porRival["C"]["p"]],
        "partidosDeB": len(porRival["B"]["partidos"]),
        "deLocal": [p["casa"] for p in porRival["B"]["partidos"]],
        "sinTorneo": server.historial_del_club(1, None),
        "sinEquipo": server.historial_del_club(None, "lpf"),
        "idPorNombre": tablas.equipo_id("A", "lpf"),
        "idQueNoEsta": tablas.equipo_id("No Existe"),
    }))
""")
with _tp2.NamedTemporaryFile("w", suffix=".py", delete=False,
                             encoding="utf-8") as _f:
    _f.write(_guion8); _gp10 = _f.name
_db8 = os.path.join(_tp2.gettempdir(), "hayvar_club_%d.db" % os.getpid())
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db8 + _ext):
        os.unlink(_db8 + _ext)
_pc3 = _sb2.run([sys.executable, _gp10, _db8, AQUI],
                capture_output=True, text=True, timeout=120)
os.unlink(_gp10)
for _ext in ("", "-wal", "-shm"):
    if os.path.exists(_db8 + _ext):
        os.unlink(_db8 + _ext)
_cl = None
for _linea in _pc3.stdout.splitlines():
    if _linea.startswith("{"):
        _cl = json.loads(_linea)
chequear("el historial del club corre entero", _cl is not None,
         (_pc3.stdout[-200:], _pc3.stderr[-400:]))
if _cl:
    # Sólo los rivales de su torneo, y el de más cruces primero.
    chequear("un rival por fila, del más jugado al menos",
             _cl["rivales"] == ["B", "C"], _cl["rivales"])
    # Ganó dos —una de local y una de visitante— y empató una.
    chequear("la cuenta se lee desde el lado del club",
             _cl["contraB"] == [3, 2, 1, 0, 4, 1], _cl["contraB"])
    chequear("y el que le ganó cuenta como perdido",
             _cl["contraC"] == [1, 0, 0, 1], _cl["contraC"])
    chequear("con sus partidos adentro para abrir",
             _cl["partidosDeB"] == 3, _cl["partidosDeB"])
    chequear("y cada uno sabe si fue de local o de visitante",
             _cl["deLocal"] == [True, False, True], _cl["deLocal"])
    # El de la Libertadores no entra: contra un equipo que no vuelve a ver
    # no hay historial, hay una anécdota.
    chequear("los torneos internacionales no entran acá",
             "Z" not in _cl["rivales"], _cl["rivales"])
    chequear("sin club o sin torneo no devuelve nada",
             _cl["sinTorneo"] == [] and _cl["sinEquipo"] == [])
    chequear("el club se encuentra por su nombre",
             _cl["idPorNombre"] == 1 and _cl["idQueNoEsta"] is None, _cl)
chequear("la ficha del club lo lleva puesto",
         '"historial": _sin_reventar(' in _SRV
         and "historial_del_club(tablas.equipo_id(canon" in _SRV)
# Es una sección nueva sobre una pantalla que ya andaba: si algo falla, que
# no se lleve puesta la ficha entera.
chequear("y si falla, la ficha del club sigue saliendo",
         "def _sin_reventar(" in _SRV)

# Y dibujada. Los partidos van adentro de un <details>: cerrados de entrada,
# y abrir uno es cosa del navegador, sin javascript propio ni estado que se
# pueda desincronizar.
if _sh.which("node"):
    _dclub = json.dumps({
        "club": "A", "primary": "#0a2472", "accent": "#f2c94c",
        "historial": [
            {"id": 2, "rival": "B", "pj": 3, "g": 2, "e": 1, "p": 0,
             "gf": 4, "gc": 1, "colores": ["#f2f2f2", "#e2001a"], "partidos": [
                {"id": 1, "dia": "2026-05-11", "local": "A", "visita": "B",
                 "gh": 2, "ga": 0, "casa": True},
                {"id": 2, "dia": "2025-11-02", "local": "B", "visita": "A",
                 "gh": 0, "ga": 1, "casa": False},
                {"id": 3, "dia": "2025-09-21", "local": "A", "visita": "B",
                 "gh": 1, "ga": 1, "casa": True}]},
            {"id": 3, "rival": "C", "pj": 1, "g": 0, "e": 0, "p": 1,
             "gf": 0, "gc": 3, "colores": None, "partidos": [
                {"id": 4, "dia": "2025-08-01", "local": "C", "visita": "A",
                 "gh": 3, "ga": 0, "casa": False}]}]}, ensure_ascii=False)
    _jcl = ("""
globalThis.fetch=async()=>({ok:true, status:200, json:async()=>({})});
const html=historialDelClub(__D__);
const nombres=(html.match(/<span class="nm">([^<]+)<\\/span>/g)||[])
  .map(s=>s.replace(/<[^>]+>/g,''));
console.log(JSON.stringify({
  filas: (html.match(/<details class="riv">/g) || []).length,
  abiertas: (html.match(/<details class="riv" open/g) || []).length,
  nombres,
  partidos: (html.match(/class="hist-p"/g) || []).length,
  enlaces: (html.match(/data-ir/g) || []).length,
  usaElSegundoColor: html.indexOf('#e2001a') >= 0,
  registro: (html.match(/<b>2<\\/b>-1-<b>0<\\/b>/) || []).length,
  vacio: historialDelClub({historial: []})}));
""").replace("__D__", _dclub)
    _gcl = (open(_DOMSITO, encoding="utf-8").read()
            + "\nglobalThis.document=doc; globalThis.window=win;"
              "\nglobalThis.location=loc; globalThis.history=historial;"
              "\nglobalThis.localStorage=almacenLocal;"
              "\nglobalThis.MutationObserver=MutationObserver;"
              "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
              "\nglobalThis.requestAnimationFrame=f=>0;"
              "\nglobalThis.setInterval=()=>0;\nlet App;\n"
            + _app.replace("const App=(()=>{", "App=(()=>{")
                  .replace("  function historialDelClub(d){",
                           "  globalThis.historialDelClub=historialDelClub;\n"
                           "  function historialDelClub(d){") + _jcl)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gcl); _rcl = _f.name
    _pcl = _sub.run(["node", _rcl], capture_output=True, text=True, timeout=60)
    os.unlink(_rcl)
    _dc = json.loads(_pcl.stdout) if _pcl.returncode == 0 and _pcl.stdout else None
    chequear("la sección del club se dibuja", _dc is not None,
             _pcl.stderr.strip().splitlines()[:2])
    if _dc:
        chequear("una fila por rival, con su nombre",
                 _dc["filas"] == 2 and _dc["nombres"] == ["B", "C"], _dc)
        # Cerradas de entrada: lo que pidió Mateo es que los partidos no
        # estén a la vista hasta que uno toque el rival.
        chequear("y ninguna abierta de entrada", _dc["abiertas"] == 0,
                 _dc["abiertas"])
        chequear("los partidos están adentro, listos para abrirse",
                 _dc["partidos"] == 4 and _dc["enlaces"] == 4, _dc)
        chequear("con el registro contra ese rival a la vista",
                 _dc["registro"] == 1, _dc["registro"])
        # El rival de camiseta casi blanca también usa su segundo color acá.
        chequear("y el color del rival, con la misma regla del partido",
                 _dc["usaElSegundoColor"], _dc)
        # Un club sin nada guardado no muestra una sección vacía.
        chequear("sin historial no se muestra la sección", _dc["vacio"] == "")

    # El escudo del rival, chiquito y del lado de la barra.
    _desc = json.dumps({
        "club": "A", "primary": "#0a2472", "accent": "#f2c94c", "historial": [
            {"id": 2, "rival": "Con Escudo", "pj": 2, "g": 1, "e": 1, "p": 0,
             "gf": 3, "gc": 1, "colores": ["#e2001a", "#fff"],
             "escudo": "/img/competidor/1/2222", "partidos": [
                {"id": 1, "dia": "2026-05-11", "local": "A",
                 "visita": "Con Escudo", "gh": 2, "ga": 0, "casa": True}]},
            {"id": 3, "rival": "Sin Escudo", "pj": 1, "g": 0, "e": 0, "p": 1,
             "gf": 0, "gc": 3, "colores": None, "escudo": None, "partidos": [
                {"id": 4, "dia": "2025-08-01", "local": "Sin Escudo",
                 "visita": "A", "gh": 3, "ga": 0, "casa": False}]}]},
        ensure_ascii=False)
    _je = ("""
globalThis.fetch=async()=>({ok:true, status:200, json:async()=>({})});
const html=historialDelClub(__D__);
const sumarios=html.match(/<summary>[\\s\\S]*?<\\/summary>/g)||[];
console.log(JSON.stringify({
  huecos: (html.match(/class="riv-esc"/g) || []).length,
  imagenes: (html.match(/riv-esc"><img/g) || []).length,
  todasConHueco: sumarios.every(s=>s.indexOf('riv-esc') >= 0),
  despuesDeLaBarra: sumarios.every(
    s=>s.indexOf('hist-barra') < s.indexOf('riv-esc'))}));
""").replace("__D__", _desc)
    _ge = (open(_DOMSITO, encoding="utf-8").read()
           + "\nglobalThis.document=doc; globalThis.window=win;"
             "\nglobalThis.location=loc; globalThis.history=historial;"
             "\nglobalThis.localStorage=almacenLocal;"
             "\nglobalThis.MutationObserver=MutationObserver;"
             "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
             "\nglobalThis.requestAnimationFrame=f=>0;"
             "\nglobalThis.setInterval=()=>0;\nlet App;\n"
           + _app.replace("const App=(()=>{", "App=(()=>{")
                 .replace("  function historialDelClub(d){",
                          "  globalThis.historialDelClub=historialDelClub;\n"
                          "  function historialDelClub(d){") + _je)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_ge); _re2 = _f.name
    _pe = _sub.run(["node", _re2], capture_output=True, text=True, timeout=60)
    os.unlink(_re2)
    _es = json.loads(_pe.stdout) if _pe.returncode == 0 and _pe.stdout else None
    chequear("el escudo del rival se dibuja", _es is not None,
             _pe.stderr.strip().splitlines()[:2])
    if _es:
        chequear("va del lado de la barra, no del nombre",
                 _es["despuesDeLaBarra"], _es)
        # El hueco existe tenga escudo o no: si no, las filas sin escudo
        # dejan la barra a distinto largo que las otras.
        chequear("y ocupa su lugar aunque el rival no tenga escudo",
                 _es["huecos"] == 2 and _es["imagenes"] == 1
                 and _es["todasConHueco"], _es)
# Chiquito y con alto fijo, para no empujar el renglón: la fila mide 18px de
# contenido contra los ~16 de la línea de texto.
chequear("es chiquito y no cambia el alto del renglón",
         ".riv summary .riv-esc{width:18px;height:18px" in HTML
         and ".riv summary .riv-esc img{width:18px;height:18px" in HTML
         and "display:block}" in HTML
         and "grid-template-columns:1fr auto 72px 18px" in HTML)
# El escudo sale de donde ya sale el de la ficha, y si esa lectura falla el
# historial se muestra igual: una sección nueva no puede tumbar la pantalla.
chequear("el escudo se pide una sola vez y no puede tumbar el historial",
         "escudos = _sin_reventar(_logos, {}) or {}" in _SRV
         and '"escudo": (escudos.get(rnombre) or {}).get("logo")' in _SRV)

print("\n── el submenú de la Liga Profesional ──")
# Fixture/Tablas no lleva nada en la dirección para no romper los links que
# ya andan dando vueltas; las otras dos sí, así se comparten y el botón de
# atrás las distingue.
for _r, _q in (("/liga-profesional", "Liga Profesional Clausura"),
               ("/liga-profesional/equipos", "Equipos de Liga Profesional"),
               ("/liga-profesional/calculadora", "Calculadora de promedios")):
    _t = server._titulo_de_ruta(_r)
    chequear("%s tiene su propio título" % _r, _t and _q in _t[0],
             _t and _t[0])
# Una dirección inventada no es nuestra: no se sirve la página.
chequear("y una sección que no existe no es una dirección nuestra",
         server._titulo_de_ruta("/liga-profesional/cualquiera") is None)
chequear("las secciones están declaradas en un solo lugar",
         sorted(server.SECCIONES_LIGA) == ["calculadora", "equipos"])
chequear("y la página conoce las mismas",
         "calculadora:{rotulo:'Calculadora de promedios'" in HTML
         and "equipos:{rotulo:'Equipos'" in HTML
         and "const CON_SECCIONES={lpf:['calculadora','equipos']};" in HTML)
# Entrar en frío a una sección tomaba el atajo de la portada de la LPF y
# cargaba el fixture en vez de la sección.
chequear("entrar en frío a una sección no cae en el fixture",
         "d.id==='lpf'&&!SECCIONES[d.sec]" in HTML)

if _sh.which("node"):
    _clubes = [{"name": n, "logo": ("/img/x/%d" % i) if i else None}
               for i, n in enumerate(["River Plate", "Boca Juniors",
                                      "Ñublense", "Aldosivi"])]
    _rsub = json.dumps({
        "/api/clubes": {"clubes": _clubes}, "/api/standings": {"zones": []},
        "/api/annual": {"rows": []}, "/api/promedios": {"rows": []},
        "/api/scorers": {"rows": []},
        "/api/rounds": {"rounds": [1], "current": 1},
        "/api/games": {"games": []}, "/api/ligas": {"ligas": []},
        "/api/visita": {"v": "x"}}, ensure_ascii=False)

    def _entrar(ruta):
        _js = ("""
process.on('unhandledRejection',()=>{});
const RESP=__R__;
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='__E__';
App.init();
(async()=>{
  for(let i=0;i<150;i++) await new Promise(r=>setImmediate(r));
  const sub=doc.querySelector('#subm').innerHTML||'';
  const main=doc.querySelector('#matches').innerHTML||'';
  console.log(JSON.stringify({
    haySubmenu: sub.indexOf('Fixture/Tablas') >= 0,
    opciones: (sub.match(/class="sm/g) || []).length,
    seleccionado: (sub.match(/class="sm on"[^>]*>([^<]+)</) || [])[1] || '',
    pestanas: [...(doc.querySelector('#tabs').innerHTML||'')
      .matchAll(/>([^<]+)<\/button>/g)].map(m=>m[1]),
    equipos: (main.match(/class="eq-item"/g) || []).length,
    nombres: [...main.matchAll(/<span class="nm">([^<]+)</g)].map(m=>m[1]),
    linkAlClub: main.indexOf('href="/boca-juniors"') >= 0}));
})();
""").replace("__R__", _rsub).replace("__E__", ruta)
        _g = (open(_DOMSITO, encoding="utf-8").read()
              + "\nglobalThis.document=doc; globalThis.window=win;"
                "\nglobalThis.location=loc; globalThis.history=historial;"
                "\nglobalThis.localStorage=almacenLocal;"
                "\nglobalThis.MutationObserver=MutationObserver;"
                "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
                "\nglobalThis.requestAnimationFrame=f=>0;"
                "\nglobalThis.setInterval=()=>0;\nlet App;\n"
              + _app.replace("const App=(()=>{", "App=(()=>{") + _js)
        with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as _f:
            _f.write(_g); _rr = _f.name
        _p = _sub.run(["node", _rr], capture_output=True, text=True, timeout=60)
        os.unlink(_rr)
        return json.loads(_p.stdout) if _p.returncode == 0 and _p.stdout else None

    # El error que costó una subida: `drawSubmenu()` y `pestanasLpf()` se
    # llamaban ANTES de que `shell()` armara la pantalla. En el navegador
    # `querySelector` devuelve null y no se dibujaba nada; peor todavía,
    # `shell()` después reescribía las pestañas con las de su plantilla y
    # se llevaba puesta la de "Promedios 2027".
    #
    # Acá no se detectaba porque el DOM de mentira inventaba un nodo para
    # cualquier selector. Ahora un id que nadie escribió no existe, igual
    # que en el navegador, y esta prueba tiene sentido.
    # Con `find` y no con `index`: si el texto no está, esto tiene que
    # fallar como un control más, no reventar la corrida entera y dejar sin
    # correr todo lo que viene después.
    _iShell = HTML.find("shell();\n      drawSide();")
    _iDespues = HTML.find("      pestanasLpf();\n      drawSubmenu();")
    chequear("el submenú y las pestañas se dibujan después del armazón",
             _iShell >= 0 and _iDespues > _iShell, (_iShell, _iDespues))
    chequear("y el navegador de mentira sabe que un id sin escribir no existe",
             "const IDS = new Set([" in open(_DOMSITO, encoding="utf-8").read()
             and "if(m && !IDS.has(m[1])) return null;"
                 in open(_DOMSITO, encoding="utf-8").read())

    _s1 = _entrar("/liga-profesional")
    _s2 = _entrar("/liga-profesional/equipos")
    chequear("el submenú se dibuja al entrar", _s1 is not None and _s2 is not None,
             (_s1, _s2))
    if _s1 and _s2:
        chequear("con las tres opciones y Fixture/Tablas ya elegida",
                 _s1["haySubmenu"] and _s1["opciones"] == 3
                 and _s1["seleccionado"] == "Fixture/Tablas", _s1)
        # Y las pestañas del panel, dibujadas de verdad: `shell()` las
        # reescribía con las de su plantilla y se llevaba puesta la nueva.
        chequear("y las pestañas incluyen la de Promedios 2027",
                 _s1["pestanas"] == ["Zona A", "Zona B", "Anual", "Promedios",
                                     "Promedios 2027", "Goles"],
                 _s1["pestanas"])
        chequear("y entrando por el link de una sección, ésa",
                 _s2["seleccionado"] == "Equipos", _s2)
        # El bug: por el atajo de la LPF, entrar en frío a una sección
        # cargaba el fixture y la sección no se armaba nunca.
        chequear("los equipos aparecen entrando en frío", _s2["equipos"] == 4,
                 _s2["equipos"])
        chequear("ordenados y con su escudo",
                 _s2["nombres"] == ["Aldosivi", "Boca Juniors", "Ñublense",
                                    "River Plate"], _s2["nombres"])
        chequear("y cada uno lleva a su ficha", _s2["linkAlClub"], _s2)


print("\n── los promedios: el año que viene y lo que necesita cada uno ──")
# AFA publica los puntos de cada temporada por separado pero los partidos
# jugados todos juntos. Para la tabla del año que viene hay que poder
# restarle los partidos de 2024, no sólo los puntos: se deducen por
# diferencia usando a los ascendidos, que no jugaron todas las temporadas.
# Los partidos de cada temporada no salen de ningún lado: AFA publica los
# tres juntos en una sola columna. Están cargados a mano —41 en 2024 y 32
# en 2025— y lo que hace el servidor es comprobar que cierren con lo que
# publica AFA antes de mostrar nada.
_A = server.PARTIDOS_DE_TEMPORADA["2024"]
_B = server.PARTIDOS_DE_TEMPORADA["2025"]
_C = 22                                   # lo que va de 2026

# La tabla real, tal como se ve hoy en el sitio: total, y los tres años.
_REALES = [("Lanús", 140, 59, 50, 31), ("Huracán", 139, 62, 47, 30),
           ("Talleres (C)", 136, 72, 34, 30),
           ("Independiente Rivadavia", 131, 46, 43, 42),
           ("Barracas Central", 128, 49, 49, 30), ("Unión", 127, 60, 39, 28),
           ("San Lorenzo", 125, 45, 51, 29), ("Belgrano", 122, 49, 37, 36),
           ("Instituto", 121, 53, 34, 34), ("Tigre", 119, 39, 49, 31),
           ("Platense", 116, 57, 35, 24), ("Banfield", 101, 41, 35, 25),
           ("Sarmiento (J)", 101, 35, 35, 31)]
_filasP = [{"team": {"name": n}, "pts": pts, "pj": _A + _B + _C,
            "p2024": a, "p2025": b, "p2026": c,
            "prom": round(pts / (_A + _B + _C), 4)}
           for n, pts, a, b, c in _REALES]
# Lo primero: que los tres años sumen el total en cada club. Si esto no
# diera, el resto de la cuenta no tendría sentido.
chequear("los tres años suman el total en cada club",
         all(r["p2024"] + r["p2025"] + r["p2026"] == r["pts"] for r in _filasP))
_pt = server.partidos_por_temporada(_filasP, {})
chequear("los partidos de la temporada en curso salen restando",
         _pt == {"2024": _A, "2025": _B, "2026": _C}, _pt)
# Si a algún club no le cierra —otro formato, un descuento de puntos, un
# ascendido con otro arranque— el modelo está mal, y una tabla de descensos
# equivocada es mucho peor que no mostrarla.
_roto = [dict(r) for r in _filasP]
_roto[0]["pj"] += 1
chequear("y si a algún club no le cierra, no se muestra nada",
         server.partidos_por_temporada(_roto, {}) is None)
# Nadie puede haber sacado más de tres puntos por partido.
_imposible = [dict(r) for r in _filasP]
_imposible[0] = dict(_imposible[0], p2024=3 * _A + 1)
chequear("ni si alguno sacó más puntos de los que se podían",
         server.partidos_por_temporada(_imposible, {}) is None)
_prox = server.tabla_del_ano_que_viene(_filasP, _pt)
_porNombre = {x["team"]["name"]: x for x in _prox}
# Lanús: 50 puntos en 2025 y 31 en lo que va de 2026, sobre 32 + 22 partidos.
chequear("la tabla del año que viene es la de hoy sin 2024",
         _porNombre["Lanús"]["pts"] == 81
         and _porNombre["Lanús"]["pj"] == _B + _C
         and abs(_porNombre["Lanús"]["prom"] - 81 / 54) < 1e-9,
         _porNombre["Lanús"])
# Y lo que la hace interesante: el orden cambia. Independiente Rivadavia
# está 13° hoy y primero el año que viene, porque de 2024 pierde 46 puntos
# y Talleres pierde 72.
chequear("y el orden cambia, que es de lo que se trata",
         _prox[0]["team"]["name"] == "Independiente Rivadavia"
         and _porNombre["Talleres (C)"]["pierde"] == 72,
         [x["team"]["name"] for x in _prox[:3]])
chequear("sin la deducción no se arma la tabla",
         server.tabla_del_ano_que_viene(_filasP, None) is None)


def _fn(n, pts, pj, rest):
    return {"team": {"name": n}, "pts": pts, "pj": pj, "restantes": rest,
            "prom": round(pts / pj, 4)}


_filasN = sorted([_fn("Comodo", 90, 50, 2), _fn("Peligro", 45, 50, 2),
                  _fn("Ultimo", 40, 50, 2)], key=lambda r: -r["prom"])
server.puntos_para_salvarse(_filasN)
_nec = {r["team"]["name"]: r["necesita"] for r in _filasN}
# Peligro necesita 2: con 1 queda 46/52 = 0,88461, exactamente el mejor
# promedio posible de Ultimo. Empatar no alcanza.
chequear("los puntos que necesita cada uno salen bien",
         _nec == {"Comodo": 0, "Peligro": 2, "Ultimo": None}, _nec)
# El error que tenía: contar sólo contra "los que hoy descienden" hacía que
# el último se quedara sin nadie a quien superar y figurara salvado.
chequear("y el último de la tabla no figura salvado",
         _nec["Ultimo"] is None)

# Cuándo se pinta de amarillo.
#
# "Todavía lo pueden alcanzar" es cierto casi siempre: a mitad de
# temporada quedan cuarenta y ocho puntos en juego y una tabla que se abre
# en cuarenta, así que cualquiera puede terminar en cualquier lado. Con esa
# regla quedaban diecisiete equipos marcados, y el escenario que lo
# justificaba era que el último ganara sus dieciséis partidos y el otro
# perdiera los dieciséis. Ahora se pinta por lo que le costaría salvarse.
def _amarillos(faltan):
    filas = []
    for n, pts, _a, _b, _c in _REALES:
        r = {"team": {"name": n}, "pts": pts, "pj": 95, "restantes": faltan,
             "prom": round(pts / 95, 4)}
        base = 95 + faltan
        r["promMax"] = round((pts + 3 * faltan) / base, 4)
        r["promMin"] = round(pts / base, 4)
        filas.append(r)
    filas.sort(key=lambda r: -r["prom"])
    server.puntos_para_salvarse(filas)
    zona = filas[-server.DESCIENDEN:]
    marcados = 0
    for r in filas:
        d = 3 * faltan
        exige = (1.0 if r.get("necesita") is None or not d
                 else r["necesita"] / d)
        if exige > 1.0 / 3 and r not in zona:
            marcados += 1
    return marcados

_a16, _a6, _a2 = _amarillos(16), _amarillos(6), _amarillos(2)
chequear("el amarillo se achica solo a medida que avanza el torneo",
         _a16 > _a6 >= _a2, (_a16, _a6, _a2))
# Faltando dos fechas, con seis puntos en juego, casi nadie está en duda.
chequear("y sobre el final queda en muy pocos", _a2 <= 2, _a2)
chequear("se pinta por lo que le costaría, no por si es alcanzable",
         'r["enRiesgo"] = exige > UN_TERCIO' in _SRV
         and 'r["exige"] = round(exige, 3)' in _SRV)
# Y que la tabla muestre el número, para que el color signifique algo.
chequear("la tabla dice cuántos puntos necesita",
         '<td class="nec">${r.necesita===0?' in HTML
         and "los ${(rows[0]||{}).disponibles ?? 0} que quedan en juego" in HTML)
# El mismo cruce en la misma instancia, pero de dos ediciones distintas:
# la Copa Argentina es a partido único y guardamos dos temporadas, así que
# Instituto–Platense de una edición y de la otra aparecían como "Ida" y
# "Vuelta" de una llave que nunca existió.
_ca1 = {"id": 1, "round": 3, "temporada": 15, "start": "2025-09-05T20:00:00",
        "home": {"canon": "Instituto", "name": "Instituto"},
        "away": {"canon": "Platense", "name": "Platense"}}
_ca2 = {"id": 2, "round": 3, "temporada": 16, "start": "2026-08-19T20:00:00",
        "home": {"canon": "Instituto", "name": "Instituto"},
        "away": {"canon": "Platense", "name": "Platense"}}
server.marcar_ida_vuelta([_ca1, _ca2])
chequear("dos ediciones distintas no son una llave de ida y vuelta",
         _ca1.get("tramo") is None and _ca2.get("tramo") is None,
         (_ca1.get("tramo"), _ca2.get("tramo")))
# Y una llave de verdad —dos partidos de la misma edición y la misma
# instancia— se sigue marcando.
_id = {"id": 3, "round": 5, "temporada": 69, "start": "2026-08-12T20:00:00",
       "home": {"canon": "Boca Juniors", "name": "Boca Juniors"},
       "away": {"canon": "Flamengo", "name": "Flamengo"}}
_vu = {"id": 4, "round": 5, "temporada": 69, "start": "2026-08-19T20:00:00",
       "home": {"canon": "Flamengo", "name": "Flamengo"},
       "away": {"canon": "Boca Juniors", "name": "Boca Juniors"}}
server.marcar_ida_vuelta([_vu, _id])
chequear("y la de ida y vuelta de verdad se sigue marcando",
         _id.get("tramo") == "Ida" and _vu.get("tramo") == "Vuelta",
         (_id.get("tramo"), _vu.get("tramo")))
chequear("el cuadro tampoco junta dos ediciones en una llave",
         "(m.get(\"temporada\"), llave_de(m)), []).append(m)" in _SRV)

# El caso de verdad que apareció en la Copa Argentina: el mismo partido
# llegando dos veces, con dos identificadores distintos, el mismo día y el
# mismo local. Se mostraba como "Partidos de ida" y "Partidos de vuelta" de
# una llave que no existe.
def _pca(i, loc, vis, dia, gh=None, live=None):
    return {"id": i, "start": dia + "T21:15:00", "gh": gh,
            "ga": 0 if gh is not None else None, "liveId": live,
            "round": 3, "temporada": 16,
            "home": {"canon": loc, "name": loc},
            "away": {"canon": vis, "name": vis}}

_dupes = [_pca(1, "Platense", "Instituto", "2026-08-27"),
          _pca(2, "Platense", "Instituto", "2026-08-27", live=99)]
_limpio = server.sin_repetidos(_dupes)
chequear("el mismo partido dos veces queda en una sola fila",
         len(_limpio) == 1, len(_limpio))
# Se queda el que más sabe, para que el repetido no se lleve ningún dato.
chequear("y se queda el que trae más información",
         _limpio[0]["id"] == 2, _limpio[0]["id"])
# Segunda red: aunque un repetido sobreviva, no puede volverse una llave.
_dos = [_pca(1, "Platense", "Instituto", "2026-08-27"),
        _pca(2, "Platense", "Instituto", "2026-08-27")]
server.marcar_ida_vuelta(_dos)
chequear("dos partidos el mismo día no son ida y vuelta",
         [x.get("tramo") for x in _dos] == [None, None], _dos)
# En una llave de verdad el local se invierte: el que recibe la ida visita
# la vuelta. Dos con el mismo local son el mismo partido repetido.
_mismoLocal = [_pca(1, "Platense", "Instituto", "2026-08-27"),
               _pca(2, "Platense", "Instituto", "2026-09-03")]
server.marcar_ida_vuelta(_mismoLocal)
chequear("ni dos con el mismo local, aunque sean de días distintos",
         [x.get("tramo") for x in _mismoLocal] == [None, None], _mismoLocal)
_llave = [_pca(1, "Boca Juniors", "Flamengo", "2026-08-12"),
          _pca(2, "Flamengo", "Boca Juniors", "2026-08-19")]
server.marcar_ida_vuelta(_llave)
chequear("y la llave de verdad se sigue marcando",
         [x.get("tramo") for x in _llave] == ["Ida", "Vuelta"], _llave)
chequear("el fixture se limpia antes de armar el cuadro",
         "games = sin_repetidos(games)" in _SRV
         and _SRV.index("games = sin_repetidos(games)")
             < _SRV.index('res = {"games": games'))

chequear("la calculadora se sirve de un solo pedido",
         '"/api/calculadora": api_calculadora,' in _SRV
         and "def api_calculadora(q):" in _SRV)
# Y la tabla del año que viene vive en la principal, al lado de Promedios.
chequear("los promedios del año que viene tienen su pestaña",
         "['prox','Promedios 2027']" in HTML
         and "else if(S.tab==='prox')" in HTML)

if _sh.which("node"):
    _eqp = lambda n: {"name": n, "canon": n, "logo": None, "short": ""}
    _pprom = json.dumps({
        "rows": [], "porTemporada": {"2024": 27, "2025": 30, "2026": 20},
        "proximaTemporada": [
            {"pos": 1, "team": _eqp("Subio2026"), "pts": 35, "pj": 20,
             "prom": 1.75, "pierde": 0, "jugo2024": False,
             "descendiendo": False},
            {"pos": 2, "team": _eqp("Veterano"), "pts": 75, "pj": 50,
             "prom": 1.5, "pierde": 40, "jugo2024": True,
             "descendiendo": False},
            {"pos": 3, "team": _eqp("Flojo"), "pts": 34, "pj": 50,
             "prom": 0.68, "pierde": 20, "jugo2024": True,
             "descendiendo": True}]}, ensure_ascii=False)
    _jpx = ("""
process.on('unhandledRejection',()=>{});
globalThis.fetch=async()=>({ok:true, status:200, json:async()=>({})});
S.promedios=__P__;
const html=proxTable();
S.promedios={};
console.log(JSON.stringify({
  filas: (html.match(/<tr class=/g) || []).length,
  desciende: (html.match(/fila-desciende/g) || []).length,
  loQuePierde: html.indexOf('−40') >= 0 && html.indexOf('>—<') >= 0,
  explica: html.indexOf('27 en 2024') >= 0,
  sinDeduccion: proxTable().indexOf('Todavía no se') >= 0}));
""").replace("__P__", _pprom)
    _gpx = (open(_DOMSITO, encoding="utf-8").read()
            + "\nglobalThis.document=doc; globalThis.window=win;"
              "\nglobalThis.location=loc; globalThis.history=historial;"
              "\nglobalThis.localStorage=almacenLocal;"
              "\nglobalThis.MutationObserver=MutationObserver;"
              "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
              "\nglobalThis.requestAnimationFrame=f=>0;"
              "\nglobalThis.setInterval=()=>0;\nlet App;\n"
            + _app.replace("const App=(()=>{", "App=(()=>{")
                  .replace("  function proxTable(){",
                           "  globalThis.proxTable=proxTable; globalThis.S=S;\n"
                           "  function proxTable(){") + _jpx)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gpx); _rpx = _f.name
    _ppx = _sub.run(["node", _rpx], capture_output=True, text=True, timeout=60)
    os.unlink(_rpx)
    _px = json.loads(_ppx.stdout) if _ppx.returncode == 0 and _ppx.stdout else None
    chequear("la tabla del año que viene se dibuja", _px is not None,
             _ppx.stderr.strip().splitlines()[:2])
    if _px:
        chequear("con una fila por equipo y el descenso marcado",
                 _px["filas"] == 3 and _px["desciende"] == 1, _px)
        chequear("y diciendo cuántos puntos pierde cada uno",
                 _px["loQuePierde"], _px)
        # Los partidos por temporada son deducidos, no publicados: que la
        # pantalla lo diga en vez de presentarlos como un dato de AFA.
        chequear("explica que los partidos por temporada son deducidos",
                 _px["explica"], _px)
        chequear("y si la deducción no cierra, lo dice en vez de inventar",
                 _px["sinDeduccion"], _px)

if _sh.which("node"):
    _rcalc = json.dumps({
        "/api/calculadora": {
            "desciende": 1, "fuente": "AFA", "nota": "nota",
            "equipos": [
                {"name": "Comodo", "logo": None, "pts": 90, "pj": 50,
                 "prom": 1.8, "restantes": 2, "necesita": 0},
                {"name": "Peligro", "logo": None, "pts": 45, "pj": 50,
                 "prom": 0.9, "restantes": 2, "necesita": 2},
                {"name": "Ultimo", "logo": None, "pts": 40, "pj": 50,
                 "prom": 0.8, "restantes": 2, "necesita": None}],
            "faltan": [
                {"id": "1", "ronda": 15, "dia": "2026-09-01",
                 "local": "Peligro", "visita": "Ultimo"},
                {"id": "2", "ronda": 15, "dia": "2026-09-01",
                 "local": "Comodo", "visita": "Peligro"},
                {"id": "3", "ronda": 16, "dia": "2026-09-08",
                 "local": "Ultimo", "visita": "Comodo"}]},
        "/api/ligas": {"ligas": []}, "/api/visita": {"v": "x"},
        "/api/clubes": {"clubes": []}}, ensure_ascii=False)
    _jc2 = ("""
process.on('unhandledRejection',()=>{});
const RESP=__R__;
globalThis.fetch=async(u)=>{
  const k=Object.keys(RESP).sort((a,b)=>b.length-a.length).find(x=>u.startsWith(x));
  return {ok:true, status:200, json:async()=>(k?RESP[k]:{})};};
loc.pathname='/liga-profesional/calculadora';
App.init();
(async()=>{
  const esperar=async n=>{for(let i=0;i<n;i++) await new Promise(r=>setImmediate(r));};
  await esperar(150);
  const der=()=>doc.querySelector('#right').innerHTML||'';
  const izq=()=>doc.querySelector('#matches').innerHTML||'';
  const leer=()=>[...der().matchAll(
    /<span class="tn">([^<]+)<\\/span>[\\s\\S]*?<td class="pts[^"]*">([\\d.]+)<\\/td>\\s*<td>(\\d+)<\\/td><td>(\\d+)<\\/td>/g)]
    .map(m=>[m[1], m[2], +m[3], +m[4]]);
  const antes=leer();
  const partidos=(izq().match(/class="calc-p"/g)||[]).length;
  const fechas=(izq().match(/class="calc-fecha"/g)||[]).length;
  const botones=(izq().match(/class="cbtn-lim"/g)||[]).length;
  App.calc('1','l'); await esperar(5); const gano=leer();
  App.calc('2','l'); await esperar(5); const perdio=leer();
  App.calc('2','l'); await esperar(5); const desmarcado=leer();
  App.calcLimpiar(); await esperar(5);
  // el botón de completar: marca todo lo que quedó sin marcar
  App.calc('1','e'); await esperar(5);
  App.calcSortear(); await esperar(5);
  const trasSortear=izq();
  const marcadosTrasSortear=(trasSortear.match(/class="cbtn3 on"/g)||[]).length;
  const respetoElMio=/marcado/.test(trasSortear)
    && (trasSortear.match(/<b>3<\/b> marcados/)||[]).length===1;
  App.calcLimpiar(); await esperar(5);
  console.log(JSON.stringify({partidos, fechas, antes, gano, perdio, botones,
    desmarcarVuelve: JSON.stringify(desmarcado)===JSON.stringify(gano),
    limpiarVuelve: JSON.stringify(leer())===JSON.stringify(antes),
    marcadosTrasSortear, respetoElMio}));
})();
""").replace("__R__", _rcalc)
    _gc2 = (open(_DOMSITO, encoding="utf-8").read()
            + "\nglobalThis.document=doc; globalThis.window=win;"
              "\nglobalThis.location=loc; globalThis.history=historial;"
              "\nglobalThis.localStorage=almacenLocal;"
              "\nglobalThis.MutationObserver=MutationObserver;"
              "\nglobalThis.URL=URL2; globalThis.screen={width:1440,height:900};"
              "\nglobalThis.requestAnimationFrame=f=>0;"
              "\nglobalThis.setInterval=()=>0;\nlet App;\n"
            + _app.replace("const App=(()=>{", "App=(()=>{") + _jc2)
    with _tmp.NamedTemporaryFile("w", suffix=".js", delete=False,
                                 encoding="utf-8") as _f:
        _f.write(_gc2); _rc3 = _f.name
    _pc4 = _sub.run(["node", _rc3], capture_output=True, text=True, timeout=60)
    os.unlink(_rc3)
    _ca = json.loads(_pc4.stdout) if _pc4.returncode == 0 and _pc4.stdout else None
    chequear("la calculadora se dibuja", _ca is not None,
             _pc4.stderr.strip().splitlines()[:2])
    if _ca:
        chequear("con los partidos que faltan, agrupados por fecha",
                 _ca["partidos"] == 3 and _ca["fechas"] == 2, _ca)
        chequear("y la tabla de hoy antes de tocar nada",
                 _ca["antes"] == [["Comodo", "1.800", 90, 50],
                                  ["Peligro", "0.900", 45, 50],
                                  ["Ultimo", "0.800", 40, 50]], _ca["antes"])
        # Peligro le gana a Ultimo: 48/51 y 40/51. Los dos suman un jugado.
        chequear("marcar un partido rehace los dos promedios",
                 _ca["gano"] == [["Comodo", "1.800", 90, 50],
                                 ["Peligro", "0.941", 48, 51],
                                 ["Ultimo", "0.784", 40, 51]], _ca["gano"])
        # Y después Comodo le gana a Peligro: 93/51 y 48/52.
        chequear("y se van acumulando",
                 _ca["perdio"] == [["Comodo", "1.824", 93, 51],
                                   ["Peligro", "0.923", 48, 52],
                                   ["Ultimo", "0.784", 40, 51]], _ca["perdio"])
        # Tocar el mismo botón otra vez lo desmarca: es la forma de
        # arrepentirse sin buscar un botón de borrar.
        chequear("tocar el mismo resultado otra vez lo desmarca",
                 _ca["desmarcarVuelve"])
        chequear("y empezar de nuevo devuelve la tabla de hoy",
                 _ca["limpiarVuelve"])
        # Y el botón de completar lo que falta: llena los tres partidos,
        # uno por equipo por fecha, sin pisar lo que ya estaba marcado.
        chequear("hay un botón para completar los que faltan",
                 _ca["botones"] == 2, _ca["botones"])
        chequear("y completa todos los que quedaban sin marcar",
                 _ca["marcadosTrasSortear"] == 3,
                 _ca["marcadosTrasSortear"])

print("\n" + ("Todo bien." if not fallas
              else "FALLARON %d:\n  - %s" % (len(fallas), "\n  - ".join(fallas))))
sys.exit(1 if fallas else 0)
