"""Convierte los archivos de LP timeline de u.gg en data/<id>.json.

u.gg entrega, por cada partida ranked: score (LP absoluto), tier, rank y championId.
De la diferencia de LP entre partidas inferimos victoria/derrota y cuánto LP se ganó.
NO trae KDA/CS/oro/daño: esos los completa fetch.py cuando haya una API key válida.

Mapeo de colas (verificado con analyze): track[1] = Solo/Duo, track[0] = Flex.

Uso:
    python scripts/seed_ugg.py <archivo_me.json> <archivo_friend.json>
o sin args usa las rutas por defecto del escritorio.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

# Mapeo verificado contra el rank en vivo de la API (league-v4):
# el final exacto de cada track coincide con la entrada de su cola.
# track[0] = Solo/Duo, track[1] = Flex.
QUEUE_BY_TRACK = {0: "SOLO", 1: "FLEX"}

TIER_NAME = {
    "IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro",
    "PLATINUM": "Platino", "EMERALD": "Esmeralda", "DIAMOND": "Diamante",
    "MASTER": "Maestro", "GRANDMASTER": "Gran Maestro", "CHALLENGER": "Retador",
}


def get_champ_map():
    """championId (numérico) -> nombre para iconos, desde ddragon público."""
    ver = "16.16.1"
    try:
        vs = json.loads(urllib.request.urlopen(
            "https://ddragon.leagueoflegends.com/api/versions.json", timeout=15).read())
        ver = vs[0]
    except Exception as e:
        print("  (aviso) no pude leer versión ddragon, uso", ver, "-", e)
    cmap = {}
    try:
        url = f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json"
        champs = json.loads(urllib.request.urlopen(url, timeout=20).read())["data"]
        for name, info in champs.items():
            cmap[int(info["key"])] = info["id"]  # id = nombre para el icono
    except Exception as e:
        print("  (aviso) no pude leer champion.json:", e)
    return ver, cmap


def load_ugg(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["data"]["fetchPlayerLpTimeline"]


def rank_label(tier, rank, lp):
    apex = tier in ("MASTER", "GRANDMASTER", "CHALLENGER")
    return f'{TIER_NAME.get(tier, tier)}{"" if apex else " " + rank} {lp} LP'


def build_track(points, queue, cmap):
    """points = lista de LpStatus de un track (una cola). Devuelve historial ordenado."""
    ranked = [p for p in points if p.get("tier")]
    ranked.sort(key=lambda p: p["matchId"])  # cronológico (matchId crece con el tiempo)
    hist = []
    prev = None
    for i, p in enumerate(ranked):
        lp_abs = p["score"]
        delta = None if prev is None else lp_abs - prev
        win = None if delta is None or delta == 0 else (delta > 0)
        hist.append({
            "i": i,
            "lp": lp_abs,
            "tier": p["tier"],
            "rank": p["rank"],
            "lpInDiv": p["lp"],
            "champion": cmap.get(p["championId"]),
            "championId": p["championId"],
            "matchId": p["matchId"],
            "delta": delta,
            "win": win,
            "queue": queue,
        })
        prev = lp_abs
    return hist


def summarize_rank(hist):
    if not hist:
        return None
    wins = sum(1 for h in hist if h["win"] is True)
    losses = sum(1 for h in hist if h["win"] is False)
    last = hist[-1]
    return {
        "tier": last["tier"], "rank": last["rank"], "lp": last["lpInDiv"],
        "wins": wins, "losses": losses, "absoluteLp": last["lp"],
    }


def build_player(pid, name, riot_id, ugg_path, cmap):
    tracks = load_ugg(ugg_path)
    solo = build_track(tracks[0]["lpTrack"], "SOLO", cmap) if len(tracks) > 0 else []
    flex = build_track(tracks[1]["lpTrack"], "FLEX", cmap) if len(tracks) > 1 else []

    # historial de partidas: unir ambas colas, más recientes primero (por matchId)
    matches = []
    for h in solo + flex:
        matches.append({
            "matchId": h["matchId"],
            "queue": h["queue"],
            "champion": h["champion"],
            "championId": h["championId"],
            "win": h["win"],
            "lpChange": h["delta"],
            "lpAfter": h["lp"],
            "tier": h["tier"],
            "rank": h["rank"],
            "rankLabel": rank_label(h["tier"], h["rank"], h["lpInDiv"]),
            # stats de la API (a completar con fetch.py):
            "kills": None, "deaths": None, "assists": None, "kda": None,
            "cs": None, "csPerMin": None, "gold": None, "goldPerMin": None,
            "damage": None, "damagePerMin": None, "visionScore": None,
            "killParticipation": None, "duration": None, "position": None,
            "timestamp": None,
        })
    matches.sort(key=lambda m: m["matchId"], reverse=True)

    return {
        "player": {"id": pid, "name": name, "riotId": riot_id,
                    "platform": "la2", "regional": "americas"},
        "rank": {"solo": summarize_rank(solo), "flex": summarize_rank(flex)},
        "lpHistory": {"solo": solo, "flex": flex},
        "matches": matches,
        "source": "ugg-seed",  # marca de que aún no tiene stats de la API
    }


def main():
    args = sys.argv[1:]
    me_path = args[0] if len(args) > 0 else r"C:\Users\User\Desktop\lp_raagusth.json.txt"
    fr_path = args[1] if len(args) > 1 else r"C:\Users\User\Desktop\lp_alchemist_bomb.json.txt"

    print("Leyendo ddragon (mapa de campeones)...")
    ver, cmap = get_champ_map()
    print(f"  versión {ver}, {len(cmap)} campeones")

    me = build_player("me", "Agustín", "Ragusth#7822", me_path, cmap)
    fr = build_player("friend", "Joel", "alchemist bomb#LAS", fr_path, cmap)

    with open(os.path.join(DATA, "me.json"), "w", encoding="utf-8") as f:
        json.dump(me, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "friend.json"), "w", encoding="utf-8") as f:
        json.dump(fr, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"ddragonVersion": ver,
                    "updated": datetime.now(timezone.utc).isoformat(),
                    "mock": False, "source": "ugg-seed"}, f, ensure_ascii=False, indent=2)

    for tag, p in (("Agustín", me), ("Joel", fr)):
        s, fx = p["rank"]["solo"], p["rank"]["flex"]
        print(f"\n{tag}:")
        if s: print(f"  Solo: {s['tier']} {s['rank']} {s['lp']}LP · {s['wins']}V {s['losses']}D · {len(p['lpHistory']['solo'])} pts")
        if fx: print(f"  Flex: {fx['tier']} {fx['rank']} {fx['lp']}LP · {fx['wins']}V {fx['losses']}D · {len(p['lpHistory']['flex'])} pts")
        print(f"  Historial: {len(p['matches'])} partidas")
    print("\nListo: data/me.json, data/friend.json")


if __name__ == "__main__":
    main()
