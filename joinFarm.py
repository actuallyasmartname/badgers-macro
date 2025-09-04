# -- CONFIGURATION --
COOKIE = "" # add your .ROBLOSECURITY if you want a more straightforward and potentially faster way to check if a game is public (dw i won't bite)
DELAY = 2 # default 2 seconds in between game launch. if the script isn't gaining visits at all, try increasing this.

USE_CSV = False # if the spreadsheet isn't connecting, use this to enable CSV mode
CSV_LOCATION = "ids_list.csv" # if the above is set to True, go off of this CSV file. your custom list must have a raw universeId as the first column.

# !! SPREADSHEET MODE ONLY !!
# ONLY ONE BY_ OPTION BELOW WILL BE SELECTED IF MORE THAN ONE ARE SET TO TRUE
BY_BADGES = True # whether to join games by high -> low badges or not.
BY_VISITS = False # whether to join games by high -> low visits or not.

import csv
import re
import json
import requests
import time
import threading
import webbrowser
import os
from datetime import datetime

SHEET_ID = "1QU-tL5QtPadp-doAKP7QfNIgg3fsBJ_4ACX_i68uXQI"
GOOGLE_SHEET_API = "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:json&gid="
API_URL = "https://games.roblox.com/v1/games?universeIds="
PROGRESS_FILE = "progress.csv"

def load_sheet(sheet_id):
    url = GOOGLE_SHEET_API % sheet_id + "1463482043"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        match = re.search(r'setResponse\((.*)\);?$', r.text)
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
        return data.get("table", {}).get("rows", [])
    except Exception as e:
        print(f"[ERROR] Failed to load sheet: {e}")
        return []

def load_progress():
    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if row and row[0]:
                    done.add(row[0])
    return done

def save_progress(universe_id):
    with threading.Lock():
        with open(PROGRESS_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([universe_id])

def check_publicity_nocookie(universe_id, creatorType, creatorId):
    if creatorType == "User" and creatorId:
        base_url = f"https://games.roblox.com/v2/users/{creatorId}/games"
    elif creatorType == "Group" and creatorId:
        base_url = f"https://games.roblox.com/v2/groups/{creatorId}/gamesV2"
    else:
        print(f"[ERROR] Missing creator info for {universe_id}")
        return None
    cursor = ""
    while True:
        try:
            r = requests.get(f"{base_url}?limit=50&cursor={cursor}", timeout=15)
            r.raise_for_status()
            data = r.json()
            for i in data.get("data", []):
                if str(i.get("id")) == str(universe_id):
                    return True
            cursor = data.get("nextPageCursor")
            if not cursor:
                return False
        except Exception as e:
            print(f"[ERROR] Publicity check failed for {universe_id}: {e}")
            return None

def check_publicity_withcookie(universe_id):
    try:
        r = requests.get(
            f"https://games.roblox.com/v1/games/multiget-playability-status?universeIds={universe_id}",
            cookies={".ROBLOSECURITY": COOKIE},
            timeout=15
        )
        r.raise_for_status()
        for i in r.json():
            if i.get("playabilityStatus") == "GuestProhibited":
                print("[ERROR] Invalid cookie provided.")
                exit()
            if str(i.get("universeId")) == str(universe_id) and i.get("isPlayable"):
                return True
        return False
    except Exception as e:
        print(f"[ERROR] Publicity check with cookie failed for {universe_id}: {e}")
        return None

def handle_game(universe_id, place_id):
        stop_event = threading.Event()
        def spam_launcher():
            while not stop_event.is_set():
                try:
                    webbrowser.open(f"roblox://placeId={place_id}")
                except Exception:
                    pass
                time.sleep(DELAY)
        def monitor_visits():
            last_visits = None
            while not stop_event.is_set():
                try:
                    r = requests.get(API_URL + str(universe_id), timeout=15)
                    r.raise_for_status()
                    data = r.json()
                    if data.get("data"):
                        visits = data["data"][0].get("visits", 0)
                        now = datetime.now()
                        nowDisplay = now.strftime("%Y-%m-%d %H:%M:%S")
                        if last_visits is not None:
                            print(f"[Monitor] Universe {universe_id} visits={visits} (+{visits - last_visits} in last 20s). Time: {nowDisplay}")
                        else:
                            print(f"[Monitor] Universe {universe_id} visits={visits} (initial). Time: {nowDisplay}")
                        last_visits = visits
                        if visits >= 1001:
                            print(f"[DONE] Universe {universe_id} reached {visits} visits. Stopping... Time: {nowDisplay}")
                            save_progress(universe_id)
                            stop_event.set()
                            return
                except Exception as e:
                    print(f"[Monitor ERROR] {e}")
                time.sleep(20)
        threading.Thread(target=spam_launcher, daemon=True).start()
        threading.Thread(target=monitor_visits, daemon=True).start()
        while not stop_event.is_set():
            time.sleep(0.5)

def process_ids(ids):
    chunk_size = 50
    threads = []
    for i in range(0, len(ids), chunk_size):
        try:
            r = requests.get(API_URL + ",".join(ids[i:i+chunk_size]), timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[ERROR] Failed request: {e}")
            continue
        for universe in data.get("data", []):
            uid = str(universe.get("id"))
            place_id = universe.get("rootPlaceId")
            if universe.get("visits", 0) < 1001:
                if COOKIE != "":
                    pubCheck = check_publicity_withcookie(uid)
                else:
                    pubCheck = check_publicity_nocookie(uid, universe.get("creator", {"type": None}).get("type"), universe.get("creator", {"id": None}).get("id"))
                if pubCheck == True:
                    print(f"[FOUND] Universe {uid} with {universe.get('visits', 0)} visits")
                    handle_game(uid, place_id)
                else:
                    print(f"[SKIPPED] Universe {uid} is not public/check failed")
            else:
                save_progress(uid)
    for t in threads:
        t.join()

def process_csv(filename):
    ids = []
    done = load_progress()
    print(f"[INFO] Skipping {len(done)} completed universes")
    try:
        with open(filename, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if row and row[0] not in done:
                    ids.append(row[0])
    except Exception as e:
        print(f"[ERROR] Could not read CSV: {e}")
        return
    process_ids(ids)

def process_sheet(sheetInfo):
    ids = []
    done = load_progress()
    print(f"[INFO] Skipping {len(done)} completed universes")
    if BY_VISITS:
        sheetInfo = sorted(sheetInfo, key=lambda x: x.get("c", [])[3].get("v", 0) if len(x.get("c", [])) > 3 and x["c"][3] else 0, reverse=True)
    for row in sheetInfo:
        rowInfo = row.get("c", [])
        if len(rowInfo) > 1 and rowInfo[1] and rowInfo[1].get("f") and rowInfo[1]["f"] not in done:
            ids.append(rowInfo[1]["f"])
    process_ids(ids)
    
if __name__ == "__main__":
    with requests.Session() as session:
        spreadsheetInfo = load_sheet(SHEET_ID)
        if len(spreadsheetInfo) > 0:
            process_sheet(spreadsheetInfo)
        else:
            process_csv("ids_list.csv")