import requests
import csv
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.draftkings.com/lobby#/NFL",
    "Origin": "https://www.draftkings.com",
}

# Salary-cap slates the lineup builder actually uses.
KEEP_GAME_TYPE_IDS = {
    1: "Classic",                 # Classic
    21: "Classic",                # some lobby rows use ContestTypeId 21
    96: "Showdown Captain Mode",  # full-game Showdown
    108: "Showdown 2nd Half",     # In-Game Showdown (H2)
    110: "Showdown 4th Quarter",  # In-Game Showdown (Q4)
}

SKIP_NAME_RE = re.compile(r"madden|best ball|snake|tiers|total yards|touchdowns", re.I)


def format_datetime(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        return dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return iso_str


def format_date_only(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        return dt.strftime("%-m/%-d")
    except Exception:
        return ""


def clean_suffix(raw):
    s = str(raw or "").strip()
    return s[1:-1].strip() if s.startswith("(") and s.endswith(")") else s


def slate_type_from_meta(game_type_id, contest_type_id, suffix, contest_names):
    try:
        gid = int(game_type_id or 0)
    except (TypeError, ValueError):
        gid = 0
    try:
        cid = int(contest_type_id or 0)
    except (TypeError, ValueError):
        cid = 0
    suf = suffix or ""
    # Lobby GameTypeId is the source of truth. Do not scan contest names —
    # Classic slates often contain a stray contest with "Showdown" in the title.
    if gid == 108 or cid == 108:
        return "Showdown 2nd Half"
    if gid == 110 or cid == 110:
        return "Showdown 4th Quarter"
    if gid == 96 or cid == 96:
        return "Showdown Captain Mode"
    if gid in (1, 21) or cid == 21:
        if re.search(r"early", suf, re.I):
            return "Early"
        if re.search(r"afternoon|late", suf, re.I):
            return "Late"
        return "Classic"
    blob = " ".join(contest_names or []).lower()
    if "in-game" in blob and ("2h" in blob or "2nd half" in blob):
        return "Showdown 2nd Half"
    if "in-game" in blob and ("4q" in blob or "4th quarter" in blob):
        return "Showdown 4th Quarter"
    if "showdown" in blob:
        return "Showdown Captain Mode"
    if "early" in blob or "early only" in suf.lower():
        return "Early"
    if "afternoon" in suf.lower() or "late" in blob:
        return "Late"
    return "Classic"


def matchup_from_competition(comp, suffix=""):
    if not comp:
        return ""
    name = (comp.get("name") or "").strip()
    if name and not re.fullmatch(r"@?", name) and " @ " != name:
        return name
    home = ((comp.get("homeTeam") or {}).get("abbreviation")
            or comp.get("homeTeamAbbreviation") or "")
    away = ((comp.get("awayTeam") or {}).get("abbreviation")
            or comp.get("awayTeamAbbreviation") or "")
    if away and home:
        return f"{away} @ {home}"
    # Lobby suffix is usually "(SF vs LAR)" or "(2H SF vs LAR)"
    cleaned = re.sub(r"^\s*(2H|4Q|2nd Half|4th Quarter)\s+", "", suffix or "", flags=re.I).strip()
    return cleaned


def build_slate_header(slate_type, start_iso, num_games, matchup, suffix):
    when = ""
    if start_iso:
        try:
            dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
            when = dt.strftime("%-m/%-d %-I:%M%p")
        except Exception:
            when = ""
    extra = clean_suffix(suffix)
    extra = re.sub(r"\b(2H|4Q|2nd Half|4th Quarter)\s+", "", extra, flags=re.I).strip()
    label_matchup = matchup or extra
    if slate_type == "Showdown 2nd Half":
        base = f"{when} 2H".strip()
        return f"{base} ({label_matchup})" if label_matchup else base
    if slate_type == "Showdown 4th Quarter":
        base = f"{when} Q4".strip()
        return f"{base} ({label_matchup})" if label_matchup else base
    if "Showdown" in slate_type:
        base = when
        return f"{base} ({label_matchup})" if label_matchup else base
    games_bit = f"{num_games} Games" if num_games else ""
    bits = [when, games_bit]
    # Keep Early/Afternoon/Sun-Mon tags so Classic 12 vs 14 game slates stay distinct
    tag = extra if extra and extra.lower() not in {games_bit.lower(), (label_matchup or "").lower()} else ""
    if tag and "game" not in tag.lower():
        bits.append(tag)
    return ", ".join([b for b in bits if b])


def main():
    print("Fetching DraftKings contests...")
    contest_url = "https://www.draftkings.com/lobby/getcontests?sport=NFL"

    try:
        r = requests.get(contest_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Failed to fetch contests: {e}")
        return

    contests = data.get("Contests", [])
    lobby_groups = {str(g.get("DraftGroupId")): g for g in (data.get("DraftGroups") or []) if g.get("DraftGroupId")}

    draft_groups = {}
    for c in contests:
        name = (c.get("n") or c.get("Name") or "")
        if SKIP_NAME_RE.search(name):
            continue
        gt = str(c.get("gameType") or "")
        if SKIP_NAME_RE.search(gt):
            continue

        dg = str(c.get("dg") or c.get("DraftGroupId") or "")
        cid = str(c.get("id") or c.get("ContestId") or "")
        if not dg or not cid:
            continue

        meta = lobby_groups.get(dg, {})
        gid = meta.get("GameTypeId") or c.get("gameTypeId") or meta.get("ContestTypeId")
        if gid not in KEEP_GAME_TYPE_IDS and int(gid or 0) not in KEEP_GAME_TYPE_IDS:
            # Still allow Classic/Showdown if lobby metadata is missing
            if "showdown" not in name.lower() and str(c.get("gameType") or "").lower() not in {"classic", "showdown captain mode"}:
                continue

        if dg not in draft_groups:
            draft_groups[dg] = {
                "contest_ids": [],
                "contest_names": [],
                "meta": meta,
                "game_type_id": gid,
            }
        draft_groups[dg]["contest_ids"].append(cid)
        draft_groups[dg]["contest_names"].append(name)

    print(f"Found {len(draft_groups)} usable draft groups")

    rows = []
    headers = [
        "Player Name - Slate Type", "Contest IDs", "Player ID", "Draftable ID",
        "Player Name", "First Name", "Last Name", "Salary", "Position", "Team",
        "Game", "Game Start Time", "Player Image", "Tournament", "Slate Type",
        "Game Type", "Date", "Role", "Contest Names", "Contest IDs (Full)", "Slate Header"
    ]

    for dg_id, group in draft_groups.items():
        print(f"Fetching draftables for {dg_id}...")
        url = f"https://api.draftkings.com/draftgroups/v1/draftgroups/{dg_id}/draftables?format=json"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                print(f"  Failed {dg_id}: {r.status_code}")
                continue
            salary_data = r.json()
        except Exception as e:
            print(f"  Error {dg_id}: {e}")
            continue

        draftables = salary_data.get("draftables", [])
        if not draftables:
            continue

        meta = group.get("meta") or {}
        suffix = meta.get("ContestStartTimeSuffix") or ""
        group["slate_type"] = slate_type_from_meta(
            group.get("game_type_id") or meta.get("GameTypeId") or meta.get("ContestTypeId"),
            meta.get("ContestTypeId"),
            suffix,
            group["contest_names"],
        )

        # Top-level competitions have homeTeam/awayTeam; per-player competition does not.
        comps = {}
        start_times = []
        for comp in (salary_data.get("competitions") or []):
            cid = str(comp.get("competitionId") or "")
            if not cid:
                continue
            st = comp.get("startTime") or ""
            comps[cid] = {
                "matchup": matchup_from_competition(comp, clean_suffix(suffix)),
                "startTime": st,
                "raw": comp,
            }
            if st:
                try:
                    start_times.append(datetime.fromisoformat(st.replace("Z", "+00:00")))
                except Exception:
                    pass

        for p in draftables:
            comp = p.get("competition") or {}
            cid = str(comp.get("competitionId") or "")
            if not cid or cid in comps:
                continue
            st = comp.get("startTime") or ""
            comps[cid] = {
                "matchup": matchup_from_competition(comp, clean_suffix(suffix)) or (comp.get("name") or ""),
                "startTime": st,
                "raw": comp,
            }
            if st:
                try:
                    start_times.append(datetime.fromisoformat(st.replace("Z", "+00:00")))
                except Exception:
                    pass

        num_games = len(comps) or int(meta.get("GameCount") or 0)
        start_iso = ""
        if start_times:
            start_iso = min(start_times).isoformat()
        elif meta.get("StartDate"):
            start_iso = meta.get("StartDate")

        matchup = ""
        if num_games == 1 and comps:
            matchup = next(iter(comps.values())).get("matchup") or ""
        if num_games == 1 and not matchup:
            matchup = clean_suffix(suffix)
            matchup = re.sub(r"^\s*(2H|4Q|2nd Half|4th Quarter)\s+", "", matchup, flags=re.I).strip()

        slate_header = build_slate_header(group["slate_type"], start_iso, num_games, matchup, suffix)
        group["slate_header"] = slate_header
        print(f"  {group['slate_type']} | {slate_header} | games={num_games}")

        player_versions = defaultdict(list)
        for p in draftables:
            player_id = str(p.get("playerId") or "")
            draftable_id = str(p.get("draftableId") or "")
            name = p.get("displayName") or "Unknown"
            salary = p.get("salary") or 0
            if salary <= 0 or not player_id or not draftable_id or name == "Unknown":
                continue
            comp = p.get("competition") or {}
            comp_id = str(comp.get("competitionId") or "")
            info = comps.get(comp_id, {})
            player_versions[player_id].append({
                "draftable_id": draftable_id,
                "name": name,
                "first": p.get("firstName") or "",
                "last": p.get("lastName") or "",
                "salary": salary,
                "pos": p.get("position") or "",
                "team": p.get("teamAbbreviation") or p.get("team") or "",
                "image": p.get("playerImage50") or p.get("imageUrl") or "",
                "game": info.get("matchup") or matchup,
                "start": info.get("startTime") or start_iso,
                "tournament": comp.get("name") or matchup,
                "date": format_date_only(info.get("startTime") or start_iso),
            })

        is_showdown = "Showdown" in group["slate_type"]

        for player_id, versions in player_versions.items():
            versions.sort(key=lambda x: x["salary"], reverse=True)
            if is_showdown and len(versions) >= 2:
                cpt, flex = versions[0], versions[1]
                for version, pos, role in ((cpt, "CPT", "Captain"), (flex, flex["pos"], "Flex")):
                    rows.append([
                        f"{version['name']} - {group['slate_type']} ({role})",
                        ";".join(group["contest_ids"][:20]),
                        player_id,
                        version["draftable_id"],
                        version["name"],
                        version["first"],
                        version["last"],
                        version["salary"],
                        pos,
                        version["team"],
                        version["game"],
                        format_datetime(version["start"]),
                        version["image"],
                        version["tournament"],
                        group["slate_type"],
                        "NFL",
                        version["date"],
                        role,
                        ";".join(group["contest_names"][:10]),
                        ";".join(group["contest_ids"][:20]),
                        slate_header,
                    ])
            else:
                seen = {}
                for v in versions:
                    key = (v["salary"], v["pos"], v["team"], v["name"])
                    if key not in seen or int(v["draftable_id"]) < int(seen[key]["draftable_id"]):
                        seen[key] = v
                for v in seen.values():
                    rows.append([
                        f"{v['name']} - {group['slate_type']}",
                        ";".join(group["contest_ids"][:20]),
                        player_id,
                        v["draftable_id"],
                        v["name"],
                        v["first"],
                        v["last"],
                        v["salary"],
                        v["pos"],
                        v["team"],
                        v["game"],
                        format_datetime(v["start"]),
                        v["image"],
                        v["tournament"],
                        group["slate_type"],
                        "NFL",
                        v["date"],
                        "Standard",
                        ";".join(group["contest_names"][:10]),
                        ";".join(group["contest_ids"][:20]),
                        slate_header,
                    ])

    if not rows:
        print("No player rows generated")
        return

    rows.sort(key=lambda x: int(x[7]) if str(x[7]).isdigit() else 0, reverse=True)
    with open("drafttable.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to drafttable.csv")


if __name__ == "__main__":
    main()
