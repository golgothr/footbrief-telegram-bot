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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TEABLE_TOKEN = os.environ.get('TEABLE_TOKEN')
TEABLE_API_URL = os.environ.get('TEABLE_API_URL') 
PORT = int(os.environ.get('PORT', 8000))

# IDs des champs Teable
FLD_USER_ID = "fldOJAk8jnO1KRRapu6"

# --- ORGANISATION DES LIGUES PAR GROUPES ---
LEAGUE_GROUPS = {
    "🏆 TOP 5 EUROPÉEN": {
        "lg_fr": {"name": "🇫🇷 Ligue 1", "premium": False},
        "lg_uk": {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", "premium": False},
        "lg_es": {"name": "🇪🇸 La Liga", "premium": True},
        "lg_it": {"name": "🇮🇹 Serie A", "premium": True},
        "lg_de": {"name": "🇩🇪 Bundesliga", "premium": True},
    },
    "🇪🇺 CHALLENGERS EUROPÉENS": {
        "lg_be": {"name": "🇧🇪 Jupiler Pro League", "premium": True},
        "lg_nl": {"name": "🇳🇱 Eredivisie", "premium": True},
        "lg_pt": {"name": "🇵🇹 Liga Portugal", "premium": True},
        "lg_ch": {"name": "🇨🇭 Super League", "premium": True},
        "lg_dk": {"name": "🇩🇰 Superliga", "premium": True},
        "lg_ie": {"name": "🇮🇪 League of Ireland", "premium": True},
    },
    "🌎 AMÉRIQUES": {
        "lg_us": {"name": "🇺🇸 MLS", "premium": True},
        "lg_ar": {"name": "🇦🇷 Liga Profesional", "premium": True},
        "lg_mx": {"name": "🇲🇽 Liga MX", "premium": True},
    },
    "🌍 AFRIQUE & ASIE": {
        "lg_ma": {"name": "🇲🇦 Botola Pro", "premium": True},
        "lg_kr": {"name": "🇰🇷 K League 1", "premium": True},
    }
}

# Liste à plat pour les recherches rapides
ALL_LEAGUES = {k: v for group in LEAGUE_GROUPS.values() for k, v in group.items()}

telegram_app = None

# --- LOGIQUE TEABLE ---

async def get_teable_headers():
    return {"Authorization": f"Bearer {TEABLE_TOKEN}", "Content-Type": "application/json"}

async def update_user_preferences(user_id: int, username: str, selected_leagues: list, is_premium: bool = False):
    headers = await get_teable_headers()
    async with httpx.AsyncClient() as client:
        try:
            filter_params = {"conjunction":"and","filterSet":[{"fieldId": FLD_USER_ID,"operator":"is","value": int(user_id)}]}
            search_url = f"{TEABLE_API_URL}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
            resp_search = await client.get(search_url, headers=headers)
            records = resp_search.json().get("records", [])

            fields_data = {
                "user_id": int(user_id),
                "username": username,
                "selected_leagues": json.dumps(selected_leagues),
                "is_premium": bool(is_premium)
            }

            if records:
                url = f"{TEABLE_API_URL}/record/{records[0]['id']}"
                await client.patch(url, headers=headers, json={"fieldKeyType": "name", "record": {"fields": fields_data}})
            else:
                url = f"{TEABLE_API_URL}/record"
                await client.post(url, headers=headers, json={"fieldKeyType": "name", "records": [{"fields": fields_data}]})
            return True
        except Exception as e:
            logger.error(f"Teable Error: {e}")
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
                return {"selected_leagues": json.loads(f.get("selected_leagues", "[]")), "is_premium": f.get("is_premium", False)}
        except Exception: pass
        return {"selected_leagues": [], "is_premium": False}

# --- INTERFACE ---

def build_leagues_keyboard(selected_list, is_premium):
    keyboard = []
    for group_name, leagues in LEAGUE_GROUPS.items():
        # Ajouter une ligne de texte (bouton inactif) pour le nom du groupe
        keyboard.append([InlineKeyboardButton(f"--- {group_name} ---", callback_data="ignore")])
        for lid, info in leagues.items():
            # Surbrillance : ✅ si sélectionné, ⭐ si premium dispo, 🔹 sinon
            if lid in selected_list:
                status = "✅ " 
            elif info["premium"] and not is_premium:
                status = "⭐ "
            else:
                status = "🔹 "
            keyboard.append([InlineKeyboardButton(f"{status}{info['name']}", callback_data=lid)])
    
    keyboard.append([InlineKeyboardButton("💾 VALIDER LA SÉLECTION", callback_data="validate")])
    return InlineKeyboardMarkup(keyboard)

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Correction Username : on prend le pseudo, sinon le prénom
    display_name = user.username if user.username else user.first_name
    await update_user_preferences(user.id, display_name, [], False)
    
    text = (
        f"⚽ **Bienvenue {display_name} sur YWFR !**\n\n"
        "Recevez votre résumé foot chaque lundi.\n\n"
        "🎁 **Plan Gratuit :** 1 ligue (🇫🇷 ou 🏴󠁧󠁢󠁥󠁮󠁧󠁿).\n"
        "⭐ **Plan Premium :** Accès total illimité.\n\n"
        "Utilisez /ligues pour commencer."
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    reply_markup = build_leagues_keyboard(prefs["selected_leagues"], prefs["is_premium"])
    await update.message.reply_text("🏆 **Choisissez vos championnats :**", reply_markup=reply_markup, parse_mode='Markdown')

async def compte_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    noms = [ALL_LEAGUES[c]["name"] for c in prefs["selected_leagues"] if c in ALL_LEAGUES]
    status = "⭐ Premium" if prefs["is_premium"] else "🔹 Gratuit"
    text = f"👤 **Compte YWFR**\n\n**Statut :** {status}\n**Ligues :**\n" + ("\n".join([f"- {n}" for n in noms]) if noms else "_Aucune_")
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "ignore": 
        await query.answer()
        return

    user = query.from_user
    display_name = user.username if user.username else user.first_name
    prefs = await get_user_preferences(user.id)
    selected = prefs["selected_leagues"]
    is_premium = prefs["is_premium"]

    if query.data in ALL_LEAGUES:
        league = ALL_LEAGUES[query.data]
        
        # Bloquer Premium
        if league["premium"] and not is_premium:
            await query.answer("🏆 Ce championnat est réservé aux membres Premium !", show_alert=True)
            return
        
        # Bloquer plusieurs sélections en Gratuit
        if not is_premium and query.data not in selected and len(selected) >= 1:
            await query.answer("📍 Plan Gratuit : 1 seule ligue possible. Passez Premium pour plus !", show_alert=True)
            return

        # Toggle selection
        if query.data in selected:
            selected.remove(query.data)
            await query.answer(f"Retiré : {league['name']}")
        else:
            selected.append(query.data)
            await query.answer(f"Ajouté : {league['name']}")
        
        await update_user_preferences(user.id, display_name, selected, is_premium)
        await query.edit_message_reply_markup(reply_markup=build_leagues_keyboard(selected, is_premium))

    elif query.data == "validate":
        await query.answer("Sélection enregistrée !")
        await query.edit_message_text("✅ **Préférences sauvegardées !**\n\nÀ lundi pour votre résumé.", parse_mode='Markdown')

# --- SERVEUR ---

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
    yield
    await telegram_app.stop()

async def webhook_handler(request: Request):
    data = await request.json()
    await telegram_app.process_update(Update.de_json(data, telegram_app.bot))
    return JSONResponse({"status": "ok"})

app = Starlette(lifespan=lifespan, routes=[
    Route("/webhook", webhook_handler, methods=["POST"]),
    Route("/", lambda r: PlainTextResponse("YWFR Bot Live")),
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
