# HAYVAR — Liga Profesional Argentina

Resultados reales del Torneo Clausura 2026, con actualización en vivo.

## Cómo se usa

En una terminal, parado en esta carpeta:

```bash
python3 server.py
```

Y entrar a **http://localhost:8010**. Para cortar, `Ctrl+C`.

No hay que instalar nada: el servidor usa sólo la biblioteca estándar de Python 3.
Si el puerto 8010 está ocupado, `python3 server.py 9000`.

## Qué hay adentro

| Archivo | Qué hace |
|---|---|
| `server.py` | Proxy a 365scores + armado de tablas. Sirve la página. |
| `index.html` | La interfaz. No funciona sola: necesita el servidor. |

## La base de datos

`hayvar.db` (SQLite, se crea sola). Guarda todo lo que se trae de las fuentes.
Tres motivos:

- **Menos pedidos.** Se trae una vez y se sirve mil veces. Con el plan gratis
  de API-Football, 100 pedidos por día, es la única forma de que ande.
- **No se pierde nada.** 365scores sólo publica una ventana de fechas y las
  viejas desaparecen. Lo que entra a la base se queda.
- **Aguanta si la fuente se cae.** Muestra lo último bueno con la antigüedad
  a la vista, en lugar de una pantalla vacía.

Se puede mover con la variable `HAYVAR_DB`. Si el disco no soporta SQLite
(pasa en algunos discos de red), cae a memoria sola y avisa en `/api/base`.

## Nombres de equipos

Cada fuente los escribe distinto y no siempre abrevia la misma: AFA pone
"Chaco FE" donde 365scores pone "Chaco For Ever", y a veces es al revés. El
emparejado va por capas: nombre exacto, después tokens con abreviaturas
expandidas, y como último recurso una palabra que aparezca en un solo equipo
("brown", "chicago", "tiro"). Para mostrar se elige siempre la versión menos
abreviada de las dos.

## Diagnóstico

`/api/diagnostico` revisa la clave, el plan contratado, el estado de la base y
si las fuentes responden. La clave nunca aparece en la respuesta, sólo si
funciona. Es lo primero que conviene abrir cuando algo no anda.

## La clave de API-Football

El servidor la busca en la variable de entorno `APIFOOTBALL_KEY` y, si no está,
en un archivo `clave.txt` al lado de `server.py`. Nunca va escrita en el código.

En tu máquina: creá `clave.txt` con la clave adentro y nada más. Está en el
`.gitignore`, así que no se sube a GitHub.

En Render: panel del servicio → **Environment** → **Add Environment Variable**,
nombre `APIFOOTBALL_KEY` y pegás el valor ahí.

## Escudos

No se enlazan del CDN de 365scores: pasan por `/img/…` de este mismo servidor,
que los baja una vez y los guarda en memoria. Así no se consume ancho de banda
ajeno y no dependemos de que nos dejen enlazar desde afuera.

## Publicar en internet

Ver **HAYVAR-guia-publicacion.pdf**: dominio en NIC Argentina y deploy en Render,
paso a paso. El repo ya trae `render.yaml`, así que Render se configura solo.

El servidor detecta dónde está corriendo: si existe la variable `PORT` escucha en
`0.0.0.0` (hosting); si no, sólo en `127.0.0.1` (tu máquina).

## Ligas

A la izquierda hay un menú de ligas. Andan dos:

- **Liga Profesional** — todo: fixture, zonas, anual, promedios con riesgo de
  descenso, goleadores y datos en vivo.
- **Primera Nacional** — las dos zonas con escudos y datos en vivo (365scores,
  competencia 419), tabla general, goleadores y fixture de AFA.

  Un detalle: la página de descenso de AFA para esta categoría está casi toda
  en cero (sólo carga la columna de la temporada en curso), así que la tabla
  general se arma sumando las dos zonas. Da lo mismo y siempre está al día.

El resto figura apagado con un cartelito "pronto". Para sumar una liga nueva
alcanza con agregarla al diccionario `LIGAS` de `server.py` (host y nombres de
página) y a la lista `LIGAS` de `index.html`.
| `ABRIR.command` | Doble clic: levanta el server y abre Brave. |

## De dónde salen los datos

Dos fuentes, cada una en lo que es mejor:

| | Fuente |
|---|---|
| Partidos, minuto a minuto, detalle | **365scores** (rápido) |
| Posiciones, acumulada, promedios, goleadores | **AFA / DataFactory** (oficial) |

DataFactory es el proveedor que usa la web de la Liga Profesional. Sirve las
tablas como HTML estático, así que el servidor las lee y las parsea. De ahí
salen las dos zonas por separado, la acumulada y —lo más importante— la tabla
de promedios ya calculada por AFA. Antes esos promedios se estimaban con una
base cargada a mano; ahora son el dato oficial.

**Las tablas se mueven en vivo.** Sobre la tabla oficial se suman los goles de
los partidos que están en juego, así que un equipo ganando 2-0 ya aparece con
esos 3 puntos y en la posición que le corresponde. Se marca con un puntito
verde. Con `?live=0` se ve la tabla oficial sin tocar.

## Detalles técnicos

Todo viene de la API pública de **365scores** (competencia 72). El servidor
local existe por dos motivos: el navegador bloquea por CORS las llamadas
directas desde un archivo abierto con `file://`, y además hace falta un lugar
donde armar las tablas.

**Por qué no alcanzaba con 365scores:** su endpoint de posiciones devuelve sólo
el Grupo A del Clausura. Por eso las tablas ahora salen de AFA. Si DataFactory
no responde, el servidor cae a calcularlas partido por partido desde 365scores
y lo avisa en la barra superior.

**Por qué el fixture sale de AFA:** 365scores ignora los parámetros de fecha.
Le pidas el rango que le pidas, devuelve siempre la misma ventana de unos 45
partidos (las fechas 4, 5 y 6) — por eso faltaban las primeras y las tablas
daban cualquier cosa. El fixture oficial de AFA trae las 16 fechas completas,
240 partidos, con árbitro y horario. 365scores queda para lo que hace bien: el
minuto a minuto, los escudos y el detalle del partido.

**El interzonal.** Cada fecha son 15 partidos: 7 de la Zona A, 7 de la Zona B y
uno cruzado entre los dos equipos que de otro modo quedarían libres. Va siempre
al final, en su propia sección.

## Cupos a copas

La Anual reparte 9 cupos: 1° a 3° a Libertadores, 4° a 9° a Sudamericana. Los
otros tres boletos a Libertadores son de los campeones del Apertura, del
Clausura y de la Copa Argentina. Belgrano ya está adentro por el Apertura, así
que libera su lugar y corre a todos una posición. Está configurado en
`YA_CLASIFICADOS`, arriba de `server.py`: cuando se definan el Clausura y la
Copa Argentina, se agregan ahí.

## Portada

Al entrar se abre la portada: los partidos del día de todas las ligas, con una
tira de calendario para moverse. A la derecha, el resumen del día, el partido
con más goles y lo que viene. Las tablas aparecen al entrar a un torneo.

## Modo club

El botón ◑ del encabezado deja elegir cualquiera de los 30 clubes de Primera y
la página toma sus colores. Queda guardado entre sesiones. Los colores están en
`COLORES`, en `server.py`.

## Mobile

Anda en el teléfono: el menú de ligas pasa a ser un cajón lateral, las tablas
scrollean solas y el detalle del partido se abre a pantalla completa.

## Un límite conocido

365scores sólo guarda el minuto a minuto de las fechas recientes. Para las
fechas viejas del Clausura (1, 2, 3) el resultado, el árbitro y el estadio
están —salen de AFA— pero no hay estadísticas ni formaciones. Está avisado en
la propia ventana del partido.

## Riesgo de descenso

Descienden dos: el último de la tabla de promedios y el último de la anual.
Para el de promedios, en vez de pintar una "zona de riesgo" fija, se calcula. Para cada equipo se
saca el mejor promedio posible (gana todo lo que le queda) y el peor (pierde
todo). Un equipo sigue en amarillo mientras su peor promedio pueda ser
alcanzado por el mejor promedio del que hoy desciende. Cuando ya no puede,
se apaga solo.

Como control, `/api/standings` compara el Grupo A calculado contra el que
publica 365scores y avisa en la barra superior si algo no cierra.

## Promedios

Salen tal cual los publica AFA: puntos de 2024, 2025 y 2026 sobre partidos
jugados. No se estima nada.

`BASE_PROMEDIOS` sigue en `server.py` pero ya sólo se usa para saber qué 30
clubes existen y para el modo de emergencia si AFA no responde.

## Actualización en vivo

La página se refresca sola: cada **15 segundos** si hay partidos en juego, cada
60 si no. Cuando cambia un marcador la fila hace un flash verde, el minuto va
corriendo y las tablas se reordenan solas. Al volver a la pestaña, refresca al
instante.

## Endpoints

| Ruta | Devuelve |
|---|---|
| `/api/rounds` | Fechas del torneo y cuál se está jugando |
| `/api/games?round=5` | Partidos (también acepta `?date=2026-08-14`) |
| `/api/standings` | Zona A y Zona B (oficial + vivo) |
| `/api/annual` | Acumulada 2026 oficial |
| `/api/promedios` | Promedios oficiales de AFA |
| `/api/scorers` | Goleadores, con desglose por tipo de gol |
| `/api/match?id=…` | Detalle: goles, tarjetas, estadísticas, formaciones |
| `/api/player?name=…` | Ficha del goleador + link a Transfermarkt |
| `/api/ligas` | Ligas configuradas |
| `/api/liga?id=nacional` | Tablas de otra liga |
| `/api/liga/games?id=nacional` | Fixture de otra liga |
| `/api/raw?path=games/results` | Respuesta cruda de 365scores, para explorar |

## Notas

- 365scores es una API no documentada: si algún día cambian un campo, el
  servidor lo va a acusar. `/api/raw` sirve para ver qué está llegando.
- Hay caché de 15–25 segundos sobre cada llamada para no golpear el servicio
  de más.
- El server escucha sólo en `127.0.0.1`: no queda expuesto en la red.
