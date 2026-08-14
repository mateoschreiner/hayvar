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

import json
import os
import sqlite3
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
# Se puede mover con HAYVAR_DB. Sirve para hostings donde la carpeta del
# código es de sólo lectura y hay que escribir en otro lado.
RUTA = os.environ.get("HAYVAR_DB") or os.path.join(AQUI, "hayvar.db")

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


def leer(clave, max_edad=None):
    """
    Devuelve (valor, edad_en_segundos) o (None, None).

    Con `max_edad` devuelve None si lo guardado ya es viejo. Sin `max_edad`
    devuelve lo que haya, por viejo que sea: es el modo de emergencia para
    cuando la fuente no responde.
    """
    try:
        with _lock:
            fila = _con().execute("SELECT valor, guardado FROM datos WHERE clave=?",
                                  (clave,)).fetchone()
    except sqlite3.Error:
        fila = None
    if not fila:
        return None, None
    edad = time.time() - fila[1]
    if max_edad is not None and edad > max_edad:
        return None, edad
    try:
        return json.loads(fila[0]), edad
    except json.JSONDecodeError:
        return None, edad


def con_respaldo(clave, traer, max_edad, tag=""):
    """
    El patrón que usa todo el servidor.

      1. Si hay algo guardado y todavía es fresco, se devuelve eso.
      2. Si no, se va a la fuente y se guarda lo que traiga.
      3. Si la fuente falla, se devuelve lo viejo antes que nada.

    Devuelve (valor, info) donde info explica de dónde salió, para poder
    mostrarlo en pantalla con honestidad.
    """
    valor, edad = leer(clave, max_edad)
    if valor is not None:
        return valor, {"origen": "cache", "edad": round(edad), "tag": tag}

    try:
        fresco = traer()
    except Exception as e:
        viejo, edad = leer(clave)            # sin límite de edad
        if viejo is not None:
            return viejo, {"origen": "cache-vieja", "edad": round(edad or 0),
                           "error": str(e), "tag": tag}
        raise

    guardar(clave, fresco)
    return fresco, {"origen": "fuente", "edad": 0, "tag": tag}


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
    try:
        tam = 0 if EN_MEMORIA else os.path.getsize(RUTA)
    except OSError:
        tam = 0
    return {"archivo": ":memory:" if EN_MEMORIA else RUTA,
            "en_memoria": EN_MEMORIA, "motivo": MOTIVO_MEMORIA or None,
            "bytes": tam, "entradas": n, "pedidos_hoy": pedidos_hoy(),
            "mas_viejo": round(time.time() - viejo) if viejo else None,
            "mas_nuevo": round(time.time() - nuevo) if nuevo else None}


def limpiar(mas_viejo_que=60 * 60 * 24 * 90):
    """Borra lo que ya no le sirve a nadie. Por defecto, 90 días."""
    with _lock:
        c = _con()
        c.execute("DELETE FROM datos WHERE guardado < ?", (time.time() - mas_viejo_que,))
        c.commit()


iniciar()
