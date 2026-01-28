import os
import json
from urllib.parse import quote
import logging
import asyncio
import traceback
from datetime import datetime
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.requests import Request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import httpx

# Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Config - UTILISE DES VARIABLES D'ENVIRONNEMENT SUR KOYEB
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TEABLE_API_URL = os.environ.get("TEABLE_API_URL") # Ex: https://app.teable.ai/api/table/VOTRE_TABLE_ID
TEABLE_TOKEN = os.environ.get("TEABLE_TOKEN")
PORT = int(os.environ.get('PORT', 8000))

# Championnats
LEAGUES = {
    "ligue1": {"name": "🇫🇷 Ligue 1", "id": "FL1", "premium": False},
    "premier_league": {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", "id": "PL", "premium": False},
    "laliga": {"name": "🇪🇸 La Liga", "id": "PD", "premium": True},
    "serie_a": {"name": "🇮🇹 Serie A", "id": "SA", "premium": True},
    "bundesliga": {"name": "🇩🇪 Bundesliga", "id": "BL1", "premium": True},
    "champions_league": {"name": "🇪🇺 Champions League", "id": "CL", "premium": True},
}
FREE_LEAGUES = ["ligue1", "premier_league"]

telegram_app = None

async def update_user_preferences(user_id: int, username: str, selected_leagues: list, is_premium: bool = False):
    headers = {"Authorization": f"Bearer {TEABLE_TOKEN}", "Content-Type": "application/json"}
    leagues_str = json.dumps(selected_leagues)
    
    async with httpx.AsyncClient() as client:
        try:
            # Correction du filtre Teable
            filter_params = {"conjunction":"and","filterSet":[{"fieldId":"user_id","operator":"is","value":user_id}]}
            search_url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            
            response = await client.get(search_url, headers=headers)
            data = response.json()
            records = data.get("records", [])

            fields = {
                "user_id": user_id,
                "username": username or "",
                "selected_leagues": leagues_str,
                "is_premium": is_premium
            }

            if records:
                # UPDATE (PATCH)
                record_id = records[0]["id"]
                url = f"{TEABLE_API_URL}/record/{record_id}?fieldKeyType=name"
                # Teable attend les champs dans un objet 'fields'
                await client.patch(url, headers=headers, json={"fields": fields})
            else:
                # CREATE (POST)
                url = f"{TEABLE_API_URL}/record?fieldKeyType=name"
                await client.post(url, headers=headers, json={"records": [{"fields": fields}]})
            return True
        except Exception as e:
            logger.error(f"Teable Sync Error: {e}")
            return False

async def get_user_preferences(user_id: int) -> dict:
    headers = {"Authorization": f"Bearer {TEABLE_TOKEN}"}
    async with httpx.AsyncClient() as client:
        try:
            filter_params = {"conjunction":"and","filterSet":[{"fieldId":"user_id","operator":"is","value":user_id}]}
            url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            response = await client.get(url, headers=headers)
            records = response.json().get("records", [])
            
            if records:
                f = records[0]["fields"]
                return {
                    "selected_leagues": json.loads(f.get("selected_leagues", "[]")),
                    "is_premium": f.get("is_premium", False)
                }
        except: pass
        return {"selected_leagues": [], "is_premium": False}

# --- HANDLERS BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update_user_preferences(user.id, user.username, [], False)
    await update.message.reply_text(f"⚽ *Bienvenue sur YWFR !*\nUtilisez /leagues pour choisir vos championnats.", parse_mode='Markdown')

async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    selected = prefs["selected_leagues"]
    is_premium = prefs["is_premium"]

    keyboard = []
    for lid, info in LEAGUES.items():
        prefix = "✅ " if lid in selected else ("⭐ " if info["premium"] and not is_premium else "🔹 ")
        keyboard.append([InlineKeyboardButton(f"{prefix}{info['name']}", callback_data=f"league_{lid}")])
    
    keyboard.append([InlineKeyboardButton("🚀 Valider", callback_data="validate")])
    await update.message.reply_text("Sélectionnez vos ligues :", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data.startswith("league_"):
        lid = query.data.split("_")[1]
        prefs = await get_user_preferences(user.id)
        
        if LEAGUES[lid]["premium"] and not prefs["is_premium"]:
            await query.answer("Abonnement Premium requis !", show_alert=True)
            return

        selected = prefs["selected_leagues"]
        if lid in selected: selected.remove(lid)
        else: selected.append(lid)
        
        await update_user_preferences(user.id, user.username, selected, prefs["is_premium"])
        # Optionnel: Mettre à jour le clavier ici (re-trigger leagues_command logic)
        await query.edit_message_text("Sélection mise à jour ! Tapez /leagues pour modifier ou /resume.")

# --- SERVEUR & LIFESPAN ---

@asynccontextmanager
async def lifespan(app: Starlette):
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("leagues", leagues_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    await telegram_app.initialize()
    await telegram_app.start()
    yield
    await telegram_app.stop()

async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})

app = Starlette(lifespan=lifespan, routes=[
    Route("/webhook", webhook_handler, methods=["POST"]),
    Route("/", lambda r: PlainTextResponse("Bot is Live"))
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
