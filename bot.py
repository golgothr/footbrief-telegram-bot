import os
import json
import logging
from datetime import datetime
from urllib.parse import quote
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.requests import Request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
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

FLD_USER_ID = "fldOJAk8jnO1KRRapu6"

# --- ORGANISATION DES LIGUES ---
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
    },
    "🌎 AMÉRIQUES": {
        "lg_us": {"name": "🇺🇸 MLS", "premium": True},
        "lg_ar": {"name": "🇦🇷 Liga Profesional", "premium": True},
    },
    "🌍 AFRIQUE & ASIE": {
        "lg_ma": {"name": "🇲🇦 Botola Pro", "premium": True},
        "lg_kr": {"name": "🇰🇷 K League 1", "premium": True},
    }
}
ALL_LEAGUES = {k: v for group in LEAGUE_GROUPS.values() for k, v in group.items()}

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
            fields_data = {"user_id": int(user_id), "username": username, "selected_leagues": json.dumps(selected_leagues), "is_premium": bool(is_premium)}
            if records:
                await client.patch(f"{TEABLE_API_URL}/record/{records[0]['id']}", headers=headers, json={"fieldKeyType": "name", "record": {"fields": fields_data}})
            else:
                await client.post(f"{TEABLE_API_URL}/record", headers=headers, json={"fieldKeyType": "name", "records": [{"fields": fields_data}]})
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

# --- PAIEMENTS STARS ---

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message if update.message else update.callback_query.message
    await target.reply_invoice(
        title="Passage au Plan Premium YWFR",
        description="Accès illimité à toutes les ligues mondiales.",
        payload="premium_upgrade",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Accès Premium", 250)]
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    name = user.username if user.username else user.first_name
    await update_user_preferences(user.id, name, prefs["selected_leagues"], is_premium=True)
    await update.message.reply_text("🥳 Félicitations ! Vous êtes désormais Premium.")

# --- HANDLERS INTERFACE ---

def build_leagues_keyboard(selected_list, is_premium):
    keyboard = []
    for g_name, leagues in LEAGUE_GROUPS.items():
        keyboard.append([InlineKeyboardButton(f"─── {g_name} ───", callback_data="ignore")])
        for lid, info in leagues.items():
            st = "✅ " if lid in selected_list else ("⭐ " if info["premium"] and not is_premium else "🔹 ")
            keyboard.append([InlineKeyboardButton(f"{st}{info['name']}", callback_data=lid)])
    keyboard.append([InlineKeyboardButton("💾 VALIDER LA SÉLECTION", callback_data="validate")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.username if user.username else user.first_name
    await update_user_preferences(user.id, name, [], False)
    await update.message.reply_text(f"⚽ **Bienvenue {name} !**\nUtilisez /ligues pour choisir vos championnats ou /compte pour gérer votre profil.", parse_mode='Markdown')

async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    await update.message.reply_text("🏆 **Sélection :**", reply_markup=build_leagues_keyboard(prefs["selected_leagues"], prefs["is_premium"]), parse_mode='Markdown')

async def compte_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    noms = [ALL_LEAGUES[c]["name"] for c in prefs["selected_leagues"] if c in ALL_LEAGUES]
    status = "⭐ Premium" if prefs["is_premium"] else "🔹 Gratuit"
    
    text = (f"👤 **VOTRE COMPTE**\n\n**Statut :** {status}\n"
            f"**Ligues :**\n" + ("\n".join(noms) if noms else "_Aucune_"))
    
    keyboard = [
        [InlineKeyboardButton("🔄 Changer de ligue", callback_data="open_ligues")],
        [InlineKeyboardButton("🗑 Supprimer mon compte", callback_data="confirm_delete")]
    ]
    if not prefs["is_premium"]:
        keyboard.insert(1, [InlineKeyboardButton("🚀 Devenir Premium", callback_data="go_upgrade")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data == "ignore": return
    if data == "open_ligues":
        await query.message.delete()
        prefs = await get_user_preferences(user.id)
        await query.message.reply_text("🏆 **Sélection :**", reply_markup=build_leagues_keyboard(prefs["selected_leagues"], prefs["is_premium"]), parse_mode='Markdown')
        return
    if data == "go_upgrade":
        await query.message.delete()
        await upgrade_command(update, context)
        return
    if data == "confirm_delete":
        headers = await get_teable_headers()
        async with httpx.AsyncClient() as client:
            filter_params = {"conjunction":"and","filterSet":[{"fieldId": FLD_USER_ID,"operator":"is","value": int(user.id)}]}
            search = await client.get(f"{TEABLE_API_URL}/record?filter={quote(json.dumps(filter_params))}", headers=headers)
            recs = search.json().get("records", [])
            if recs:
                await client.delete(f"{TEABLE_API_URL}/record/{recs[0]['id']}", headers=headers)
                await query.edit_message_text("🗑 Compte supprimé avec succès.")
        return

    prefs = await get_user_preferences(user.id)
    selected = prefs["selected_leagues"]
    if data in ALL_LEAGUES:
        if ALL_LEAGUES[data]["premium"] and not prefs["is_premium"]:
            await query.answer("🏆 Premium requis !", show_alert=True)
            return
        if data in selected:
            selected.remove(data)
        else:
            if not prefs["is_premium"]: selected.clear() # Remplacement auto
            selected.append(data)
        
        name = user.username if user.username else user.first_name
        await update_user_preferences(user.id, name, selected, prefs["is_premium"])
        await query.edit_message_reply_markup(reply_markup=build_leagues_keyboard(selected, prefs["is_premium"]))
    elif data == "validate":
        await query.edit_message_text("✅ Enregistré ! À lundi.")

# --- SERVEUR ---

@asynccontextmanager
async def lifespan(app: Starlette):
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("ligues", ligues_command))
    telegram_app.add_handler(CommandHandler("compte", compte_command))
    telegram_app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    telegram_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    await telegram_app.initialize()
    await telegram_app.start()
    yield
    await telegram_app.stop()

async def webhook_handler(request: Request):
    data = await request.json()
    await telegram_app.process_update(Update.de_json(data, telegram_app.bot))
    return JSONResponse({"status": "ok"})

app = Starlette(lifespan=lifespan, routes=[Route("/webhook", webhook_handler, methods=["POST"]), Route("/", lambda r: PlainTextResponse("YWFR Bot Live"))])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
