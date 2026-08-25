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
        "       (SELECT COUNT(*) FROM goles) AS goles")
    return {"porLiga": resumen,
            "partidos": (total[0]["partidos"] if total else 0),
            "equipos": (total[0]["equipos"] if total else 0),
            "participaciones": (otras[0]["participaciones"] if otras else 0),
            "jugadores": (otras[0]["jugadores"] if otras else 0),
            "goles": (otras[0]["goles"] if otras else 0)}
