#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FootBrief Telegram Bot - Version corrigee
Bot de resumes de matchs de football avec modele freemium
Utilise webhook Telegram + serveur Starlette sur port 8000
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.requests import Request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8557397197:AAGe0JW04sKQFL-JAnY0SUK8g3QL4ACGkus')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1y6qjUmY90MdRqoa5UXOZ2EUgFrXO_7GuaG6CMa7Kwkk')
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get('PORT', 8000))

# Emojis simples
EMOJI_SOCCER = "\u26BD"      # â½
EMOJI_CHECK = "\u2705"       # â
EMOJI_STAR = "\u2B50"        # â­
EMOJI_TROPHY = "\U0001F3C6"  # ð
EMOJI_PIN = "\U0001F4CD"     # ð

# Drapeaux pays (sequences Unicode)
FLAG_FR = "\U0001F1EB\U0001F1F7"  # ð«ð·
FLAG_GB = "\U0001F1EC\U0001F1E7"  # ð¬ð§
FLAG_ES = "\U0001F1EA\U0001F1F8"  # ðªð¸
FLAG_IT = "\U0001F1EE\U0001F1F9"  # ð®ð¹
FLAG_DE = "\U0001F1E9\U0001F1EA"  # ð©ðª
FLAG_BE = "\U0001F1E7\U0001F1EA"  # ð§ðª
FLAG_NL = "\U0001F1F3\U0001F1F1"  # ð³ð±
FLAG_PT = "\U0001F1F5\U0001F1F9"  # ðµð¹
FLAG_CH = "\U0001F1E8\U0001F1ED"  # ð¨ð­
FLAG_DK = "\U0001F1E9\U0001F1F0"  # ð©ð°
FLAG_IE = "\U0001F1EE\U0001F1EA"  # ð®ðª
FLAG_US = "\U0001F1FA\U0001F1F8"  # ðºð¸
FLAG_AR = "\U0001F1E6\U0001F1F7"  # ð¦ð·
FLAG_MX = "\U0001F1F2\U0001F1FD"  # ð²ð½
FLAG_MA = "\U0001F1F2\U0001F1E6"  # ð²ð¦
FLAG_KR = "\U0001F1F0\U0001F1F7"  # ð°ð·
FLAG_EU = "\U0001F1EA\U0001F1FA"  # ðªðº
FLAG_WORLD = "\U0001F30D"         # ð

# Championnats disponibles
LEAGUES = {
    # Europe Top 5
    'lg_fr': {'name': f'{FLAG_FR} Ligue 1', 'category': 'europe_top'},
    'lg_uk': {'name': f'{FLAG_GB} Premier League', 'category': 'europe_top'},
    'lg_es': {'name': f'{FLAG_ES} La Liga', 'category': 'europe_top'},
    'lg_de': {'name': f'{FLAG_DE} Bundesliga', 'category': 'europe_top'},
    'lg_it': {'name': f'{FLAG_IT} Serie A', 'category': 'europe_top'},
    # Europe Autres
    'lg_be': {'name': f'{FLAG_BE} Jupiler Pro League', 'category': 'europe_other'},
    'lg_nl': {'name': f'{FLAG_NL} Eredivisie', 'category': 'europe_other'},
    'lg_pt': {'name': f'{FLAG_PT} Liga Portugal', 'category': 'europe_other'},
    'lg_ch': {'name': f'{FLAG_CH} Super League Suisse', 'category': 'europe_other'},
    'lg_dk': {'name': f'{FLAG_DK} Superligaen', 'category': 'europe_other'},
    'lg_ie': {'name': f'{FLAG_IE} League of Ireland', 'category': 'europe_other'},
    # International
    'lg_us': {'name': f'{FLAG_US} MLS', 'category': 'international'},
    'lg_ar': {'name': f'{FLAG_AR} Liga Argentina', 'category': 'international'},
    'lg_mx': {'name': f'{FLAG_MX} Liga MX', 'category': 'international'},
    'lg_ma': {'name': f'{FLAG_MA} Botola Pro', 'category': 'international'},
    'lg_kr': {'name': f'{FLAG_KR} K-League', 'category': 'international'},
    # Competitions
    'lg_ucl': {'name': f'{EMOJI_TROPHY} Ligue des Champions', 'category': 'competitions'},
    'lg_uel': {'name': f'{EMOJI_STAR} Ligue Europa', 'category': 'competitions'},
    'lg_uecl': {'name': f'{EMOJI_SOCCER} Conference League', 'category': 'competitions'},
}

# Categories de championnats
CATEGORIES = {
    'europe_top': {'name': f'{EMOJI_TROPHY} Europe Top 5', 'callback': 'cat_europe_top'},
    'europe_other': {'name': f'{FLAG_EU} Europe Autres', 'callback': 'cat_europe_other'},
    'international': {'name': f'{FLAG_WORLD} International', 'callback': 'cat_international'},
    'competitions': {'name': f'{EMOJI_STAR} Competitions', 'callback': 'cat_competitions'},
}

# Variable globale pour le client Google Sheets
gs_client = None

def init_google_sheets():
    """Initialise le client Google Sheets avec les credentials."""
    global gs_client
    
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        if not creds_json:
            logger.error("GOOGLE_CREDENTIALS non defini dans les variables d'environnement")
            return None
        
        logger.info(f"GOOGLE_CREDENTIALS trouve, longueur: {len(creds_json)}")
        
        # Parser le JSON
        try:
            creds_data = json.loads(creds_json)
            logger.info(f"JSON parse avec succes, type: {creds_data.get('type', 'inconnu')}")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON credentials: {e}")
            return None
        
        # Creer les credentials
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = Credentials.from_service_account_info(creds_data, scopes=scopes)
        gs_client = gspread.authorize(credentials)
        
        logger.info("Client Google Sheets initialise avec succes")
        return gs_client
        
    except Exception as e:
        logger.error(f"Erreur initialisation Google Sheets: {e}")
        return None

def update_user_preferences(user_id: int, username: str, selected_league: str):
    """Met a jour les preferences utilisateur dans Google Sheets."""
    global gs_client
    
    try:
        if not gs_client:
            logger.info("Client GS non initialise, tentative d'initialisation...")
            init_google_sheets()
        
        if not gs_client:
            logger.error("Impossible d'initialiser Google Sheets")
            return False
        
        # Ouvrir le spreadsheet
        spreadsheet = gs_client.open_by_key(GOOGLE_SHEET_ID)
        logger.info(f"Spreadsheet ouvert: {spreadsheet.title}")
        
        # Chercher ou creer la feuille "users"
        try:
            worksheet = spreadsheet.worksheet("users")
            logger.info("Feuille 'users' trouvee")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="users", rows=1000, cols=10)
            worksheet.update('A1:E1', [['user_id', 'username', 'selected_league', 'league_name', 'updated_at']])
            logger.info("Feuille 'users' creee")
        
        # Nom de la ligue
        league_info = LEAGUES.get(selected_league, {})
        league_name = league_info.get('name', selected_league)
        
        # Chercher l'utilisateur existant
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            cell = worksheet.find(str(user_id))
            row = cell.row
            worksheet.update(f'A{row}:E{row}', [[str(user_id), username or '', selected_league, league_name, timestamp]])
            logger.info(f"Utilisateur {user_id} mis a jour: {selected_league}")
        except gspread.CellNotFound:
            next_row = len(worksheet.get_all_values()) + 1
            worksheet.update(f'A{next_row}:E{next_row}', [[str(user_id), username or '', selected_league, league_name, timestamp]])
            logger.info(f"Nouvel utilisateur {user_id} ajoute: {selected_league}")
        
        return True
        
    except Exception as e:
        logger.error(f"Erreur mise a jour Google Sheets: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# Variable globale pour l'application Telegram
telegram_app = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /start."""
    user = update.effective_user
    logger.info(f"Commande /start de {user.id} ({user.username})")
    
    welcome_text = f"""<b>{EMOJI_SOCCER} Bienvenue sur FootBrief !</b>

Bonjour <b>{user.first_name}</b> !

Je suis ton assistant pour les resumes de matchs de football.

{EMOJI_CHECK} <b>Comment ca marche :</b>
1. Choisis ton championnat prefere
2. Recois des resumes des matchs

{EMOJI_STAR} Utilise /ligues pour selectionner ton championnat"""

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML"
    )

async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /ligues - affiche les categories."""
    logger.info(f"Commande /ligues de {update.effective_user.id}")
    
    keyboard = []
    for cat_id, cat_info in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_info['name'], callback_data=cat_info['callback'])])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""<b>{EMOJI_SOCCER} Choisis une categorie</b>

Selectionne la categorie de championnat qui t'interesse :"""

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    
    logger.info(f"Callback '{data}' de {user.id} ({user.username})")
    
    # Gestion des categories
    if data.startswith('cat_'):
        category = data.replace('cat_', '')
        await show_leagues_for_category(query, category)
        return
    
    # Gestion de la selection d'une ligue
    if data.startswith('lg_'):
        await handle_league_selection(query, data, user)
        return
    
    # Retour au menu
    if data == 'back_categories':
        await show_categories_menu(query)
        return

async def show_leagues_for_category(query, category: str):
    """Affiche les ligues d'une categorie."""
    keyboard = []
    
    for lg_id, lg_info in LEAGUES.items():
        if lg_info['category'] == category:
            keyboard.append([InlineKeyboardButton(lg_info['name'], callback_data=lg_id)])
    
    keyboard.append([InlineKeyboardButton(f"{EMOJI_PIN} Retour", callback_data='back_categories')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cat_name = CATEGORIES.get(category, {}).get('name', 'Championnats')
    
    text = f"""<b>{cat_name}</b>

Selectionne ton championnat :"""

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def show_categories_menu(query):
    """Affiche le menu des categories."""
    keyboard = []
    for cat_id, cat_info in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_info['name'], callback_data=cat_info['callback'])])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""<b>{EMOJI_SOCCER} Choisis une categorie</b>

Selectionne la categorie de championnat qui t'interesse :"""

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def handle_league_selection(query, league_id: str, user):
    """Gere la selection d'une ligue."""
    league_info = LEAGUES.get(league_id, {})
    league_name = league_info.get('name', league_id)
    
    logger.info(f"Selection ligue {league_id} ({league_name}) par {user.id}")
    
    # Mettre a jour Google Sheets
    success = update_user_preferences(
        user_id=user.id,
        username=user.username or user.first_name,
        selected_league=league_id
    )
    
    if success:
        text = f"""<b>{EMOJI_CHECK} Championnat enregistre !</b>

Tu as selectionne : <b>{league_name}</b>

{EMOJI_STAR} Tu recevras maintenant les resumes des matchs de ce championnat.

{EMOJI_PIN} Pour changer, utilise /ligues"""
        
        logger.info(f"Preference sauvegardee avec succes pour {user.id}")
    else:
        text = f"""<b>{EMOJI_CHECK} Championnat selectionne</b>

Tu as choisi : <b>{league_name}</b>

{EMOJI_PIN} Note : La sauvegarde n'a pas fonctionne, mais tu peux continuer.
Utilise /ligues pour reessayer."""
        
        logger.warning(f"Echec sauvegarde pour {user.id}")
    
    await query.edit_message_text(
        text,
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /help."""
    help_text = f"""<b>{EMOJI_SOCCER} Aide FootBrief</b>

<b>Commandes disponibles :</b>
/start - Demarrer le bot
/ligues - Choisir ton championnat
/help - Afficher cette aide

<b>Championnats disponibles :</b>
{EMOJI_TROPHY} Europe Top 5 (Ligue 1, Premier League, etc.)
{FLAG_EU} Europe Autres
{FLAG_WORLD} International
{EMOJI_STAR} Competitions UEFA

<b>Contact :</b>
Pour toute question, contacte l'administrateur."""

    await update.message.reply_text(help_text, parse_mode="HTML")

# Routes HTTP
async def health_check(request: Request):
    """Endpoint de health check."""
    return JSONResponse({
        "status": "ok",
        "bot": "FootBrief",
        "timestamp": datetime.now().isoformat()
    })

async def webhook_handler(request: Request):
    """Handler pour les webhooks Telegram."""
    global telegram_app
    
    try:
        data = await request.json()
        logger.info(f"Webhook recu: {json.dumps(data)[:500]}")
        
        if telegram_app:
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return JSONResponse({"status": "ok"})
        else:
            logger.error("telegram_app non initialise")
            return JSONResponse({"status": "error", "message": "Bot not ready"}, status_code=503)
            
    except Exception as e:
        logger.error(f"Erreur webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@asynccontextmanager
async def lifespan(app):
    """Gestion du cycle de vie de l'application."""
    global telegram_app
    
    logger.info("Demarrage de l'application...")
    
    # Initialiser Google Sheets
    init_google_sheets()
    
    # Creer l'application Telegram
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("ligues", ligues_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    # Initialiser l'application Telegram
    await telegram_app.initialize()
    await telegram_app.start()
    
    # Configurer le webhook
    webhook_url = os.environ.get('WEBHOOK_URL')
    if webhook_url:
        full_webhook_url = f"{webhook_url}{WEBHOOK_PATH}"
        try:
            await telegram_app.bot.set_webhook(url=full_webhook_url)
            logger.info(f"Webhook configure: {full_webhook_url}")
        except Exception as e:
            logger.error(f"Erreur configuration webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL non defini")
    
    logger.info(f"Bot demarre sur le port {PORT}")
    
    yield
    
    # Cleanup
    logger.info("Arret de l'application...")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

# Configuration des routes
routes = [
    Route("/", health_check, methods=["GET"]),
    Route("/health", health_check, methods=["GET"]),
    Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
]

# Creation de l'application Starlette
app = Starlette(
    debug=False,
    routes=routes,
    lifespan=lifespan
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
