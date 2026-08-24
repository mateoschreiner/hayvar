# -*- coding: utf-8 -*-
"""
Quién entra a HAYVAR, de dónde viene y qué mira.

Google Analytics y Clarity ya cuentan todo esto y lo cuentan bien. Esto
existe por otra razón: los datos de ellos viven en sus paneles y llegan con
retraso, y para que la portada pueda reaccionar a quien está entrando, el
servidor tiene que saberlo en el momento en que llega la visita. De paso,
los bloqueadores de publicidad tapan a Google y acá se ve todo.


CÓMO SE CUENTA UNA PERSONA SIN SABER QUIÉN ES

Para decir "hoy entraron 120 personas" hay que poder distinguir una de
otra. Pero guardar la dirección IP de alguien es guardar un dato personal,
con todo lo que eso trae: el visitante no lo pidió, y a vos te convierte en
responsable de una base de datos de gente.

Así que no se guarda. Se arma una huella: se mezclan la IP, el navegador y
un secreto que cambia todos los días, y de esa mezcla se guardan dieciséis
letras. Con eso alcanza para saber que dos visitas de hoy son de la misma
persona, y no alcanza para nada más: no se puede volver atrás para sacar la
IP, y mañana la misma persona tiene otra huella distinta. Se puede contar
gente sin poder seguir a nadie.

El secreto se guarda en la base y se renueva solo cada día.


DE DÓNDE VIENE Y QUÉ BUSCABA

Del referente se guarda sólo el dominio —"google", "instagram"— y no la
dirección completa, que a veces lleva cosas privadas adentro.

Los términos que alguien buscó en Google no se pueden saber: los borra
Google desde 2011. Pero la página en la que aterriza dice lo mismo y mejor:
si cae en /partido/barcelona-vs-real-madrid, eso es lo que venía a ver.
De ahí sale la sugerencia para la portada.


CUÁNTO OCUPA

El disco es de 1 GB y la base ya va por 202 MB, así que esto no puede
crecer sin freno. Se guardan dos cosas:

  · un resumen por día, que ocupa unos pocos kilobytes y se conserva
    noventa días;
  · las últimas visitas en detalle, en un anillo de tamaño fijo, para poder
    mirar de cerca cuando algo llama la atención.

Las dos tienen tope. No hay forma de que esto llene el disco.
"""

import hashlib
import os
import re
import time
import datetime as dt

import almacen

# Cuántas visitas se guardan en detalle. Las viejas se van solas.
ULTIMAS = 400
# Cuántos días de resumen se conservan.
DIAS = 90


# ── La huella del visitante ──────────────────────────────────────────────
def _secreto_del_dia(dia):
    """
    Un secreto distinto por día, para que la huella no se pueda seguir de
    un día para el otro. Se inventa la primera vez que hace falta y se
    guarda; si la base no anda, se usa uno de la memoria del proceso.
    """
    clave = "vis:sal:%s" % dia
    guardado, _ = almacen.leer(clave)
    if guardado:
        return guardado
    nuevo = hashlib.sha256(os.urandom(32)).hexdigest()
    almacen.guardar(clave, nuevo)
    return nuevo


def huella(ip, navegador, dia=None):
    """
    Dieciséis letras que representan a una persona durante un día.

    No se puede volver atrás: de la huella no sale la IP. Y mañana la misma
    persona tiene otra, porque el secreto cambió.
    """
    dia = dia or hoy()
    mezcla = "%s|%s|%s" % (ip or "", navegador or "", _secreto_del_dia(dia))
    return hashlib.sha256(mezcla.encode("utf-8")).hexdigest()[:16]


def hoy():
    return dt.date.today().isoformat()


# ── Leer el navegador ────────────────────────────────────────────────────
# Sin biblioteca: son cuatro patrones y cubren casi todo lo que llega. Lo
# que no entra en ninguno queda como "otro", que es más honesto que forzarlo.
_SISTEMAS = [
    ("Android", r"Android"),
    ("iOS", r"iPhone|iPad|iPod"),
    ("Windows", r"Windows NT"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("Linux", r"Linux"),
]
_NAVEGADORES = [
    # el orden importa: Edge y Opera también dicen "Chrome"
    ("Edge", r"Edg/"),
    ("Opera", r"OPR/|Opera"),
    ("Samsung", r"SamsungBrowser"),
    ("Chrome", r"Chrome|CriOS"),
    ("Firefox", r"Firefox|FxiOS"),
    ("Safari", r"Safari"),
]
# Los que no son personas. No se cuentan como visitas: si no, el día que
# pasa Google a indexar parece que tuviste mil visitantes.
_ROBOTS = re.compile(
    r"bot|crawler|spider|slurp|facebookexternalhit|whatsapp|telegram|"
    r"preview|monitor|uptime|curl|wget|python-requests|headless|lighthouse",
    re.I)


def es_robot(navegador):
    return bool(_ROBOTS.search(navegador or ""))


def _primero(pares, texto, porDefecto="otro"):
    for nombre, patron in pares:
        if re.search(patron, texto or ""):
            return nombre
    return porDefecto


def sistema_de(navegador):
    return _primero(_SISTEMAS, navegador)


def navegador_de(navegador):
    return _primero(_NAVEGADORES, navegador)


def dispositivo(navegador):
    """Qué es: un teléfono, una tablet o una computadora."""
    ua = navegador or ""
    if re.search(r"iPad|Tablet", ua) or (re.search(r"Android", ua)
                                         and "Mobile" not in ua):
        return "tablet"
    if re.search(r"Mobi|Android|iPhone|iPod", ua):
        return "móvil"
    return "escritorio"


# ── De dónde viene ───────────────────────────────────────────────────────
_FUENTES = [
    ("Google", r"(^|\.)google\."),
    ("Bing", r"(^|\.)bing\."),
    ("DuckDuckGo", r"duckduckgo\."),
    ("Yahoo", r"(^|\.)yahoo\."),
    ("Instagram", r"instagram\."),
    ("Facebook", r"facebook\.|fb\."),
    # t.co es el acortador de Twitter: por ahí llegan TODOS sus links, así
    # que sin esta línea la red que más manda tráfico aparecía como "otro"
    ("X / Twitter", r"(^|\.)(twitter|x)\.com|^t\.co$"),
    ("WhatsApp", r"whatsapp\."),
    ("Reddit", r"reddit\."),
    ("YouTube", r"youtube\.|youtu\.be"),
    ("TikTok", r"tiktok\."),
    ("Telegram", r"(^|\.)t\.me"),
]


def de_donde(referente, propio):
    """
    De dónde llegó, en dos palabras. Del referente se mira sólo el dominio:
    la dirección entera puede llevar cosas privadas de la otra página.

    Devuelve (fuente, dominio). Sin referente es "directo": alguien que
    escribió la dirección, la tenía guardada o vino de una app que no avisa.
    """
    if not referente:
        return "directo", ""
    m = re.match(r"https?://([^/:?#]+)", referente.strip(), re.I)
    if not m:
        return "otro", ""
    dominio = m.group(1).lower()
    if propio and dominio.endswith(propio.lower().split(":")[0]):
        return "interno", dominio
    return _primero(_FUENTES, dominio), dominio


def que_buscaba(referente):
    """
    Los términos de la búsqueda, si el buscador los deja pasar.

    Google los borra desde 2011, así que con él casi siempre va a venir
    vacío. Algunos otros todavía los mandan. No se inventa nada: si no
    están, no están.
    """
    if not referente:
        return ""
    m = re.search(r"[?&](?:q|p|query|text)=([^&]+)", referente)
    if not m:
        return ""
    try:
        from urllib.parse import unquote_plus
        return unquote_plus(m.group(1))[:80]
    except Exception:
        return ""


def region(idiomas):
    """
    De qué país es, según cómo tiene configurado el navegador.

    No es geolocalización por IP: es el idioma que eligió la persona.
    Para lo que queremos —saber si le va a interesar el fútbol argentino—
    es incluso mejor que la IP, porque un argentino de viaje sigue
    teniendo el navegador en es-AR.
    """
    if not idiomas:
        return ""
    primero = idiomas.split(",")[0].strip()
    m = re.match(r"([a-zA-Z]{2})(?:-([a-zA-Z]{2}))?", primero)
    if not m:
        return ""
    return (m.group(2) or m.group(1)).upper()


# Qué venía a ver cada visita —el dato que después puede ordenar la
# portada— se resuelve en `server.que_venia_a_ver`, y no acá, porque
# necesita mirar la base para saber de qué torneo es un partido.


# ── Guardar ──────────────────────────────────────────────────────────────
def _resumen_vacio(dia):
    return {"dia": dia, "vistas": 0, "gente": [], "segundos": 0,
            "fuentes": {}, "paginas": {}, "dispositivos": {}, "sistemas": {},
            "navegadores": {}, "regiones": {}, "pantallas": {},
            "busquedas": {}, "intenciones": {}}


def _sumar(d, clave, cuanto=1, tope=60):
    """
    Suma uno a un contador, con tope de claves distintas.

    El tope importa: las páginas son miles —hay una por partido— y sin
    freno el resumen del día crecería igual que el tráfico. Pasado el tope
    lo que sobra va a "otras", que sigue siendo información útil.
    """
    if not clave:
        return
    clave = str(clave)[:60]
    if clave not in d and len(d) >= tope:
        clave = "otras"
    d[clave] = d.get(clave, 0) + cuanto


def anotar(datos):
    """
    Anota una visita. `datos` es lo que armó el servidor con los
    encabezados del pedido y lo que contó el navegador.

    Devuelve el identificador de la visita, para que el navegador pueda
    después avisar cuánto se quedó.
    """
    dia = hoy()
    clave = "vis:dia:%s" % dia
    r, _ = almacen.leer(clave)
    r = r or _resumen_vacio(dia)

    r["vistas"] += 1
    # La lista de huellas es lo que permite contar personas y no visitas.
    # Se guarda como lista y no como número porque hay que poder preguntar
    # "¿ya vino hoy?". Con el tope de abajo no se desborda.
    h = datos.get("huella")
    if h and h not in r["gente"]:
        if len(r["gente"]) < 20000:
            r["gente"].append(h)

    _sumar(r["fuentes"], datos.get("fuente"))
    _sumar(r["paginas"], datos.get("ruta"), tope=80)
    _sumar(r["dispositivos"], datos.get("dispositivo"), tope=8)
    _sumar(r["sistemas"], datos.get("sistema"), tope=12)
    _sumar(r["navegadores"], datos.get("navegador"), tope=12)
    _sumar(r["regiones"], datos.get("region"), tope=40)
    _sumar(r["pantallas"], datos.get("pantalla"), tope=30)
    _sumar(r["busquedas"], datos.get("busco"), tope=40)
    _sumar(r["intenciones"], datos.get("intencion"), tope=30)
    almacen.guardar(clave, r)

    # Y el detalle, en el anillo.
    #
    # El identificador lleva azar y no la hora: con la hora en
    # milisegundos, dos personas que entraran en el mismo milisegundo
    # compartían identificador, y el tiempo de una se le sumaba a la otra.
    # Pasa más de lo que parece cuando el partido lo está mirando mucha
    # gente, que es justo cuando uno quiere que los números estén bien.
    vid = "%s-%s" % (dia, os.urandom(5).hex())
    ult, _ = almacen.leer("vis:ultimas")
    ult = (ult or [])
    ult.append({"id": vid, "t": int(time.time()),
                "h": datos.get("huella", "")[:8],
                "ruta": datos.get("ruta", "")[:80],
                "fuente": datos.get("fuente", ""),
                "dominio": datos.get("dominio", "")[:40],
                "busco": datos.get("busco", ""),
                "disp": datos.get("dispositivo", ""),
                "so": datos.get("sistema", ""),
                "nav": datos.get("navegador", ""),
                "pantalla": datos.get("pantalla", ""),
                "region": datos.get("region", ""),
                "quiere": datos.get("intencion", ""),
                "seg": 0})
    almacen.guardar("vis:ultimas", ult[-ULTIMAS:])
    return vid


def latir(vid, segundos):
    """
    El navegador avisa que la persona sigue ahí. Se guarda cuánto lleva.

    Se cuenta así y no con el evento de cerrar la pestaña porque ese evento
    no llega siempre —el navegador lo puede saltear— y entonces todas las
    visitas medirían cero.
    """
    if not vid or segundos is None:
        return
    try:
        segundos = max(0, min(int(segundos), 3600))
    except (TypeError, ValueError):
        return
    ult, _ = almacen.leer("vis:ultimas")
    ult = ult or []
    for v in reversed(ult):
        if v.get("id") == vid:
            antes = v.get("seg", 0)
            if segundos <= antes:
                return
            v["seg"] = segundos
            almacen.guardar("vis:ultimas", ult)
            # Y al resumen del día se le suma sólo lo nuevo.
            #
            # Ojo con el corte: el identificador es "2026-08-24-12345678" y
            # la fecha lleva guiones adentro. Partiendo por el primero
            # quedaba "2026" y el tiempo no se sumaba en ningún lado.
            dia = vid.rsplit("-", 1)[0]
            clave = "vis:dia:%s" % dia
            r, _ = almacen.leer(clave)
            if r:
                r["segundos"] = r.get("segundos", 0) + (segundos - antes)
                almacen.guardar(clave, r)
            return


def limpiar():
    """Tira los resúmenes de más de DIAS días y las sales viejas."""
    corte = (dt.date.today() - dt.timedelta(days=DIAS)).isoformat()
    borradas = 0
    try:
        for c in almacen.claves():
            if c.startswith("vis:dia:") and c[8:] < corte:
                almacen.borrar_prefijo(c)
                borradas += 1
            elif c.startswith("vis:sal:") and c[8:] < corte:
                almacen.borrar_prefijo(c)
                borradas += 1
    except Exception:
        pass
    return borradas


# ── Leer ─────────────────────────────────────────────────────────────────
def resumen(dias=14):
    """Lo que se ve en el administrador."""
    salida, hoy_ = [], dt.date.today()
    for i in range(dias):
        d = (hoy_ - dt.timedelta(days=i)).isoformat()
        r, _ = almacen.leer("vis:dia:%s" % d)
        if not r:
            salida.append({"dia": d, "vistas": 0, "gente": 0, "segundos": 0})
            continue
        salida.append({"dia": d, "vistas": r.get("vistas", 0),
                       "gente": len(r.get("gente", [])),
                       "segundos": r.get("segundos", 0)})
    salida.reverse()

    hoyr, _ = almacen.leer("vis:dia:%s" % hoy())
    hoyr = hoyr or _resumen_vacio(hoy())
    ult, _ = almacen.leer("vis:ultimas")

    def top(d, n=10):
        return sorted(({"que": k, "cuantas": v} for k, v in (d or {}).items()),
                      key=lambda x: -x["cuantas"])[:n]

    gente = len(hoyr.get("gente", []))
    return {
        "porDia": salida,
        "hoy": {
            "gente": gente,
            "vistas": hoyr.get("vistas", 0),
            "segundos": hoyr.get("segundos", 0),
            "porPersona": round(hoyr.get("segundos", 0) / gente) if gente else 0,
            "vistasPorPersona": (round(hoyr.get("vistas", 0) / gente, 1)
                                 if gente else 0),
        },
        "fuentes": top(hoyr.get("fuentes")),
        "paginas": top(hoyr.get("paginas"), 12),
        "dispositivos": top(hoyr.get("dispositivos"), 5),
        "sistemas": top(hoyr.get("sistemas"), 8),
        "navegadores": top(hoyr.get("navegadores"), 8),
        "regiones": top(hoyr.get("regiones"), 10),
        "pantallas": top(hoyr.get("pantallas"), 10),
        "busquedas": top(hoyr.get("busquedas"), 10),
        "intenciones": top(hoyr.get("intenciones"), 10),
        "ultimas": list(reversed(ult or []))[:60],
        "comoSeCuenta": ("Se cuenta gente con una huella que mezcla la IP y "
                         "el navegador con un secreto que cambia todos los "
                         "días. No se guarda ninguna IP y la huella no se "
                         "puede revertir."),
    }
