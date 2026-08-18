# -*- coding: utf-8 -*-
"""
Regresión de HAYVAR. Se corre con:  python3 _pruebas.py

No pega contra 365scores: las respuestas de la fuente se simulan. Lo que
prueba es lo nuestro —cómo se ordena, se filtra y se cuenta— que es donde
estuvieron todos los errores.
"""
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
malos = [(n, c) for n, d in server.CLUBES_INFO.items()
         for c in ("titular", "suplente")
         if d["camisetas"][c]["patron"] not in SABE]
chequear("los 30 clubes tienen ficha", len(server.CLUBES_INFO) == 30,
         len(server.CLUBES_INFO))
chequear("todos los patrones se saben dibujar", not malos, malos)
chequear("nadie quedó sin sitio oficial",
         all(d.get("sitio") for d in server.CLUBES_INFO.values()))


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
    t = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=dias)
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


print("\n" + ("Todo bien." if not fallas
              else "FALLARON %d:\n  - %s" % (len(fallas), "\n  - ".join(fallas))))
sys.exit(1 if fallas else 0)
