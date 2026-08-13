import requests
import csv
import json
from datetime import datetime
from zoneinfo import ZoneInfo

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.draftkings.com/lobby#/NFL",
    "Origin": "https://www.draftkings.com",
}

def format_datetime(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        return dt.strftime("%m/%d/%Y %I:%M %p")
    except:
        return iso_str

def format_date_only(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        return dt.strftime("%-m/%-d")
    except:
        return ""

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
    if not contests:
        print("No contests found")
        return

    # Group by draft group
    draft_groups = {}
    for c in contests:
        name = (c.get("n") or c.get("Name") or "").lower()
        if "madden" in name or "best ball" in name:
            continue

        dg = str(c.get("dg") or c.get("DraftGroupId") or "")
        cid = str(c.get("id") or c.get("ContestId") or "")
        cname = c.get("n") or c.get("Name") or ""

        if not dg or not cid:
            continue

        slate_type = "Classic"
        if "showdown" in name:
            slate_type = "Showdown Captain Mode"
        elif "turbo" in name:
            slate_type = "Turbo"
        elif "late" in name:
            slate_type = "Late"
        elif "early" in name:
            slate_type = "Early"
        elif "night" in name:
            slate_type = "Night"

        if dg not in draft_groups:
            draft_groups[dg] = {
                "slate_type": slate_type,
                "contest_ids": [],
                "contest_names": []
            }
        draft_groups[dg]["contest_ids"].append(cid)
        draft_groups[dg]["contest_names"].append(cname)
        draft_groups[dg]["slate_type"] = slate_type

    print(f"Found {len(draft_groups)} draft groups")

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

        # Build competition lookup
        comps = {}
        start_times = []
        for p in draftables:
            comp = p.get("competition") or {}
            cid = str(comp.get("competitionId") or "")
            if cid and cid not in comps:
                home = (comp.get("homeTeam") or {}).get("abbreviation") or comp.get("homeTeamAbbreviation") or ""
                away = (comp.get("awayTeam") or {}).get("abbreviation") or comp.get("awayTeamAbbreviation") or ""
                st = comp.get("startTime") or ""
                comps[cid] = {
                    "matchup": f"{away} @ {home}",
                    "startTime": st
                }
                if st:
                    try:
                        start_times.append(datetime.fromisoformat(st.replace("Z", "+00:00")))
                    except:
                        pass

        num_games = len(comps)
        if num_games == 1:
            group["slate_type"] = "Showdown Captain Mode"

        # Slate header
        slate_header = group["slate_type"]
        slate_date = ""
        if start_times:
            min_start = min(start_times)
            slate_date = min_start.astimezone(ZoneInfo("America/New_York")).strftime("%-m/%-d")
            time_part = min_start.astimezone(ZoneInfo("America/New_York")).strftime("%-I:%M%p")
            if num_games == 1:
                matchup = list(comps.values())[0]["matchup"]
                slate_header = f"{slate_date} {time_part} ({matchup})"
            else:
                slate_header = f"{slate_date} {time_part}, {num_games} Games"

        # Collect players
        for p in draftables:
            player_id = str(p.get("playerId") or "")
            draftable_id = str(p.get("draftableId") or "")
            name = p.get("displayName") or "Unknown"
            first = p.get("firstName") or ""
            last = p.get("lastName") or ""
            salary = p.get("salary") or 0
            pos = p.get("position") or ""
            team = p.get("teamAbbreviation") or p.get("team") or ""
            image = p.get("playerImage50") or p.get("imageUrl") or ""
            
            comp = p.get("competition") or {}
            comp_id = str(comp.get("competitionId") or "")
            game = comps.get(comp_id, {}).get("matchup", "")
            start = comps.get(comp_id, {}).get("startTime", "")
            tournament = comp.get("name") or ""

            if salary <= 0 or not player_id or not draftable_id or name == "Unknown":
                continue

            date = format_date_only(start)
            role = "Captain" if pos == "CPT" else "Standard"
            if "Showdown" in group["slate_type"] and pos != "CPT":
                role = "Flex"

            row = [
                f"{name} - {group['slate_type']}",
                ";".join(group["contest_ids"][:20]),  # truncate
                player_id,
                draftable_id,
                name,
                first,
                last,
                salary,
                pos,
                team,
                game,
                format_datetime(start),
                image,
                tournament,
                group["slate_type"],
                "NFL",
                date,
                role,
                ";".join(group["contest_names"][:10]),
                ";".join(group["contest_ids"][:20]),
                slate_header
            ]
            rows.append(row)

    if not rows:
        print("No player rows generated")
        return

    # Sort by salary descending
    rows.sort(key=lambda x: int(x[7]) if str(x[7]).isdigit() else 0, reverse=True)

    with open("drafttable.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to drafttable.csv")

if __name__ == "__main__":
    main()
