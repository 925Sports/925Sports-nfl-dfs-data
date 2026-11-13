import requests
import json
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.fanduel.com",
    "Referer": "https://www.fanduel.com/research/nfl/fantasy/dfs-projections"
}

GRAPHQL_URL = "https://fdresearch-api.fanduel.com/graphql"

QUERY = """
query GetProjections($input: ProjectionsInput!) {
  getProjections(input: $input) {
    ... on NflSkill {
      player { name position }
      team { abbreviation }
      gameInfo { awayTeam { abbreviation } homeTeam { abbreviation } }
      completionsAttempts
      passingYards
      passingTouchdowns
      interceptionsThrown
      rushingAttempts
      rushingYards
      rushingTouchdowns
      receptions
      targets
      receivingYards
      receivingTouchdowns
      fantasy
    }
    ... on NflKicker {
      player { name position }
      team { abbreviation }
      gameInfo { awayTeam { abbreviation } homeTeam { abbreviation } }
      fieldGoalsMade
      extraPointsMade
      fantasy
    }
    ... on NflDefenseSt {
      player { name position }
      team { abbreviation }
      gameInfo { awayTeam { abbreviation } homeTeam { abbreviation } }
      pointsAllowed
      yardsAllowed
      sacks
      interceptions
      fumblesRecovered
      touchdowns
      fantasy
    }
  }
}
"""

def fetch_position(position_group):
    payload = {
        "operationName": "GetProjections",
        "variables": {
            "input": {
                "type": "WEEKLY",
                "position": position_group,
                "sport": "NFL"
            }
        },
        "query": QUERY
    }
    r = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("getProjections", [])

def normalize(projections, position_group):
    result = {}
    for p in projections:
        if not p.get("player") or not p["player"].get("name"):
            continue
        
        player = p["player"]["name"].strip()
        pos = (p["player"].get("position") or "").upper()
        if pos == "D":
            pos = "DST"
        
        team = (p.get("team") or {}).get("abbreviation", "").upper()
        fpts = float(p.get("fantasy") or 0)
        
        if not player or not pos or not team or fpts <= 0:
            continue
        
        opp = ""
        gi = p.get("gameInfo") or {}
        away = (gi.get("awayTeam") or {}).get("abbreviation", "")
        home = (gi.get("homeTeam") or {}).get("abbreviation", "")
        if team == away:
            opp = home
        elif team == home:
            opp = away
        
        stats = {"fpts": round(fpts, 2)}
        
        if position_group == "NFL_SKILL":
            ca = str(p.get("completionsAttempts") or "")
            if "/" in ca:
                parts = ca.split("/")
                stats["pass_cmp"] = float(parts[0] or 0)
                stats["pass_att"] = float(parts[1] or 0)
            stats["pass_yds"] = float(p.get("passingYards") or 0)
            stats["pass_td"] = float(p.get("passingTouchdowns") or 0)
            stats["int"] = float(p.get("interceptionsThrown") or 0)
            stats["rush_att"] = float(p.get("rushingAttempts") or 0)
            stats["rush_yds"] = float(p.get("rushingYards") or 0)
            stats["rush_td"] = float(p.get("rushingTouchdowns") or 0)
            stats["rec"] = float(p.get("receptions") or 0)
            stats["tgts"] = float(p.get("targets") or 0)
            stats["rec_yds"] = float(p.get("receivingYards") or 0)
            stats["rec_td"] = float(p.get("receivingTouchdowns") or 0)
        
        elif position_group == "NFL_KICKER":
            stats["fg"] = float(p.get("fieldGoalsMade") or 0)
            stats["xpt"] = float(p.get("extraPointsMade") or 0)
        
        elif position_group == "NFL_D_ST":
            stats["pa"] = float(p.get("pointsAllowed") or 0)
            stats["yds_agn"] = float(p.get("yardsAllowed") or 0)
            stats["sack"] = float(p.get("sacks") or 0)
            stats["int"] = float(p.get("interceptions") or 0)
            stats["fr"] = float(p.get("fumblesRecovered") or 0)
            stats["td"] = float(p.get("touchdowns") or 0)
        
        key = f"{player}_{pos}".lower()
        result[key] = {
            "info": {
                "player": player,
                "position": pos,
                "team": team,
                "opp": opp
            },
            "stats": stats
        }
    
    return result

def main():
    all_data = {}
    for group in ["NFL_SKILL", "NFL_KICKER", "NFL_D_ST"]:
        try:
            projections = fetch_position(group)
            parsed = normalize(projections, group)
            all_data.update(parsed)
            print(f"{group}: {len(parsed)} players")
        except Exception as e:
            print(f"Error on {group}: {e}")
    
    output = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "slateId": "WEEKLY",
        "players": all_data
    }
    
    with open("fanduel_projections.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"Wrote {len(all_data)} players to fanduel_projections.json")

if __name__ == "__main__":
    main()
