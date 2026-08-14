# 🎮 LoL Dashboard

Dashboard personalizado de estadísticas de League of Legends (estilo OP.GG pero a tu gusto).
Web estática + datos que se actualizan solos con GitHub Actions. Sin servidor propio.

## ¿Qué muestra?
- **Player selector** para cambiar entre vos y tu amigo.
- **Rank cards** de Solo/Duo y Flex con LP y winrate.
- **Gráfica de LP total** en el tiempo (Solo/Flex).
- **Gráfica de LP por partida** con selector de 10 / 20 / 30 partidas.
- **Historial** con campeón, KDA, KP, CS/min, oro/min, visión y daño por partida, filtrable por cola.

---

## 🚀 Puesta en marcha

### 1. Conseguir una API key de Riot
1. Entrá a **https://developer.riotgames.com** e iniciá sesión con tu cuenta de Riot.
2. **Para probar ya:** en el dashboard principal copiá la **"Development API Key"** (empieza con `RGAPI-...`).
   ⚠️ **Caduca cada 24 horas**, sirve solo para pruebas locales.
3. **Para el sitio hosteado (recomendado):** pedí una **"Personal API Key"** en
   *Register Product → Personal API Key*. Es gratis, **no caduca**, y es justo para
   proyectos personales como este. La aprobación puede tardar unos días.

### 2. Configurar tus jugadores
Editá [`data/players.json`](data/players.json) con tus Riot IDs reales:

```json
{
  "players": [
    { "id": "me",     "name": "Tu Nombre",  "riotId": "TuNombre#TAG",   "platform": "la2", "regional": "americas", "puuid": "" },
    { "id": "friend", "name": "Tu Amigo",   "riotId": "SuNombre#TAG",   "platform": "la2", "regional": "americas", "puuid": "" }
  ]
}
```

**Tabla de región** (poné `platform` y `regional` según dónde juegan):

| Servidor | platform | regional |
|----------|----------|----------|
| LAS (Cono Sur)     | `la2` | `americas` |
| LAN (Latam Norte)  | `la1` | `americas` |
| NA                 | `na1` | `americas` |
| BR                 | `br1` | `americas` |
| EUW                | `euw1`| `europe`   |
| EUNE               | `eun1`| `europe`   |
| KR                 | `kr`  | `asia`     |

> El `id` (`me`, `friend`) es interno y da nombre al archivo `data/<id>.json`. No lo cambies una vez creado.

### 3. Sembrar el historial de LP desde u.gg (ya hecho)
Los datos actuales salen de tus exports de u.gg (LP real por partida). Para regenerarlos:
```bash
python scripts/seed_ugg.py "ruta/lp_yo.json" "ruta/lp_amigo.json"
```
Esto crea `data/me.json` y `data/friend.json` con las timelines de LP (Solo/Flex),
el historial por partida (campeón, LP ±, rango) y el winrate. **No necesita API key.**

### 4. Enriquecer con la API (KDA, CS, oro, daño) y LP en vivo
Con una key **válida**, esto agrega las stats detalladas y sigue la timeline en la temporada actual,
**sin borrar** el seed de u.gg:
```bash
# Windows PowerShell
$env:RIOT_API_KEY = "RGAPI-tu-key-aca"
python scripts/fetch.py
```
```bash
# macOS / Linux
export RIOT_API_KEY=RGAPI-tu-key-aca
python scripts/fetch.py
```
Luego serví la carpeta y abrí el dashboard:
```bash
python -m http.server 8123
# abrir http://localhost:8123
```

> ¿Solo querés ver el diseño con datos inventados? Corré `python scripts/make_mock.py`.

---

## ☁️ Hosting en GitHub Pages (URL pública)

1. Creá un repo en GitHub y subí **el contenido de esta carpeta** como raíz del repo.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Nombre: `RIOT_API_KEY`
   - Valor: tu Personal API Key. *(Nunca va en el código; solo vive acá.)*
3. **Settings → Pages → Build and deployment → Source: "Deploy from a branch" → `main` / `(root)`**.
   Tu dashboard queda en `https://TU_USUARIO.github.io/TU_REPO/`.
4. El workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) corre **cada 30 min**,
   baja tus datos y hace commit. También podés dispararlo a mano en la pestaña **Actions → Actualizar datos → Run workflow**.

---

## 📈 Sobre las gráficas de LP
La API de Riot **no entrega historial de LP** (solo el actual), por eso el historial se **siembra desde u.gg**,
que sí guarda el LP real por partida. Las gráficas se dibujan por **índice de partida ranked** (no por fecha,
porque el export de u.gg no trae timestamps): el eje X es "partida #1, #2, …" y el Y es el LP absoluto.

- **Victoria/derrota** de cada partida sale de la **API de Riot** (dato autoritativo), no de u.gg.
- **LP por partida en el historial:** Riot no expone el LP por partida, así que se **estima ±20**
  (+20 victoria / −20 derrota). En cuanto `fetch.py` corre seguido (cron) y captura un snapshot
  de LP antes y después de una partida, se reemplaza por el **LP real** (`snapshot posterior − anterior`,
  cuando hubo una sola ranked de esa cola entre ambos snapshots). Esas filas se marcan `lpReal`.
- Al correr `fetch.py`, cada actualización **agrega** el LP actual al final de la timeline (temporada en curso).

**LP absoluto** (el `score` de u.gg) = índice de tier × 400 + división × 100 + LP.
Ej: Oro II con 67 LP → Oro es índice 3 → `3*400 + 2*100 + 67 = 1467`.
(Divisiones: IV=0, III=1, II=2, I=3; Esmeralda va entre Platino y Diamante).

---

## 🗂️ Estructura
```
index.html                 # dashboard
assets/style.css           # estilos
assets/app.js              # lógica + gráficas (Chart.js por CDN)
data/players.json          # config (tus Riot IDs) + meta
data/<id>.json             # datos por jugador (los genera fetch.py)
data/meta.json             # versión de Data Dragon + timestamp
scripts/seed_ugg.py        # convierte los exports de u.gg en data/<id>.json
scripts/fetch.py           # enriquece con la API de Riot (KDA/CS/oro/daño) + LP en vivo
scripts/make_mock.py       # datos de ejemplo para ver el diseño
.github/workflows/update.yml  # cron de actualización
```

## ⚖️ Límites de rate
Con key de desarrollador/personal: ~20 req/s y 100 req/2 min. El script solo baja
partidas nuevas (las ya guardadas se saltean), así que tras la primera corrida es muy liviano.

---
*Este producto no está avalado por Riot Games. LoL es marca de Riot Games, Inc.*
