# -*- coding: utf-8 -*-
"""
Lee las tablas de RSSSF y arma la tabla histórica de Primera División.

Por qué existe este archivo
───────────────────────────
La tabla histórica del fútbol argentino no está publicada bien en ningún
lado. La de Wikipedia falla las cuatro verificaciones básicas: está
congelada en abril de 2020 aunque diga 2025, tiene quince clubes con un
parche de +14 partidos que no se reflejó en ganados/empatados/perdidos,
Racing con 98 partidos de más, Lanús con 238 de menos, y Barracas Central
directamente no aparece.

Así que se arma de cero, sumando la tabla final de cada torneo. Y se arma
con código y no a mano: son unas 1.900 filas de números y transcribirlas
a mano es garantía de error.

Esto NO corre en el servidor. Corre una vez acá, escupe `tabla.py`, y eso
es lo que se publica. La fuente queda guardada al lado para poder
rehacerlo cuando termine cada temporada.
"""
import os
import re
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))

# ── Qué cuenta y qué no ──────────────────────────────────────────────────
# Cuenta el campeonato de Primera División: el torneo largo que define al
# campeón, en todas sus formas —Campeonato, Copa Campeonato, Metropolitano,
# Nacional, Apertura, Clausura, Inicial, Final, Liga Profesional—, incluidas
# sus zonas y sus fases finales, porque todo eso es el campeonato.
#
# NO cuenta:
#   · Reclasificación, Promocional, Petit, Liguilla y Pre Libertadores:
#     son torneos aparte que se jugaban después, para repartir cupos o
#     definir descensos. No son el campeonato.
#   · Los playoffs de descenso y las promociones, por lo mismo.
#   · La Copa de la Liga Profesional, que es una copa y ya está contada
#     como copa en historia.py.
#   · Las tablas "combinadas", donde RSSSF suma dos torneos para definir
#     posiciones: sumarlas sería contar los mismos partidos dos veces.
FUERA = (
    "reclasificat", "reclasificac", "against relegation", "promocional",
    "petit", "liguilla", "pre libertadores", "pre-libertadores",
    "relegation", "descenso", "promoci", "league cup", "copa de la liga",
    "copa lpf", "tabla general", "general table", "playoff", "desempate",
    "top scorers", "goleadores",
)

# Una fila de tabla: posición, nombre, PJ G E P GF:GC (o GF-GC) y puntos.
#
# La posición es OPCIONAL, y ésa es la trampa de todo esto: cuando dos
# equipos empatan en puntos, RSSSF escribe el número una sola vez y la
# segunda fila arranca con espacios. Pidiendo el número se perdían filas
# enteras —trece de dieciocho equipos en los años 50— y el error no se
# notaba, porque una tabla a la que le faltan equipos sigue pareciendo
# una tabla. Se notó recién al comprobar que los ganados no daban los
# perdidos.
# Y el espacio después del punto tampoco está garantizado: las páginas
# viejas escriben " 1. Boca Juniors" y las nuevas "10.CA Lanús", pegado.
# Pidiéndolo se cortaban las tablas modernas en la fila 9 —justo donde el
# número pasa a tener dos dígitos y se come el espacio de la izquierda—.
FILA = re.compile(
    r"^\s*(?:\d+\.)?\s*"                  # "12." o nada, con o sin espacio
    r"(?P<club>[^\d\s][^\n]*?)\s\s+"      # el nombre, hasta dos espacios
    r"(?P<pj>\d+)\s+(?P<g>\d+)\s+(?P<e>\d+)\s+(?P<p>\d+)\s+"
    r"(?P<gf>\d+)\s*[:\-]\s*(?P<gc>\d+)"  # 85: 49  ó  62- 30
    r"(?:\s+[-\d.]+)*"                    # los puntos, y lo que venga
    r"(?:\s*\((?P<ciudad>[^)]*)\))?"      # (Remedios de Escalada)
)
GOLES = re.compile(r"^\s*Goals:\s*(\d+)", re.I)
CAMPEON = re.compile(r"^\s*Champion:\s*(.+?)\.?\s*$", re.I)


def limpio(s):
    """
    El texto viene en windows-1252 mal decodificado: "Hurac�n", "V�lez".

    No se puede arreglar carácter por carácter con una tabla, porque el
    reemplazo perdió la información. Pero sí se puede normalizar: el
    signo raro se convierte en un comodín y después el nombre se resuelve
    contra la lista de clubes que ya conocemos. Acá sólo se deja el
    nombre parejo para poder agruparlo.
    """
    s = s.replace("�", "?").replace("\x92", "'")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(".").strip()
    return s


def plano(s):
    """Para comparar: sin tildes, sin mayúsculas, sin puntos."""
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9?]+", " ", s).strip()


# Las siglas societarias que RSSSF pone adelante en las páginas modernas y
# no en las viejas: "River Plate" en 1931 y "CA River Plate" en 2021 son el
# mismo club, y sin sacarlas quedan como dos, cada uno con la mitad de la
# historia. Fue lo último que se descubrió y lo que más cambiaba los
# números: River aparecía con 2.524 partidos en vez de 3.300.
SIGLAS = ("ca", "cd", "cs", "csd", "csyd", "cdd", "aa", "ac", "accа", "acca",
          "amsyd", "cade", "c", "cadu", "asd", "cdyd", "csa", "clab",
          "club", "cdz", "afc", "fc", "ca de", "cf", "sd", "cdc")
# Y las de atrás, que aparecen sueltas: "Arsenal FC", "Quilmes AC".
COLA = ("fc", "ac", "afc", "cf", "sc")


def sin_siglas(nombre):
    """El nombre del club sin la sigla de sociedad, adelante o atrás."""
    p = plano(nombre).split()
    while p and p[0] in SIGLAS:
        p = p[1:]
    while p and p[-1] in COLA:
        p = p[:-1]
    return " ".join(p) or plano(nombre)


def bloques(texto):
    """
    Corta el archivo en bloques, uno por encabezado.

    Devuelve (encabezado, temporada, líneas). La temporada sale del
    encabezado más cercano que tenga un año, porque los encabezados de
    torneo a veces lo repiten y a veces no.
    """
    salida = []
    enc, temporada, lineas = "", "", []
    ultima_temp = ""
    for ln in texto.split("\n"):
        if ln.startswith("#"):
            if enc:
                salida.append((enc, temporada, lineas))
            enc = limpio(re.sub(r"\[(.*?)\]\(.*?\)", r"\1", ln).strip("# "))
            m = re.search(r"(\d{4}(?:/\d{2,4})?)", enc)
            if m:
                ultima_temp = m.group(1)
            temporada = ultima_temp
            lineas = []
        else:
            lineas.append(ln)
    if enc:
        salida.append((enc, temporada, lineas))
    return salida


def cuenta(enc):
    """¿Este bloque es parte del campeonato de Primera?"""
    e = plano(enc)
    return not any(f in e for f in FUERA)


def leer(archivo):
    """Las filas de un archivo, ya filtradas, con su torneo."""
    texto = open(os.path.join(AQUI, archivo), encoding="utf-8",
                 errors="replace").read()
    filas, saltados = [], []
    for enc, temporada, lineas in bloques(texto):
        if not cuenta(enc):
            saltados.append(enc)
            continue
        # Adentro de un bloque puede haber varias tablas separadas por
        # rótulos sueltos ("Semifinal", "Final", "Zona A"). Se toman
        # todas: son fases del mismo campeonato.
        goles_dice = None
        aqui = []
        # Cada tabla suelta adentro del bloque lleva su propio número, para
        # poder comprobarlas de a una. Una tabla es un grupo de filas
        # seguidas; el rótulo del medio ("Zona A", "Final") la corta.
        sub, hueco = 0, 0
        for ln in lineas:
            m = FILA.match(ln)
            # La regla que limpia todo: una fila de tabla tiene que cumplir
            # PJ = G + E + P. Suena obvio y es lo que separa el grano de la
            # paja, porque adentro de estas páginas hay otras tablas que
            # también empiezan con "12. Nombre" y siguen con números —la de
            # promedios, sobre todo— y se colaban enteras. Una fila que no
            # cierra consigo misma no es una fila de posiciones.
            if m and int(m.group("pj")) != (int(m.group("g"))
                                            + int(m.group("e"))
                                            + int(m.group("p"))):
                m = None
            if m:
                if hueco:
                    sub += 1
                hueco = 0
                aqui.append({
                    "club": limpio(m.group("club")),
                    "pj": int(m.group("pj")), "g": int(m.group("g")),
                    "e": int(m.group("e")), "p": int(m.group("p")),
                    "gf": int(m.group("gf")), "gc": int(m.group("gc")),
                    "ciudad": limpio(m.group("ciudad") or ""),
                    "sub": sub,
                })
                continue
            if ln.strip():
                hueco = 1
            mg = GOLES.match(ln)
            if mg:
                goles_dice = int(mg.group(1))
        for f in aqui:
            f["torneo"] = enc
            f["temporada"] = temporada
            f["golesDice"] = goles_dice
        filas += sin_resumenes(aqui)
    return filas, saltados


def sin_resumenes(aqui):
    """
    Saca las tablas que son la suma de otras dos.

    Éste es el error que las cuatro verificaciones NO agarran, y por eso
    va aparte y con su propia regla. RSSSF publica, en la misma página, el
    Inicial, el Final y **la suma de los dos**; lo mismo con Apertura y
    Clausura. Sumando todo, esos partidos se cuentan dos veces. Y como una
    tabla duplicada está internamente balanceada, los ganados siguen dando
    los perdidos y los goles siguen dando: parece que está todo bien.

    Se detecta por aritmética, no por el título, que cambia de década en
    década: si un club aparece en una tabla con exactamente los partidos
    que suman sus otras tablas del mismo bloque, esa tabla es el resumen.
    """
    porclub = {}
    for f in aqui:
        porclub.setdefault(plano(f["club"]), []).append(f)
    resumen = set()
    for _c, fs in porclub.items():
        if len(fs) < 2:
            continue
        for f in fs:
            otros = [o for o in fs if o is not f]
            if f["pj"] and f["pj"] == sum(o["pj"] for o in otros) \
                    and len(otros) > 1:
                resumen.add((f["sub"], f["torneo"]))
    return [f for f in aqui if (f["sub"], f["torneo"]) not in resumen]


ARCHIVOS = ["rsssf-1930s.txt", "rsssf-1940s.txt", "rsssf-1950s.txt",
            "rsssf-1960s.txt", "rsssf-1970s.txt", "rsssf-1980s.txt",
            "rsssf-1990s.txt", "rsssf-2000s.txt", "rsssf-2010s.txt",
            "rsssf-2020s.txt"]


def todo():
    filas, saltados = [], []
    for a in ARCHIVOS:
        f, s = leer(a)
        filas += f
        saltados += s
    return filas, saltados


if __name__ == "__main__":
    filas, saltados = todo()
    print("filas leídas:", len(filas))
    print("bloques salteados:", len(saltados))
    # Las cuatro verificaciones, sobre el total.
    sg = sum(f["g"] for f in filas)
    sp = sum(f["p"] for f in filas)
    se = sum(f["e"] for f in filas)
    sgf = sum(f["gf"] for f in filas)
    sgc = sum(f["gc"] for f in filas)
    malas = [f for f in filas if f["pj"] != f["g"] + f["e"] + f["p"]]
    print("  PJ != G+E+P en %d filas" % len(malas))
    print("  ΣG %d vs ΣP %d   → %+d" % (sg, sp, sg - sp))
    print("  ΣGF %d vs ΣGC %d → %+d" % (sgf, sgc, sgf - sgc))
    print("  ΣE %d → %s" % (se, "par" if se % 2 == 0 else "IMPAR"))
    print()
    for f in malas[:10]:
        print("   ", f["temporada"], f["club"], f["pj"], f["g"], f["e"],
              f["p"], "|", f["torneo"][:50])
