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

# --- CONFIGURATION LOGS ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- VARIABLES D'ENVIRONNEMENT ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TEABLE_TOKEN = os.environ.get('TEABLE_TOKEN')
TEABLE_API_URL = os.environ.get('TEABLE_API_URL') 
PORT = int(os.environ.get('PORT', 8000))

# --- IDS DES CHAMPS TEABLE (Tes fldXXX réels) ---
FLD_USER_ID = "fldOJAk8jnO1KRRapu6"
FLD_USERNAME = "fldUWEWNqO4WI69RyvG"
FLD_LEAGUES = "fldHthW8Lgy1xzDHnca"
FLD_PREMIUM = "fldfnTldzqcCZsbmUCd"

# --- DONNÉES DES LIGUES (16 Championnats) ---
LEAGUES = {
    "lg_fr": {"name": "🇫🇷 Ligue 1", "premium": False},
    "lg_uk": {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", "premium": False},
    "lg_es": {"name": "🇪🇸 La Liga", "premium": True},
    "lg_it": {"name": "🇮🇹 Serie A", "premium": True},
    "lg_de": {"name": "🇩🇪 Bundesliga", "premium": True},
    "lg_be": {"name": "🇧🇪 Jupiler Pro League", "premium": True},
    "lg_nl": {"name": "🇳🇱 Eredivisie", "premium": True},
    "lg_pt": {"name": "🇵🇹 Liga Portugal", "premium": True},
    "lg_ch": {"name": "🇨🇭 Super League", "premium": True},
    "lg_dk": {"name": "🇩🇰 Superliga", "premium": True},
    "lg_ie": {"name": "🇮🇪 League of Ireland", "premium": True},
    "lg_us": {"name": "🇺🇸 MLS", "premium": True},
    "lg_ar": {"name": "🇦🇷 Liga Profesional", "premium": True},
    "lg_mx": {"name": "🇲🇽 Liga MX", "premium": True},
    "lg_ma": {"name": "🇲🇦 Botola Pro", "premium": True},
    "lg_kr": {"name": "🇰🇷 K League 1", "premium": True},
}

telegram_app = None

# --- LOGIQUE TEABLE (Version corrigée et robuste) ---

async def get_teable_headers():
    return {
        "Authorization": f"Bearer {TEABLE_TOKEN}",
        "Content-Type": "application/json"
    }

async def update_user_preferences(user_id: int, username: str, selected_leagues: list, is_premium: bool = False):
    headers = await get_teable_headers()
    user_id_int = int(user_id)
    
    async with httpx.AsyncClient() as client:
        try:
            # 1. RECHERCHE DE L'UTILISATEUR (Filtre par Field ID obligatoire)
            filter_params = {"conjunction":"and","filterSet":[{"fieldId": FLD_USER_ID,"operator":"is","value": user_id_int}]}
            search_url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            
            resp_search = await client.get(search_url, headers=headers)
            records = resp_search.json().get("records", [])

            fields_data = {
                "user_id": user_id_int,
                "username": str(username) if username else "Anonyme",
                "selected_leagues": json.dumps(selected_leagues),
                "is_premium": bool(is_premium)
            }

            if records:
                # 2. MISE À JOUR (PATCH)
                record_id = records[0]["id"]
                url = f"{TEABLE_API_URL}/record/{record_id}"
                payload = {
                    "fieldKeyType": "name",
                    "record": {"fields": fields_data}
                }
                res = await client.patch(url, headers=headers, json=payload)
            else:
                # 3. CRÉATION (POST)
                url = f"{TEABLE_API_URL}/record"
                payload = {
                    "fieldKeyType": "name", 
                    "records": [{"fields": fields_data}]
                }
                res = await client.post(url, headers=headers, json=payload)
            
            if res.status_code not in [200, 201]:
                logger.error(f"❌ Erreur Teable {res.status_code}: {res.text}")
            return res.status_code in [200, 201]

        except Exception as e:
            logger.error(f"💥 Erreur update_user_preferences: {e}")
            return False

async def get_user_preferences(user_id: int) -> dict:
    headers = await get_teable_headers()
    async with httpx.AsyncClient() as client:
        try:
            filter_params = {"conjunction":"and","filterSet":[{"fieldId": FLD_USER_ID,"operator":"is","value": int(user_id)}]}
            url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            resp = await client.get(url, headers=headers)
            records = resp.json().get("records", [])
            if records:
                f = records[0]["fields"]
                return {
                    "selected_leagues": json.loads(f.get("selected_leagues", "[]")),
                    "is_premium": f.get("is_premium", False)
                }
        except Exception:
            pass
        return {"selected_leagues": [], "is_premium": False}

# --- HANDLERS TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Enregistrement immédiat dans Teable
    await update_user_preferences(user.id, user.username, [], False)
    
    welcome_text = (
        "⚽ **Bienvenue sur YWFR !**\n\n"
        "Votre bot qui résume l'actu foot chaque lundi matin.\n\n"
        "🎁 **Gratuit :** 1 championnat au choix (🇫🇷 ou 🏴󠁧󠁢󠁥󠁮󠁧󠁿).\n"
        "⭐ **Premium :** Accès illimité aux 16 championnats mondiaux.\n\n"
        "📌 **Commandes :**\n"
        "/ligues - Choisir mes championnats\n"
        "/compte - Voir mon statut et mes choix"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    selected = prefs["selected_leagues"]
    is_premium = prefs["is_premium"]

    keyboard = []
    for lid, info in LEAGUES.items():
        st = "✅ " if lid in selected else ("⭐ " if info["premium"] and not is_premium else "🔹 ")
        keyboard.append([InlineKeyboardButton(f"{st}{info['name']}", callback_data=lid)])
    keyboard.append([InlineKeyboardButton("💾 Valider la sélection", callback_data="validate")])
    
    await update.message.reply_text("🏆 **Sélectionnez vos championnats :**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def compte_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    noms = [LEAGUES[c]["name"] for c in prefs["selected_leagues"] if c in LEAGUES]
    status = "⭐ Premium" if prefs["is_premium"] else "🔹 Gratuit"
    
    text = (
        f"👤 **Votre Compte YWFR**\n\n"
        f"🆔 **ID :** `{user.id}`\n"
        f"📈 **Statut :** {status}\n\n"
        f"📋 **Ligues suivies :**\n" + ("\n".join([f"- {n}" for n in noms]) if noms else "_Aucune ligue sélectionnée._") +
        f"\n\n💡 _Pour modifier, utilisez /ligues._"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data in LEAGUES:
        prefs = await get_user_preferences(user.id)
        selected = prefs["selected_leagues"]
        
        # Logique Freemium
        if LEAGUES[query.data]["premium"] and not prefs["is_premium"]:
            await query.answer("🏆 Ce championnat nécessite un abonnement Premium !", show_alert=True)
            return
        if not prefs["is_premium"] and len(selected) >= 1 and query.data not in selected:
            await query.answer("📍 Mode gratuit limité à 1 seul championnat.", show_alert=True)
            return

        if query.data in selected: selected.remove(query.data)
        else: selected.append(query.data)
        
        await update_user_preferences(user.id, user.username, selected, prefs["is_premium"])
        
        # Mise à jour du clavier
        keyboard = []
        for lid, info in LEAGUES.items():
            st = "✅ " if lid in selected else ("⭐ " if info["premium"] and not prefs["is_premium"] else "🔹 ")
            keyboard.append([InlineKeyboardButton(f"{st}{info['name']}", callback_data=lid)])
        keyboard.append([InlineKeyboardButton("💾 Valider la sélection", callback_data="validate")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "validate":
        await query.edit_message_text("✅ Vos préférences ont été enregistrées. À lundi !")

# --- SERVEUR STARLETTE ---

@asynccontextmanager
async def lifespan(app: Starlette):
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("ligues", ligues_command))
    telegram_app.add_handler(CommandHandler("compte", compte_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Bot démarré")
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
    Route("/", lambda r: PlainTextResponse("YWFR Bot Live")),
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
