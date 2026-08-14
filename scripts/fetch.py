"""Enriquece los datos sembrados desde u.gg con la API de Riot.

Requiere la variable de entorno RIOT_API_KEY (una key VÁLIDA de Riot).

Qué hace, sin destruir el seed de u.gg:
  1. Resuelve el PUUID de cada jugador y su rango actual (league-v4).
  2. Agrega un "snapshot" del LP actual al final de lpHistory  → la timeline
     sigue creciendo con la temporada en curso.
  3. Baja las partidas recientes (match-v5) y las inserta/actualiza en el
     historial con KDA, CS, oro, daño, visión, etc.
  4. Best-effort: intenta enriquecer partidas ya existentes por matchId
     (las viejas de u.gg pueden dar 404 por retención; se saltean sin romper).

Uso local (Windows PowerShell):
    $env:RIOT_API_KEY = "RGAPI-...."
    python scripts/fetch.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
API_KEY = os.environ.get("RIOT_API_KEY", "").strip()

# Riot está detrás de Cloudflare, que bloquea el User-Agent por defecto de urllib
# (devuelve "error code: 1010"). Hay que mandar un UA de navegador.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

QUEUE_MAP = {420: "SOLO", 440: "FLEX"}
NORMAL_QUEUES = {400: "NORMAL", 430: "NORMAL", 490: "NORMAL", 450: "ARAM", 700: "CLASH"}
MATCH_COUNT = 45
SNAPSHOT_MIN_GAP_H = 6

TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND",
         "MASTER", "GRANDMASTER", "CHALLENGER"]
DIVS = {"IV": 0, "III": 1, "II": 2, "I": 3}
TIER_NAME = {
    "IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro",
    "PLATINUM": "Platino", "EMERALD": "Esmeralda", "DIAMOND": "Diamante",
    "MASTER": "Maestro", "GRANDMASTER": "Gran Maestro", "CHALLENGER": "Retador",
}


def absolute_lp(tier, division, lp):
    if not tier:
        return None
    ti = TIERS.index(tier)
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        return TIERS.index("DIAMOND") * 400 + 400 + lp
    return ti * 400 + DIVS.get(division, 0) * 100 + lp


def rank_label(tier, rank, lp):
    apex = tier in ("MASTER", "GRANDMASTER", "CHALLENGER")
    return f'{TIER_NAME.get(tier, tier)}{"" if apex else " " + rank} {lp} LP'


# ---------------- HTTP ----------------
def api_get(url):
    for attempt in range(6):
        req = urllib.request.Request(url, headers={
            "X-Riot-Token": API_KEY, "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry = int(e.headers.get("Retry-After", "2"))
                print(f"  429 rate limit, esperando {retry}s...")
                time.sleep(retry + 1)
                continue
            if e.code in (404,):
                return None
            if e.code in (500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            if e.code in (401, 403):
                raise RuntimeError(f"HTTP {e.code}: API key inválida o sin permisos. {e.read().decode()[:200]}")
            raise RuntimeError(f"HTTP {e.code} en {url}: {e.read().decode()[:200]}")
        except urllib.error.URLError:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Fallaron los reintentos para {url}")


def get_ddragon_version():
    try:
        vs = json.loads(urllib.request.urlopen(
            "https://ddragon.leagueoflegends.com/api/versions.json", timeout=15).read())
        return vs[0]
    except Exception:
        return "16.16.1"


# ---------------- endpoints ----------------
def resolve_puuid(regional, riot_id):
    name, tag = riot_id.split("#", 1)
    url = (f"https://{regional}.api.riotgames.com/riot/account/v1/accounts/"
           f"by-riot-id/{urllib.parse.quote(name)}/{urllib.parse.quote(tag)}")
    acc = api_get(url)
    return acc["puuid"] if acc else None


def get_ranks(platform, puuid):
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    entries = api_get(url) or []
    out = {}
    for e in entries:
        q = e.get("queueType")
        key = "solo" if q == "RANKED_SOLO_5x5" else "flex" if q == "RANKED_FLEX_SR" else None
        if not key:
            continue
        out[key] = {
            "tier": e.get("tier"), "rank": e.get("rank"), "lp": e.get("leaguePoints", 0),
            "wins": e.get("wins", 0), "losses": e.get("losses", 0),
            "absoluteLp": absolute_lp(e.get("tier"), e.get("rank"), e.get("leaguePoints", 0)),
        }
    return out


def get_match_ids(regional, puuid, count):
    url = (f"https://{regional}.api.riotgames.com/lol/match/v5/matches/"
           f"by-puuid/{puuid}/ids?start=0&count={count}")
    return api_get(url) or []


def get_match(regional, match_id):
    return api_get(f"https://{regional}.api.riotgames.com/lol/match/v5/matches/{match_id}")


def parse_match(match, puuid, champ_by_id):
    info = match.get("info", {})
    qid = info.get("queueId")
    queue = QUEUE_MAP.get(qid) or NORMAL_QUEUES.get(qid) or "OTHER"
    me = next((p for p in info.get("participants", []) if p.get("puuid") == puuid), None)
    if not me:
        return None
    dur = info.get("gameDuration", 0)
    minutes = max(1, dur) / 60.0
    cs = me.get("totalMinionsKilled", 0) + me.get("neutralMinionsKilled", 0)
    gold = me.get("goldEarned", 0)
    dmg = me.get("totalDamageDealtToChampions", 0)
    k, d, a = me.get("kills", 0), me.get("deaths", 0), me.get("assists", 0)
    kp = me.get("challenges", {}).get("killParticipation")
    return {
        "matchId": int(match.get("metadata", {}).get("matchId", "0").split("_")[-1]),
        "queue": queue,
        "champion": me.get("championName"),
        "championId": me.get("championId"),
        "win": bool(me.get("win")),
        "lpChange": None, "lpAfter": None, "tier": None, "rank": None, "rankLabel": None,
        "kills": k, "deaths": d, "assists": a,
        "kda": round((k + a) / max(1, d), 2),
        "cs": cs, "csPerMin": round(cs / minutes, 1),
        "gold": gold, "goldPerMin": round(gold / minutes),
        "damage": dmg, "damagePerMin": round(dmg / minutes),
        "visionScore": me.get("visionScore", 0),
        "killParticipation": round(kp * 100) if kp is not None else None,
        "duration": dur,
        "position": me.get("teamPosition") or me.get("individualPosition") or "",
        "timestamp": info.get("gameStartTimestamp") or info.get("gameCreation", 0),
    }


# ---------------- snapshots ----------------
def append_snapshot(hist_list, ranks_entry, queue):
    """Agrega un punto de LP actual al historial (mismo formato que el seed de u.gg)."""
    if not ranks_entry or ranks_entry.get("absoluteLp") is None:
        return
    abs_lp = ranks_entry["absoluteLp"]
    now_ms = int(time.time() * 1000)
    if hist_list:
        last = hist_list[-1]
        if last["lp"] == abs_lp:
            return  # sin cambio de LP: no agregamos un punto nuevo
        delta = abs_lp - last["lp"]
    else:
        delta = None
    hist_list.append({
        "i": len(hist_list), "lp": abs_lp,
        "tier": ranks_entry["tier"], "rank": ranks_entry["rank"], "lpInDiv": ranks_entry["lp"],
        "champion": None, "championId": None, "matchId": None,
        "delta": delta, "win": (None if delta in (None, 0) else delta > 0),
        "queue": queue, "t": now_ms, "live": True,
    })


def assign_real_lp(matches, lp_history):
    """LP real por partida = snapshot posterior - snapshot anterior.
    Solo se asigna cuando entre dos snapshots (con timestamp) ocurrió UNA sola
    partida de esa cola; si no, se deja el estimado ±20 del frontend.
    Requiere que fetch.py corra seguido (cron) para tener snapshots alrededor de cada game.
    """
    for queue, key in (("SOLO", "solo"), ("FLEX", "flex")):
        snaps = sorted([s for s in lp_history.get(key, []) if s.get("t")], key=lambda s: s["t"])
        qm = sorted([m for m in matches if m["queue"] == queue and m.get("timestamp")],
                    key=lambda m: m["timestamp"])
        for a, b in zip(snaps, snaps[1:]):
            between = [m for m in qm if a["t"] < (m["timestamp"] + (m.get("duration") or 0) * 1000) <= b["t"]]
            if len(between) == 1:
                m = between[0]
                m["lpChange"] = b["lp"] - a["lp"]
                m["lpReal"] = True


# ---------------- main ----------------
def load_existing(pid):
    path = os.path.join(DATA, f"{pid}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"player": {}, "rank": {}, "lpHistory": {"solo": [], "flex": []}, "matches": []}


def main():
    if not API_KEY:
        print("ERROR: falta RIOT_API_KEY en el entorno.")
        sys.exit(1)

    with open(os.path.join(DATA, "players.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    version = get_ddragon_version()

    for p in cfg["players"]:
        pid = p["id"]
        print(f"-> {p.get('name', pid)} ({p['riotId']})")
        try:
            data = load_existing(pid)
            lp_history = data.get("lpHistory") or {"solo": [], "flex": []}
            lp_history.setdefault("solo", []); lp_history.setdefault("flex", [])

            puuid = p.get("puuid") or resolve_puuid(p["regional"], p["riotId"])
            if not puuid:
                print("   PUUID no encontrado, salteando."); continue
            p["puuid"] = puuid

            ranks = get_ranks(p["platform"], puuid)
            append_snapshot(lp_history["solo"], ranks.get("solo"), "SOLO")
            append_snapshot(lp_history["flex"], ranks.get("flex"), "FLEX")

            # partidas recientes → enriquecer/insertar
            by_id = {m["matchId"]: m for m in data.get("matches", [])}
            ids = get_match_ids(p["regional"], puuid, MATCH_COUNT)
            new_n = 0
            for mid in ids:
                md = get_match(p["regional"], mid)
                time.sleep(0.6)
                if not md:
                    continue
                parsed = parse_match(md, puuid, None)
                if not parsed:
                    continue
                num = parsed["matchId"]
                if num in by_id:
                    by_id[num].update({k: v for k, v in parsed.items() if v is not None})
                else:
                    by_id[num] = parsed; new_n += 1
            print(f"   {new_n} partidas nuevas ({len(ids)} recientes consultadas)")

            matches = sorted(by_id.values(), key=lambda m: (m.get("timestamp") or 0, m["matchId"]), reverse=True)
            assign_real_lp(matches, lp_history)  # LP real donde haya snapshots que lo permitan

            out = {
                "player": {**data.get("player", {}), **{k: p[k] for k in ("id", "name", "riotId", "platform", "regional")}},
                "rank": {"solo": ranks.get("solo") or data.get("rank", {}).get("solo"),
                          "flex": ranks.get("flex") or data.get("rank", {}).get("flex")},
                "lpHistory": lp_history,
                "matches": matches,
                "source": "riot+ugg",
            }
            with open(os.path.join(DATA, f"{pid}.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print(f"   OK -> data/{pid}.json")
        except Exception as e:
            print(f"   ERROR con {pid}: {e}")

    cfg.setdefault("meta", {})["ddragonVersion"] = version
    with open(os.path.join(DATA, "players.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"ddragonVersion": version,
                    "updated": datetime.now(timezone.utc).isoformat(),
                    "mock": False, "source": "riot+ugg"}, f, ensure_ascii=False, indent=2)
    print("Listo.")


if __name__ == "__main__":
    main()
