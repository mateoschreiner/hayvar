# -*- coding: utf-8 -*-
"""
Los títulos internacionales de los clubes argentinos.

76 títulos oficiales, de 1964 a 2026. Verificado contra los totales que
publican CONMEBOL, RSSSF y Wikipedia por separado: los ocho controles
clásicos —Independiente 7 Libertadores, Boca 6, Estudiantes 4, River 4,
y una cada uno Racing, Vélez, Argentinos y San Lorenzo— dan exacto, y el
total de 25 Libertadores argentinas coincide con la tabla por país.

Qué cuenta
──────────
Todo lo que CONMEBOL lista como competencia oficial de clubes, incluidas
las discontinuadas: la Supercopa, la Copa CONMEBOL, el Mercosur, la
Interamericana, la Copa Master y la Copa de Oro. Y la Intercontinental,
que era el partido contra el campeón de Europa.

Qué NO cuenta, y por qué
────────────────────────
· La Copa Suruga Bank está abajo, en APARTE, y no suma al total. CONMEBOL
  la coorganizaba y la lista como oficial, pero era un partido único
  contra un equipo japonés y Wikipedia en inglés directamente la cataloga
  como amistoso. Contarla cambia quién está primero —Boca 18 solo, o Boca
  e Independiente empatados en 18—, así que la decisión se toma a la vista
  y no escondida en un total.
· Las copas rioplatenses (Aldao, Tie Cup, Cousenier) son títulos
  internacionales de verdad, pero son anteriores a que CONMEBOL
  organizara torneos de clubes y no integran su nómina.
· El Mundial de Clubes no está porque ningún club argentino lo ganó.
  Cuatro finales perdidas: Boca 2007, Estudiantes 2009, San Lorenzo 2014
  y River 2015.

Un detalle de fechas
────────────────────
La Copa Interamericana se jugaba con más de un año de atraso respecto de
la Libertadores que daba la clasificación, y las fuentes usan tres
numeraciones distintas para los mismos partidos. Acá va el año en que se
jugó, que es el criterio de Wikipedia en español y el único que no se
contradice consigo mismo.

Fuente: CONMEBOL, RSSSF (Stokkermans) y Wikipedia, cruzadas entre sí.
"""

# (competencia, [(año, campeón, a quién le ganó la final)])
COPAS = [
    ("Copa Libertadores", [
        ("1964", "Independiente", "Nacional (URU)"),
        ("1965", "Independiente", "Peñarol (URU)"),
        ("1967", "Racing", "Nacional (URU)"),
        ("1968", "Estudiantes (LP)", "Palmeiras (BRA)"),
        ("1969", "Estudiantes (LP)", "Nacional (URU)"),
        ("1970", "Estudiantes (LP)", "Peñarol (URU)"),
        ("1972", "Independiente", "Universitario (PER)"),
        ("1973", "Independiente", "Colo-Colo (CHI)"),
        ("1974", "Independiente", "São Paulo (BRA)"),
        ("1975", "Independiente", "Unión Española (CHI)"),
        ("1977", "Boca Juniors", "Cruzeiro (BRA)"),
        ("1978", "Boca Juniors", "Deportivo Cali (COL)"),
        ("1984", "Independiente", "Grêmio (BRA)"),
        ("1985", "Argentinos Juniors", "América de Cali (COL)"),
        ("1986", "River Plate", "América de Cali (COL)"),
        ("1994", "Vélez Sarsfield", "São Paulo (BRA)"),
        ("1996", "River Plate", "América de Cali (COL)"),
        ("2000", "Boca Juniors", "Palmeiras (BRA)"),
        ("2001", "Boca Juniors", "Cruz Azul (MEX)"),
        ("2003", "Boca Juniors", "Santos (BRA)"),
        ("2007", "Boca Juniors", "Grêmio (BRA)"),
        ("2009", "Estudiantes (LP)", "Cruzeiro (BRA)"),
        ("2014", "San Lorenzo", "Nacional (PAR)"),
        ("2015", "River Plate", "Tigres UANL (MEX)"),
        ("2018", "River Plate", "Boca Juniors"),
    ]),
    ("Copa Sudamericana", [
        ("2002", "San Lorenzo", "Atlético Nacional (COL)"),
        ("2004", "Boca Juniors", "Bolívar (BOL)"),
        ("2005", "Boca Juniors", "Pumas UNAM (MEX)"),
        ("2007", "Arsenal", "América (MEX)"),
        ("2010", "Independiente", "Goiás (BRA)"),
        ("2013", "Lanús", "Ponte Preta (BRA)"),
        ("2014", "River Plate", "Atlético Nacional (COL)"),
        ("2017", "Independiente", "Flamengo (BRA)"),
        ("2020", "Defensa y Justicia", "Lanús"),
        ("2024", "Racing", "Cruzeiro (BRA)"),
        ("2025", "Lanús", "Atlético Mineiro (BRA)"),
    ]),
    ("Recopa Sudamericana", [
        ("1990", "Boca Juniors", "Atlético Nacional (COL)"),
        ("1995", "Independiente", "Vélez Sarsfield"),
        ("1997", "Vélez Sarsfield", "River Plate"),
        ("2005", "Boca Juniors", "Once Caldas (COL)"),
        ("2006", "Boca Juniors", "São Paulo (BRA)"),
        ("2008", "Boca Juniors", "Arsenal"),
        ("2015", "River Plate", "San Lorenzo"),
        ("2016", "River Plate", "Independiente Santa Fe (COL)"),
        ("2019", "River Plate", "Athletico Paranaense (BRA)"),
        ("2021", "Defensa y Justicia", "Palmeiras (BRA)"),
        ("2025", "Racing", "Botafogo (BRA)"),
        ("2026", "Lanús", "Flamengo (BRA)"),
    ]),
    ("Copa Intercontinental", [
        ("1967", "Racing", "Celtic (ESC)"),
        ("1968", "Estudiantes (LP)", "Manchester United (ING)"),
        ("1973", "Independiente", "Juventus (ITA)"),
        ("1977", "Boca Juniors", "Borussia Mönchengladbach (RFA)"),
        ("1984", "Independiente", "Liverpool (ING)"),
        ("1986", "River Plate", "Steaua Bucarest (RUM)"),
        ("1994", "Vélez Sarsfield", "Milan (ITA)"),
        ("2000", "Boca Juniors", "Real Madrid (ESP)"),
        ("2003", "Boca Juniors", "Milan (ITA)"),
    ]),
    ("Copa Interamericana", [
        ("1969", "Estudiantes (LP)", "Toluca (MEX)"),
        ("1973", "Independiente", "Olimpia (HON)"),
        ("1974", "Independiente", "Deportivo Municipal (GUA)"),
        ("1976", "Independiente", "Atlético Español (MEX)"),
        ("1986", "Argentinos Juniors", "Defence Force (TRI)"),
        ("1987", "River Plate", "LD Alajuelense (CRC)"),
        ("1996", "Vélez Sarsfield", "Cartaginés (CRC)"),
    ]),
    ("Supercopa Sudamericana", [
        ("1988", "Racing", "Cruzeiro (BRA)"),
        ("1989", "Boca Juniors", "Independiente"),
        ("1994", "Independiente", "Boca Juniors"),
        ("1995", "Independiente", "Flamengo (BRA)"),
        ("1996", "Vélez Sarsfield", "Cruzeiro (BRA)"),
        ("1997", "River Plate", "São Paulo (BRA)"),
    ]),
    ("Copa CONMEBOL", [
        ("1995", "Rosario Central", "Atlético Mineiro (BRA)"),
        ("1996", "Lanús", "Independiente Santa Fe (COL)"),
        ("1999", "Talleres (C)", "CSA (BRA)"),
    ]),
    ("Copa Mercosur", [
        ("2001", "San Lorenzo", "Flamengo (BRA)"),
    ]),
    ("Copa Master de Supercopa", [
        ("1992", "Boca Juniors", "Cruzeiro (BRA)"),
    ]),
    ("Copa de Oro", [
        ("1993", "Boca Juniors", "Atlético Mineiro (BRA)"),
    ]),
]

# Los tres que no suman al total, y por qué. Se muestran igual: existen,
# los clubes los exhiben, y esconderlos sería tan discutible como
# contarlos.
APARTE = [
    ("Copa Suruga Bank",
     "CONMEBOL la coorganizaba con Japón y la lista como oficial, pero "
     "era un partido único contra el campeón de la Copa J.League y "
     "Wikipedia en inglés la cataloga como amistoso. No suma al total.",
     [("2008", "Arsenal", "Gamba Osaka (JPN)"),
      ("2015", "River Plate", "Gamba Osaka (JPN)"),
      ("2018", "Independiente", "Cerezo Osaka (JPN)")]),
]
