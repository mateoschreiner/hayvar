# -*- coding: utf-8 -*-
"""
Los campeones del fútbol argentino, era profesional.

Esto es lo único del sitio que está escrito a mano y no sale de ninguna
API, porque no hay ninguna que lo dé bien. La fuente es la lista de RSSSF
—Osvaldo José Gorgazzi y Héctor Villa Martínez, la misma que cita
Wikipedia—, cruzada contra los totales por club que la propia RSSSF
publica al pie: si mi transcripción tuviera un error, esos totales no
darían. Esa comprobación está en las pruebas y corre en cada cambio.

Qué cuenta como liga
────────────────────
Todo lo que AFA cuenta, que es más de lo que uno diría:

  · Metropolitano y Nacional (1967-1985) son DOS títulos por año. Fueron
    campeonatos distintos, con campeones distintos, y AFA los lista a los
    dos. Por eso 1972 tiene dos San Lorenzo y 1975 dos River.
  · Apertura y Clausura (1991/92-2013/14) también son dos por temporada.
  · 1936 tiene tres: el Campeonato, la Copa de Honor y la Copa de Oro. Los
    dos últimos no eran campeonatos de liga, pero AFA los incorporó a la
    lista de campeones por una nota de su secretario general del 4 de
    julio de 2013, y desde entonces cuentan.
  · 2012/13 tiene tres: Inicial, Final, y el Campeonato que se definió
    entre esos dos.
  · 2025 tiene tres: Apertura, Clausura, y la tabla Anual que AFA declaró
    campeona el 20 de noviembre de 2025 aunque el reglamento no la
    preveía. Está discutida; está igual, porque AFA la cuenta.

La era amateur (1891-1934) no está. El profesionalismo arranca en 1931 y
es lo que pidió el pedido. Los títulos amateurs existen y son de otra
cosa: Alumni ganó diez y ya no existe como club.

Las copas van aparte, abajo, porque no son lo mismo y mezclarlas es la
forma más común de que una lista de campeones quede mal.
"""

# ── Las ligas ────────────────────────────────────────────────────────────
# (temporada, torneo, campeón). El torneo vacío quiere decir que ese año
# hubo uno solo y no hace falta nombrarlo.
LIGAS = [
    ("1931", "", "Boca Juniors"),
    ("1932", "", "River Plate"),
    ("1933", "", "San Lorenzo"),
    ("1934", "", "Boca Juniors"),
    ("1935", "", "Boca Juniors"),
    ("1936", "Campeonato", "River Plate"),
    ("1936", "Copa de Honor", "San Lorenzo"),
    ("1936", "Copa de Oro", "River Plate"),
    ("1937", "", "River Plate"),
    ("1938", "", "Independiente"),
    ("1939", "", "Independiente"),
    ("1940", "", "Boca Juniors"),
    ("1941", "", "River Plate"),
    ("1942", "", "River Plate"),
    ("1943", "", "Boca Juniors"),
    ("1944", "", "Boca Juniors"),
    ("1945", "", "River Plate"),
    ("1946", "", "San Lorenzo"),
    ("1947", "", "River Plate"),
    ("1948", "", "Independiente"),
    ("1949", "", "Racing"),
    ("1950", "", "Racing"),
    ("1951", "", "Racing"),
    ("1952", "", "River Plate"),
    ("1953", "", "River Plate"),
    ("1954", "", "Boca Juniors"),
    ("1955", "", "River Plate"),
    ("1956", "", "River Plate"),
    ("1957", "", "River Plate"),
    ("1958", "", "Racing"),
    ("1959", "", "San Lorenzo"),
    ("1960", "", "Independiente"),
    ("1961", "", "Racing"),
    ("1962", "", "Boca Juniors"),
    ("1963", "", "Independiente"),
    ("1964", "", "Boca Juniors"),
    ("1965", "", "Boca Juniors"),
    ("1966", "", "Racing"),
    # Desde acá, dos por año: Metropolitano y Nacional.
    ("1967", "Metropolitano", "Estudiantes (LP)"),
    ("1967", "Nacional", "Independiente"),
    ("1968", "Metropolitano", "San Lorenzo"),
    ("1968", "Nacional", "Vélez Sarsfield"),
    ("1969", "Metropolitano", "Chacarita Juniors"),
    ("1969", "Nacional", "Boca Juniors"),
    ("1970", "Metropolitano", "Independiente"),
    ("1970", "Nacional", "Boca Juniors"),
    ("1971", "Metropolitano", "Independiente"),
    ("1971", "Nacional", "Rosario Central"),
    ("1972", "Metropolitano", "San Lorenzo"),
    ("1972", "Nacional", "San Lorenzo"),
    ("1973", "Metropolitano", "Huracán"),
    ("1973", "Nacional", "Rosario Central"),
    ("1974", "Metropolitano", "Newell's Old Boys"),
    ("1974", "Nacional", "San Lorenzo"),
    ("1975", "Metropolitano", "River Plate"),
    ("1975", "Nacional", "River Plate"),
    ("1976", "Metropolitano", "Boca Juniors"),
    ("1976", "Nacional", "Boca Juniors"),
    ("1977", "Metropolitano", "River Plate"),
    ("1977", "Nacional", "Independiente"),
    ("1978", "Metropolitano", "Quilmes"),
    ("1978", "Nacional", "Independiente"),
    ("1979", "Metropolitano", "River Plate"),
    ("1979", "Nacional", "River Plate"),
    # Talleres entró a Primera y el torneo dejó de llamarse Metropolitano.
    ("1980", "Campeonato", "River Plate"),
    ("1980", "Nacional", "Rosario Central"),
    ("1981", "Campeonato", "Boca Juniors"),
    ("1981", "Nacional", "River Plate"),
    ("1982", "Campeonato", "Estudiantes (LP)"),
    ("1982", "Nacional", "Ferro Carril Oeste"),
    ("1983", "Campeonato", "Independiente"),
    ("1983", "Nacional", "Estudiantes (LP)"),
    ("1984", "Campeonato", "Argentinos Juniors"),
    ("1984", "Nacional", "Ferro Carril Oeste"),
    ("1985", "Nacional", "Argentinos Juniors"),
    # Vuelve el torneo único, ahora de mitad de año a mitad de año.
    ("1985/86", "", "River Plate"),
    ("1986/87", "", "Rosario Central"),
    ("1987/88", "", "Newell's Old Boys"),
    ("1988/89", "", "Independiente"),
    ("1989/90", "", "River Plate"),
    ("1990/91", "", "Newell's Old Boys"),
    # Y desde acá, Apertura y Clausura.
    ("1991/92", "Apertura", "River Plate"),
    ("1991/92", "Clausura", "Newell's Old Boys"),
    ("1992/93", "Apertura", "Boca Juniors"),
    ("1992/93", "Clausura", "Vélez Sarsfield"),
    ("1993/94", "Apertura", "River Plate"),
    ("1993/94", "Clausura", "Independiente"),
    ("1994/95", "Apertura", "River Plate"),
    ("1994/95", "Clausura", "San Lorenzo"),
    ("1995/96", "Apertura", "Vélez Sarsfield"),
    ("1995/96", "Clausura", "Vélez Sarsfield"),
    ("1996/97", "Apertura", "River Plate"),
    ("1996/97", "Clausura", "River Plate"),
    ("1997/98", "Apertura", "River Plate"),
    ("1997/98", "Clausura", "Vélez Sarsfield"),
    ("1998/99", "Apertura", "Boca Juniors"),
    ("1998/99", "Clausura", "Boca Juniors"),
    ("1999/00", "Apertura", "River Plate"),
    ("1999/00", "Clausura", "River Plate"),
    ("2000/01", "Apertura", "Boca Juniors"),
    ("2000/01", "Clausura", "San Lorenzo"),
    ("2001/02", "Apertura", "Racing"),
    ("2001/02", "Clausura", "River Plate"),
    ("2002/03", "Apertura", "Independiente"),
    ("2002/03", "Clausura", "River Plate"),
    ("2003/04", "Apertura", "Boca Juniors"),
    ("2003/04", "Clausura", "River Plate"),
    ("2004/05", "Apertura", "Newell's Old Boys"),
    ("2004/05", "Clausura", "Vélez Sarsfield"),
    ("2005/06", "Apertura", "Boca Juniors"),
    ("2005/06", "Clausura", "Boca Juniors"),
    ("2006/07", "Apertura", "Estudiantes (LP)"),
    ("2006/07", "Clausura", "San Lorenzo"),
    ("2007/08", "Apertura", "Lanús"),
    ("2007/08", "Clausura", "River Plate"),
    ("2008/09", "Apertura", "Boca Juniors"),
    ("2008/09", "Clausura", "Vélez Sarsfield"),
    ("2009/10", "Apertura", "Banfield"),
    ("2009/10", "Clausura", "Argentinos Juniors"),
    ("2010/11", "Apertura", "Estudiantes (LP)"),
    ("2010/11", "Clausura", "Vélez Sarsfield"),
    ("2011/12", "Apertura", "Boca Juniors"),
    ("2011/12", "Clausura", "Arsenal"),
    ("2012/13", "Inicial", "Vélez Sarsfield"),
    ("2012/13", "Final", "Newell's Old Boys"),
    ("2012/13", "Campeonato", "Vélez Sarsfield"),
    ("2013/14", "Inicial", "San Lorenzo"),
    ("2013/14", "Final", "River Plate"),
    ("2014", "", "Racing"),
    ("2015", "", "Boca Juniors"),
    ("2016", "", "Lanús"),
    ("2016/17", "", "Boca Juniors"),
    # Los tres años de la Superliga, que era una sociedad aparte.
    ("2017/18", "", "Boca Juniors"),
    ("2018/19", "", "Racing"),
    ("2019/20", "", "Boca Juniors"),
    # Y de vuelta adentro de AFA, como Liga Profesional.
    ("2021", "", "River Plate"),
    ("2022", "", "Boca Juniors"),
    ("2023", "", "River Plate"),
    ("2024", "", "Vélez Sarsfield"),
    ("2025", "Apertura", "Platense"),
    ("2025", "Clausura", "Estudiantes (LP)"),
    ("2025", "Anual", "Rosario Central"),
    ("2026", "Apertura", "Belgrano"),
]

# Lo que hay que aclarar de algunos títulos. La nota va al lado del año, no
# en un pie que nadie lee.
NOTAS = {
    ("1936", "Copa de Honor"): "AFA la sumó a la lista de campeones en 2013.",
    ("1936", "Copa de Oro"): "AFA la sumó a la lista de campeones en 2013.",
    ("1967", "Nacional"): "El Nacional lo jugaban también equipos del "
                          "interior que no estaban en Primera.",
    ("2012/13", "Campeonato"): "Se definió entre el campeón del Inicial y "
                               "el del Final.",
    ("2025", "Anual"): "AFA declaró campeón al primero de la tabla anual el "
                       "20 de noviembre de 2025, sin que el reglamento lo "
                       "previera.",
}

# ── Las copas ────────────────────────────────────────────────────────────
# Aparte de las ligas y a propósito: son otra cosa. Están las nacionales
# de la era moderna, que son las que la gente busca. Las viejas —Copa de
# Competencia, Ibarguren, Escobar, Campeonato de la República— son de una
# época en la que la mitad eran torneos amateurs o mixtos, y meterlas sin
# explicarlas sería confundir más de lo que aclara.
COPAS = [
    ("Copa Argentina", [
        ("2011/12", "Boca Juniors"), ("2012/13", "Arsenal"),
        ("2013/14", "Huracán"), ("2014/15", "Boca Juniors"),
        ("2015/16", "River Plate"), ("2016/17", "River Plate"),
        ("2017/18", "Rosario Central"), ("2018/19", "River Plate"),
        ("2019/20", "Boca Juniors"), ("2022", "Patronato"),
        ("2023", "Estudiantes (LP)"), ("2024", "Central Córdoba (SdE)"),
        ("2025", "Independiente Rivadavia"),
    ]),
    ("Copa de la Liga Profesional", [
        ("2020", "Boca Juniors"), ("2021", "Colón"), ("2022", "Boca Juniors"),
        ("2023", "Rosario Central"), ("2024", "Estudiantes (LP)"),
    ]),
    ("Supercopa Argentina", [
        ("2012", "Arsenal"), ("2013", "Vélez Sarsfield"), ("2014", "Huracán"),
        ("2015", "San Lorenzo"), ("2016", "Lanús"), ("2017", "River Plate"),
        ("2018", "Boca Juniors"), ("2019", "River Plate"),
        ("2022", "Boca Juniors"), ("2023", "River Plate"),
        ("2024", "Vélez Sarsfield"),
    ]),
    ("Trofeo de Campeones", [
        ("2019", "Racing"), ("2021", "River Plate"), ("2022", "Racing"),
        ("2023", "River Plate"), ("2024", "Estudiantes (LP)"),
        ("2025", "Estudiantes (LP)"),
    ]),
    ("Supercopa Internacional", [
        ("2022", "Racing"), ("2023", "Talleres (C)"),
        ("2024", "Vélez Sarsfield"),
    ]),
    ("Copa de la Superliga", [("2019", "Tigre")]),
    ("Copa Campeonato de Primera División", [("2013/14", "River Plate")]),
    ("Copa del Bicentenario", [("2016", "Lanús")]),
]

# La primera temporada del profesionalismo, para poder decirlo en pantalla
# sin repetir el número en tres lugares.
DESDE = LIGAS[0][0]


def _clave(temporada):
    """Para ordenar '1985/86' entre '1985' y '1986/87'."""
    return (int(temporada[:4]), temporada)


def por_ano():
    """
    Los campeones año por año, del más nuevo al más viejo, con los años de
    dos títulos agrupados en una sola fila para que se vea que fueron el
    mismo año y no dos.
    """
    filas = {}
    for temporada, torneo, campeon in LIGAS:
        filas.setdefault(temporada, []).append({
            "torneo": torneo, "campeon": campeon,
            "nota": NOTAS.get((temporada, torneo)),
        })
    return [{"temporada": t, "titulos": filas[t]}
            for t in sorted(filas, key=_clave, reverse=True)]


def por_club(cual=None):
    """
    Cuántas ligas tiene cada club, de mayor a menor, con el detalle de
    cuáles para poder desplegarlo.

    `cual` permite pedir lo mismo pero de una copa: se le pasa la lista de
    (temporada, campeón).
    """
    cuenta = {}
    for fila in (cual if cual is not None else LIGAS):
        temporada, campeon = fila[0], fila[-1]
        torneo = fila[1] if cual is None else ""
        c = cuenta.setdefault(campeon, {"club": campeon, "titulos": 0,
                                        "detalle": []})
        c["titulos"] += 1
        c["detalle"].append({"temporada": temporada, "torneo": torneo})
    salida = sorted(cuenta.values(),
                    key=lambda c: (-c["titulos"], c["club"]))
    for c in salida:
        c["detalle"].sort(key=lambda d: _clave(d["temporada"]), reverse=True)
    for i, c in enumerate(salida, 1):
        # Los que empatan comparten posición: no es lo mismo "octavo" que
        # "octavo entre cinco de seis títulos".
        c["pos"] = i if i == 1 or c["titulos"] != salida[i - 2]["titulos"] \
            else salida[i - 2]["pos"]
    return salida


def copas():
    """Cada copa con sus campeones, del más nuevo al más viejo."""
    return [{"copa": nombre,
             "campeones": sorted(
                 [{"temporada": t, "campeon": c} for t, c in filas],
                 key=lambda x: _clave(x["temporada"]), reverse=True),
             "porClub": por_club(filas)}
            for nombre, filas in COPAS]


def _plano(texto):
    """Un nombre sin tildes ni mayúsculas, para poder compararlos."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower())
                   if unicodedata.category(c) != "Mn")


def resumen_por_club():
    """
    Cada club con su total de títulos y el desglose: cuántas ligas y
    cuántas copas.

    El total va primero porque es lo que se pregunta —"¿cuántas tiene
    Boca?"— pero el desglose tiene que estar al lado sí o sí: una liga y
    una Supercopa no son lo mismo, y una lista que las suma sin decirlo es
    la clase de dato que después alguien discute en un bar.

    El orden es por total, después por ligas —a igual total gana el que
    tiene más ligas, que es lo que cualquiera diría— y después alfabético.
    """
    c = {}

    def entrada(club):
        return c.setdefault(club, {"club": club, "total": 0, "ligas": 0,
                                   "copas": 0, "detalleLigas": [],
                                   "detalleCopas": []})

    for temporada, torneo, campeon in LIGAS:
        x = entrada(campeon)
        x["ligas"] += 1
        x["detalleLigas"].append({"temporada": temporada, "torneo": torneo})
    for nombre, filas in COPAS:
        porCopa = {}
        for temporada, campeon in filas:
            porCopa.setdefault(campeon, []).append(temporada)
        for campeon, temporadas in porCopa.items():
            x = entrada(campeon)
            x["copas"] += len(temporadas)
            x["detalleCopas"].append({
                "copa": nombre,
                "temporadas": sorted(temporadas, key=_clave, reverse=True)})

    salida = sorted(c.values(),
                    key=lambda x: (-(x["ligas"] + x["copas"]), -x["ligas"],
                                   _plano(x["club"])))
    for x in salida:
        x["total"] = x["ligas"] + x["copas"]
        x["detalleLigas"].sort(key=lambda d: _clave(d["temporada"]),
                               reverse=True)
        x["detalleCopas"].sort(key=lambda d: (-len(d["temporadas"]), d["copa"]))
    for i, x in enumerate(salida, 1):
        x["pos"] = i if i == 1 or x["total"] != salida[i - 2]["total"] \
            else salida[i - 2]["pos"]
    return salida


# Se arma una sola vez: es una lista fija y la pide cada ficha de club.
_POR_CLUB = None


def titulos_de(club):
    """
    Los títulos de un club, para su ficha. None si no ganó ninguno —que es
    la mayoría— para que la ficha no muestre un cero.
    """
    global _POR_CLUB
    if _POR_CLUB is None:
        _POR_CLUB = {_plano(x["club"]): x for x in resumen_por_club()}
    return _POR_CLUB.get(_plano(club))


# Qué competencia del sitio corresponde a cada lista de campeones. Sin
# esto, la pantalla de Copa Argentina no sabría cuál de las ocho copas es
# la suya.
DE_LA_COMPETENCIA = {
    "ca": "Copa Argentina",
}


def de_copa(nombre):
    """
    La historia de una copa sola, con la misma forma que la de la liga.

    Devuelve las mismas claves —`porAno`, `porClub`, `total`— para que la
    pantalla sea una y no dos: lo único que cambia es que una copa no
    tiene dos campeones en el mismo año, así que cada fila trae uno.
    """
    filas = next((f for n, f in COPAS if n == nombre), None)
    if filas is None:
        return None
    por_ano = [{"temporada": t, "titulos": [{"torneo": "", "campeon": c,
                                             "nota": None}]}
               for t, c in sorted(filas, key=lambda x: _clave(x[0]),
                                  reverse=True)]
    por_club = []
    for x in por_club_de(filas):
        por_club.append(x)
    return {
        "copa": nombre,
        "titulo": nombre,
        # Cómo se llama cada título en esta pantalla. En Primera son ligas
        # y copas; acá son todas copas, y decir "3 ligas" abajo del nombre
        # de un campeón de la Copa Argentina es sencillamente falso.
        "unidad": "copa",
        "desde": min(t for t, _c in filas),
        "total": len(filas),
        "porAno": por_ano,
        "porClub": por_club,
        "copas": [],
        "fuente": "RSSSF (Gorgazzi y Villa Martínez) sobre registros de AFA",
        "nota": ("Todos los campeones de la %s. Una copa se gana una vez "
                 "por edición, así que acá cada año tiene un solo campeón."
                 % nombre),
    }


def por_club_de(filas):
    """
    Cuántas veces ganó cada club una copa, con la misma forma que la de la
    liga para que la pantalla no tenga que distinguir.
    """
    cuenta = {}
    for temporada, campeon in filas:
        c = cuenta.setdefault(campeon, {"club": campeon, "ligas": 0,
                                        "copas": 0, "detalleLigas": [],
                                        "detalleCopas": []})
        c["copas"] += 1
        c["detalleLigas"].append({"temporada": temporada, "torneo": ""})
    salida = sorted(cuenta.values(),
                    key=lambda x: (-x["copas"], _plano(x["club"])))
    for x in salida:
        x["total"] = x["copas"]
        # Se muestran en el mismo lugar que las ligas de la otra pantalla:
        # acá "las ligas" del club son sus ediciones ganadas.
        x["ligas"] = x["copas"]
        x["copas"] = 0
        x["detalleCopas"] = []
        x["detalleLigas"].sort(key=lambda d: _clave(d["temporada"]),
                               reverse=True)
    for i, x in enumerate(salida, 1):
        x["pos"] = i if i == 1 or x["total"] != salida[i - 2]["total"] \
            else salida[i - 2]["pos"]
    return salida


def todo():
    """Lo que se manda a la pantalla, ya armado."""
    return {
        "titulo": "Ligas",
        "desde": DESDE,
        "total": len(LIGAS),
        "porAno": por_ano(),
        "porClub": resumen_por_club(),
        "copas": copas(),
        "fuente": "RSSSF (Gorgazzi y Villa Martínez) sobre registros de AFA",
        "nota": ("Era profesional, desde %s. Metropolitano y Nacional "
                 "(1967-1985) y Apertura y Clausura (1991-2014) cuentan "
                 "como dos títulos por temporada, que es como los cuenta "
                 "AFA." % DESDE),
    }
