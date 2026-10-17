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
        "url": "https://sirplease.net/api/bans",
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
        self._browser_page = None
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

    def _get_browser_page(self):
        """
        Returns an active ChromiumPage configured with silent headless/minimized flags.
        Reuses the existing page instance if alive, otherwise launches a new one.
        """
        if self._browser_page is not None:
            try:
                _ = self._browser_page.title
                return self._browser_page
            except Exception:
                try:
                    self._browser_page.quit()
                except Exception:
                    pass
                self._browser_page = None

        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.auto_port()

        force_headed = os.getenv("FORCE_HEADED", "false").lower() == "true"
        if not force_headed:
            co.set_argument('--headless=new')

        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--mute-audio')
        co.set_argument('--window-size=1920,1080')
        co.set_argument('--window-position=-32000,-32000')
        co.set_argument('--start-minimized')

        for candidate_path in ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']:
            if os.path.exists(candidate_path):
                co.set_browser_path(candidate_path)
                break

        co.set_user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

        self._browser_page = ChromiumPage(co)
        return self._browser_page

    def close_browser(self):
        """
        Gracefully closes the reused browser instance if active.
        """
        if self._browser_page is not None:
            try:
                self._browser_page.quit()
            except Exception:
                pass
            finally:
                self._browser_page = None

    def resolve_steam_id(self, input_str):
        """
        Resolves a Steam Profile URL (vanity or ID64), SteamID2, SteamID3, or vanity name to a SteamID64 string.
        """
        if not input_str:
            return None
        input_str = input_str.strip()

        # Already an ID64? (17 digits)
        if re.match(r'^\d{17}$', input_str):
            return input_str

        # Check for SteamID2 format (STEAM_0:X:Y or STEAM_1:X:Y)
        s2 = self.steam2_to_steam64(input_str)
        if s2:
            return s2

        # Check for SteamID3 format ([U:1:X] or U:1:X)
        s3 = self.steam3_to_steam64(input_str)
        if s3:
            return s3

        # URL parsing
        # Check for /profiles/ (Direct ID)
        match_profiles = re.search(r'steamcommunity\.com/profiles/(\d{17})', input_str)
        if match_profiles:
            return match_profiles.group(1)

        # Check for /id/ (Vanity URL)
        match_id = re.search(r'steamcommunity\.com/id/([^/?]+)', input_str)
        if match_id:
            vanity = match_id.group(1)
            return self._resolve_vanity_xml(vanity)

        # If user just gave the vanity name without URL
        if not "/" in input_str and not input_str.isdigit():
            return self._resolve_vanity_xml(input_str)

        print(f"Error: No se pudo interpretar el input: {input_str}")
        return None

    def parse_multiple_steam_inputs(self, raw_text):
        """
        Parses single or bulk text (e.g. L4D2 console 'status' output, list of URLs, SteamID2, SteamID3, SteamID64, or vanity names)
        and extracts all unique 17-digit SteamID64 strings in order of discovery.
        """
        if not raw_text:
            return []

        resolved_ids = []
        seen = set()

        def add_id(sid):
            if sid and isinstance(sid, str):
                sid = sid.strip()
                if re.match(r'^\d{17}$', sid):
                    if sid not in seen:
                        seen.add(sid)
                        resolved_ids.append(sid)

        pattern = re.compile(
            r'(?:steamcommunity\.com/profiles/(?P<prof>7656\d{13}))|'
            r'(?:steamcommunity\.com/id/(?P<vanity>[a-zA-Z0-9_-]+))|'
            r'(?P<steam2>STEAM_[01]:[01]:\d+)|'
            r'(?P<steam3>\[?U:1:\d+\]?)|'
            r'(?:\b(?P<id64>7656\d{13})\b)',
            re.IGNORECASE
        )

        matches_found = False
        for match in pattern.finditer(raw_text):
            matches_found = True
            gd = match.groupdict()
            if gd.get('prof'):
                add_id(gd['prof'])
            elif gd.get('vanity'):
                resolved = self._resolve_vanity_xml(gd['vanity'])
                if resolved:
                    add_id(resolved)
            elif gd.get('steam2'):
                add_id(self.steam2_to_steam64(gd['steam2']))
            elif gd.get('steam3'):
                add_id(self.steam3_to_steam64(gd['steam3']))
            elif gd.get('id64'):
                add_id(gd['id64'])

        # Fallback if no regex pattern matched in raw_text:
        # Split raw_text by newlines, commas, or spaces and try resolve_steam_id for tokens
        if not matches_found or not resolved_ids:
            tokens = re.split(r'[\r\n,\s]+', raw_text.strip())
            for tok in tokens:
                tok = tok.strip()
                if tok:
                    res = self.resolve_steam_id(tok)
                    if res:
                        add_id(res)

        return resolved_ids

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

    def steam2_to_steam64(self, steam2_str):
        """
        Converts SteamID2 (STEAM_0:Y:Z or STEAM_1:Y:Z) to SteamID64 string.
        Formula: 76561197960265728 + (Z * 2) + Y
        """
        m = re.search(r'STEAM_[01]:([01]):(\d+)', steam2_str, re.IGNORECASE)
        if m:
            y = int(m.group(1))
            z = int(m.group(2))
            return str(76561197960265728 + (z * 2) + y)
        return None

    def steam3_to_steam64(self, steam3_str):
        """
        Converts SteamID3 ([U:1:W] or U:1:W) to SteamID64 string.
        Formula: 76561197960265728 + W
        """
        m = re.search(r'\[?U:1:(\d+)\]?', steam3_str, re.IGNORECASE)
        if m:
            w = int(m.group(1))
            return str(76561197960265728 + w)
        return None

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
        Fetches SirPlease bans using their API: https://sirplease.net/api/bans
        Critically: The API uses SteamID2 format (STEAM_1:x:y), NOT SteamID64.
        We calculate the SteamID2 from the 64-bit ID and use the search query param.
        """
        api_url = "https://sirplease.net/api/bans"

        # Calculate y and z from steam_id (SteamID64, base 76561197960265728)
        try:
            sid64_int = int(steam_id)
            base_num = 76561197960265728
            if sid64_int > base_num:
                w = sid64_int - base_num
                y = w % 2
                z = (w - y) // 2
                steam_suffix = f"{y}:{z}"
                steam2_variants = [f"STEAM_1:{y}:{z}", f"STEAM_0:{y}:{z}"]
            else:
                steam_suffix = steam_id
                steam2_variants = [steam_id]
        except:
            steam_suffix = steam_id
            steam2_variants = [steam_id]

        print(f"[*] Verificando SirPlease (API): {api_url} con búsqueda: {steam_suffix}")

        try:
            resp = self.session.get(api_url, params={"search": steam_suffix}, timeout=10)
            if resp.status_code != 200:
                return {
                    "source": "SirPlease",
                    "error": f"API Error {resp.status_code}",
                    "status": "Error",
                    "history": [],
                    "manual_check_url": f"https://sirplease.net/bans?search={steam2_variants[0]}",
                    "related_ids": []
                }

            json_resp = resp.json()
            if not json_resp.get("success"):
                return {
                    "source": "SirPlease",
                    "error": "API response not success",
                    "status": "Error",
                    "history": [],
                    "manual_check_url": f"https://sirplease.net/bans?search={steam2_variants[0]}",
                    "related_ids": []
                }

            ban_list = json_resp.get("data", [])
            found_bans = []
            player_name = "Unknown"
            related_steam2_ids = set()

            for ban in ban_list:
                b_sid = ban.get("steam_id", "")
                reason = ban.get("reason", "Unknown")

                # Match a ban record if b_sid in steam2_variants OR if steam_suffix in reason (or any variant in steam2_variants is in reason)
                if not (b_sid in steam2_variants or steam_suffix in reason or any(v in reason for v in steam2_variants)):
                    continue

                if b_sid in steam2_variants:
                    player_name = ban.get("player_name") or ban.get("name", "Unknown")

                duration = ban.get("duration", 0)
                status_str = ban.get("status", "Banned")
                created = ban.get("ban_date", "")

                details = f"[{created[:10]}] {reason} (Status: {status_str})"
                if duration == 0:
                    details += " [Permanent]"
                else:
                    details += f" [Duration: {duration}m]"

                if b_sid not in steam2_variants:
                    details += f" (Linked Account: {b_sid} - {ban.get('player_name', 'Unknown')})"

                found_bans.append(details)

                # Collect any STEAM_[01]:[01]:\d+ found in b_sid or ban.get("reason", "") (not in steam2_variants)
                for candidate in re.findall(r"STEAM_[01]:[01]:\d+", f"{b_sid} {reason}"):
                    if candidate not in steam2_variants:
                        related_steam2_ids.add(candidate)

            if found_bans:
                return {
                    "source": "SirPlease",
                    "status": "Found Records",
                    "history": found_bans,
                    "manual_check_url": f"https://sirplease.net/bans?search={steam2_variants[0]}",
                    "player_name": player_name,
                    "related_ids": list(related_steam2_ids)
                }

            return {
                "source": "SirPlease",
                "status": "Clean",
                "history": [],
                "manual_check_url": f"https://sirplease.net/bans?search={steam2_variants[0]}",
                "related_ids": []
            }

        except Exception as e:
            return {
                "source": "SirPlease",
                "error": f"Request Error: {str(e)}",
                "status": "Error",
                "history": [],
                "manual_check_url": f"https://sirplease.net/bans?search={steam2_variants[0]}",
                "related_ids": []
            }

    def check_l4d2center(self, base_url, steam_id):
        """
        Scraper for L4D2Center using DrissionPage (Browser Automation)
        to bypass Cloudflare protection with reused silent headless session.
        """
        if base_url.endswith("/bans"):
            search_link = f"{base_url}/?search={steam_id}"
        else:
            search_link = f"{base_url}/bans/?search={steam_id}"

        steam2_id = self.steam64_to_id2(steam_id)
        try:
            sid64_int = int(steam_id)
            base_num = 76561197960265728
            if sid64_int > base_num:
                w = sid64_int - base_num
                y = w % 2
                z = (w - y) // 2
                steam_suffix = f"{y}:{z}"
            else:
                steam_suffix = steam_id
        except Exception:
            steam_suffix = steam_id

        print(f"[*] Verificando L4D2Center (Browser Interaction): {base_url} -> Search {steam_id}")

        page = None
        try:
            page = self._get_browser_page()

            # Target URL
            target_url = base_url
            if not target_url.endswith("/bans") and not target_url.endswith("/bans/"):
                target_url = f"{target_url}/bans"

            current_url = getattr(page, 'url', '') or ''
            if not current_url.startswith(target_url):
                page.get(target_url)

            import time
            import random

            # Wait for Cloudflare on initial load if needed
            print(f"[*] Loading page: {target_url} ...")
            for i in range(25):
                title = page.title.lower() if page.title else "no-title"
                print(f"[DEBUG] Check {i}: Title='{title}'")

                try:
                    page.actions.move(random.randint(100, 500), random.randint(100, 500), duration=0.2)
                except Exception:
                    pass

                try:
                    if "just a moment" in title:
                        frames = page.eles("tag:iframe")
                        for f in frames:
                            try:
                                box = f.rect
                                if box:
                                    cx = box.location[0] + box.size[0] / 2
                                    cy = box.location[1] + box.size[1] / 2
                                    page.actions.move(cx, cy).click()
                            except Exception:
                                pass
                except Exception:
                    pass

                if "just a moment" not in title and "cloudflare" not in title and "checking" not in title:
                    if page.ele("css:input[name='search']") or page.ele("css:input[type='text']"):
                        print("[DEBUG] Search box found! Cloudflare passed.")
                        break
                time.sleep(1)
            else:
                print("[!] Timeout waiting for Cloudflare.")
                return {
                    "source": "L4D2Center",
                    "status": "Protected (Cloudflare)",
                    "history": ["No se pudo verificar automáticamente (Captcha). Revisa el link manual."],
                    "manual_check_url": search_link,
                    "related_ids": []
                }

            # Interact with search box
            try:
                search_box = page.ele("css:input[placeholder*='Search']") or page.ele("css:input[name='search']")
                if search_box:
                    print("[*] L4D2Center: Typing SteamID manually...")
                    search_box.clear()
                    search_box.input(steam_id)
                    page.actions.send_keys('')  # Press Enter

                    time.sleep(1)
                    for k in range(10):
                        html_now = page.html.lower()
                        if (steam_id in html_now or steam2_id.lower() in html_now or steam_suffix in html_now) and ("reason" in html_now or "expira" in html_now or "permanent" in html_now):
                            break
                        if "no bans found" in html_now or "0 bans" in html_now:
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
            soup = BeautifulSoup(html_content, "lxml")

            text_lower = soup.get_text(" ", strip=True).lower()
            if "checking your browser" in text_lower or "enable javascript" in text_lower:
                return {
                    "source": "L4D2Center",
                    "status": "Protected (Cloudflare)",
                    "history": ["No se pudo evadir la protección."],
                    "manual_check_url": search_link,
                    "related_ids": []
                }

            if "no bans found" in text_lower or "0 bans" in text_lower:
                return {"source": "L4D2Center", "status": "Clean", "history": [], "manual_check_url": search_link, "related_ids": []}

            history = []
            found_nickname = "Unknown"
            related_ids = set()

            rows = soup.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if not cols:
                    continue

                row_text = row.get_text()
                match_id = (steam_id in row_text) or (steam2_id in row_text) or (steam_suffix in row_text)
                if match_id:
                    try:
                        if len(cols) > 0:
                            found_nickname = cols[0].get_text(strip=True)

                        unban_str = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                        reason = cols[4].get_text(strip=True) if len(cols) > 4 else "Unknown"
                        desc = cols[5].get_text(strip=True) if len(cols) > 5 else ""

                        ban_info = f"Reason: {reason}"
                        if desc:
                            ban_info += f" | Desc: {desc}"
                        if unban_str:
                            ban_info += f" | Expira: {unban_str}"

                        history.append(ban_info)
                    except Exception:
                        history.append(row_text)

                    # Extract any related steam IDs in this matched row text
                    for cand in re.findall(r'7656\d{13}|STEAM_[01]:[01]:\d+|\[?U:1:\d+\]?', row_text, re.IGNORECASE):
                        if cand != steam_id and cand != steam2_id and steam_suffix not in cand:
                            related_ids.add(cand)

            if history:
                return {
                    "source": "L4D2Center",
                    "status": "Found Records",
                    "history": history,
                    "manual_check_url": search_link,
                    "player_name": found_nickname,
                    "related_ids": list(related_ids)
                }

            if steam_id in html_content or steam2_id in html_content:
                for cand in re.findall(r'7656\d{13}|STEAM_[01]:[01]:\d+|\[?U:1:\d+\]?', html_content, re.IGNORECASE):
                    if cand != steam_id and cand != steam2_id and steam_suffix not in cand:
                        related_ids.add(cand)
                return {
                    "source": "L4D2Center",
                    "status": "Found Records",
                    "history": ["Registro detectado (No se pudieron leer detalles)."],
                    "manual_check_url": search_link,
                    "related_ids": list(related_ids)
                }

            return {"source": "L4D2Center", "status": "Clean", "history": [], "manual_check_url": search_link, "related_ids": []}

        except Exception as e:
            print(f"[ERROR] L4D2Center Failed: {e}")
            self.close_browser()
            return {
                "source": "L4D2Center",
                "error": f"Browser Error: {str(e)}",
                "status": "Error",
                "history": [],
                "manual_check_url": search_link,
                "related_ids": []
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
        try:
            steam_id = self.resolve_steam_id(input_check)
            if not steam_id:
                return None

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
        finally:
            self.close_browser()

    def _extract_related_ids(self, results, current_id=None):
        """
        Universal smurf extractor: scans all history entries and related_ids lists.
        Extracts SteamID64, SteamID2 (converted), SteamID3 (converted), profile URLs, and vanity URLs.
        Returns a deduplicated list of 17-digit SteamID64 strings, excluding current_id.
        """
        discovered = []
        seen = set()

        def add_candidate(cand):
            if cand and isinstance(cand, str):
                cand = cand.strip()
                if cand != current_id and re.match(r'^\d{17}$', cand):
                    if cand not in seen:
                        seen.add(cand)
                        discovered.append(cand)

        for source in results:
            texts = []
            if "history" in source and isinstance(source["history"], list):
                texts.extend(source["history"])
            if "related_ids" in source and isinstance(source["related_ids"], list):
                texts.extend(source["related_ids"])

            for text in texts:
                if not isinstance(text, str):
                    continue

                # 1. steamcommunity.com/profiles/(7656\d{13})
                for prof_id in re.findall(r'steamcommunity\.com/profiles/(7656\d{13})', text):
                    add_candidate(prof_id)

                # 2. steamcommunity.com/id/([a-zA-Z0-9_-]+)
                for vanity in re.findall(r'steamcommunity\.com/id/([a-zA-Z0-9_-]+)', text):
                    resolved = self._resolve_vanity_xml(vanity)
                    if resolved:
                        add_candidate(resolved)

                # 3. STEAM_[01]:[01]:\d+ -> convert to 64
                for s2 in re.findall(r'STEAM_[01]:[01]:\d+', text, re.IGNORECASE):
                    add_candidate(self.steam2_to_steam64(s2))

                # 4. \[?U:1:\d+\]? -> convert to 64
                for s3 in re.findall(r'\[?U:1:\d+\]?', text, re.IGNORECASE):
                    add_candidate(self.steam3_to_steam64(s3))

                # 5. 7656\d{13}
                for s64 in re.findall(r'7656\d{13}', text):
                    add_candidate(s64)

        return discovered

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
        Yields: {"type": "progress"|"complete"|"error"|"info"|"player_result", "msg": "...", "result": data, "player": player_data}
        """
        yield {"type": "progress", "msg": "Analizando entrada y resolviendo Steam IDs..."}

        initial_ids = self.parse_multiple_steam_inputs(start_input)
        if not initial_ids:
            yield {"type": "error", "msg": "No se pudo identificar ningún Steam ID válido en el texto ingresado."}
            return

        yield {"type": "progress", "msg": f"Jugadores detectados en cola inicial: {len(initial_ids)}"}

        visited = set()
        queued_ids = set(initial_ids)
        queue = [{"steam_id": sid, "is_smurf": False, "smurf_of": None, "smurf_of_name": None} for sid in initial_ids]

        all_players_data = []

        try:
            while queue:
                item = queue.pop(0)
                current_id = item["steam_id"]
                if current_id in visited:
                    continue

                visited.add(current_id)

                # --- START PER-ACCOUNT PROCESSING ---

                # 1. Fetch Profile Details (Avatar, Name)
                yield {"type": "progress", "msg": f"Obteniendo datos de perfil ({current_id})..."}
                details = self.get_live_steam_details(current_id)
                name = details.get("name", "Unknown") if details else "Unknown"
                avatar = details.get("avatar", "") if details else ""

                yield {"type": "info", "msg": f"Analizando a: {name}", "avatar": avatar, "name": name, "steam_id": current_id}

                if item["is_smurf"]:
                    smurf_origin = item["smurf_of_name"] or item["smurf_of"]
                    yield {"type": "progress", "msg": f"🔍 Analizando Smurf vinculado a {smurf_origin}: {name} ({current_id})..."}
                else:
                    yield {"type": "progress", "msg": f"Analizando jugador: {name} ({current_id})..."}

                bans_found = []

                for source in SOURCES:
                    s_name = source["name"]
                    yield {"type": "progress", "msg": f"Consultando {s_name}..."}

                    res = {}
                    try:
                        if source["type"] == "steam_official":
                            res = self.check_steam_official(current_id)
                        elif source["type"] == "l4d2center_api":
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

                # Fallback for player name if Steam profile was private/unknown
                if name in ["Unknown", "[Privado/Error]", None, ""]:
                    for b in bans_found:
                        p_name = b.get("player_name")
                        if p_name and p_name not in ["Unknown", "[Privado/Error]", ""]:
                            name = p_name
                            break

                # Smurf detection & queueing
                detected_ids = self._extract_related_ids(bans_found, current_id=current_id)
                for rid in detected_ids:
                    if rid not in visited and rid not in queued_ids:
                        queued_ids.add(rid)
                        queue.append({
                            "steam_id": rid,
                            "is_smurf": True,
                            "smurf_of": current_id,
                            "smurf_of_name": name
                        })
                        yield {"type": "progress", "msg": f"🔗 Smurf detectado en historial de {name}: {rid} (añadido a la cola)"}

                # Construct player object
                player_data = {
                    "steam_id": current_id,
                    "profile_url": f"https://steamcommunity.com/profiles/{current_id}",
                    "player_name": name,
                    "results": bans_found,
                    "avatar": avatar,
                    "is_smurf": item["is_smurf"],
                    "smurf_of": item["smurf_of"],
                    "smurf_of_name": item["smurf_of_name"]
                }
                all_players_data.append(player_data)

                # Immediately yield player_result for live rendering
                yield {"type": "player_result", "player": player_data}

            yield {"type": "complete", "result": all_players_data}
        finally:
            self.close_browser()

    def get_all_bans(self, start_input):
        # Wrapper for legacy compatibility
        gen = self.get_all_bans_generator(start_input)
        final = None
        for item in gen:
            if item["type"] == "complete":
                final = item["result"]
        return final

