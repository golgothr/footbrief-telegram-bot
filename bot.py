import os
import json
import logging
import traceback
from datetime import datetime
from urllib.parse import quote
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

# --- CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables d'environnement (À configurer sur Koyeb)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TEABLE_TOKEN = os.environ.get('TEABLE_TOKEN')
# L'URL doit être : https://app.teable.ai/api/table/VOTRE_TABLE_ID
TEABLE_API_URL = os.environ.get('TEABLE_API_URL') 
PORT = int(os.environ.get('PORT', 8000))

# --- DONNÉES ---
LEAGUES = {
    "ligue1": {"name": "🇫🇷 Ligue 1", "premium": False},
    "premier_league": {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", "premium": False},
    "laliga": {"name": "🇪🇸 La Liga", "premium": True},
    "serie_a": {"name": "🇮🇹 Serie A", "premium": True},
    "bundesliga": {"name": "🇩🇪 Bundesliga", "premium": True},
    "champions_league": {"name": "🇪🇺 Champions League", "premium": True},
}

telegram_app = None

# --- LOGIQUE TEABLE ---

async def get_teable_headers():
    return {
        "Authorization": f"Bearer {TEABLE_TOKEN}",
        "Content-Type": "application/json"
    }

async def update_user_preferences(user_id: int, username: str, selected_leagues: list, is_premium: bool = False):
    headers = await get_teable_headers()
    leagues_json = json.dumps(selected_leagues)
    
    async with httpx.AsyncClient() as client:
        try:
            # Recherche par user_id (Attention: remplace 'user_id' par l'ID exact du champ dans Teable si besoin)
            filter_params = {"conjunction":"and","filterSet":[{"fieldId":"user_id","operator":"is","value":user_id}]}
            search_url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            
            resp = await client.get(search_url, headers=headers)
            records = resp.json().get("records", [])

            fields = {
                "user_id": user_id,
                "username": username or "Anonyme",
                "selected_leagues": leagues_json,
                "is_premium": is_premium
            }

            if records:
                # Mise à jour (PATCH)
                record_id = records[0]["id"]
                await client.patch(f"{TEABLE_API_URL}/record/{record_id}?fieldKeyType=name", 
                                   headers=headers, json={"fields": fields})
            else:
                # Création (POST)
                await client.post(f"{TEABLE_API_URL}/record?fieldKeyType=name", 
                                  headers=headers, json={"records": [{"fields": fields}]})
            return True
        except Exception as e:
            logger.error(f"Erreur Teable Sync: {e}")
            return False

async def get_user_preferences(user_id: int) -> dict:
    headers = await get_teable_headers()
    async with httpx.AsyncClient() as client:
        try:
            filter_params = {"conjunction":"and","filterSet":[{"fieldId":"user_id","operator":"is","value":user_id}]}
            url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            resp = await client.get(url, headers=headers)
            records = resp.json().get("records", [])
            
            if records:
                f = records[0]["fields"]
                return {
                    "selected_leagues": json.loads(f.get("selected_leagues", "[]")),
                    "is_premium": f.get("is_premium", False)
                }
        except Exception as e:
            logger.error(f"Erreur Teable Read: {e}")
        return {"selected_leagues": [], "is_premium": False}

# --- HANDLERS TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update_user_preferences(user.id, user.username, [], False)
    text = "⚽ *Bienvenue sur YWFR!*\n\nUtilisez /leagues pour configurer vos championnats."
    await update.message.reply_text(text, parse_mode='Markdown')

async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    selected = prefs["selected_leagues"]
    is_premium = prefs["is_premium"]

    keyboard = []
    for lid, info in LEAGUES.items():
        status = "✅ " if lid in selected else ("⭐ " if info["premium"] and not is_premium else "🔹 ")
        keyboard.append([InlineKeyboardButton(f"{status}{info['name']}", callback_data=f"lg_{lid}")])
    
    keyboard.append([InlineKeyboardButton("💾 Valider la sélection", callback_data="validate")])
    await update.message.reply_text("Choisissez vos championnats :", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data.startswith("lg_"):
        lid = query.data.replace("lg_", "")
        prefs = await get_user_preferences(user.id)
        
        if LEAGUES[lid]["premium"] and not prefs["is_premium"]:
            await query.answer("🏆 Mode Premium requis pour cette ligue !", show_alert=True)
            return

        selected = prefs["selected_leagues"]
        if lid in selected:
            selected.remove(lid)
        else:
            selected.append(lid)
        
        await update_user_preferences(user.id, user.username, selected, prefs["is_premium"])
        # Rafraîchir le menu
        keyboard = []
        for l_id, info in LEAGUES.items():
            status = "✅ " if l_id in selected else ("⭐ " if info["premium"] and not prefs["is_premium"] else "🔹 ")
            keyboard.append([InlineKeyboardButton(f"{status}{info['name']}", callback_data=f"lg_{l_id}")])
        keyboard.append([InlineKeyboardButton("💾 Valider la sélection", callback_data="validate")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "validate":
        await query.edit_message_text("✅ Sélection enregistrée ! Vous recevrez votre résumé lundi matin.")

# --- STARLETTE SERVER ---

@asynccontextmanager
async def lifespan(app: Starlette):
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("leagues", leagues_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Bot démarré avec succès")
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()

async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"status": "ok"})

app = Starlette(lifespan=lifespan, routes=[
    Route("/webhook", webhook_handler, methods=["POST"]),
    Route("/", lambda r: PlainTextResponse("YWFR Bot is Running")),
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
