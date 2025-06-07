# Zillabot.py
# A Discord bot that detects Zillow links in messages and then fetches property details
#
# Date: June 5th, 2024
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
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Referer": "https://www.google.com/"
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
        if name:
            # Remove anything after a pipe and all commas
            clean_name = name.split('|')[0].replace(",", "").strip()
            words = clean_name.split()
            # Get up to the first 3 words (street number and name)
            street_part = " ".join(words[:3])
            # Get the last word (should be the zip)
            zip_part = words[-1] if len(words) > 0 else ""
            address = f"{street_part} {zip_part}".strip()
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
            # Overpass API to find nearest hospital with emergency department
            overpass_url = "https://overpass-api.de/api/interpreter"
            overpass_query = f"""
            [out:json];
            (
              node["amenity"="hospital"]["emergency"="yes"](around:100000,{lat},{lon});
              way["amenity"="hospital"]["emergency"="yes"](around:100000,{lat},{lon});
              relation["amenity"="hospital"]["emergency"="yes"](around:100000,{lat},{lon});
            );
            out center 1;
            """
            resp = requests.post(overpass_url, data=overpass_query, headers={"User-Agent": "Zillabot/1.0"}, timeout=25)
            data = resp.json()
            print(f"Overpass response: {data}")
            min_dist = None
            nearest_hospital = None
            for element in data.get("elements", []):
                if "tags" in element and "name" in element["tags"]:
                    # Get hospital coordinates
                    if "lat" in element and "lon" in element:
                        hosp_lat = element["lat"]
                        hosp_lon = element["lon"]
                    elif "center" in element:
                        hosp_lat = element["center"]["lat"]
                        hosp_lon = element["center"]["lon"]
                    else:
                        continue
                    # Haversine distance in miles
                    from math import radians, sin, cos, sqrt, atan2
                    R_miles = 3958.8
                    dlat = radians(hosp_lat - lat)
                    dlon = radians(hosp_lon - lon)
                    a = sin(dlat/2)**2 + cos(radians(lat)) * cos(radians(hosp_lat)) * sin(dlon/2)**2
                    c = 2 * atan2(sqrt(a), sqrt(1-a))
                    dist_miles = R_miles * c
                    if min_dist is None or dist_miles < min_dist:
                        min_dist = dist_miles
                        nearest_hospital = element["tags"]["name"]
            if nearest_hospital and min_dist is not None:
                hospital_name = nearest_hospital
                hospital_distance_miles = round(min_dist, 2)
            else:
                print("No full-service hospital with ER found in Overpass data.")
        else:
            print("No geocoding result from Nominatim.")
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
        