# Zillabot.py 
# A Discord bot that detects Zillow links in messages and then fetches property details
#
# Date: June 5th, 2024
# Last Updated: June 9th, 2024
# Author: Matt G

# Library Import
import discord # Discord.py
import re # Hieroglyphics
import sqlite3 # Database stuff
import requests # Web requests stuff
from bs4 import BeautifulSoup # Web data parsing stuff

# Define bot intents (These are what the bot can do based of discord dev portal)
intents = discord.Intents.default() # Include default intents
intents.message_content = True # Needs message content to see messages

# Loads discord token from token.dat file so that it's not hardcoded in the script
def load_token_from_file(token_file_path: str) -> str:
    with open(token_file_path, "r") as token_file:
        return token_file.readline().strip()

# Initializes the database and creates the properties table if it doesn't exist
# SQLite!
def init_db(db_path="Data/zillow_properties.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            name TEXT,
            price TEXT,
            size TEXT,
            hospital_name TEXT,
            hospital_distance_miles REAL
        )
    """)
    conn.commit()
    conn.close()

# Save property info to the database
def save_property_to_db(url, name, price, size, hospital_name, hospital_distance_miles, db_path="Data/zillow_properties.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO properties (url, name, price, size, hospital_name, hospital_distance_miles) VALUES (?, ?, ?, ?, ?, ?)",
        (url, name, price, size, hospital_name, hospital_distance_miles)
    )
    conn.commit()
    conn.close()

# Fetch property details from Zillow
def get_property_details_from_zillow(url):
    try:
        # Use Mozilla user agent to avoid zillow bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Referer": "https://www.google.com/",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Name
        title = soup.title.string if soup.title else "Unknown Property"
        name = title.replace(" | Zillow", "").strip()
        # Price
        price = "Unknown"
        price_tag = soup.find("span", string=re.compile(r"\$\d[\d,]*"))
        if price_tag:
            price = price_tag.get_text(strip=True)
        # Size
        size = "Unknown"
        size_tag = soup.find(string=re.compile(r"[\d,]+ ?sqft"))
        if size_tag:
            size = size_tag.strip()
        # Address
        address = None
        # Try several methods to extract the full address robustly
        # 1. Try meta tags (most reliable)
        meta_street = soup.find("meta", {"property": "og:street-address"})
        meta_city = soup.find("meta", {"property": "og:locality"})
        meta_state = soup.find("meta", {"property": "og:region"})
        meta_zip = soup.find("meta", {"property": "og:postal-code"})
        if meta_street and meta_city and meta_state and meta_zip:
            address = f"{meta_street['content']}, {meta_city['content']}, {meta_state['content']} {meta_zip['content']}"
        # 2. Try span with data-testid (sometimes used by Zillow)
        if not address:
            span_addr = soup.find("span", {"data-testid": "home-details-summary-headline"})
            if span_addr:
                address = span_addr.get_text(strip=True)
        # 3. Try h1 with data-testid (legacy fallback)
        if not address:
            address_tag = soup.find("h1", {"data-testid": "home-details-summary-headline"})
            if address_tag:
                address = address_tag.get_text(strip=True)
        # 4. Try address container (older Zillow markup)
        if not address:
            addr_container = soup.find("h1", class_=re.compile(r"ds-address-container|Text-c11n-8-65-2__sc-aiai24-0"))
            if addr_container:
                address = addr_container.get_text(separator=" ", strip=True)
        # 5. Try address tag
        if not address:
            addr_tag = soup.find("address")
            if addr_tag:
                address = addr_tag.get_text(separator=" ", strip=True)
        # 6. Fallback to previous logic (title parsing)
        if not address:
            if name:
                clean_name = name.split('|')[0].replace(",", "").strip()
                words = clean_name.split()
                street_part = " ".join(words[:3])
                zip_part = words[-1] if len(words) > 0 else ""
                address = f"{street_part} {zip_part}".strip()
        # 7. If still not found, set to None and print error
        if not address:
            print("Could not extract address from Zillow page.")
            address = None
        print(f"address: {address}")
        return name, price, size, address
    except Exception as e:
        return f"Error fetching property: {e}", "Unknown", "Unknown", None

# Find the nearest hospital using OpenStreetMap Nominatim and Overpass API
# Thanks chatgpt
def get_nearest_hospital(address):
    """
    Uses OpenStreetMap Nominatim and Overpass API to find the nearest full-service hospital (with emergency).
    Returns (hospital_name, distance_in_miles).
    No API key required.
    """
    hospital_name = None
    hospital_distance_miles = None
    if not address:
        print("No address provided.")
        print(address)
        return hospital_name, hospital_distance_miles
    # Clean address: remove anything after a pipe or "MLS"
    address = address.split('|')[0].strip()
    address = re.sub(r"MLS\s*#\w+", "", address, flags=re.IGNORECASE).strip()
    try:
        # Geocode address using Nominatim
        print(f"Geocoding address: {address}")
        nominatim_url = f"https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        geo_resp = requests.get(nominatim_url, params=params, headers={"User-Agent": "Zillabot/1.0"}, timeout=10)
        geo_data = geo_resp.json()
        print(f"Nominatim response: {geo_data}")
        if geo_data:
            lat = float(geo_data[0]['lat'])
            lon = float(geo_data[0]['lon'])
            # Now use Nominatim to search for hospitals near this lat/lon
            search_url = "https://nominatim.openstreetmap.org/search.php"
            search_params = {
                "q": f"hospital near {lat},{lon}",
                "format": "jsonv2",
                "limit": 20
            }
            try:
                search_resp = requests.get(search_url, params=search_params, headers={"User-Agent": "Zillabot/1.0"}, timeout=15)
                if search_resp.status_code != 200:
                    print(f"Nominatim hospital search HTTP error: {search_resp.status_code}")
                    hospital_name = "Nominatim hospital search failed (HTTP error)"
                    hospital_distance_miles = None
                    return hospital_name, hospital_distance_miles
                try:
                    hospitals = search_resp.json()
                except Exception as json_err:
                    print(f"Nominatim hospital search JSON decode error: {json_err}")
                    hospital_name = "Nominatim hospital search failed (invalid response)"
                    hospital_distance_miles = None
                    return hospital_name, hospital_distance_miles
                print(f"Nominatim hospital search response: {hospitals}")
                # Calculate distances and pick the closest with 'hospital' in the name
                from math import radians, sin, cos, sqrt, atan2
                best = None
                best_dist = None
                for h in hospitals:
                    if 'display_name' in h and 'lat' in h and 'lon' in h:
                        name = h.get('display_name', '')
                        if 'hospital' not in name.lower():
                            continue
                        hospital_short_name = name.split(',')[0].strip()
                        hosp_lat = float(h['lat'])
                        hosp_lon = float(h['lon'])
                        dlat = radians(hosp_lat - lat)
                        dlon = radians(hosp_lon - lon)
                        R_miles = 3958.8
                        a = sin(dlat/2)**2 + cos(radians(lat)) * cos(radians(hosp_lat)) * sin(dlon/2)**2
                        c = 2 * atan2(sqrt(a), sqrt(1-a))
                        dist_miles = R_miles * c
                        print(f"Found hospital: {name} at {dist_miles:.2f} miles (lat: {hosp_lat}, lon: {hosp_lon})")
                        if best is None or dist_miles < best_dist:
                            best = (hospital_short_name, dist_miles)
                            best_dist = dist_miles
                if best:
                    print(f"Selected nearest hospital: {best[0]} at {best[1]:.2f} miles")
                    hospital_name = best[0]
                    hospital_distance_miles = round(best[1], 2)
                else:
                    print("No hospital found in Nominatim search.")
            except Exception as search_e:
                print(f"Nominatim hospital search error: {search_e}")
                hospital_name = "Nominatim hospital search failed (timeout or error)"
                hospital_distance_miles = None
                return hospital_name, hospital_distance_miles
        else:
            print("No geocoding result from Nominatim.")
            hospital_name = "Sorry, I couldn't Geocode Address with OpenStreetMap :("
            hospital_distance_miles = None
        return hospital_name, hospital_distance_miles
    except Exception as e:
        print(f"Hospital lookup error: {e}")
        return hospital_name, hospital_distance_miles

# ZillowBot Class Declaration
class ZillowBot(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        init_db()

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Check for zillow.com links
        zillow_links = re.findall(r'https?://(?:www\.)?zillow\.com[^\s]*', message.content)
        for link in zillow_links:
            await message.channel.send(f"Rawr! Zillow link detected: {link}")
            name, price, size, address = get_property_details_from_zillow(link)
            hospital_name, hospital_distance_miles = get_nearest_hospital(address)
            save_property_to_db(link, name, price, size, hospital_name, hospital_distance_miles)
            if hospital_name == "Could not geocode address with OpenStreetMap/Nominatim":
                await message.channel.send(
                    f"Property saved: {name} | Price: {price} | Size: {size} | "
                    f"Could not geocode address with OpenStreetMap/Nominatim. Hospital lookup unavailable."
                )
            else:
                await message.channel.send(
                    f"Property saved: {name} | Price: {price} | Size: {size} | "
                    f"Nearest hospital: {hospital_name or 'Unknown'} ({hospital_distance_miles if hospital_distance_miles is not None else '?'} miles)"
                )

# Just normal main function stuff
if __name__ == "__main__":
    # Try to load the token, complain if can't
    try:
        TOKEN = load_token_from_file("Data/token.dat")
    except Exception as e:
        print(f"Failed to load token: {e}")
        TOKEN = None

    if not TOKEN:
        print("Please create a file named 'token.dat' with your Discord bot token on the first line.")
    else:
        # Run the bot 😎
        client = ZillowBot(intents=intents)
        client.run(TOKEN)