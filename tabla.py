# -*- coding: utf-8 -*-
"""
La tabla histórica de Primera División, era profesional.

ESTE ARCHIVO SE GENERA. No lo edites a mano: lo escribe
`_fuente/armar.py` a partir de las tablas de RSSSF guardadas en
`_fuente/`. Para actualizarlo cuando termine una temporada, se baja la
página de esa temporada y se vuelve a correr.

De dónde sale
─────────────
De sumar la tabla final de cada torneo de Primera desde 1931: Campeonato,
Copa Campeonato, Metropolitano, Nacional, Apertura, Clausura, Inicial,
Final y Liga Profesional, con sus zonas y sus fases finales.

No cuentan los torneos que no son el campeonato —Reclasificación,
Liguilla Pre Libertadores, Promocional, Petit— ni los playoffs de
descenso, ni la Copa de la Liga, que es una copa y ya está en historia.py.

Por qué se hizo de cero
───────────────────────
Porque no existe publicada y bien. La de Wikipedia falla las cuatro
verificaciones básicas: los ganados de todos los clubes suman 390 más que
los perdidos, hay 24 filas donde los partidos no dan la suma de ganados,
empatados y perdidos, está congelada en abril de 2020 aunque el título
diga 2025, y Barracas Central no aparece.

Los puntos
──────────
Se cuentan 3 por victoria en toda la historia, también en los años en que
se daban 2. Es la única forma de comparar a un equipo de los 60 con uno
de hoy: con el sistema viejo, un triunfo del 72 vale menos que uno del
2020 y el orden queda distorsionado a favor de los clubes modernos.

Qué tan exacta es
─────────────────
Las cuatro verificaciones corren en las pruebas. Los partidos dan la suma
de ganados, empatados y perdidos en las 3.238 filas leídas, sin una
sola excepción. Quedan 15 partidos y 17 goles de desbalance
sobre 25.555 y 99.511: es el residuo de la propia fuente, que asienta de
forma asimétrica los partidos dados por ganados y los abandonados.

Fuente: RSSSF, tablas finales de Argentina, de Osvaldo José Gorgazzi y
Víctor Hugo Kurhy. 94 temporadas, de 1931 a 2024.
"""

# (club, PJ, G, E, P, GF, GC). Los puntos se calculan: 3*G + E.
TABLA = [
    ("River Plate",              3506,  1803,   914,   789,   6363,   3895),
    ("Boca Juniors",             3581,  1753,   954,   874,   6056,   4032),
    ("San Lorenzo",              3645,  1557,  1017,  1071,   5804,   4643),
    ("Independiente",            3551,  1535,  1017,   999,   5687,   4318),
    ("Vélez Sarsfield",          3488,  1447,   995,  1046,   5191,   4302),
    ("Racing",                   3483,  1405,  1013,  1065,   5328,   4445),
    ("Estudiantes (LP)",         3556,  1372,   998,  1186,   5135,   4661),
    ("Newell's Old Boys",        3174,  1140,   998,  1036,   4345,   3964),
    ("Rosario Central",          2957,  1040,   912,  1005,   4137,   3979),
    ("Huracán",                  3007,  1066,   808,  1133,   4389,   4506),
    ("Gimnasia y Esgrima (LP)",  2996,   969,   873,  1154,   4043,   4556),
    ("Argentinos Juniors",       2781,   851,   872,  1058,   3498,   3967),
    ("Lanús",                    2562,   894,   714,   954,   3605,   3907),
    ("Ferro Carril Oeste",       2266,   689,   717,   860,   2954,   3470),
    ("Platense",                 2107,   625,   647,   835,   2784,   3303),
    ("Banfield",                 2026,   627,   618,   781,   2564,   2820),
    ("Colón",                    1835,   608,   561,   666,   2259,   2474),
    ("Chacarita Juniors",        1974,   611,   504,   859,   2696,   3265),
    ("Unión",                    1494,   444,   502,   548,   1748,   1903),
    ("Atlanta",                  1488,   443,   379,   666,   2126,   2720),
    ("Talleres (C)",             1206,   426,   366,   414,   1601,   1580),
    ("Tigre",                    1428,   405,   337,   686,   1927,   2637),
    ("Quilmes",                  1266,   352,   355,   559,   1438,   1969),
    ("Arsenal",                   908,   309,   266,   333,   1002,   1118),
    ("Belgrano",                  911,   290,   309,   312,    990,   1049),
    ("Godoy Cruz",                791,   274,   223,   294,    948,    988),
    ("Instituto",                 622,   190,   183,   249,    744,    867),
    ("All Boys",                  653,   170,   196,   287,    661,    944),
    ("Deportivo Español",         539,   163,   189,   187,    568,    632),
    ("Atlético Tucumán",          479,   156,   149,   174,    566,    625),
    ("Olimpo",                    510,   140,   141,   229,    513,    670),
    ("Racing (C)",                403,   130,   125,   148,    487,    519),
    ("San Martín Tucumán",        443,   116,   131,   196,    491,    665),
    ("Temperley",                 425,   109,   129,   187,    444,    607),
    ("Defensa y Justicia",        276,   114,    80,    82,    337,    277),
    ("Gimnasia de Jujuy",         379,   104,   108,   167,    436,    600),
    ("Atlético Rafaela",          332,    94,    96,   142,    377,    466),
    ("San Martín San Juan",       320,    90,    91,   139,    358,    432),
    ("Gimnasia y Esgrima (M)",    275,    86,    81,   108,    336,    377),
    ("Deportivo Mandiyú",         303,    68,   122,   113,    306,    383),
    ("Nueva Chicago",             286,    70,    89,   127,    295,    417),
    ("Sarmiento (J)",             282,    65,    91,   126,    271,    372),
    ("Aldosivi",                  228,    67,    49,   112,    229,    346),
    ("Talleres (RdE)",            236,    57,    43,   136,    374,    560),
    ("Patronato",                 171,    48,    54,    69,    178,    226),
    ("Los Andes",                 183,    44,    46,    93,    219,    323),
    ("Central Córdoba (SdE)",     158,    42,    43,    73,    162,    226),
    ("San Martín (M)",            108,    38,    30,    40,    149,    172),
    ("Chaco For Ever",            158,    33,    42,    83,    155,    282),
    ("Independiente Rivadavia",   115,    33,    37,    45,    125,    178),
    ("Almagro",                   108,    24,    31,    53,    145,    214),
    ("Barracas Central",           81,    20,    32,    29,     71,    100),
    ("Deportivo Armenio",          95,    16,    40,    39,     81,    132),
    ("Central Norte (S)",          92,    21,    21,    50,     87,    167),
    ("Gimnasia y Tiro",           104,    17,    30,    57,     81,    178),
    ("Cipolletti",                 79,    17,    21,    41,     91,    150),
    ("Desamparados",               63,    17,    18,    28,     94,    120),
    ("Central Córdoba (R)",        60,    19,    10,    31,     89,    131),
    ("Altos Hornos Zapla",         70,    14,    21,    35,     72,    118),
    ("Atlético Ledesma",           64,    15,    18,    31,     74,    105),
    ("Huracán (CR)",               70,    13,    24,    33,     83,    163),
    ("Kimberley",                  77,    14,    21,    42,     98,    167),
    ("Guaraní A. Franco",          50,    13,    13,    24,     57,     83),
    ("Loma Negra",                 26,    14,     9,     3,     38,     15),
    ("Juventud Antoniana",         77,    10,    18,    49,     90,    169),
    ("Atlético Concepción",        36,    11,     7,    18,     40,     54),
    ("Deportivo Roca",             30,    10,     8,    12,     30,     41),
    ("Deportivo Riestra",          27,     8,    11,     8,     26,     27),
    ("Unión Talleres-Lanús",       39,     8,    11,    20,     50,     81),
    ("San Telmo",                  47,     7,    11,    29,     54,    100),
    ("Renato Cesarini",            28,     7,     8,    13,     35,     47),
    ("Sportivo Italiano",          38,     6,    11,    21,     29,     59),
    ("Jorge Newbery",              34,     5,    12,    17,     23,     42),
    ("Tiro Federal",               38,     7,     6,    25,     37,     70),
    ("San Lorenzo (MdP)",          30,     6,     7,    17,     37,     63),
    ("Huracán (Tres Arroyos)",     42,     4,    12,    26,     38,     82),
    ("Juventud Alianza (SJ)",      22,     7,     1,    14,     28,     51),
    ("Los Andes (SJ)",             14,     6,     4,     4,     22,     19),
    ("Deportivo Morón",            22,     5,     3,    14,     16,     38),
    ("Huracán (IW)",               29,     4,     6,    19,     18,     82),
    ("San Martín (T)",             20,     4,     5,    11,     27,     47),
    ("Estudiantes (RC)",           18,     4,     4,    10,     25,     34),
    ("Sarmiento (R)",              14,     4,     4,     6,     18,     29),
    ("Sportivo Patria",            18,     4,     4,    10,     24,     37),
    ("Atlético Regina",            18,     3,     6,     9,     13,     30),
    ("Alianza Juventud-Pringles",    14,     3,     5,     6,     15,     21),
    ("Crucero del Norte",          30,     3,     5,    22,     21,     55),
    ("Alvarado",                   14,     3,     4,     7,     20,     28),
    ("Don Orione",                 14,     4,     0,    10,     16,     34),
    ("Unión San Vicente",          28,     1,     9,    18,     28,     66),
    ("Círculo Deportivo",          20,     2,     4,    14,     13,     35),
    ("Huracán Las Heras",           6,     2,     3,     1,      8,      8),
    ("Argentino (Firmat)",          6,     2,     1,     3,      5,     10),
    ("Huracán (SR)",               18,     1,     4,    13,     12,     48),
    ("Ramón Santamarina",           6,     2,     1,     3,      5,      6),
    ("Bartolomé Mitre",            29,     1,     3,    25,     21,     88),
    ("Puerto Comercial",           18,     2,     0,    16,     14,     75),
    ("Estudiantes (SdE)",          16,     1,     2,    13,     13,     41),
    ("Unión (GP)",                  6,     0,     5,     1,      6,      7),
    ("Argentino de Quilmes",       34,     0,     4,    30,     35,    148),
    ("Andino",                      6,     1,     0,     5,      3,     13),
    ("Gimnasia y Esgrima (CdU)",     2,     1,     0,     1,      3,      4),
    ("Independiente (Trelew)",     13,     0,     3,    10,     10,     46),
    ("Ferro Carril Oeste (GP)",     6,     0,     2,     4,      6,     12),
    ("Mariano Moreno",             16,     0,     2,    14,     11,     53),
    ("Atlético Uruguay",            6,     0,     1,     5,      2,     24),
    ("Atlético Santa Rosa",         6,     0,     0,     6,      4,     24),
]

DESDE = '1931'
HASTA = '2024'
TEMPORADAS = 94
