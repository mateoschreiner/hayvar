# -*- coding: utf-8 -*-
"""
Las fichas de los veinte clubes de LaLiga.

Los nombres de los estadios van sin marca
─────────────────────────────────────────
Es la misma regla que el resto del sitio: nada de patrocinadores. Así que
acá dice Camp Nou y no Spotify Camp Nou, Metropolitano y no Riyadh Air
Metropolitano, Balaídos y no Abanca-Balaídos. El nombre comercial queda
en `estadioOficial` para el que lo quiera, pero no es lo que se muestra.

Un caso que no es marca y parece: el Estadi Ciutat de València es el
nombre oficial en valenciano, no un patrocinio. Va tal cual.

Lo que quedó vacío está vacío a propósito
─────────────────────────────────────────
Cinco clubes no tienen un clásico que las fuentes reconozcan como
principal —Alavés y Rayo directamente no tienen, el del Racing está
discutido— y ahí el campo va vacío en vez de inventado. Poner "Athletic
Club" en el Alavés porque los dos son vascos sería escribir un dato que
nadie sostiene.

Otros cinco lo tienen contra un club que hoy no juega Primera. Ésos van
igual, con el nombre del rival: el clásico del Getafe es con el Leganés
aunque el Leganés esté en Segunda, y esconderlo no lo haría más cierto.

La capacidad es el campo más blando
───────────────────────────────────
Es el que más discrepa entre fuentes: la web del club, la ficha del
estadio y la tabla de la liga suelen dar tres números distintos, y las
reformas los mueven todos los años. Donde no hubo acuerdo quedó anotado
en `notaCapacidad` en vez de elegir en silencio. Y donde no hay ningún
número que describa el estadio de hoy —el Camp Nou, que se está
construyendo mientras se juega— quedó vacío.

Fuentes: Wikipedia en español e inglés, Wikidata, laliga.com y las webs
oficiales de los clubes. Agosto de 2026.
"""

CLUBES = {
    "Alavés": {
        "nombre": "Deportivo Alavés, S.A.D.",
        "apodo": "Babazorros",
        "fundado": 1921,
        "estadio": "Estadio de Mendizorroza",
        "estadioApodo": "Mendi",
        "capacidad": 19840,
        "direccion": "Paseo de Cervantes, s/n, Vitoria-Gasteiz",
        "ciudad": "Vitoria-Gasteiz, País Vasco",
        "division": "LaLiga",
        "sitio": "https://www.deportivoalaves.com",
        # Sin clásico. El derbi vasco es Athletic contra la Real y el
        # Alavés no aparece ni mencionado en ninguna fuente.
        "clasico": "",
    },
    "Athletic Club": {
        "nombre": "Athletic Club",
        "apodo": "Los Leones",
        "fundado": 1898,
        "estadio": "San Mamés",
        "estadioApodo": "La Catedral",
        "capacidad": 53289,
        "direccion": "Rafael Moreno Pitxitxi, s/n, Bilbao",
        "ciudad": "Bilbao, País Vasco",
        "division": "LaLiga",
        "sitio": "https://www.athletic-club.eus",
        "clasico": "Real Sociedad",
        "clasicoNombre": "Derbi vasco",
        # El nombre legal es "Athletic Club" a secas, sin "de Bilbao".
    },
    "Atlético de Madrid": {
        "nombre": "Club Atlético de Madrid, S.A.D.",
        "apodo": "Colchoneros",
        "fundado": 1903,
        "estadio": "Estadio Metropolitano",
        "estadioOficial": "Estadio Riyadh Air Metropolitano",
        "capacidad": 70692,
        "direccion": "Avenida de Luis Aragonés 4, Madrid",
        "ciudad": "Madrid, Comunidad de Madrid",
        "division": "LaLiga",
        "sitio": "https://www.atleticodemadrid.com",
        "clasico": "Real Madrid",
        "clasicoNombre": "Derbi madrileño",
    },
    "Celta de Vigo": {
        "nombre": "Real Club Celta de Vigo, S.A.D.",
        "apodo": "Celtiñas",
        "fundado": 1923,
        "estadio": "Balaídos",
        "estadioOficial": "Estadio Abanca-Balaídos",
        "capacidad": 24870,
        "direccion": "Avenida de Balaídos 13, Vigo",
        "ciudad": "Vigo, Galicia",
        "division": "LaLiga",
        "sitio": "https://www.celta.gal",
        "clasico": "RC Deportivo",
        "clasicoNombre": "Derbi gallego",
    },
    "Elche CF": {
        "nombre": "Elche Club de Fútbol, S.A.D.",
        "apodo": "Franjiverdes",
        "fundado": 1922,
        "estadio": "Estadio Manuel Martínez Valero",
        "capacidad": 31388,
        "notaCapacidad": "Las tablas de la liga publican 33.732.",
        "direccion": "Avenida Manuel Martínez Valero 3, Elche",
        "ciudad": "Elche, Comunidad Valenciana",
        "division": "LaLiga",
        "sitio": "https://www.elchecf.es",
        # El rival del clásico no está en Primera, y va igual.
        "clasico": "Hércules CF",
        "clasicoNombre": "Derbi de la provincia de Alicante",
    },
    "FC Barcelona": {
        "nombre": "Fútbol Club Barcelona",
        "apodo": "Barça",
        "fundado": 1899,
        "estadio": "Camp Nou",
        "estadioOficial": "Spotify Camp Nou",
        # Vacío a propósito: el estadio se está construyendo mientras se
        # juega. La web del club publica 99.354, que describe el estadio
        # anterior; las tablas publican 105.000, que es el proyecto
        # terminado. El primer partido de esta Liga tuvo 59.326 personas.
        # Ninguno de los tres números dice cuánta gente entra hoy.
        "capacidad": None,
        "notaCapacidad": "En obra. Se publican 99.354 (aforo anterior) y "
                         "105.000 (proyecto), pero la tercera grada se "
                         "construye durante esta temporada.",
        "direccion": "Carrer d'Arístides Maillol 12, Barcelona",
        "ciudad": "Barcelona, Cataluña",
        "division": "LaLiga",
        "sitio": "https://www.fcbarcelona.com",
        "clasico": "Real Madrid",
        "clasicoNombre": "El Clásico",
    },
    "Getafe CF": {
        "nombre": "Getafe Club de Fútbol, S.A.D.",
        "apodo": "Azulones",
        "fundado": 1983,
        "estadio": "Coliseum",
        "capacidad": 16500,
        "notaCapacidad": "Aforo nominal. Hay gradas cerradas por reforma y "
                         "el aforo habilitado es bastante menor.",
        "direccion": "Avenida Teresa de Calcuta, s/n, Getafe",
        "ciudad": "Getafe, Comunidad de Madrid",
        "division": "LaLiga",
        "sitio": "https://www.getafecf.com",
        "clasico": "CD Leganés",
        "clasicoNombre": "Derbi del sur de Madrid",
    },
    "Levante UD": {
        "nombre": "Levante Unión Deportiva, S.A.D.",
        "apodo": "Granotas",
        "fundado": 1909,
        "estadio": "Estadi Ciutat de València",
        "estadioApodo": "El Ciutat",
        "capacidad": 26354,
        "direccion": "Calle San Vicente de Paúl 44, Valencia",
        "ciudad": "Valencia, Comunidad Valenciana",
        "division": "LaLiga",
        "sitio": "https://www.levanteud.com",
        "clasico": "Valencia CF",
        "clasicoNombre": "Derbi valenciano",
    },
    "Málaga CF": {
        "nombre": "Málaga Club de Fútbol, S.A.D.",
        "apodo": "Boquerones",
        # 1948 es la fundación del Club Atlético Malagueño, la línea que
        # el club reivindica como propia y que siguen las dos Wikipedias.
        # LaLiga publica 1994, que es cuando se constituyó la sociedad
        # actual tras desaparecer el CD Málaga. Es una discusión de
        # continuidad institucional, no un error de nadie.
        "fundado": 1948,
        "notaFundado": "LaLiga publica 1994, cuando se constituyó la "
                       "sociedad actual. 1948 es la línea histórica que "
                       "el club reivindica.",
        "estadio": "La Rosaleda",
        "capacidad": 30044,
        "notaCapacidad": "Wikipedia en español publica 30.778.",
        "direccion": "Paseo de Martiricos, s/n, Málaga",
        "ciudad": "Málaga, Andalucía",
        "division": "LaLiga",
        "sitio": "https://www.malagacf.com",
        "clasico": "Sevilla FC",
        # El histórico era con el Granada, dado por extinto.
    },
    "Osasuna": {
        "nombre": "Club Atlético Osasuna",
        "apodo": "Rojillos",
        # 1920 según la propia web del club. Wikipedia en español pone
        # 1919 y ella misma lo marca como "oficiosa".
        "fundado": 1920,
        "estadio": "El Sadar",
        "estadioApodo": "El Muro Rojo",
        "capacidad": 23576,
        "ciudad": "Pamplona, Navarra",
        "division": "LaLiga",
        "sitio": "https://www.osasuna.es",
        "clasico": "Real Zaragoza",
        "clasicoNombre": "Derbi navarro-aragonés",
    },
    "Racing de Santander": {
        "nombre": "Real Racing Club de Santander, S.A.D.",
        "apodo": "Racinguistas",
        "fundado": 1913,
        "estadio": "El Sardinero",
        "capacidad": 22514,
        "direccion": "Calle Real Racing Club, s/n, Santander",
        "ciudad": "Santander, Cantabria",
        "division": "LaLiga",
        "sitio": "https://www.realracingclub.es",
        # Discutido: es el único club plenamente profesional de Cantabria
        # y las fuentes no coinciden. Al Oviedo lo llaman rivalidad menor
        # y hay quien pone al Athletic por cercanía. Mejor vacío.
        "clasico": "",
    },
    "Rayo Vallecano": {
        "nombre": "Rayo Vallecano de Madrid, S.A.D.",
        "apodo": "Franjirrojos",
        "fundado": 1924,
        "estadio": "Estadio de Vallecas",
        "capacidad": 14708,
        "direccion": "Avenida de la Albufera 114, Madrid",
        "ciudad": "Madrid, Comunidad de Madrid",
        "division": "LaLiga",
        "sitio": "https://www.rayovallecano.es",
        # Sin clásico consolidado: lo único documentado es una rivalidad
        # reciente con el Getafe por el tercer puesto madrileño.
        "clasico": "",
    },
    "RC Deportivo": {
        # Ojo con el nombre: hoy es "de A Coruña", no "de La Coruña".
        "nombre": "Real Club Deportivo de A Coruña, S.A.D.",
        "apodo": "Dépor",
        "fundado": 1906,
        "estadio": "Riazor",
        "estadioOficial": "Estadio Abanca-Riazor",
        "capacidad": 32490,
        "direccion": "Calle Manuel Murguía, s/n, A Coruña",
        "ciudad": "A Coruña, Galicia",
        "division": "LaLiga",
        "sitio": "https://www.rcdeportivo.es",
        "clasico": "Celta de Vigo",
        "clasicoNombre": "Derbi gallego",
    },
    "RCD Espanyol": {
        "nombre": "Real Club Deportivo Espanyol de Barcelona, S.A.D.",
        "apodo": "Pericos",
        "fundado": 1900,
        "estadio": "RCDE Stadium",
        "estadioApodo": "Cornellà-El Prat",
        "capacidad": 37776,
        "notaCapacidad": "Las fuentes dan entre 37.776 y 40.500 y ninguna "
                         "es oficial.",
        "direccion": "Avenida del Baix Llobregat 100, Cornellà de Llobregat",
        "ciudad": "Cornellà de Llobregat, Cataluña",
        "division": "LaLiga",
        "sitio": "https://www.rcdespanyol.com",
        "clasico": "FC Barcelona",
        "clasicoNombre": "Derbi barcelonés",
    },
    "Real Betis": {
        "nombre": "Real Betis Balompié, S.A.D.",
        "apodo": "Béticos",
        "fundado": 1907,
        # Su estadio es el Villamarín. Está cerrado por obra desde 2025 y
        # esta temporada juega en La Cartuja, pero la ficha describe al
        # club y no a la temporada: en 2027 vuelve y no hay que tocar
        # nada.
        "estadio": "Estadio Benito Villamarín",
        "capacidad": 60721,
        "notaCapacidad": "Cerrado por obras desde 2025. Esta temporada "
                         "juega en La Cartuja.",
        "direccion": "Avenida de Heliópolis, s/n, Sevilla",
        "ciudad": "Sevilla, Andalucía",
        "division": "LaLiga",
        "sitio": "https://www.realbetisbalompie.es",
        "clasico": "Sevilla FC",
        "clasicoNombre": "Derbi sevillano",
    },
    "Real Madrid": {
        "nombre": "Real Madrid Club de Fútbol",
        "apodo": "Merengues",
        "fundado": 1902,
        "estadio": "Estadio Santiago Bernabéu",
        "estadioApodo": "La Casa Blanca",
        "capacidad": 83186,
        "direccion": "Avenida de Concha Espina 1, Madrid",
        "ciudad": "Madrid, Comunidad de Madrid",
        "division": "LaLiga",
        "sitio": "https://www.realmadrid.com",
        "clasico": "FC Barcelona",
        "clasicoNombre": "El Clásico",
    },
    "Real Sociedad": {
        "nombre": "Real Sociedad de Fútbol, S.A.D.",
        "apodo": "Txuri-urdin",
        "fundado": 1909,
        # El patrocinio del estadio venció y volvió a llamarse Anoeta, así
        # que acá el oficial y el tradicional coinciden.
        "estadio": "Anoeta",
        "capacidad": 39313,
        "notaCapacidad": "El club y Wikidata publican 40.000.",
        "direccion": "Anoeta Pasealekua 1, San Sebastián",
        "ciudad": "San Sebastián, País Vasco",
        "division": "LaLiga",
        "sitio": "https://www.realsociedad.eus",
        "clasico": "Athletic Club",
        "clasicoNombre": "Derbi vasco",
    },
    "Sevilla FC": {
        "nombre": "Sevilla Fútbol Club, S.A.D.",
        "apodo": "Sevillistas",
        "fundado": 1890,
        "estadio": "Estadio Ramón Sánchez-Pizjuán",
        "capacidad": 43883,
        "direccion": "Calle Sevilla Fútbol Club, s/n, Sevilla",
        "ciudad": "Sevilla, Andalucía",
        "division": "LaLiga",
        "sitio": "https://www.sevillafc.es",
        "clasico": "Real Betis",
        "clasicoNombre": "Derbi sevillano",
    },
    "Valencia CF": {
        "nombre": "Valencia Club de Fútbol, S.A.D.",
        "apodo": "Chés",
        "fundado": 1919,
        "estadio": "Mestalla",
        "estadioApodo": "El Coliseo Blanquinegro",
        "capacidad": 49430,
        "direccion": "Avenida de Suecia, s/n, Valencia",
        "ciudad": "Valencia, Comunidad Valenciana",
        "division": "LaLiga",
        "sitio": "https://www.valenciacf.com",
        "clasico": "Levante UD",
        "clasicoNombre": "Derbi valenciano",
    },
    "Villarreal CF": {
        "nombre": "Villarreal Club de Fútbol, S.A.D.",
        "apodo": "Submarino Amarillo",
        # 1923 según la web del club, Wikipedia en inglés y LaLiga.
        # Wikipedia en español pone 1942 y queda sola.
        "fundado": 1923,
        "estadio": "Estadio de la Cerámica",
        "estadioApodo": "El Madrigal",
        "capacidad": 23500,
        "direccion": "Calle Blasco Ibáñez 2, Vila-real",
        "ciudad": "Vila-real, Comunidad Valenciana",
        "division": "LaLiga",
        "sitio": "https://www.villarrealcf.es",
        "clasico": "Valencia CF",
        "clasicoNombre": "Derbi de la Comunitat",
    },
}
