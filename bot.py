import os
import json
import logging
import httpx
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

# --- CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

class TeableClient:
    def __init__(self, api_url, token):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.client = httpx.AsyncClient(headers=self.headers, timeout=10.0)

    async def close(self):
        await self.client.aclose()

    async def get_user_record(self, user_id: int):
        filter_params = {"conjunction": "and", "filterSet": [{"fieldId": FLD_USER_ID, "operator": "is", "value": int(user_id)}]}
        url = f"{self.api_url}/record?fieldKeyType=name&filter={quote(json.dumps(filter_params))}"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json().get("records", [])

    async def update_or_create_user(self, user_id: int, username: str, selected_leagues: list, is_premium: bool = None):
        try:
            records = await self.get_user_record(user_id)
            fields_data = {"user_id": int(user_id), "username": username, "selected_leagues": json.dumps(selected_leagues)}
            if is_premium is not None: fields_data["is_premium"] = bool(is_premium)

            if records:
                if is_premium is None: fields_data["is_premium"] = records[0]["fields"].get("is_premium", False)
                await self.client.patch(f"{self.api_url}/record/{records[0]['id']}", json={"fieldKeyType": "name", "record": {"fields": fields_data}})
            else:
                if is_premium is None: fields_data["is_premium"] = False
                await self.client.post(f"{self.api_url}/record", json={"fieldKeyType": "name", "records": [{"fields": fields_data}]})
            return True
        except Exception as e:
            logger.error(f"Teable Update Error: {e}")
            return False

    async def get_user_preferences(self, user_id: int) -> dict:
        try:
            records = await self.get_user_record(user_id)
            if records:
                f = records[0]["fields"]
                return {"selected_leagues": json.loads(f.get("selected_leagues", "[]")), "is_premium": f.get("is_premium", False)}
        except Exception: pass
        return {"selected_leagues": [], "is_premium": False}

    async def delete_user(self, user_id: int):
        try:
            records = await self.get_user_record(user_id)
            if records:
                await self.client.delete(f"{self.api_url}/record/{records[0]['id']}")
                return True
        except Exception: pass
        return False

teable = None

# --- PAIEMENTS STARS ---

async def send_upgrade_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.reply_invoice(
        title="Passage au Plan Premium YWFR",
        description="Accès illimité à toutes les ligues mondiales.",
        payload="premium_upgrade",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Accès Premium", 250)]
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await teable.get_user_preferences(user.id)
    await teable.update_or_create_user(user.id, user.username or user.first_name, prefs["selected_leagues"], is_premium=True)
    await update.message.reply_text("🥳 Félicitations ! Vous êtes désormais Premium. Profitez de toutes les ligues !")

# --- HANDLERS INTERFACE ---

def build_leagues_keyboard(selected_list, is_premium):
    keyboard = []
    for g_name, leagues in LEAGUE_GROUPS.items():
        keyboard.append([InlineKeyboardButton(f"─── {g_name} ───", callback_data="ignore")])
        row = []
        for lid, info in leagues.items():
            # Icônes dynamiques
            if lid in selected_list:
                icon = "✅"
            elif info["premium"] and not is_premium:
                icon = "🔒" # Cadenas pour les ligues premium non accessibles
            else:
                icon = "▫️"
            
            # On met 2 boutons par ligne pour une meilleure UX sur mobile
            row.append(InlineKeyboardButton(f"{icon} {info['name']}", callback_data=f"toggle_{lid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("💾 ENREGISTRER MA SÉLECTION", callback_data="validate")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.username or user.first_name
    prefs = await teable.get_user_preferences(user.id)
    if not prefs.get("selected_leagues"):
        await teable.update_or_create_user(user.id, name, [], False)
        
    welcome_text = (
        f"👋 **Bonjour {name} !**\n\n"
        "Bienvenue sur votre assistant de suivi foot. Choisissez vos championnats pour recevoir les alertes.\n\n"
        "💡 _En mode gratuit, vous pouvez suivre 1 championnat parmi les ligues gratuites._"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏆 Choisir mes ligues", callback_data="open_ligues")],
        [InlineKeyboardButton("👤 Mon Compte", callback_data="open_compte")]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await teable.get_user_preferences(user.id)
    
    status_text = "⭐ **Mode Premium** (Illimité)" if prefs["is_premium"] else "🔹 **Mode Gratuit** (1 ligue max, hors Premium 🔒)"
    
    await update.message.reply_text(
        f"{status_text}\n\n🏆 **Sélectionnez vos championnats :**", 
        reply_markup=build_leagues_keyboard(prefs["selected_leagues"], prefs["is_premium"]), 
        parse_mode='Markdown'
    )

async def compte_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    prefs = await teable.get_user_preferences(user.id)
    
    noms = [ALL_LEAGUES[c]["name"] for c in prefs["selected_leagues"] if c in ALL_LEAGUES]
    status = "🌟 Premium" if prefs["is_premium"] else "🆓 Gratuit"
    
    text = (
        f"👤 **VOTRE PROFIL**\n"
        f"━━━━━━━━━━━━━━\n"
        f"**Statut :** {status}\n"
        f"**Ligues suivies :** {len(noms)}\n" 
        + ("\n".join([f"• {n}" for n in noms]) if noms else "_Aucune sélection_")
    )
    
    keyboard = [[InlineKeyboardButton("🔄 Modifier mes ligues", callback_data="open_ligues")]]
    if not prefs["is_premium"]:
        keyboard.append([InlineKeyboardButton("🚀 Passer Premium (250 ⭐️)", callback_data="go_upgrade")])
    keyboard.append([InlineKeyboardButton("🗑 Supprimer mes données", callback_data="confirm_delete")])
    
    # Si c'est un callback, on édite, sinon on envoie
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data == "ignore": 
        await query.answer()
        return
    
    if data == "open_ligues":
        prefs = await teable.get_user_preferences(user.id)
        status_text = "⭐ **Mode Premium**" if prefs["is_premium"] else "🔹 **Mode Gratuit** (1 ligue max, hors 🔒)"
        await query.message.edit_text(
            f"{status_text}\n\n🏆 **Sélectionnez vos championnats :**", 
            reply_markup=build_leagues_keyboard(prefs["selected_leagues"], prefs["is_premium"]), 
            parse_mode='Markdown'
        )
        return

    if data == "open_compte":
        await compte_command(update, context)
        return
        
    if data == "go_upgrade":
        await query.answer("Préparation du paiement...")
        await send_upgrade_invoice(update, context)
        return
        
    if data == "confirm_delete":
        if await teable.delete_user(user.id):
            await query.edit_message_text("🗑 Vos données ont été supprimées. À bientôt !")
        else:
            await query.answer("Erreur lors de la suppression.", show_alert=True)
        return

    if data.startswith("toggle_"):
        league_id = data.replace("toggle_", "")
        prefs = await teable.get_user_preferences(user.id)
        selected = prefs["selected_leagues"]
        is_premium = prefs["is_premium"]
        league = ALL_LEAGUES[league_id]

        if league_id in selected:
            selected.remove(league_id)
            await query.answer(f"❌ Retiré : {league['name']}")
        else:
            if not is_premium:
                if league["premium"]:
                    # UX : Proposer directement l'upgrade si clic sur une ligue verrouillée
                    keyboard = [
                        [InlineKeyboardButton("🚀 Devenir Premium", callback_data="go_upgrade")],
                        [InlineKeyboardButton("🔙 Retour", callback_data="open_ligues")]
                    ]
                    await query.message.edit_text(
                        f"🔒 **Ligue Premium**\n\nLa {league['name']} est réservée aux membres Premium.\n\n"
                        "Le mode Premium débloque toutes les ligues mondiales pour seulement 250 Stars.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                    return
                
                if len(selected) >= 1:
                    selected = [league_id]
                    await query.answer(f"🔄 Remplacé par {league['name']}")
                else:
                    selected.append(league_id)
                    await query.answer(f"✅ Ajouté : {league['name']}")
            else:
                selected.append(league_id)
                await query.answer(f"✅ Ajouté : {league['name']}")
        
        await teable.update_or_create_user(user.id, user.username or user.first_name, selected)
        try:
            await query.edit_message_reply_markup(reply_markup=build_leagues_keyboard(selected, is_premium))
        except Exception: pass
        
    elif data == "validate":
        await query.edit_message_text(
            "✅ **C'est noté !**\n\nVos préférences ont été enregistrées. Vous recevrez les notifications pour vos championnats dès lundi.\n\n_Vous pouvez modifier vos choix à tout moment avec /ligues._",
            parse_mode='Markdown'
        )

# --- SERVEUR ---

@asynccontextmanager
async def lifespan(app: Starlette):
    global telegram_app, teable
    teable = TeableClient(TEABLE_API_URL, TEABLE_TOKEN)
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
    await teable.close()

async def webhook_handler(request: Request):
    try:
        data = await request.json()
        await telegram_app.process_update(Update.de_json(data, telegram_app.bot))
    except Exception as e: logger.error(f"Webhook Error: {e}")
    return JSONResponse({"status": "ok"})

app = Starlette(lifespan=lifespan, routes=[
    Route("/webhook", webhook_handler, methods=["POST"]),
    Route("/", lambda r: PlainTextResponse("YWFR Bot UX Active")),
    Route("/health", lambda r: JSONResponse({"status": "ok"}))
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
