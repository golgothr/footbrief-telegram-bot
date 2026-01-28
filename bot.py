#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Your Weekly Football Resume (YWFR) - Telegram Bot
Bot de resumes de matchs de football avec modele freemium
Utilise webhook Telegram + serveur Starlette sur port 8000
"""

import os
import json
import logging
import asyncio
import traceback
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

# Configuration du logging - niveau DEBUG pour plus de details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8557397197:AAGe0JW04sKQFL-JAnY0SUK8g3QL4ACGkus')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1y6qjUmY90MdRqoa5UXOZ2EUgFrXO_7GuaG6CMa7Kwkk')
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get('PORT', 8000))

# Nom du service
SERVICE_NAME = "Your Weekly Football Resume"
SERVICE_SHORT = "YWFR"

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
FLAG_TR = "\U0001F1F9\U0001F1F7"  # ð¹ð·
FLAG_BR = "\U0001F1E7\U0001F1F7"  # ð§ð·
FLAG_AR = "\U0001F1E6\U0001F1F7"  # ð¦ð·
FLAG_MX = "\U0001F1F2\U0001F1FD"  # ð²ð½
FLAG_US = "\U0001F1FA\U0001F1F8"  # ðºð¸
FLAG_SA = "\U0001F1F8\U0001F1E6"  # ð¸ð¦
FLAG_JP = "\U0001F1EF\U0001F1F5"  # ð¯ðµ
FLAG_CN = "\U0001F1E8\U0001F1F3"  # ð¨ð³

# Championnats disponibles avec emojis drapeaux
LEAGUES = {
    # Europe Top 5
    "ligue1": {"name": f"{FLAG_FR} Ligue 1", "free": True, "category": "europe_top"},
    "premier_league": {"name": f"{FLAG_GB} Premier League", "free": True, "category": "europe_top"},
    "laliga": {"name": f"{FLAG_ES} La Liga", "free": True, "category": "europe_top"},
    "bundesliga": {"name": f"{FLAG_DE} Bundesliga", "free": True, "category": "europe_top"},
    "serie_a": {"name": f"{FLAG_IT} Serie A", "free": True, "category": "europe_top"},
    # Europe Autres
    "liga_portugal": {"name": f"{FLAG_PT} Liga Portugal", "free": False, "category": "europe_other"},
    "eredivisie": {"name": f"{FLAG_NL} Eredivisie", "free": False, "category": "europe_other"},
    "pro_league": {"name": f"{FLAG_BE} Pro League", "free": False, "category": "europe_other"},
    "super_lig": {"name": f"{FLAG_TR} Super Lig", "free": False, "category": "europe_other"},
    # Ameriques
    "brasileirao": {"name": f"{FLAG_BR} Brasileirao", "free": False, "category": "americas"},
    "liga_argentina": {"name": f"{FLAG_AR} Liga Argentina", "free": False, "category": "americas"},
    "liga_mx": {"name": f"{FLAG_MX} Liga MX", "free": False, "category": "americas"},
    "mls": {"name": f"{FLAG_US} MLS", "free": False, "category": "americas"},
    # Afrique & Asie
    "saudi_pro": {"name": f"{FLAG_SA} Saudi Pro League", "free": False, "category": "africa_asia"},
    "j_league": {"name": f"{FLAG_JP} J-League", "free": False, "category": "africa_asia"},
    "chinese_super": {"name": f"{FLAG_CN} Chinese Super League", "free": False, "category": "africa_asia"},
}

# Cache utilisateurs en memoire
users_cache = {}

# Variable globale pour Google Sheets
sheets_client = None
worksheet = None

def debug_google_credentials():
    """Debug la configuration des credentials Google"""
    logger.info("=" * 60)
    logger.info("DEBUG GOOGLE CREDENTIALS")
    logger.info("=" * 60)
    
    creds_env = os.environ.get('GOOGLE_CREDENTIALS', '')
    logger.info(f"GOOGLE_CREDENTIALS env var present: {bool(creds_env)}")
    logger.info(f"GOOGLE_CREDENTIALS length: {len(creds_env)}")
    
    if creds_env:
        # Afficher les premiers caracteres pour debug
        logger.info(f"GOOGLE_CREDENTIALS starts with: {creds_env[:100]}...")
        logger.info(f"GOOGLE_CREDENTIALS ends with: ...{creds_env[-50:]}")
        
        # Tenter de parser le JSON
        try:
            creds_data = json.loads(creds_env)
            logger.info("JSON parsing: SUCCESS")
            logger.info(f"Keys in credentials: {list(creds_data.keys())}")
            if 'client_email' in creds_data:
                logger.info(f"Service account email: {creds_data['client_email']}")
            if 'project_id' in creds_data:
                logger.info(f"Project ID: {creds_data['project_id']}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing: FAILED - {e}")
            # Essayer de nettoyer le JSON
            logger.info("Attempting to clean JSON...")
            try:
                # Remplacer les newlines echappees
                cleaned = creds_env.replace('\\n', '\n')
                creds_data = json.loads(cleaned)
                logger.info("Cleaned JSON parsing: SUCCESS")
            except Exception as e2:
                logger.error(f"Cleaned JSON parsing: FAILED - {e2}")
    else:
        logger.warning("GOOGLE_CREDENTIALS is empty or not set!")
    
    logger.info(f"GOOGLE_SHEET_ID: {GOOGLE_SHEET_ID}")
    logger.info("=" * 60)

def init_google_sheets():
    """Initialise la connexion Google Sheets avec logs detailles"""
    global sheets_client, worksheet
    
    logger.info("=" * 60)
    logger.info("INITIALIZING GOOGLE SHEETS CONNECTION")
    logger.info("=" * 60)
    
    # Debug credentials first
    debug_google_credentials()
    
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS', '')
        
        if not creds_json:
            logger.error("GOOGLE_CREDENTIALS environment variable is not set!")
            logger.error("Please set GOOGLE_CREDENTIALS with the service account JSON")
            return False
        
        logger.info("Step 1: Parsing GOOGLE_CREDENTIALS JSON...")
        try:
            creds_data = json.loads(creds_json)
            logger.info(f"Step 1: SUCCESS - Found {len(creds_data)} keys")
        except json.JSONDecodeError as e:
            logger.error(f"Step 1: FAILED - JSON decode error: {e}")
            # Tentative de nettoyage
            logger.info("Attempting to clean the JSON string...")
            creds_json_cleaned = creds_json.replace('\\n', '\n')
            try:
                creds_data = json.loads(creds_json_cleaned)
                logger.info("Step 1b: SUCCESS after cleaning")
            except Exception as e2:
                logger.error(f"Step 1b: FAILED even after cleaning: {e2}")
                return False
        
        logger.info("Step 2: Creating Google credentials object...")
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_info(creds_data, scopes=scopes)
        logger.info(f"Step 2: SUCCESS - Service account: {credentials.service_account_email}")
        
        logger.info("Step 3: Authorizing gspread client...")
        sheets_client = gspread.authorize(credentials)
        logger.info("Step 3: SUCCESS - gspread client authorized")
        
        logger.info(f"Step 4: Opening spreadsheet with ID: {GOOGLE_SHEET_ID}")
        spreadsheet = sheets_client.open_by_key(GOOGLE_SHEET_ID)
        logger.info(f"Step 4: SUCCESS - Opened spreadsheet: {spreadsheet.title}")
        
        logger.info("Step 5: Getting first worksheet...")
        worksheet = spreadsheet.sheet1
        logger.info(f"Step 5: SUCCESS - Worksheet: {worksheet.title}")
        
        # Verifier les colonnes
        logger.info("Step 6: Checking worksheet structure...")
        headers = worksheet.row_values(1)
        logger.info(f"Step 6: Headers found: {headers}")
        
        expected_headers = ['user_id', 'username', 'selected_leagues', 'is_premium']
        missing = [h for h in expected_headers if h not in headers]
        if missing:
            logger.warning(f"Missing expected headers: {missing}")
            # Creer les headers si la sheet est vide
            if not headers or headers == ['']:
                logger.info("Creating headers in empty sheet...")
                worksheet.update('A1:D1', [expected_headers])
                logger.info("Headers created successfully")
        
        # Test de lecture
        logger.info("Step 7: Testing read operation...")
        all_values = worksheet.get_all_values()
        logger.info(f"Step 7: SUCCESS - Found {len(all_values)} rows (including header)")
        
        logger.info("=" * 60)
        logger.info("GOOGLE SHEETS INITIALIZATION COMPLETE")
        logger.info("=" * 60)
        return True
        
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet not found with ID: {GOOGLE_SHEET_ID}")
        logger.error("Make sure the service account has access to this spreadsheet")
        logger.error(f"Service account email to share with: footbrief-bot@footbrief-bot-461615.iam.gserviceaccount.com")
        return False
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API Error: {e}")
        logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Google Sheets: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def save_user_to_sheets(user_id: int, username: str, leagues: list, is_premium: bool = False):
    """Sauvegarde un utilisateur dans Google Sheets avec logs detailles"""
    global worksheet
    
    logger.info(f"[SAVE_USER] Starting save for user {user_id} ({username})")
    logger.info(f"[SAVE_USER] Leagues: {leagues}, Premium: {is_premium}")
    
    if worksheet is None:
        logger.error("[SAVE_USER] Worksheet is None! Attempting to reinitialize...")
        if not init_google_sheets():
            logger.error("[SAVE_USER] Reinitialization failed, saving to cache only")
            users_cache[user_id] = {
                'username': username,
                'leagues': leagues,
                'is_premium': is_premium
            }
            return False
    
    try:
        logger.info("[SAVE_USER] Step 1: Reading all values from sheet...")
        all_values = worksheet.get_all_values()
        logger.info(f"[SAVE_USER] Found {len(all_values)} rows")
        
        # Chercher si l'utilisateur existe deja
        user_row = None
        for idx, row in enumerate(all_values[1:], start=2):  # Skip header
            if row and row[0] == str(user_id):
                user_row = idx
                logger.info(f"[SAVE_USER] User found at row {user_row}")
                break
        
        leagues_str = ','.join(leagues)
        premium_str = 'true' if is_premium else 'false'
        new_data = [str(user_id), username or '', leagues_str, premium_str]
        logger.info(f"[SAVE_USER] Data to save: {new_data}")
        
        if user_row:
            logger.info(f"[SAVE_USER] Step 2: Updating existing row {user_row}...")
            worksheet.update(f'A{user_row}:D{user_row}', [new_data])
            logger.info(f"[SAVE_USER] SUCCESS - Updated row {user_row}")
        else:
            logger.info("[SAVE_USER] Step 2: Appending new row...")
            worksheet.append_row(new_data)
            logger.info("[SAVE_USER] SUCCESS - New row appended")
        
        # Mettre a jour le cache aussi
        users_cache[user_id] = {
            'username': username,
            'leagues': leagues,
            'is_premium': is_premium
        }
        logger.info("[SAVE_USER] Cache updated")
        
        return True
        
    except gspread.exceptions.APIError as e:
        logger.error(f"[SAVE_USER] API Error: {e}")
        logger.error(f"[SAVE_USER] Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return False
    except Exception as e:
        logger.error(f"[SAVE_USER] Error saving user: {e}")
        logger.error(f"[SAVE_USER] Traceback: {traceback.format_exc()}")
        return False

def load_user_from_sheets(user_id: int):
    """Charge un utilisateur depuis Google Sheets"""
    global worksheet
    
    # Verifier le cache d'abord
    if user_id in users_cache:
        logger.info(f"[LOAD_USER] User {user_id} found in cache")
        return users_cache[user_id]
    
    if worksheet is None:
        logger.warning("[LOAD_USER] Worksheet not initialized")
        return None
    
    try:
        logger.info(f"[LOAD_USER] Searching for user {user_id} in sheet...")
        all_values = worksheet.get_all_values()
        
        for row in all_values[1:]:  # Skip header
            if row and row[0] == str(user_id):
                user_data = {
                    'username': row[1] if len(row) > 1 else '',
                    'leagues': row[2].split(',') if len(row) > 2 and row[2] else [],
                    'is_premium': row[3].lower() == 'true' if len(row) > 3 else False
                }
                users_cache[user_id] = user_data
                logger.info(f"[LOAD_USER] User {user_id} loaded from sheet: {user_data}")
                return user_data
        
        logger.info(f"[LOAD_USER] User {user_id} not found in sheet")
        return None
        
    except Exception as e:
        logger.error(f"[LOAD_USER] Error loading user: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user
    logger.info(f"[START] User {user.id} ({user.username}) started the bot")
    
    # Charger l'utilisateur existant ou creer nouveau
    user_data = load_user_from_sheets(user.id)
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_TROPHY} Choisir mon championnat", callback_data="select_league")],
        [InlineKeyboardButton(f"{EMOJI_STAR} Premium - Tous les championnats", callback_data="premium_info")],
    ]
    
    if user_data and user_data.get('leagues'):
        keyboard.append([InlineKeyboardButton(f"{EMOJI_SOCCER} Mes championnats", callback_data="my_leagues")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
{EMOJI_SOCCER} *Bienvenue sur {SERVICE_NAME}!* {EMOJI_SOCCER}

Je suis votre assistant pour ne rien manquer du football!

{EMOJI_TROPHY} *Gratuit*: 1 championnat au choix parmi les Top 5 europeens
{EMOJI_STAR} *Premium*: Tous les championnats + alertes temps reel

Selectionnez une option ci-dessous:
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def select_league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les categories de championnats"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_TROPHY} Europe Top 5 (Gratuit)", callback_data="cat_europe_top")],
        [InlineKeyboardButton(f"{FLAG_PT} Europe Autres (Premium)", callback_data="cat_europe_other")],
        [InlineKeyboardButton(f"{FLAG_BR} Ameriques (Premium)", callback_data="cat_americas")],
        [InlineKeyboardButton(f"{FLAG_SA} Afrique & Asie (Premium)", callback_data="cat_africa_asia")],
        [InlineKeyboardButton("< Retour", callback_data="back_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{EMOJI_PIN} *Selectionnez une region:*\n\nLes championnats Europe Top 5 sont gratuits!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_category_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les championnats d'une categorie"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    category = query.data.replace("cat_", "")
    
    logger.info(f"[CATEGORY] User {user.id} viewing category: {category}")
    
    # Verifier si premium pour les categories payantes
    user_data = load_user_from_sheets(user.id)
    is_premium = user_data.get('is_premium', False) if user_data else False
    
    keyboard = []
    for league_id, league_info in LEAGUES.items():
        if league_info['category'] == category:
            # Si pas premium et ligue payante, montrer comme verrouillee
            if not is_premium and not league_info['free']:
                btn_text = f"{league_info['name']} {EMOJI_STAR}"
                callback = "premium_required"
            else:
                btn_text = league_info['name']
                callback = f"toggle_{league_id}"
            
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("< Retour", callback_data="select_league")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    category_names = {
        'europe_top': f'{EMOJI_TROPHY} Europe Top 5',
        'europe_other': f'{FLAG_PT} Europe Autres',
        'americas': f'{FLAG_BR} Ameriques',
        'africa_asia': f'{FLAG_SA} Afrique & Asie'
    }
    
    await query.edit_message_text(
        f"*{category_names.get(category, 'Championnats')}*\n\nSelectionnez un championnat:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def toggle_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/desactive un championnat pour l'utilisateur"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    league_id = query.data.replace("toggle_", "")
    
    logger.info(f"[TOGGLE] User {user.id} toggling league: {league_id}")
    
    # Charger donnees utilisateur
    user_data = load_user_from_sheets(user.id)
    if user_data is None:
        user_data = {'username': user.username, 'leagues': [], 'is_premium': False}
    
    current_leagues = user_data.get('leagues', [])
    is_premium = user_data.get('is_premium', False)
    
    league_info = LEAGUES.get(league_id)
    if not league_info:
        await query.edit_message_text("Championnat non trouve.")
        return
    
    # Verifier les droits
    if not is_premium and not league_info['free']:
        await query.edit_message_text(
            f"{EMOJI_STAR} *Ce championnat necessite Premium*\n\n"
            f"Passez a Premium pour acceder a tous les championnats!",
            parse_mode='Markdown'
        )
        return
    
    # Toggle la ligue
    if league_id in current_leagues:
        current_leagues.remove(league_id)
        action = "retire"
    else:
        # Utilisateur gratuit: max 1 ligue
        if not is_premium and len(current_leagues) >= 1:
            # Remplacer la ligue existante
            current_leagues = [league_id]
            action = "remplace par"
        else:
            current_leagues.append(league_id)
            action = "ajoute"
    
    # Sauvegarder
    logger.info(f"[TOGGLE] Saving leagues for user {user.id}: {current_leagues}")
    save_success = save_user_to_sheets(user.id, user.username, current_leagues, is_premium)
    
    if save_success:
        status_msg = f"{EMOJI_CHECK} {league_info['name']} {action}!"
    else:
        status_msg = f"{EMOJI_CHECK} {league_info['name']} {action}! (sauvegarde locale uniquement)"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_SOCCER} Voir mes championnats", callback_data="my_leagues")],
        [InlineKeyboardButton("< Retour aux categories", callback_data="select_league")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(status_msg, reply_markup=reply_markup)

async def my_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les championnats de l'utilisateur"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = load_user_from_sheets(user.id)
    
    if not user_data or not user_data.get('leagues'):
        await query.edit_message_text(
            f"{EMOJI_SOCCER} Vous n'avez pas encore selectionne de championnat.\n\n"
            f"Utilisez /start pour commencer!",
            parse_mode='Markdown'
        )
        return
    
    leagues_list = []
    for league_id in user_data['leagues']:
        if league_id in LEAGUES:
            leagues_list.append(f"  {EMOJI_CHECK} {LEAGUES[league_id]['name']}")
    
    is_premium = user_data.get('is_premium', False)
    status = f"{EMOJI_STAR} Premium" if is_premium else "Gratuit"
    
    text = f"""
{EMOJI_SOCCER} *Mes championnats {SERVICE_SHORT}*

{chr(10).join(leagues_list)}

Statut: {status}
"""
    
    keyboard = [
        [InlineKeyboardButton("Modifier mes championnats", callback_data="select_league")],
        [InlineKeyboardButton("< Retour", callback_data="back_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos Premium"""
    query = update.callback_query
    await query.answer()
    
    text = f"""
{EMOJI_STAR} *{SERVICE_NAME} Premium* {EMOJI_STAR}

Debloquez tous les avantages:

{EMOJI_CHECK} *15+ championnats* - Europe, Ameriques, Afrique, Asie
{EMOJI_CHECK} *Alertes temps reel* - Buts, cartons, resultats
{EMOJI_CHECK} *Statistiques avancees* - xG, possession, tirs
{EMOJI_CHECK} *Historique complet* - Acces a tous les resumes

Prix: *4.99 EUR/mois*

Contactez @votre_support pour souscrire!
"""
    
    keyboard = [
        [InlineKeyboardButton("< Retour", callback_data="back_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def premium_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message quand Premium est requis"""
    query = update.callback_query
    await query.answer(f"{EMOJI_STAR} Ce championnat necessite Premium!", show_alert=True)

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu principal"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = load_user_from_sheets(user.id)
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_TROPHY} Choisir mon championnat", callback_data="select_league")],
        [InlineKeyboardButton(f"{EMOJI_STAR} Premium - Tous les championnats", callback_data="premium_info")],
    ]
    
    if user_data and user_data.get('leagues'):
        keyboard.append([InlineKeyboardButton(f"{EMOJI_SOCCER} Mes championnats", callback_data="my_leagues")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
{EMOJI_SOCCER} *Bienvenue sur {SERVICE_NAME}!* {EMOJI_SOCCER}

Je suis votre assistant pour ne rien manquer du football!

{EMOJI_TROPHY} *Gratuit*: 1 championnat au choix parmi les Top 5 europeens
{EMOJI_STAR} *Premium*: Tous les championnats + alertes temps reel

Selectionnez une option ci-dessous:
"""
    
    await query.edit_message_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    help_text = f"""
{EMOJI_SOCCER} *Aide {SERVICE_NAME}* {EMOJI_SOCCER}

*Commandes disponibles:*
/start - Demarrer le bot
/help - Afficher cette aide
/status - Voir vos championnats

*Comment ca marche:*
1. Selectionnez un championnat gratuit ou passez Premium
2. Recevez les resumes de matchs automatiquement
3. Personnalisez vos alertes

*Support:* @votre_support
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /status"""
    user = update.effective_user
    user_data = load_user_from_sheets(user.id)
    
    if not user_data:
        await update.message.reply_text(
            f"Vous n'etes pas encore inscrit. Utilisez /start pour commencer!"
        )
        return
    
    leagues_text = "Aucun" if not user_data.get('leagues') else ", ".join(
        LEAGUES[l]['name'] for l in user_data['leagues'] if l in LEAGUES
    )
    status = "Premium" if user_data.get('is_premium') else "Gratuit"
    
    await update.message.reply_text(
        f"{EMOJI_SOCCER} *Votre profil {SERVICE_SHORT}*\n\n"
        f"Championnats: {leagues_text}\n"
        f"Statut: {status}",
        parse_mode='Markdown'
    )

# Application Telegram
telegram_app = None

@asynccontextmanager
async def lifespan(app):
    """Gestion du cycle de vie de l'application"""
    global telegram_app
    
    logger.info("=" * 60)
    logger.info(f"STARTING {SERVICE_NAME} BOT")
    logger.info("=" * 60)
    
    # Initialiser Google Sheets au demarrage
    sheets_ok = init_google_sheets()
    if sheets_ok:
        logger.info("Google Sheets: CONNECTED")
    else:
        logger.warning("Google Sheets: NOT CONNECTED - using cache only")
    
    # Initialiser le bot Telegram
    logger.info("Initializing Telegram bot...")
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    telegram_app.add_handler(CallbackQueryHandler(select_league_callback, pattern="^select_league$"))
    telegram_app.add_handler(CallbackQueryHandler(show_category_leagues, pattern="^cat_"))
    telegram_app.add_handler(CallbackQueryHandler(toggle_league, pattern="^toggle_"))
    telegram_app.add_handler(CallbackQueryHandler(my_leagues, pattern="^my_leagues$"))
    telegram_app.add_handler(CallbackQueryHandler(premium_info, pattern="^premium_info$"))
    telegram_app.add_handler(CallbackQueryHandler(premium_required, pattern="^premium_required$"))
    telegram_app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    
    await telegram_app.initialize()
    
    # Configurer le webhook
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    if webhook_url:
        full_webhook_url = f"{webhook_url}{WEBHOOK_PATH}"
        logger.info(f"Setting webhook to: {full_webhook_url}")
        await telegram_app.bot.set_webhook(url=full_webhook_url)
        logger.info("Webhook configured successfully")
    else:
        logger.warning("WEBHOOK_URL not set, webhook not configured")
    
    logger.info(f"{SERVICE_NAME} bot started successfully!")
    
    yield
    
    # Cleanup
    logger.info("Shutting down...")
    if telegram_app:
        await telegram_app.shutdown()

async def webhook_handler(request: Request):
    """Handler pour les webhooks Telegram"""
    global telegram_app
    
    try:
        data = await request.json()
        logger.debug(f"Webhook received: {json.dumps(data, indent=2)}")
        
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

async def health_check(request: Request):
    """Health check endpoint"""
    global worksheet
    
    sheets_status = "connected" if worksheet is not None else "disconnected"
    
    return JSONResponse({
        "status": "healthy",
        "service": SERVICE_NAME,
        "google_sheets": sheets_status,
        "timestamp": datetime.now().isoformat()
    })

async def homepage(request: Request):
    """Page d'accueil"""
    return PlainTextResponse(f"{SERVICE_NAME} Telegram Bot is running!")

# Configuration des routes
routes = [
    Route("/", homepage),
    Route("/health", health_check),
    Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
]

# Application Starlette
app = Starlette(
    routes=routes,
    lifespan=lifespan
)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting {SERVICE_NAME} server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
