import os
import datetime
import requests
import json
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from google import genai
from google.cloud import storage
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import secretmanager

# --- CONFIGURATION & ENV VARIABLES ---

# 1. Fallback safely to the injected Docker environment variable
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "emerald-vent-384708")

def get_secret(secret_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{os.getenv('GCP_PROJECT_ID')}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Fetch all keys from the single JSON secret
config = json.loads(get_secret("tulip-bot"))

OPENWEATHER_KEY = config["OPENWEATHER_KEY"]
GOOGLE_MAPS_KEY = config["GOOGLE_MAPS_KEY"]
TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
TELEGRAM_USER_ID = config["TELEGRAM_USER_ID"]
CALENDAR_ID = config["CALENDAR_ID"]

# Load the Calendar Credentials directly from Secret Manager
calendar_creds_json = config["GOOGLE_CALENDAR_CREDS_JSON"]
creds = service_account.Credentials.from_service_account_info(
    json.loads(calendar_creds_json), 
    scopes=['https://www.googleapis.com/auth/calendar.readonly']
)

# Initialize Gemini Client
client = genai.Client()
SYSTEM_INSTRUCTION = (
    "You are 'Tulip', a proactive, witty personal travel assistant for a family vacation in Holland. "
    "You have direct access to live tools for weather, travel times, and the family Google Calendar. "
    "Provide structured, kid-friendly, and highly scannable bulleted text responses."
)

# In-memory session fallback cache
chats_sessions = {}

# --- GOOGLE CLOUD STORAGE HISTORY BACKUP UTILITIES ---

def get_gcs_blob_path(chat_id: int) -> str:
    """Organizes conversation backups by date pathing: conversations/YYYY-MM-DD/chat_id.json"""
    today_str = datetime.date.today().isoformat()
    return f"conversations/{today_str}/{chat_id}.json"

def save_history_to_gcs(chat_id: int, history_data: list):
    """Uploads serialized chat transaction history arrays to your GCS bucket."""
    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(get_gcs_blob_path(chat_id))
        blob.upload_from_string(json.dumps(history_data), content_type='application/json')
        print(f"Synced conversation state to GCS.")
    except Exception as e:
        print(f"Failed to sync state to GCS: {e}")

def load_history_from_gcs(chat_id: int) -> list:
    """Downloads existing conversation state logs matching today's lifecycle window."""
    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(get_gcs_blob_path(chat_id))
        if blob.exists():
            return json.loads(blob.download_as_text())
    except Exception as e:
        print(f"Failed to read historical state from GCS: {e}")
    return []

# --- LIVE HARDWARE / API ENGINE ACTIONS (Tools) ---

def get_current_weather(location: str) -> str:
    """Fetches the current live weather and description strings for a given city in Holland."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location},NL&appid={OPENWEATHER_KEY}&units=metric"
    try:
        res = requests.get(url).json()
        return f"Current weather in {location}: {res['weather']['description']}, {res['main']['temp']}°C."
    except Exception:
        return f"Could not pull current weather values for {location} right now."

def get_travel_time(origin: str, destination: str, mode: str = "transit") -> str:
    """Calculates active path transit or driving travel times using the Google Maps Engine."""
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin}&destinations={destination}&mode={mode}&key={GOOGLE_MAPS_KEY}"
    try:
        data = requests.get(url).json()
        element = data["rows"]["elements"]
        return f"Via {mode}: {element['duration']['text']} ({element['distance']['text']})."
    except Exception:
        return "Live routing metric configurations are currently unretrievable."

def get_nearby_places(location: str, place_type: str = "restaurant") -> str:
    """Finds nearby places (restaurants, cafes, attractions) using Google Places API."""
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={place_type}+in+{location}&key={GOOGLE_MAPS_KEY}"
    try:
        res = requests.get(url).json()
        results = res.get("results", [])[:3] # Top 3 only
        output = f"Top 3 {place_type}s in {location}:\n"
        for p in results:
            output += f"- {p['name']} (Rating: {p.get('rating', 'N/A')})\n"
        return output
    except Exception:
        return "Could not retrieve nearby places."

def get_calendar_itinerary(date_str: str = None) -> str:
    """Queries your shared Google Calendar to extract active timeline logs for a specified target day (YYYY-MM-DD)."""
    try:
        # Reads credentials.json shared natively to container space during local mounts or actions builds
        creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        if not date_str:
            date_str = datetime.date.today().isoformat()
            
        time_min = f"{date_str}T00:00:00Z"
        time_max = f"{date_str}T23:59:59Z"
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events:
            return f"Your schedule is totally wide open on {date_str}! No events logged."
            
        schedule = f"Confirmed Schedule for {date_str}:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            time_only = start.split('T')[:5] if 'T' in start else "All Day"
            schedule += f"- [{time_only}] {event.get('summary')}: At {event.get('location', 'Unlisted location')}. Details: {event.get('description', 'None')}\n"
        return schedule
    except Exception as e:
        return f"Could not open live calendar schedules: {e}"

def send_telegram_message(text: str, chat_id: str = TELEGRAM_USER_ID):
    """Fires a localized markdown push ping notification to your target device interface."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# --- THE AGENT COGNITIVE INTERFACE ---

def ask_agent(chat_id: int, user_message: str) -> str:
    """Orchestrates historical reconstruction across cold storage GCS targets before generating responses."""
    if chat_id not in chats_sessions:
        gcs_history = load_history_from_gcs(chat_id)
        history_objs = []
        for turn in gcs_history:
            history_objs.append(
                genai.types.Content(
                    role=turn["role"],
                    parts=[genai.types.Part.from_text(text=p["text"]) for p in turn["parts"] if "text" in p]
                )
            )
        
        chats_sessions[chat_id] = client.chats.create(
            model='gemini-2.5-flash',
            history=history_objs,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[get_current_weather, get_travel_time, get_calendar_itinerary],
                temperature=0.3
            )
        )

    active_chat = chats_sessions[chat_id]
    response = active_chat.send_message(user_message)
    
    # Extract structural session parameters and save cleanly back to GCS
    updated_history = active_chat.get_history()
    serializable_history = []
    for content in updated_history:
        parts_data = [{"text": p.text} for p in content.parts if p.text is not None]
        if parts_data:
            serializable_history.append({"role": content.role, "parts": parts_data})
            
    save_history_to_gcs(chat_id, serializable_history)
    return response.text

# --- TIME CRITICAL BACKGROUND AUTOMATION RUNNERS ---

def check_upcoming_events():
    """Runs automatically every 15 minutes to generate automated contextual alerts."""
    print("Automated job scanning schedule entries via service credentials...")
    today_str = datetime.date.today().isoformat()
    
    try:
        creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        time_min = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = service.events().list(
            calendarId=CALENDAR_ID, timeMin=time_min, maxResults=5,
            singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        now = datetime.datetime.utcnow()
        
        for event in events:
            start_str = event['start'].get('dateTime')
            if not start_str: 
                continue # Skip all-day blocks
                
            # Parse timeline window constraints
            event_time = datetime.datetime.strptime(start_str[:19], "%Y-%m-%dT%H:%M:%S")
            time_difference = event_time - now
            
            if datetime.timedelta(minutes=105) < time_difference <= datetime.timedelta(minutes=120):
                dest_addr = event.get('location', 'Amsterdam')
                transit_info = get_travel_time(origin="Your Amsterdam Hotel Location", destination=dest_addr, mode="transit")
                
                alert_msg = (
                    f"⏰ *Proactive Trip Alert!*\n\n"
                    f"*Booking:* {event.get('summary')}\n"
                    f"*Scheduled Time:* {start_str[11:16]}\n"
                    f"*Details:* {event.get('description', 'No attached confirmation notes found.')}\n\n"
                    f"🚌 *Live Transit Routing:* {transit_info}"
                )
                send_telegram_message(alert_msg)
    except Exception as e:
        print(f"Scheduler tracking pass logged an error: {e}")

# --- WEB SERVER INTERFACE LIFECYCLE MANAGEMENT ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_upcoming_events, 'interval', minutes=15)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_status():
    return {"status": "Tulip is initialized and online."}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    if "message" in payload:
        chat_id = payload["message"]["chat"]["id"]
        user_text = payload["message"].get("text", "")
        if user_text:
            ai_reply = ask_agent(chat_id, user_text)
            send_telegram_message(ai_reply, chat_id=chat_id)
    return {"ok": True}

