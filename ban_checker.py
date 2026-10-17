import requests
import re
import sys
import os
import argparse
from bs4 import BeautifulSoup
from tabulate import tabulate
import xml.etree.ElementTree as ET
import cloudscraper

# Configuration
STEAM_API_KEY = os.getenv("STEAM_API_KEY", "") # User can set this env var or input it
SOURCES = [
    {
        "name": "Steam Official",
        "url": "https://steamcommunity.com/profiles/",
        "type": "steam_official"
    },
    {
        "name": "SirPlease",
        "url": "https://sirplease.vercel.app/api/bans",
        "type": "custom_sirplease"
    },
    {
        "name": "L4D2Center",
        "url": "https://l4d2center.com/bans",
        "type": "l4d2center_api"
    },
    {
        "name": "CedaPug",
        "url": "https://cedapug.com/bans",
        "type": "cedapug_scrape"
    }
]


class BanChecker:
    def __init__(self, api_key=None):
        self.api_key = api_key
        # Use cloudscraper with browser emulation
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })

    def resolve_steam_id(self, input_str):
        """
        Resolves a Steam Profile URL (vanity or ID64) to a SteamID64 string.
        """
        input_str = input_str.strip()
        
        # Already an ID64? (17 digits)
        if re.match(r'^\d{17}$', input_str):
            return input_str
            
        # URL parsing
        # Check for /profiles/ (Direct ID)
        # Handle trailing slashes or query params
        match_profiles = re.search(r'steamcommunity\.com/profiles/(\d{17})', input_str)
        if match_profiles:
            return match_profiles.group(1)
            
        # Check for /id/ (Vanity URL)
        # Stop at / or ? or end of string
        match_id = re.search(r'steamcommunity\.com/id/([^/?]+)', input_str)
        if match_id:
            vanity = match_id.group(1)
            return self._resolve_vanity_xml(vanity)
            
        # If user just gave the vanity name without URL
        if not "/" in input_str and not input_str.isdigit():
             return self._resolve_vanity_xml(input_str)

        print(f"Error: No se pudo interpretar el input: {input_str}")
        return None

    def _resolve_vanity_xml(self, vanity):
        print(f"[*] Resolviendo Vanity URL '{vanity}' vía XML...")
        try:
            url = f"https://steamcommunity.com/id/{vanity}/?xml=1"
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Error HTTP {response.status_code} al resolver vanity.")
                return None
            
            tree = ET.fromstring(response.content)
            steamid64 = tree.find("steamID64")
            if steamid64 is not None:
                return steamid64.text
            else:
                print("Error: No se encontró <steamID64> en el XML. ¿Perfil privado o inválido?")
                return None
        except Exception as e:
            print(f"Excepción al resolver vanity: {e}")
            return None

    def check_steam_api(self, steam_id):
        """
        Checks official VAC/Game bans using Steam Web API.
        """
        if not self.api_key:
            return {"source": "Steam API", "error": "Falta API Key"}
            
        url = "http://api.steampowered.com/ISteamUser/GetPlayerBans/v1/"
        params = {"key": self.api_key, "steamids": steam_id}
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            players = data.get("players", [])
            if not players:
                return {"source": "Steam API", "error": "No data"}
                
            p = players[0]
            vac_banned = p.get("VACBanned", False)
            game_bans = p.get("NumberOfGameBans", 0)
            days_since = p.get("DaysSinceLastBan", 0)
            eco_ban = p.get("EconomyBan", "None")
            
            result_str = "Limpio"
            if vac_banned or game_bans > 0:
                result_str = f"VAC: {vac_banned}, Game Bans: {game_bans}, Days Since: {days_since}"
            
            if eco_ban != "None":
                result_str += f", Eco: {eco_ban}"

            return {
                "source": "Steam Official",
                "status": "BANNED" if (vac_banned or game_bans > 0) else "Clean",
                "details": result_str,
                "history": [] # Steam API doesn't give history details, just totals
            }
        except Exception as e:
            return {"source": "Steam Official", "error": str(e)}

    def steam64_to_id2(self, steam_id64):
        """
        Converts SteamID64 to SteamID2 (STEAM_1:X:Y).
        """
        try:
            steamid64_int = int(steam_id64)
            # Basic validation
            if steamid64_int < 76561197960265728:
                 return steam_id64
            
            # Formula:
            # Y = steamid64 % 2
            # X = (steamid64 - Y - 76561197960265728) / 2
            
            y = steamid64_int % 2
            x = (steamid64_int - y - 76561197960265728) // 2
            
            # Usually STEAM_1:Y:X or STEAM_0:Y:X?
            # Modern Convention is typically STEAM_1, but older games used STEAM_0.
            # Most bans checkers accept either, but let's default to STEAM_1
            return f"STEAM_1:{y}:{x}"
        except:
            return steam_id64

    def check_steam_official(self, steam_id):
        """
        Checks official Steam VAC and Trade bans.
        Uses Steam API if key is available, falls back to XML community profile.
        """
        if self.api_key:
            res = self.check_steam_api(steam_id)
            if not res.get("error"):
                res.setdefault("manual_check_url", f"https://steamcommunity.com/profiles/{steam_id}")
                if res.get("status") == "BANNED" and not res.get("history") and res.get("details"):
                    res["history"] = [res["details"]]
                return res

        url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return {
                    "source": "Steam Official",
                    "status": "Error",
                    "error": f"HTTP {resp.status_code}",
                    "details": f"HTTP Error {resp.status_code}",
                    "history": [],
                    "manual_check_url": f"https://steamcommunity.com/profiles/{steam_id}"
                }

            tree = ET.fromstring(resp.content)
            vac_elem = tree.findtext("vacBanned", "").strip()
            trade_elem = tree.findtext("tradeBanState", "").strip()

            vac_banned = (vac_elem == "1")
            trade_banned = bool(trade_elem and trade_elem.lower() != "none")
            is_banned = vac_banned or trade_banned

            bans = []
            if vac_banned:
                bans.append("VAC Banned")
            if trade_banned:
                bans.append(f"Trade Ban: {trade_elem}")

            details_str = ", ".join(bans) if bans else "Limpio"

            return {
                "source": "Steam Official",
                "status": "BANNED" if is_banned else "Clean",
                "details": details_str,
                "history": [details_str] if is_banned else [],
                "manual_check_url": f"https://steamcommunity.com/profiles/{steam_id}"
            }
        except Exception as e:
            return {
                "source": "Steam Official",
                "status": "Error",
                "error": str(e),
                "details": str(e),
                "history": [],
                "manual_check_url": f"https://steamcommunity.com/profiles/{steam_id}"
            }

    def check_sirplease_custom(self, base_url, steam_id):
        """
        Fetches SirPlease bans using their hidden API: https://sirplease.vercel.app/api/bans
        Critically: The API uses SteamID2 format (STEAM_1:x:y), NOT SteamID64.
        We must calculate the SteamID2 from the 64-bit ID to find the record.
        """
        api_url = "https://sirplease.vercel.app/api/bans"
        print(f"[*] Verificando SirPlease (API): {api_url}")

        # Convert SteamID64 to SteamID2
        # Formula:
        # W = Z * 2 + Y
        # Y = W % 2
        # Z = (W - Y) / 2 
        # Base: 76561197960265728
        try:
            sid64_int = int(steam_id)
            base_num = 76561197960265728
            if sid64_int > base_num:
                w = sid64_int - base_num
                y = w % 2
                z = (w - y) // 2
                # Standard format usually uses universe 1 for these accounts
                # Try both STEAM_0 and STEAM_1 just in case, but usually STEAM_1
                steam2_variants = [f"STEAM_1:{y}:{z}", f"STEAM_0:{y}:{z}"]
            else:
                steam2_variants = [steam_id] # Should not happen if valid 64
        except:
             steam2_variants = [steam_id]

        print(f"[*] Buscando variantes: {steam2_variants}")

        try:
            # Fetch all bans (API seems to return full list ~400 items)
            # Query params like ?search= exist but might fail if format differs. 
            # Safe bet: Fetch all and filter in Python.
            resp = self.session.get(api_url, timeout=10)
            if resp.status_code != 200:
                return {"source": "SirPlease", "error": f"API Error {resp.status_code}"}
            
            json_resp = resp.json()
            if not json_resp.get("success"):
                 return {"source": "SirPlease", "error": "API response not success"}
            
            ban_list = json_resp.get("data", [])
            found_bans = []
            player_name = "Unknown"

            for ban in ban_list:
                # ban['steam_id'] is e.g. "STEAM_1:1:593455009"
                b_sid = ban.get("steam_id", "")
                
                if b_sid in steam2_variants:
                    player_name = ban.get("player_name") or ban.get("name", "Unknown")
                    reason = ban.get("reason", "Unknown")
                    duration = ban.get("duration", 0) 
                    status_str = ban.get("status", "Banned")
                    created = ban.get("ban_date", "")
                    
                    details = f"[{created[:10]}] {reason} (Status: {status_str})"
                    if duration == 0:
                        details += " [Permanent]"
                    else:
                        details += f" [Duration: {duration}m]"
                        
                    found_bans.append(details)

            if found_bans:
                return {
                    "source": "SirPlease",
                    "status": "Found Records",
                    "history": found_bans,
                    "manual_check_url": f"https://sirplease.vercel.app/bans?search={steam_id}", # Keep web url for user
                    "player_name": player_name
                }
            
            return {"source": "SirPlease", "status": "Clean", "history": []}

        except Exception as e:
            return {"source": "SirPlease", "error": f"Request Error: {str(e)}"}

    def check_l4d2center(self, base_url, steam_id):
        """
        Scraper for L4D2Center using DrissionPage (Browser Automation)
        to bypass Cloudflare protection.
        Restored: Manual Navigation + Type Search (More robust against CF).
        """
        if base_url.endswith("/bans"):
             search_link = f"{base_url}/?search={steam_id}"
        else:
             search_link = f"{base_url}/bans/?search={steam_id}"

        print(f"[*] Verificando L4D2Center (Browser Interaction): {base_url} -> Search")

        page = None
        try:
            import os
            from DrissionPage import ChromiumPage, ChromiumOptions
            
            co = ChromiumOptions()
            co.auto_port()
            
            # Check for Docker/Headless env
            is_headless = os.getenv("HEADLESS", "false").lower() == "true"
            
            if is_headless:
                print("[*] Running in DOCKER mode with XVFB (Virtual Screen)...")
                # Important: valid HEADED mode to bypass Cloudflare
                co.headless(False) 
                co.set_argument('--no-sandbox')
                co.set_argument('--disable-gpu')
                co.set_argument('--disable-dev-shm-usage')
                
                # Explicitly set chromium path for Debian/Docker
                # In python:3.11-slim-bookworm + apt install chromium, it is usually here:
                co.set_browser_path('/usr/bin/chromium')
                
                # Anti-detection
                co.set_argument('--disable-blink-features=AutomationControlled')
                # MATCH OS: Use Linux UA for Docker (Render is Linux)
                co.set_user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                print("[*] Chromium path set to /usr/bin/chromium")
            else:
                co.headless(False)
                co.set_argument('--window-position=-10000,0') 

            co.set_argument('--window-size=1920,1080')
            
            page = ChromiumPage(co)
            
            # 1. Go to main bans page
            target_url = base_url
            if not target_url.endswith("/bans") and not target_url.endswith("/bans/"):
                 target_url = f"{target_url}/bans"
            
            page.get(target_url)
            
            import time
            import random
            
            # Wait for Cloudflare on initial load
            print(f"[*] Loading page: {target_url} ...")
            for i in range(25):
                title = page.title.lower() if page.title else "no-title"
                print(f"[DEBUG] Check {i}: Title='{title}'")
                
                # Human simulation: Random mouse moves
                try: 
                    page.actions.move(random.randint(100, 500), random.randint(100, 500), duration=0.2)
                except: 
                    pass
                
                # Try to find specific Cloudflare iframe/checkbox if implied
                try:
                    # Generic attempt to click any visible checkbox in probable turnstile frames
                    if "just a moment" in title:
                        frames = page.eles("tag:iframe")
                        for f in frames:
                             try:
                                 # blind click in center of iframe
                                 box = f.rect
                                 if box:
                                     cx = box.location[0] + box.size[0]/2
                                     cy = box.location[1] + box.size[1]/2
                                     page.actions.move(cx, cy).click()
                             except: pass
                except: pass

                if "just a moment" not in title and "cloudflare" not in title and "checking" not in title:
                     # Check for search box presence
                     if page.ele("css:input[name='search']") or page.ele("css:input[type='text']"):
                         print("[DEBUG] Search box found! Cloudflare passed.")
                         break
                time.sleep(1)
            else:
                 # Loop finished without break -> Timeout
                 print("[!] Timeout waiting for Cloudflare.")
                 if page: page.quit()
                 return {
                    "source": "L4D2Center",
                    "status": "Protected (Cloudflare)",
                    "history": ["No se pudo verificar automáticamente (Captcha). Revisa el link manual."],
                    "manual_check_url": search_link
                 }
            
            # 2. Interact
            try:
                search_box = page.ele("css:input[placeholder*='Search']") or page.ele("css:input[name='search']")
                if search_box:
                    print("[*] L4D2Center: Typing SteamID manually...")
                    search_box.clear()
                    search_box.input(steam_id)
                    page.actions.send_keys('\ue007') # Press Enter
                    
                    # Wait for results
                    time.sleep(1)
                    for k in range(10):
                         html_now = page.html.lower()
                         # Check if results updated (ID matches) or empty message
                         if steam_id in html_now and ("reason" in html_now or "expira" in html_now or "permanent" in html_now):
                              break
                         if "no bans found" in html_now:
                              break
                         time.sleep(1)
                else:
                    print("[!] Search box not found, trying fallback URL navigate...")
                    page.get(search_link)
                    time.sleep(4)
                    
            except Exception as e:
                print(f"[!] Interaction error: {e}, falling back to URL.")
                page.get(search_link)
                time.sleep(4)
            
            html_content = page.html
            page.quit() 
            
            soup = BeautifulSoup(html_content, "lxml")
            
            # Check protections
            text_lower = soup.get_text(" ", strip=True).lower()
            if "checking your browser" in text_lower or "enable javascript" in text_lower:
                 return {
                    "source": "L4D2Center",
                    "status": "Protected (Cloudflare)",
                    "history": ["No se pudo evadir la protección."],
                    "manual_check_url": search_link
                }
            
            if "no bans found" in text_lower or "0 bans" in text_lower:
                 return {"source": "L4D2Center", "status": "Clean", "history": []}
            
            history = []
            found_nickname = "Unknown"
            # Try to find the results table
            # Based on image: standard table structure
            rows = soup.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if not cols: 
                    continue
                
                # Check if this row belongs to the user (contains SteamID)
                # or if we assume all rows are relevant in this search view
                row_text = row.get_text()
                if steam_id in row_text:
                    try:
                        # 0: Nickname, 1: SteamID, ...
                        if len(cols) > 0:
                             found_nickname = cols[0].get_text(strip=True)
                        
                        # ... rest of parsing ...
                        unban_str = cols[3].get_text(strip=True)
                        reason = cols[4].get_text(strip=True)
                        if not reason:
                             reason = "Unknown" 
                        
                        desc = ""
                        if len(cols) > 5:
                            desc = cols[5].get_text(strip=True)
                        
                        ban_info = f"Reason: {reason}"
                        if desc:
                            ban_info += f" | Desc: {desc}"
                        ban_info += f" | Expira: {unban_str}"
                        
                        history.append(ban_info)
                    except:
                        history.append(row_text[:100])

            if history:
                 # Extract name from first row if available
                 return {
                    "source": "L4D2Center",
                    "status": "Found Records",
                    "history": history,
                    "manual_check_url": search_link,
                    "player_name": found_nickname # Capture this
                 }

            # Fallback text search if table parsing failed but ID is there
            if steam_id in html_content:
                 return {
                    "source": "L4D2Center",
                    "status": "Found Records",
                    "history": ["Registro detectado (No se pudieron leer detalles)."],
                    "manual_check_url": search_link
                 }

            # If not found, and no error -> Clean
            # NOTE: "No bans found" might strictly be for empty searches.
            # If checking arbitrary ID, it might just be empty list.
            return {"source": "L4D2Center", "status": "Clean", "history": []}

        except Exception as e:
            print(f"[ERROR] L4D2Center Failed: {e}")
            if page: 
                try: page.quit()
                except: pass
            return {
                "source": "L4D2Center",
                "error": f"Browser Error: {str(e)}", 
                "manual_check_url": search_link
            }

    def check_cedapug(self, base_url, steam_id):
        """
        Scrapes CedaPug.com bans using basic requests.
        Note: CedaPug seems to return "Invalid user" text or similar if the user is not found/clean via the search URL,
        or it might require converting SteamID. For now, we assume "Invalid user" == Clean.
        """
        search_link = f"{base_url}?SteamId={steam_id}"
        print(f"[*] Verificando CedaPug: {search_link}")

        try:
            # Simple GET request
            resp = self.session.get(search_link, timeout=10)
            
            if "Invalid user" in resp.text:
                # Likely implies user not found in ban DB or bad format
                return {"source": "CedaPug", "status": "Clean", "history": []}
            
            soup = BeautifulSoup(resp.content, "lxml")
            
            ban_lines = soup.find_all("div", class_="ban-line")
            found_bans = []
            import datetime
            import re

            for line in ban_lines:
                text = line.get_text(separator="|", strip=True)
                
                # Double check steamID presence just in case query param didn't filter
                if steam_id not in text:
                    continue
                
                # Regex logic
                reason_match = re.search(r"Reason\|(.*?)(?:\||$)", text, re.IGNORECASE)
                start_match = re.search(r"Start\|(\d+)", text)
                
                reason = "Unknown Reason"
                date_str = "?"
                
                if reason_match:
                    reason = reason_match.group(1).strip()
                
                if start_match:
                    try:
                        ts = int(start_match.group(1))
                        if ts <= 0:
                            date_str = "?"
                        else:
                            d = datetime.datetime.fromtimestamp(ts)
                            if d.year < 2010: # Safety check
                                date_str = "?"
                            else:
                                date_str = d.strftime('%Y-%m-%d')
                    except:
                        pass

                if reason == "Unknown Reason" and date_str == "?":
                     clean_text = text.replace("Unban Reason", "").replace("Banned By", "By:").replace("Reason", "Reason:").strip()
                     found_bans.append(clean_text[:100])
                else:
                     found_bans.append(f"[{date_str}] {reason}")
            
            if found_bans:
                 return {
                    "source": "CedaPug",
                    "status": "Found Records",
                    "history": found_bans,
                    "manual_check_url": search_link
                 }
            
            # If no bans found and no "Invalid user" text?
            return {"source": "CedaPug", "status": "Clean", "history": []}

        except Exception as e:
            return {"source": "CedaPug", "error": str(e), "manual_check_url": search_link}

    def get_bans(self, input_check):
        """
        Main method to get all bans. Returns a dictionary with structure:
        {
            "steam_id": "...",
            "summary": [ {source, status, details}, ... ],
            "results": [ {source, status, history: []}, ... ]
        }
        """
        steam_id = self.resolve_steam_id(input_check)
        if not steam_id:
            return None

        # Collect results
        results_list = []

        for source in SOURCES:
            if source["type"] == "steam_official":
                res = self.check_steam_official(steam_id)
            elif source["type"] == "l4d2center_api" or source["name"] == "L4D2Center":
                res = self.check_l4d2center(source["url"], steam_id)
            elif source["type"] == "cedapug_scrape":
                res = self.check_cedapug(source["url"], steam_id)
            elif source["type"] == "custom_sirplease":
                res = self.check_sirplease_custom(source["url"], steam_id)
            else:
                res = {"source": source["name"], "status": "Skipped", "history": []}
            results_list.append(res)
            
        return {
            "steam_id": steam_id,
            "results": results_list
        }

    # Helper to find related IDs in ban history text
    def _extract_related_ids(self, results):
        related = set()
        for source in results:
            if "history" in source:
                for record in source["history"]:
                    # Pattern 1: "Duplicate of banned account (STEAM_... or 765...)"
                    match = re.search(r"Duplicate of banned account \((\d{17})\)", record)
                    if match:
                        related.add(match.group(1))
                    
                    # Pattern 2: "only allowed to play from: 765...,765..."
                    if "only allowed to play from" in record.lower():
                         ids = re.findall(r"7656\d{13}", record)
                         for i in ids:
                             related.add(i)
        return related

    def get_live_steam_details(self, steam_id):
        """
        Fetches public profile info (Name, Avatar) from Steam XML.
        Returns dict or None
        """
        try:
            url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                tree = ET.fromstring(resp.content)
                name_elem = tree.find("steamID")
                avatar_elem = tree.find("avatarFull") 
                
                # Check privacy or error
                error = tree.find("error")
                if error is not None:
                     return {"name": "[Privado/Error]", "avatar": ""}
                
                return {
                    "name": name_elem.text if name_elem is not None else "Unknown",
                    "avatar": avatar_elem.text if avatar_elem is not None else ""
                }
        except Exception as e:
            print(f"[!] Error gathering steam details: {e}")
        return None

    def get_all_bans_generator(self, start_input):
        """
        Generator for SSE progress updates.
        Yields: {"type": "progress"|"complete"|"error"|"info", "msg": "...", "result": data}
        """
        yield {"type": "progress", "msg": f"Resolviendo Steam ID: {start_input}..."}
        
        start_id = self.resolve_steam_id(start_input)
        if not start_id:
              yield {"type": "error", "msg": "No se pudo resolver el Steam ID. Verifique la URL/ID."}
              return
        
        yield {"type": "progress", "msg": f"ID Resuelto: {start_id}"}
        
        # Initial setup
        visited = set()
        queue = [start_id]
        
        all_players_data = [] 
        
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            
            visited.add(current_id)
            
            # --- START PER-ACCOUNT PROCESSING ---
            
            # 1. Fetch Profile Details (Avatar, Name)
            yield {"type": "progress", "msg": "Obteniendo datos de perfil..."}
            details = self.get_live_steam_details(current_id)
            name = details.get("name", "Unknown") if details else "Unknown"
            avatar = details.get("avatar", "") if details else ""
            
            # Send INFO update to UI (For main account or Smurf)
            # If it's a smurf, the UI might handle it differently or just update the "Scanning..." card
            yield {"type": "info", "msg": f"Analizando a: {name}", "avatar": avatar, "name": name, "steam_id": current_id}

            if current_id != start_id:
                 yield {"type": "progress", "msg": f"🔍 Analizando Smurf: {name} ({current_id})..."}
            else:
                 yield {"type": "progress", "msg": f"Analizando cuenta principal: {current_id}..."}
            
            bans_found = []
            
            for source in SOURCES:
                 s_name = source["name"]
                 yield {"type": "progress", "msg": f"Consultando {s_name}..."}
                 
                 res = {}
                 try:
                    if source["type"] == "steam_official":
                        res = self.check_steam_official(current_id)
                    elif source["type"] == "l4d2center_api":
                        # Add extra notification since this is slow
                        res = self.check_l4d2center(source["url"], current_id)
                    elif source["type"] == "cedapug_scrape":
                        res = self.check_cedapug(source["url"], current_id)
                    elif source["type"] == "custom_sirplease":
                        res = self.check_sirplease_custom(source["url"], current_id)
                    else:
                        res = {"source": s_name, "status": "Unknown", "history": []}
                 except Exception as e:
                     res = {"source": s_name, "status": "Error", "history": [str(e)]}

                 if res.get("status") in ["Found Records", "Banned", "BANNED"]:
                       yield {"type": "progress", "msg": f"⚠️ {s_name}: ¡ENCONTRADO!"}
                 else:
                       yield {"type": "success", "msg": f"{s_name}: Limpio"}
                 
                 bans_found.append(res)
                 
            # Construct player object
            player_data = {
                "steam_id": current_id,
                "profile_url": f"https://steamcommunity.com/profiles/{current_id}",
                "player_name": name, # Now redundant but kept for structure
                "results": bans_found,
                "avatar": avatar # Important for Results Page
            }
            
            # Simple smurf extraction placeholder
            detected_ids = self._extract_related_ids(bans_found)
            for rid in detected_ids:
                 if rid not in visited and rid not in queue:
                      queue.append(rid)
                      yield {"type": "progress", "msg": f"Cola: Posible Smurf {rid}"}

            all_players_data.append(player_data)
            
            # Limit to prevent infinite loop
            if len(all_players_data) >= 3: 
                 yield {"type": "progress", "msg": "Límite de profundidad (3 cuentas) alcanzado."}
                 break

        yield {"type": "complete", "result": all_players_data}

    def get_all_bans(self, start_input):
        # Wrapper for legacy compatibility
        gen = self.get_all_bans_generator(start_input)
        final = None
        for item in gen:
            if item["type"] == "complete":
                final = item["result"]
        return final

