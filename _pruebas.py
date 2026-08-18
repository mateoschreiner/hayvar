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

HTML = open(os.path.join(AQUI, "index.html"), encoding="utf-8").read()
fallas = []
def chequear(titulo, cond, detalle=""):
    print("  %s %s%s" % ("✓" if cond else "✗", titulo,
                         "" if cond else "  <- " + str(detalle)))
    if not cond:
        fallas.append(titulo)


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
server.almacen.guardar("recorrido:version", 0)
server.reparar_recorridos()
_comps = sorted({c for f in server.LIGAS.values() for c in server.comps_de(f)})
chequear("reabre el recorrido de todas las competencias",
         not [c for c in _comps
              if (server.almacen.leer("hist:%s" % c)[0] or {}).get("listo")])
chequear("sin borrar un solo partido",
         all(len(server.almacen.leer("fixture:%s" % c)[0] or []) == 1 for c in _comps))
server.almacen.guardar("hist:72", {"listo": True})
server.reparar_recorridos()
chequear("y no se repite dentro de la misma versión",
         server.almacen.leer("hist:72")[0] == {"listo": True})
_src = open(os.path.join(AQUI, "server.py"), encoding="utf-8").read()
chequear("el cliente que se va no ensucia el log",
         "except self.SE_FUE:" in _src and "def handle_one_request" in _src)


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
