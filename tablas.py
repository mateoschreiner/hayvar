# -*- coding: utf-8 -*-
"""
Los partidos, uno por fila.

POR QUÉ

El almacén guarda todo como clave y valor: un torneo entero es un solo
bloque de JSON. Anda bien para servir una pantalla —se lee el bloque, se
manda— pero no se le puede preguntar nada. `fixture:11` son 753 partidos en
463 kilobytes: para mirar uno hay que parsear los 753, y para corregir un
resultado hay que reescribir los 463 KB enteros.

Y lo que no se puede hacer de ninguna manera es cruzar. "Cómo les fue las
últimas cinco veces que se cruzaron", "cómo viene el club comparado con la
temporada pasada", "en qué torneos jugó este equipo este año": todas esas
preguntas atraviesan los dieciséis bloques, y con bloques no hay forma.

Acá cada partido es una fila. Los datos son los mismos —esto se arma
leyendo los bloques que ya están, sin pedirle nada a nadie— pero se les
puede preguntar.


QUÉ NO ES

No reemplaza al almacén. Los bloques siguen siendo la verdad y las
pantallas se siguen sirviendo de ahí. Esto es un índice armado a partir de
ellos: si sale mal, se borra y se vuelve a armar, y no se pierde nada.


EL PARTIDO QUE APARECE DOS VECES

Las clasificatorias de la Champions y la Europa se guardan en dos
competencias: la del torneo y la de la previa, que 365scores numera aparte.
Son 151 partidos que están en dos bloques con el mismo identificador.

Con la clave equivocada eso se convierte en 151 partidos contados dos
veces, y ahí las tablas quedan mal armadas para siempre. La clave es el
identificador del partido y nada más, y cuando el mismo llega por los dos
lados gana el de la competencia principal: un partido se jugó una sola vez.
"""

import sqlite3

import almacen

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS partidos (
    id         INTEGER PRIMARY KEY,
    liga       TEXT    NOT NULL,
    comp       INTEGER,
    -- Si vino por la competencia principal del torneo o por la de su
    -- clasificación. Decide quién gana cuando el mismo partido llega por
    -- los dos lados.
    principal  INTEGER NOT NULL DEFAULT 1,
    temporada  INTEGER,
    ronda      INTEGER,
    etapa      TEXT,
    zona       TEXT,
    dia        TEXT,
    cuando     TEXT,
    local_id   INTEGER,
    local      TEXT,
    visita_id  INTEGER,
    visita     TEXT,
    gh         INTEGER,
    ga         INTEGER,
    estado     TEXT,
    cancha     TEXT
);
-- El calendario de un torneo, que es como se lee hoy.
CREATE INDEX IF NOT EXISTS ix_partidos_liga ON partidos(liga, temporada, ronda);
-- Los partidos de un día, para la portada.
CREATE INDEX IF NOT EXISTS ix_partidos_dia ON partidos(dia);
-- Y los de un equipo. Van dos índices, uno por lado: un equipo juega de
-- local en la mitad de sus partidos y de visitante en la otra, y sin los
-- dos la mitad de cualquier pregunta sobre un club recorre la tabla entera.
CREATE INDEX IF NOT EXISTS ix_partidos_local ON partidos(local_id);
CREATE INDEX IF NOT EXISTS ix_partidos_visita ON partidos(visita_id);

-- Quién jugó qué. Es la tabla del medio, la que une jugadores con partidos,
-- y la que hace que se pueda preguntar por un jugador sin recorrer todo.
--
-- El jugador se identifica por su nombre normalizado, que es como está
-- guardado en todos lados desde el principio. No es perfecto —dos personas
-- pueden llamarse igual— pero inventarle otra identidad acá sería tener dos
-- formas de nombrar a la misma persona, que es peor.
-- Sin columna de torneo a propósito. La clave `pj:<liga>:<jugador>` lleva
-- uno adentro, pero no siempre es el que corresponde: quedaron restos de
-- cuando un partido sin torneo conocido se anotaba como Liga Profesional
-- por defecto, y así hay jugadores de LaLiga con partidos anotados en la
-- LPF. El torneo de un partido lo sabe la tabla de partidos, que se arma
-- del calendario; guardarlo también acá sería guardar dos respuestas para
-- la misma pregunta, y una de las dos equivocada.
CREATE TABLE IF NOT EXISTS participaciones (
    jugador  TEXT    NOT NULL,
    partido  INTEGER NOT NULL,
    PRIMARY KEY (jugador, partido)
);
CREATE INDEX IF NOT EXISTS ix_part_jugador ON participaciones(jugador);
CREATE INDEX IF NOT EXISTS ix_part_partido ON participaciones(partido);

-- Los goles, con su autor y su minuto.
--
-- La clave lleva el minuto porque un jugador puede hacer dos en el mismo
-- partido y son dos goles, no uno. Cuando el minuto no se sabe va -1: se
-- pierde el caso raro de dos goles sin minuto del mismo jugador en el mismo
-- partido, y a cambio volver a pasar la misma lista nunca duplica nada, que
-- es lo que importa.
CREATE TABLE IF NOT EXISTS goles (
    partido  INTEGER NOT NULL,
    jugador  TEXT    NOT NULL,
    minuto   INTEGER NOT NULL DEFAULT -1,
    equipo   TEXT,
    lado     TEXT,
    PRIMARY KEY (partido, jugador, minuto)
);
CREATE INDEX IF NOT EXISTS ix_goles_jugador ON goles(jugador);
CREATE INDEX IF NOT EXISTS ix_goles_partido ON goles(partido);

-- El dibujo de cada equipo en cada partido: "4-3-3". Va aparte y no en la
-- tabla de partidos porque son dos por partido, uno por lado.
CREATE TABLE IF NOT EXISTS alineaciones (
    partido    INTEGER NOT NULL,
    lado       TEXT    NOT NULL,          -- h o a
    equipo     TEXT,
    dibujo     TEXT,
    confirmada INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (partido, lado)
);

-- Quién estuvo en cada partido y cómo: titular, en el banco o dirigiendo,
-- en qué puesto, con qué número y dónde paraba en la cancha.
--
-- Es distinto de `participaciones`, que dice nada más si jugó: eso se sabe
-- de todos los torneos y esto sólo de los diez que valen la pena guardar
-- en detalle. Se separan para que la carrera de un jugador siga estando
-- completa aunque su formación en el Federal A no se guarde.
CREATE TABLE IF NOT EXISTS formaciones (
    partido  INTEGER NOT NULL,
    jugador  TEXT    NOT NULL,
    equipo   TEXT,
    lado     TEXT,
    rol      TEXT,                        -- titular, suplente o dt
    puesto   TEXT,
    dorsal   INTEGER,
    puntaje  REAL,
    x        REAL,
    y        REAL,
    PRIMARY KEY (partido, jugador)
);
CREATE INDEX IF NOT EXISTS ix_form_jugador ON formaciones(jugador);
CREATE INDEX IF NOT EXISTS ix_form_partido ON formaciones(partido);

-- Las estadísticas de un jugador en un partido, una por fila.
--
-- Van así y no como columnas porque la fuente publica unas cuarenta
-- distintas y no las mismas para todos: un arquero tiene atajadas y un
-- delantero no. Con columnas, cada estadística nueva sería una migración;
-- así, entra sola.
CREATE TABLE IF NOT EXISTS estadisticas (
    partido  INTEGER NOT NULL,
    jugador  TEXT    NOT NULL,
    clave    TEXT    NOT NULL,
    valor    REAL,
    PRIMARY KEY (partido, jugador, clave)
);
CREATE INDEX IF NOT EXISTS ix_est_jugador ON estadisticas(jugador, clave);
"""

_CAMPOS = ("id", "liga", "comp", "principal", "temporada", "ronda", "etapa",
           "zona", "dia", "cuando", "local_id", "local", "visita_id", "visita",
           "gh", "ga", "estado", "cancha")


def iniciar():
    """Crea la tabla y sus índices. Se puede llamar todas las veces."""
    try:
        with almacen.conexion() as c:
            c.executescript(_ESQUEMA)
            c.commit()
        return True
    except sqlite3.Error:
        return False


def _fila(m, liga, comp, principal):
    """Un partido del bloque, convertido en fila."""
    loc, vis = m.get("home") or {}, m.get("away") or {}
    cuando = m.get("start") or ""
    return (
        m.get("id"), liga, comp, 1 if principal else 0,
        m.get("temporada"), m.get("round"),
        (m.get("etapa") or m.get("stage") or "") or None,
        m.get("zone"),
        cuando[:10] or None, cuando or None,
        loc.get("id"), loc.get("canon") or loc.get("name"),
        vis.get("id"), vis.get("canon") or vis.get("name"),
        m.get("gh"), m.get("ga"), m.get("status"),
        m.get("venue") or None,
    )


def guardar(liga, comp, partidos, principal=True):
    """
    Mete o actualiza estos partidos.

    El `WHERE` del final es lo que resuelve el partido que llega dos veces:
    lo que viene por la competencia de la clasificación no pisa lo que ya
    está por la principal. Al revés sí, porque la principal manda.

    Devuelve cuántas filas quedaron escritas.
    """
    filas = [_fila(m, liga, comp, principal) for m in partidos if m.get("id")]
    if not filas:
        return 0
    huecos = ",".join("?" * len(_CAMPOS))
    pisar = ", ".join("%s=excluded.%s" % (k, k) for k in _CAMPOS if k != "id")
    sql = ("INSERT INTO partidos (%s) VALUES (%s) "
           "ON CONFLICT(id) DO UPDATE SET %s "
           "WHERE excluded.principal >= partidos.principal"
           % (",".join(_CAMPOS), huecos, pisar))
    try:
        with almacen.conexion() as c:
            c.executemany(sql, filas)
            c.commit()
        return len(filas)
    except sqlite3.Error:
        return 0


def guardar_participaciones(filas):
    """
    Quién jugó qué. `filas` son pares (jugador, partido).

    Con `OR REPLACE` volver a pasar lo mismo no duplica: la clave es el par
    jugador–partido, que es lo que de verdad no se puede repetir.
    """
    limpias = [(j, int(p)) for j, p in filas if j and p]
    if not limpias:
        return 0
    try:
        with almacen.conexion() as c:
            c.executemany("INSERT OR REPLACE INTO participaciones "
                          "(jugador, partido) VALUES (?,?)", limpias)
            c.commit()
        return len(limpias)
    except sqlite3.Error:
        return 0


def guardar_goles(filas):
    """Los goles. `filas` son (partido, jugador, minuto, equipo, lado)."""
    limpias = [(int(p), j, -1 if m is None else int(m), e, s)
               for p, j, m, e, s in filas if p and j]
    if not limpias:
        return 0
    try:
        with almacen.conexion() as c:
            c.executemany(
                "INSERT OR REPLACE INTO goles "
                "(partido, jugador, minuto, equipo, lado) "
                "VALUES (?,?,?,?,?)", limpias)
            c.commit()
        return len(limpias)
    except sqlite3.Error:
        return 0


def _meter(tabla, columnas, filas):
    """Mete filas pisando lo que hubiera con la misma clave."""
    if not filas:
        return 0
    sql = ("INSERT OR REPLACE INTO %s (%s) VALUES (%s)"
           % (tabla, ",".join(columnas), ",".join("?" * len(columnas))))
    try:
        with almacen.conexion() as c:
            c.executemany(sql, filas)
            c.commit()
        return len(filas)
    except sqlite3.Error:
        return 0


def guardar_formacion(partido, lados, gente, stats=()):
    """
    Todo lo de un partido de una vez: el dibujo de cada equipo, quién estuvo
    y con qué rol, y las estadísticas de cada uno.

    Se escribe entero o no se escribe: si a mitad de camino algo falla, es
    preferible que el partido quede sin formación a que quede a medias y
    parezca completa.

      lados  (lado, equipo, dibujo, confirmada)
      gente  (jugador, equipo, lado, rol, puesto, dorsal, puntaje, x, y)
      stats  (jugador, clave, valor)
    """
    if not partido:
        return {"alineaciones": 0, "formaciones": 0, "estadisticas": 0}
    p = int(partido)
    return {
        "alineaciones": _meter(
            "alineaciones", ("partido", "lado", "equipo", "dibujo", "confirmada"),
            [(p, l, e, d, 1 if c else 0) for l, e, d, c in lados if l]),
        "formaciones": _meter(
            "formaciones", ("partido", "jugador", "equipo", "lado", "rol",
                            "puesto", "dorsal", "puntaje", "x", "y"),
            [(p,) + tuple(f) for f in gente if f and f[0]]),
        "estadisticas": _meter(
            "estadisticas", ("partido", "jugador", "clave", "valor"),
            [(p, j, k, v) for j, k, v in stats if j and k and v is not None]),
    }


def borrar_liga(liga):
    """Todos los partidos de un torneo. Para poder rearmarlo de cero."""
    try:
        with almacen.conexion() as c:
            n = c.execute("DELETE FROM partidos WHERE liga=?", (liga,)).rowcount
            c.commit()
        return n
    except sqlite3.Error:
        return 0


def _filas(sql, params=()):
    try:
        with almacen.conexion() as c:
            c.row_factory = sqlite3.Row
            try:
                return [dict(f) for f in c.execute(sql, params).fetchall()]
            finally:
                c.row_factory = None
    except sqlite3.Error:
        return []


# ── Preguntas ────────────────────────────────────────────────────────────
#
# Todavía no las usa ninguna pantalla: la tabla se arma y se verifica
# primero. Están acá porque son la razón de que la tabla exista, y porque
# probarlas es la única forma de saber que quedó bien armada.
def entre(a, b, tope=10):
    """
    Los partidos entre dos equipos, en cualquier torneo, del más nuevo al
    más viejo. Es la pregunta que con bloques no se podía hacer.
    """
    return _filas(
        "SELECT * FROM partidos "
        " WHERE (local_id=? AND visita_id=?) OR (local_id=? AND visita_id=?) "
        " ORDER BY cuando DESC LIMIT ?", (a, b, b, a, tope))


def del_equipo(equipo, temporada=None, liga=None, tope=500):
    """Todos los partidos de un equipo, de cualquier torneo."""
    sql = "SELECT * FROM partidos WHERE (local_id=? OR visita_id=?)"
    p = [equipo, equipo]
    if temporada is not None:
        sql += " AND temporada=?"
        p.append(temporada)
    if liga:
        sql += " AND liga=?"
        p.append(liga)
    sql += " ORDER BY cuando DESC LIMIT ?"
    p.append(tope)
    return _filas(sql, p)


def racha_de(equipo, liga=None, tope=5):
    """
    Los últimos partidos jugados de un equipo, del más nuevo al más viejo.

    Devuelve el resultado desde el lado de ESTE equipo —"G", "E", "P"— y
    no desde el del local, que es lo que uno quiere leer en una previa:
    "viene de ganar tres seguidos" no depende de dónde jugó.

    Sólo los terminados: un partido suspendido o en curso no es racha.
    """
    sql = ("SELECT * FROM partidos "
           " WHERE (local_id=? OR visita_id=?) AND estado='FIN' "
           "   AND gh IS NOT NULL AND ga IS NOT NULL")
    p = [equipo, equipo]
    if liga:
        sql += " AND liga=?"
        p.append(liga)
    sql += " ORDER BY cuando DESC LIMIT ?"
    p.append(tope)
    salida = []
    for m in _filas(sql, p):
        casa = m["local_id"] == equipo
        mios = m["gh"] if casa else m["ga"]
        suyos = m["ga"] if casa else m["gh"]
        salida.append({
            "id": m["id"], "cuando": m["cuando"],
            "rival": m["visita"] if casa else m["local"],
            "casa": casa, "gf": mios, "gc": suyos,
            "como": "G" if mios > suyos else ("E" if mios == suyos else "P"),
        })
    return salida


def goleadores_de(equipo, liga=None, temporada=None, desde=None, tope=6):
    """
    Los goleadores de UN equipo, para poder decir quién viene en racha.

    `desde` acota a los partidos posteriores a esa fecha, que es como se
    mira la forma: no importa quién hizo más goles en todo el año sino
    quién los viene haciendo ahora.
    """
    sql = ("SELECT g.jugador, COUNT(*) AS goles, "
           "       COUNT(DISTINCT g.partido) AS partidos, "
           "       MAX(p.cuando) AS ultimo "
           "  FROM goles g JOIN partidos p ON p.id=g.partido "
           " WHERE (p.local_id=? OR p.visita_id=?) "
           # El gol tiene el nombre del equipo que lo hizo: sin esto, los
           # goles del rival contarían como propios.
           "   AND (g.equipo IS NULL OR g.equipo=("
           "        SELECT CASE WHEN p.local_id=? THEN p.local ELSE p.visita END))")
    p = [equipo, equipo, equipo]
    if liga:
        sql += " AND p.liga=?"
        p.append(liga)
    if temporada is not None:
        sql += " AND p.temporada=?"
        p.append(temporada)
    if desde:
        sql += " AND p.cuando>=?"
        p.append(desde)
    sql += (" GROUP BY g.jugador ORDER BY goles DESC, partidos ASC LIMIT ?")
    p.append(tope)
    return _filas(sql, p)


def temporadas(liga):
    """Qué temporadas hay guardadas de un torneo, y cuántos partidos de cada."""
    return _filas(
        "SELECT temporada, COUNT(*) AS partidos, MIN(dia) AS desde, "
        "       MAX(dia) AS hasta "
        "  FROM partidos WHERE liga=? AND temporada IS NOT NULL "
        " GROUP BY temporada ORDER BY temporada DESC", (liga,))


def carrera_de(jugador, tope=200):
    """
    Los partidos de un jugador, con el torneo y la temporada de cada uno.

    Es la pregunta que justifica la tabla del medio: sin ella hay que
    abrir el bloque de cada torneo y buscarlo adentro, uno por uno.
    """
    return _filas(
        "SELECT p.*, "
        "       (SELECT COUNT(*) FROM goles g "
        "         WHERE g.partido=p.id AND g.jugador=?) AS goles "
        "  FROM participaciones pa JOIN partidos p ON p.id=pa.partido "
        " WHERE pa.jugador=? ORDER BY p.cuando DESC LIMIT ?",
        (jugador, jugador, tope))


def goleadores(liga=None, temporada=None, tope=20):
    """
    La tabla de goleadores, calculada. Sin acotarla, la de todos los
    torneos y todas las temporadas juntas, que antes no existía.
    """
    sql = ("SELECT g.jugador, COUNT(*) AS goles, "
           "       COUNT(DISTINCT g.partido) AS partidos "
           "  FROM goles g JOIN partidos p ON p.id=g.partido WHERE 1=1")
    p = []
    if liga:
        sql += " AND p.liga=?"
        p.append(liga)
    if temporada is not None:
        sql += " AND p.temporada=?"
        p.append(temporada)
    sql += " GROUP BY g.jugador ORDER BY goles DESC, partidos ASC LIMIT ?"
    p.append(tope)
    return _filas(sql, p)


def como_juega(jugador, tope=60):
    """
    De qué jugó y cuántas veces, mirando sus formaciones. Es la respuesta a
    "¿es lateral o volante?" que hasta ahora salía de la ficha del jugador,
    que dice uno solo aunque haya jugado en tres puestos distintos.
    """
    return _filas(
        "SELECT puesto, rol, COUNT(*) AS veces, AVG(puntaje) AS puntaje "
        "  FROM formaciones WHERE jugador=? AND puesto IS NOT NULL "
        " GROUP BY puesto, rol ORDER BY veces DESC LIMIT ?", (jugador, tope))


def promedio_de(jugador, clave, liga=None, temporada=None):
    """Cuánto promedia un jugador en una estadística, y en cuántos partidos."""
    # El cruce con los partidos va sólo si hace falta acotar por torneo o
    # temporada. Sin él, un partido cuyo detalle llegó antes que el
    # calendario igual cuenta, que es lo correcto: la estadística existe.
    acota = bool(liga) or temporada is not None
    sql = ("SELECT AVG(e.valor) AS promedio, SUM(e.valor) AS total, "
           "       COUNT(*) AS partidos FROM estadisticas e "
           + ("JOIN partidos p ON p.id=e.partido " if acota else "")
           + " WHERE e.jugador=? AND e.clave=?")
    p = [jugador, clave]
    if liga:
        sql += " AND p.liga=?"
        p.append(liga)
    if temporada is not None:
        sql += " AND p.temporada=?"
        p.append(temporada)
    f = _filas(sql, p)
    return f[0] if f else {"promedio": None, "total": None, "partidos": 0}


def once_de(partido, lado):
    """El once de un equipo en un partido, con su dibujo."""
    dib = _filas("SELECT dibujo, confirmada FROM alineaciones "
                 " WHERE partido=? AND lado=?", (partido, lado))
    return {"dibujo": dib[0]["dibujo"] if dib else None,
            "confirmada": bool(dib[0]["confirmada"]) if dib else False,
            "gente": _filas(
                "SELECT jugador, rol, puesto, dorsal, puntaje, x, y "
                "  FROM formaciones WHERE partido=? AND lado=? "
                " ORDER BY CASE rol WHEN 'titular' THEN 0 WHEN 'suplente' "
                "                   THEN 1 ELSE 2 END, dorsal", (partido, lado))}


def equipo_id(nombre, liga=None):
    """
    El identificador de un club a partir de su nombre canónico.

    Las fichas de club trabajan con el nombre; las tablas, con el número
    que le pone la fuente. Se busca de los dos lados porque un club puede
    no haber jugado nunca de local en lo que tenemos guardado.
    """
    if not nombre:
        return None
    p = [nombre, nombre, nombre]
    cond = ""
    if liga:
        cond = " AND liga=?"
        p.append(liga)
    f = _filas("SELECT CASE WHEN local=? THEN local_id ELSE visita_id END AS id "
               "  FROM partidos WHERE (local=? OR visita=?)%s "
               " ORDER BY cuando DESC LIMIT 1" % cond, p)
    return f[0]["id"] if f else None


def contra_cada_rival(equipo, liga):
    """
    Todos los partidos de un equipo en un torneo, para armar el historial
    contra cada rival.

    Devuelve los partidos crudos y no el resumen: el resumen se calcula
    afuera, donde ya se sabe leerlo desde el lado del club —quién ganó
    depende de si jugó de local o de visitante, y eso en SQL queda
    ilegible—.
    """
    if not equipo or not liga:
        return []
    return _filas(
        "SELECT * FROM partidos "
        " WHERE liga=? AND (local_id=? OR visita_id=?) AND gh IS NOT NULL "
        " ORDER BY cuando DESC", (liga, equipo, equipo))


def sin_formacion(ligas, tope=5, saltear=()):
    """
    Partidos ya jugados de estos torneos a los que todavía no les guardamos
    la formación, del más nuevo al más viejo.

    Es la lista de lo que falta para completar la historia. Se pide de a
    poco a propósito: cada uno cuesta un pedido a la fuente, y el que
    aparece primero es el que más chance tiene de que alguien lo mire.
    """
    if not ligas:
        return []
    huecos = ",".join("?" * len(ligas))
    p = list(ligas)
    sql = ("SELECT id, liga FROM partidos "
           " WHERE liga IN (%s) AND gh IS NOT NULL "
           "   AND id NOT IN (SELECT partido FROM alineaciones)" % huecos)
    if saltear:
        saltear = [int(x) for x in saltear]
        sql += " AND id NOT IN (%s)" % ",".join("?" * len(saltear))
        p += saltear
    sql += " ORDER BY cuando DESC LIMIT ?"
    p.append(tope)
    return _filas(sql, p)


def cuantos_sin_formacion(ligas):
    """Cuántos faltan, para poder mostrar cuánto queda."""
    if not ligas:
        return 0
    huecos = ",".join("?" * len(ligas))
    f = _filas("SELECT COUNT(*) AS n FROM partidos "
               " WHERE liga IN (%s) AND gh IS NOT NULL "
               "   AND id NOT IN (SELECT partido FROM alineaciones)" % huecos,
               list(ligas))
    return f[0]["n"] if f else 0


def estado():
    """Qué hay adentro, para poder mirarlo desde el administrador."""
    resumen = _filas(
        "SELECT liga, COUNT(*) AS partidos, COUNT(DISTINCT temporada) AS temporadas, "
        "       MIN(dia) AS desde, MAX(dia) AS hasta, "
        "       SUM(CASE WHEN gh IS NOT NULL THEN 1 ELSE 0 END) AS jugados "
        "  FROM partidos GROUP BY liga ORDER BY partidos DESC")
    total = _filas("SELECT COUNT(*) AS partidos, "
                   "       COUNT(DISTINCT local_id) AS equipos FROM partidos")
    otras = _filas(
        "SELECT (SELECT COUNT(*) FROM participaciones) AS participaciones, "
        "       (SELECT COUNT(DISTINCT jugador) FROM participaciones) AS jugadores, "
        "       (SELECT COUNT(*) FROM goles) AS goles, "
        "       (SELECT COUNT(*) FROM formaciones) AS formaciones, "
        "       (SELECT COUNT(DISTINCT partido) FROM alineaciones) AS conFormacion, "
        "       (SELECT COUNT(*) FROM estadisticas) AS estadisticas")
    d = otras[0] if otras else {}
    return {"porLiga": resumen,
            "partidos": (total[0]["partidos"] if total else 0),
            "equipos": (total[0]["equipos"] if total else 0),
            "participaciones": d.get("participaciones", 0),
            "jugadores": d.get("jugadores", 0),
            "goles": d.get("goles", 0),
            "formaciones": d.get("formaciones", 0),
            "conFormacion": d.get("conFormacion", 0),
            "estadisticas": d.get("estadisticas", 0)}


# Igual que el almacén: las tablas se crean al importar el módulo. Sin esto,
# lo primero que quisiera escribir se encontraría con que no existen y
# fallaría en silencio — que fue exactamente lo que pasó la primera vez.
iniciar()
