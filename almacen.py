# -*- coding: utf-8 -*-
"""
Almacén de HAYVAR: una base SQLite al lado del servidor.

Para qué sirve:

  1. Bajar los pedidos a las fuentes. Se trae una vez y se sirve mil veces.
     Con el plan gratis de API-Football (100 pedidos por día) esto no es un
     lujo, es la única forma de que funcione.

  2. No perder lo que ya se trajo. 365scores sólo publica una ventana móvil
     de fechas: las viejas desaparecen. Lo que entra a la base se queda.

  3. Seguir andando cuando la fuente falla. Si AFA no responde, se muestra
     lo último que se guardó con un aviso de cuándo se actualizó, en vez de
     una pantalla vacía.

Es una sola tabla clave/valor con JSON adentro. Suena simple y lo es: los
volúmenes son chicos (un torneo entero son pocos cientos de KB) y así el
esquema no se rompe cuando una fuente cambia un campo.
"""

import contextlib
import json
import os
import re
import sqlite3
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))


def _donde_guardar():
    """
    Dónde vive la base.

    El orden importa. En un hosting, la carpeta del código se borra y se
    vuelve a crear en cada publicación: si la base vive ahí, cada deploy
    arranca de cero y hay que volver a descargar meses de partidos. Por eso
    se busca primero un disco persistente montado aparte —Render y compañía
    los montan en /var/data o /data— y recién después se usa la carpeta del
    proyecto, que sirve para trabajar en la compu de uno.
    """
    puesto = os.environ.get("HAYVAR_DB")
    if puesto:
        return puesto
    for disco in ("/var/data", "/data"):
        if os.path.isdir(disco) and os.access(disco, os.W_OK):
            return os.path.join(disco, "hayvar.db")
    return os.path.join(AQUI, "hayvar.db")


RUTA = _donde_guardar()

_lock = threading.Lock()
_local = threading.local()

# Si el disco no soporta SQLite (algunos discos de red y carpetas
# compartidas no permiten el bloqueo que necesita), se pasa a memoria. Se
# pierde la persistencia pero la página sigue funcionando, que es lo que
# importa. Queda anotado en `MOTIVO_MEMORIA` para poder avisarlo.
EN_MEMORIA = False
MOTIVO_MEMORIA = ""


def _abrir(ruta):
    c = sqlite3.connect(ruta, timeout=10, check_same_thread=False)
    if ruta != ":memory:":
        c.execute("PRAGMA journal_mode=WAL")     # varios lectores a la vez
    c.execute("PRAGMA synchronous=NORMAL")
    return c


_ESQUEMA = """
CREATE TABLE IF NOT EXISTS datos (
    clave     TEXT PRIMARY KEY,
    valor     TEXT NOT NULL,
    guardado  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pedidos (
    dia    TEXT PRIMARY KEY,
    cuenta INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_datos_guardado ON datos(guardado);
"""

_memoria = None      # conexión única compartida cuando se cae a memoria


def _con():
    """Una conexión por hilo: sqlite3 no permite compartirlas."""
    global _memoria
    if EN_MEMORIA:
        if _memoria is None:
            _memoria = _abrir(":memory:")
            _memoria.executescript(_ESQUEMA)
            _memoria.commit()
        return _memoria
    c = getattr(_local, "con", None)
    if c is None:
        c = _abrir(RUTA)
        _local.con = c
    return c


def _borrar_archivos():
    for extra in ("", "-wal", "-shm"):
        try:
            os.remove(RUTA + extra)
        except OSError:
            pass


def iniciar(reintento=False):
    """
    Prepara la base. Si el archivo está dañado o su contenido no sirve, lo
    tira y arranca de cero: acá no hay nada irreemplazable, todo se vuelve a
    pedir a la fuente. Es preferible perder la caché a servir basura.
    """
    global EN_MEMORIA, MOTIVO_MEMORIA
    try:
        with _lock:
            c = _con()
            c.executescript(_ESQUEMA)
            c.execute("SELECT COUNT(*) FROM datos").fetchone()   # prueba real
            c.commit()
        return
    except sqlite3.DatabaseError as e:
        if not reintento:
            # archivo corrupto: se descarta y se vuelve a crear
            try:
                if _local.con is not None:
                    _local.con.close()
            except Exception:
                pass
            _local.con = None
            _borrar_archivos()
            return iniciar(reintento=True)
        EN_MEMORIA, MOTIVO_MEMORIA = True, str(e)
    except sqlite3.Error as e:
        EN_MEMORIA, MOTIVO_MEMORIA = True, str(e)

    _local.con = None
    with _lock:
        c = _con()
        c.executescript(_ESQUEMA)
        c.commit()


def vaciar():
    """Borra todo lo guardado. La página lo vuelve a pedir solo."""
    try:
        with _lock:
            c = _con()
            c.execute("DELETE FROM datos")
            c.commit()
        return True
    except sqlite3.Error:
        return False


def guardar(clave, valor):
    try:
        with _lock:
            c = _con()
            c.execute("INSERT INTO datos (clave, valor, guardado) VALUES (?,?,?) "
                      "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, "
                      "guardado=excluded.guardado",
                      (clave, json.dumps(valor, ensure_ascii=False), time.time()))
            c.commit()
    except sqlite3.Error:
        pass        # no poder guardar nunca debe romper una respuesta


def leer(clave, max_edad=None, con_largo=False):
    """
    Devuelve (valor, edad_en_segundos) o (None, None).

    Con `max_edad` devuelve None si lo guardado ya es viejo. Sin `max_edad`
    devuelve lo que haya, por viejo que sea: es el modo de emergencia para
    cuando la fuente no responde.

    Con `con_largo` agrega un tercer valor: cuántos caracteres ocupa lo
    guardado. Lo usa el caché de memoria del servidor para saber si algo
    entra o no: hay respuestas de dos kilobytes y otras de cinco megas, y
    contar entradas en vez de tamaño era contar peras.
    """
    try:
        with _lock:
            fila = _con().execute("SELECT valor, guardado FROM datos WHERE clave=?",
                                  (clave,)).fetchone()
    except sqlite3.Error:
        fila = None
    if not fila:
        return (None, None, 0) if con_largo else (None, None)
    edad = time.time() - fila[1]
    if max_edad is not None and edad > max_edad:
        return (None, edad, 0) if con_largo else (None, edad)
    try:
        v = json.loads(fila[0])
        return (v, edad, len(fila[0])) if con_largo else (v, edad)
    except json.JSONDecodeError:
        return (None, edad, 0) if con_largo else (None, edad)


def leer_prefijo(prefijo, tanda=500):
    """
    Todo lo que empieza con ese prefijo, de pocas pasadas.

    Hace falta para armar las tablas: hay once mil claves `pj:` y leerlas
    de a una son once mil consultas, cada una con su candado.

    Va por tandas y no de una sola vez por una razón concreta: si una
    página del archivo está dañada, la consulta entera se cae y esto
    devolvía una lista vacía sin decir nada —que es la peor forma de
    fallar, porque parece que no hay datos—. Así, una tanda rota se
    reintenta clave por clave y se pierde nada más lo que de verdad no se
    puede leer.
    """
    try:
        with _lock:
            claves = [f[0] for f in _con().execute(
                "SELECT clave FROM datos WHERE clave LIKE ? ORDER BY clave",
                (prefijo + "%",)).fetchall()]
    except sqlite3.Error:
        return []

    salida = []

    def sumar(clave, crudo):
        try:
            salida.append((clave, json.loads(crudo)))
        except (json.JSONDecodeError, TypeError):
            pass

    for i in range(0, len(claves), tanda):
        grupo = claves[i:i + tanda]
        huecos = ",".join("?" * len(grupo))
        try:
            with _lock:
                for clave, crudo in _con().execute(
                        "SELECT clave, valor FROM datos WHERE clave IN (%s)"
                        % huecos, grupo).fetchall():
                    sumar(clave, crudo)
        except sqlite3.Error:
            for clave in grupo:          # la tanda tiene una página rota
                try:
                    with _lock:
                        f = _con().execute(
                            "SELECT valor FROM datos WHERE clave=?",
                            (clave,)).fetchone()
                except sqlite3.Error:
                    continue
                if f:
                    sumar(clave, f[0])
    return salida


def con_respaldo(clave, traer, max_edad, tag=""):
    """
    El patrón que usa todo el servidor.

      1. Si hay algo guardado y todavía es fresco, se devuelve eso.
      2. Si no, se va a la fuente y se guarda lo que traiga.
      3. Si la fuente falla, se devuelve lo viejo antes que nada.

    Devuelve (valor, info) donde info explica de dónde salió, para poder
    mostrarlo en pantalla con honestidad.
    """
    valor, edad, largo = leer(clave, max_edad, con_largo=True)
    if valor is not None:
        return valor, {"origen": "cache", "edad": round(edad), "tag": tag,
                       "bytes": largo}

    try:
        fresco = traer()
    except Exception as e:
        viejo, edad = leer(clave)            # sin límite de edad
        if viejo is not None:
            return viejo, {"origen": "cache-vieja", "edad": round(edad or 0),
                           "error": str(e), "tag": tag}
        raise

    guardar(clave, fresco)
    _, _, largo = leer(clave, con_largo=True)
    return fresco, {"origen": "fuente", "edad": 0, "tag": tag,
                    "bytes": largo or 0}


# ── Presupuesto diario de pedidos ────────────────────────────────────────
def _hoy():
    return time.strftime("%Y-%m-%d")


def pedidos_hoy():
    try:
        with _lock:
            fila = _con().execute("SELECT cuenta FROM pedidos WHERE dia=?",
                                  (_hoy(),)).fetchone()
    except sqlite3.Error:
        return 0
    return fila[0] if fila else 0


def contar_pedido(n=1):
    try:
        with _lock:
            c = _con()
            c.execute("INSERT INTO pedidos (dia, cuenta) VALUES (?,?) "
                      "ON CONFLICT(dia) DO UPDATE SET cuenta=cuenta+?",
                      (_hoy(), n, n))
            c.commit()
    except sqlite3.Error:
        pass


def hay_presupuesto(tope, reserva=5):
    """
    ¿Queda margen para un pedido más?

    Se deja una reserva sin usar para que, si aparece algo urgente al final
    del día, todavía se pueda pedir.
    """
    return pedidos_hoy() < max(0, tope - reserva)


def estado():
    try:
        with _lock:
            c = _con()
            n = c.execute("SELECT COUNT(*) FROM datos").fetchone()[0]
            viejo = c.execute("SELECT MIN(guardado) FROM datos").fetchone()[0]
            nuevo = c.execute("SELECT MAX(guardado) FROM datos").fetchone()[0]
    except sqlite3.Error as e:
        return {"error": str(e), "en_memoria": EN_MEMORIA}
    tam = _tamano()
    # ¿el archivo sobrevive a una publicación? Sólo si está en un disco
    # montado aparte; la carpeta del código se borra en cada deploy.
    persistente = EN_MEMORIA is False and not RUTA.startswith(AQUI)
    return {"archivo": ":memory:" if EN_MEMORIA else RUTA,
            "en_memoria": EN_MEMORIA, "motivo": MOTIVO_MEMORIA or None,
            "sobrevive_al_deploy": persistente,
            "aviso": None if persistente or EN_MEMORIA else
                     ("La base vive en la carpeta del código y se borra en "
                      "cada publicación. Montá un disco en /var/data para "
                      "que se conserve."),
            "bytes": tam, "entradas": n, "pedidos_hoy": pedidos_hoy(),
            "mas_viejo": round(time.time() - viejo) if viejo else None,
            "mas_nuevo": round(time.time() - nuevo) if nuevo else None}


def borrar_prefijo(prefijo):
    """
    Borra todo lo que empieza con ese prefijo y compacta el archivo.

    Sin el VACUUM, SQLite marca el espacio como libre pero no le devuelve
    los megas al disco —ni a la memoria, si la base quedó en memoria—.
    """
    with _lock:
        c = _con()
        n = c.execute("DELETE FROM datos WHERE clave LIKE ?",
                      (prefijo + "%",)).rowcount
        c.commit()
        if n:
            _compactar(c)
        return n


def claves():
    """Todas las claves guardadas. Para poder mirar qué hay adentro."""
    with _lock:
        c = _con()
        return [f[0] for f in c.execute("SELECT clave FROM datos").fetchall()]


def _compactar(c):
    """
    Devolverle al disco el espacio de lo borrado. Son dos pasos, no uno.

    El VACUUM reconstruye la base sin los huecos, pero en modo WAL esa
    reconstrucción se escribe en el WAL: el archivo principal queda como
    estaba y el WAL se infla con la base entera. Medido justo después, una
    limpieza de 200 KB daba "creció 3,7 MB", y era cierto. El checkpoint
    con TRUNCATE es el que pasa todo al archivo principal y deja el WAL en
    cero, que es cuando el espacio vuelve a estar libre de verdad.
    """
    for orden in ("VACUUM", "PRAGMA wal_checkpoint(TRUNCATE)"):
        try:
            c.execute(orden)
        except sqlite3.Error:
            pass


def copia_de_seguridad(nombre=None):
    """
    Una copia de la base, al lado de la original.

    Es para antes de tocar filas ya guardadas. Se hace con `VACUUM INTO`,
    que es la forma que trae SQLite para copiar una base **en caliente**:
    respeta las transacciones en curso, no hace falta parar el servidor, y
    de paso la copia sale compactada. Copiar el archivo a mano mientras
    alguien escribe puede dejar una copia rota, que es peor que no tenerla.

    Devuelve {"archivo": ..., "bytes": ...} o None si no se pudo.
    """
    if RUTA == ":memory:":
        return None
    import datetime as _dt
    sello = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = nombre or "%s.copia-%s" % (RUTA, sello)
    if os.path.exists(destino):
        return None                      # nunca pisar una copia que ya está
    try:
        with conexion() as c:
            c.execute("VACUUM INTO ?", (destino,))
    except Exception:
        return None
    try:
        return {"archivo": destino, "bytes": os.path.getsize(destino)}
    except OSError:
        return {"archivo": destino, "bytes": None}


def copias():
    """Las copias que hay, de la más nueva a la más vieja."""
    if RUTA == ":memory:":
        return []
    carpeta = os.path.dirname(RUTA) or "."
    base = os.path.basename(RUTA) + ".copia-"
    salida = []
    try:
        for n in os.listdir(carpeta):
            if n.startswith(base):
                camino = os.path.join(carpeta, n)
                salida.append({"archivo": n,
                               "bytes": os.path.getsize(camino)})
    except OSError:
        return []
    return sorted(salida, key=lambda x: x["archivo"], reverse=True)


def _tamano():
    """
    Lo que ocupa la base en el disco, contando todos sus archivos.

    Ojo con esto: la base anda en modo WAL, y en WAL lo recién escrito vive
    en un archivo aparte —`hayvar.db-wal`— hasta que SQLite lo consolida.
    Mirando sólo el archivo principal, la base parecía más chica de lo que
    era; y peor, una limpieza podía dar "creció 400 KB", porque el VACUUM
    consolida y recién ahí lo del WAL aparece en el principal. El disco lo
    ocupan los tres archivos, así que se suman los tres.
    """
    if EN_MEMORIA:
        return 0
    total = 0
    for extra in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(RUTA + extra)
        except OSError:
            pass
    return total


@contextlib.contextmanager
def conexion():
    """
    La conexión a la base, tomada con su candado.

    Es la costura para lo que no entra en clave/valor: las tablas de
    `tablas.py` viven en este mismo archivo y comparten la conexión, el
    candado y el disco. Abrir una segunda conexión aparte andaría, pero
    serían dos cosas que creerse dueñas de lo mismo.

    Ojo adentro del `with`: el candado no es reentrante, así que nada de
    llamar a `leer` o `guardar` desde ahí. Lo que haya que leer se lee
    antes.
    """
    with _lock:
        yield _con()


def familia(clave):
    """
    A qué grupo pertenece una clave, para poder mirar la base por partes.

    Las de la caché de 365scores son todas `sc:` seguido de la dirección
    entera, así que juntas no dicen nada: se las separa por lo que se
    pidió —`game`, `standings`, `athletes`—, que es lo que hace falta para
    saber qué está ocupando el disco.
    """
    if clave.startswith("sc:"):
        m = re.search(r"365scores\.com/web/([^/?]+(?:/[^/?]+)?)/?\?", clave)
        return "sc:" + (m.group(1) if m else "?")
    return clave.split(":")[0] if ":" in clave else clave


def pesos():
    """
    Cuánto ocupa cada familia y cuál es su fila más vieja.

    Es para poder decidir qué limpiar mirando números en vez de a ojo, y
    para ver si el disco alcanza o hay que agrandarlo. Recorre la tabla
    entera, así que se guarda el resultado un rato: no es para llamarla en
    cada visita, es para el administrador.
    """
    global _PESOS
    if _PESOS and time.time() - _PESOS[0] < 600:
        return _PESOS[1]
    ahora, salida = time.time(), {}
    try:
        with _lock:
            filas = _con().execute(
                "SELECT clave, LENGTH(valor), guardado FROM datos").fetchall()
    except sqlite3.Error as e:
        return {"error": str(e)}
    for clave, largo, guardado in filas:
        f = familia(clave)
        d = salida.setdefault(f, {"familia": f, "filas": 0, "bytes": 0,
                                  "dias": 0})
        d["filas"] += 1
        d["bytes"] += largo or 0
        d["dias"] = max(d["dias"], round((ahora - (guardado or ahora)) / 86400))
    orden = sorted(salida.values(), key=lambda x: -x["bytes"])
    _PESOS = (ahora, orden)
    return orden


_PESOS = None


def limpiar(prefijo, mas_viejo_que):
    """
    Borra lo viejo de una familia de claves, y sólo de ésa.

    El prefijo es obligatorio a propósito. Antes esto borraba por fecha sin
    mirar qué era cada fila, y con eso se llevaba puesto justo lo que no
    caduca nunca: la carrera de cada jugador y el índice de jugadores, que
    se escriben una sola vez —cuando lo vemos por primera vez— y se leen
    para siempre; y los calendarios, que son partidos ya jugados. A los
    noventa días las fichas habrían quedado vacías y las tablas mal
    armadas. Por eso nunca se llamó a esta función: como estaba, llamarla
    era romper la base.

    La fecha que se mira es la de la última escritura, y para una caché eso
    es exactamente lo que hace falta: lo que se sigue usando se reescribe
    solo cada vez que vence, así que una fila vieja es una que nadie pidió
    en todo ese tiempo.

    Devuelve cuántas filas se fueron y cuántos bytes le devolvió al disco.
    """
    if not prefijo:
        raise ValueError("limpiar necesita un prefijo: borrar por fecha a "
                         "secas se lleva la carrera de los jugadores")
    global _PESOS
    antes = _tamano()
    with _lock:
        c = _con()
        n = c.execute("DELETE FROM datos WHERE clave LIKE ? AND guardado < ?",
                      (prefijo + "%", time.time() - mas_viejo_que)).rowcount
        c.commit()
        if n:
            _compactar(c)
    _PESOS = None
    despues = _tamano()
    return {"prefijo": prefijo, "filas": n, "bytes": max(0, antes - despues)}


iniciar()
