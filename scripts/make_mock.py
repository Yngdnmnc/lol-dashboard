"""Genera datos de ejemplo (mock) para ver el dashboard sin API key.
Produce data/me.json y data/friend.json con el MISMO esquema que fetch.py.
Uso:  python scripts/make_mock.py
"""
import json
import os
import random
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

CHAMPS = [
    "Ahri", "Yasuo", "Jinx", "Thresh", "LeeSin", "Lux", "Ezreal", "Katarina",
    "Zed", "Kaisa", "Sett", "Vi", "Caitlyn", "Morgana", "Viego", "Akali",
    "Nautilus", "Jhin", "Yone", "Senna",
]
POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
QUEUES = ["SOLO", "SOLO", "SOLO", "FLEX", "FLEX", "NORMAL"]  # ponderado a soloq

TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND",
         "MASTER", "GRANDMASTER", "CHALLENGER"]
DIVS = {"IV": 0, "III": 1, "II": 2, "I": 3}


def absolute_lp(tier, division, lp):
    """Convierte tier+division+lp a un número acumulado único para graficar."""
    ti = TIERS.index(tier)
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        # todos comparten la base de Diamond I 100 y suman LP continuo
        return TIERS.index("DIAMOND") * 400 + 400 + lp
    return ti * 400 + DIVS.get(division, 0) * 100 + lp


def gen_match(i, base_ts, seed_champ_pool):
    dur = random.randint(18, 38) * 60  # segundos
    minutes = dur / 60.0
    win = random.random() < 0.53
    kills = random.randint(0, 15)
    deaths = random.randint(1, 10)
    assists = random.randint(0, 22)
    cs = int(random.uniform(4.5, 9.5) * minutes)
    gold = int(random.uniform(300, 480) * minutes)
    dmg = int(random.uniform(400, 1100) * minutes)
    kda = round((kills + assists) / max(1, deaths), 2)
    queue = random.choice(QUEUES)
    champ = random.choice(seed_champ_pool)
    team_kills = kills + random.randint(10, 40)
    kp = round((kills + assists) / max(1, team_kills) * 100)
    ts = base_ts - i * random.randint(1800, 7200) * 1000  # ms, hacia atrás
    return {
        "matchId": f"MOCK_{i}",
        "queue": queue,
        "champion": champ,
        "championId": 0,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kda": kda,
        "cs": cs,
        "csPerMin": round(cs / minutes, 1),
        "gold": gold,
        "goldPerMin": round(gold / minutes),
        "damage": dmg,
        "damagePerMin": round(dmg / minutes),
        "visionScore": random.randint(8, 60),
        "killParticipation": kp,
        "duration": dur,
        "timestamp": ts,
        "position": random.choice(POSITIONS),
        "items": [random.randint(1000, 3900) for _ in range(6)],
    }


def gen_player(pid, name, tier, division, lp, champ_pool):
    now_ms = int(time.time() * 1000)
    matches = [gen_match(i, now_ms, champ_pool) for i in range(30)]

    # historial de LP total (snapshots) simulando progresión hacia el rank actual
    abs_now = absolute_lp(tier, division, lp)
    solo_hist = []
    val = abs_now - random.randint(150, 400)
    for d in range(40, -1, -1):  # 40 snapshots
        val += random.randint(-25, 35)
        val = max(0, val)
        t = now_ms - d * 12 * 3600 * 1000
        solo_hist.append({"t": t, "lp": val})
    solo_hist[-1]["lp"] = abs_now  # el último coincide con el rank actual

    flex_hist = []
    valf = abs_now - random.randint(300, 600)
    for d in range(40, -1, -1):
        valf += random.randint(-20, 30)
        valf = max(0, valf)
        t = now_ms - d * 14 * 3600 * 1000
        flex_hist.append({"t": t, "lp": valf})

    # LP acumulado ligado a partidas ranked (para la gráfica "últimas N partidas")
    ranked = [m for m in matches if m["queue"] in ("SOLO", "FLEX")]
    ranked_sorted = sorted(ranked, key=lambda m: m["timestamp"])
    cur = abs_now - sum(20 if m["win"] else -18 for m in ranked_sorted)
    for m in ranked_sorted:
        cur += 20 if m["win"] else -18
        m["lpAfter"] = cur

    wins = sum(1 for m in matches if m["queue"] == "SOLO" and m["win"])
    losses = sum(1 for m in matches if m["queue"] == "SOLO" and not m["win"])
    fwins = sum(1 for m in matches if m["queue"] == "FLEX" and m["win"])
    flosses = sum(1 for m in matches if m["queue"] == "FLEX" and not m["win"])

    return {
        "player": {"id": pid, "name": name, "riotId": f"{name}#MOCK",
                    "platform": "la2", "regional": "americas"},
        "rank": {
            "solo": {"tier": tier, "rank": division, "lp": lp,
                      "wins": wins, "losses": losses,
                      "absoluteLp": absolute_lp(tier, division, lp)},
            "flex": {"tier": "SILVER", "rank": "II", "lp": 44,
                      "wins": fwins, "losses": flosses,
                      "absoluteLp": absolute_lp("SILVER", "II", 44)},
        },
        "lpHistory": {"solo": solo_hist, "flex": flex_hist},
        "matches": sorted(matches, key=lambda m: m["timestamp"], reverse=True),
    }


def main():
    random.seed(7)
    me = gen_player("me", "Yo", "GOLD", "II", 67, CHAMPS[:10])
    fr = gen_player("friend", "Mi Amigo", "PLATINUM", "IV", 21, CHAMPS[8:18])
    with open(os.path.join(DATA, "me.json"), "w", encoding="utf-8") as f:
        json.dump(me, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "friend.json"), "w", encoding="utf-8") as f:
        json.dump(fr, f, ensure_ascii=False, indent=2)

    # meta con la versión de ddragon (para iconos de campeones)
    meta = {"ddragonVersion": "15.15.1",
            "updated": datetime.now(timezone.utc).isoformat(), "mock": True}
    with open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("Mock generado: data/me.json, data/friend.json, data/meta.json")


if __name__ == "__main__":
    main()
