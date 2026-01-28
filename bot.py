#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FootBrief Telegram Bot - Koyeb Web Service Version
Bot de rÃ©sumÃ©s de matchs de football avec modÃ¨le freemium
Utilise webhook Telegram + serveur Starlette
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

# Championnats disponibles avec emojis drapeaux
LEAGUES = {
    # Europe Top 5
    'lg_fr': {'name': 'ð«ð· Ligue 1', 'category': 'europe_top'},
    'lg_uk': {'name': 'ð´ó §ó ¢ó ¥ó ®ó §ó ¿ Premier League', 'category': 'europe_top'},
    'lg_es': {'name': 'ðªð¸ La Liga', 'category': 'europe_top'},
    'lg_de': {'name': 'ð©ðª Bundesliga', 'category': 'europe_top'},
    'lg_it': {'name': 'ð®ð¹ Serie A', 'category': 'europe_top'},
    # Europe Autres
    'lg_pt': {'name': 'ðµð¹ Liga Portugal', 'category': 'europe_other'},
    'lg_nl': {'name': 'ð³ð± Eredivisie', 'category': 'europe_other'},
    'lg_be': {'name': 'ð§ðª Pro League', 'category': 'europe_other'},
    'lg_tr': {'name': 'ð¹ð· SÃ¼per Lig', 'category': 'europe_other'},
    'lg_ru': {'name': 'ð·ðº Premier Liga', 'category': 'europe_other'},
    # AmÃ©riques
    'lg_br': {'name': 'ð§ð· BrasileirÃ£o', 'category': 'americas'},
    'lg_ar': {'name': 'ð¦ð· Liga Argentina', 'category': 'americas'},
    'lg_mx': {'name': 'ð²ð½ Liga MX', 'category': 'americas'},
    'lg_us': {'name': 'ðºð¸ MLS', 'category': 'americas'},
    # Afrique & Asie
    'lg_sa': {'name': 'ð¸ð¦ Saudi Pro League', 'category': 'africa_asia'},
    'lg_jp': {'name': 'ð¯ðµ J-League', 'category': 'africa_asia'},
    'lg_cn': {'name': 'ð¨ð³ Chinese Super League', 'category': 'africa_asia'},
}

# CatÃ©gories avec emojis
CATEGORIES = {
    'europe_top': {'name': 'ð Europe Top 5', 'callback': 'cat_europe_top'},
    'europe_other': {'name': 'ðªðº Europe Autres', 'callback': 'cat_europe_other'},
    'americas': {'name': 'ð AmÃ©riques', 'callback': 'cat_americas'},
    'africa_asia': {'name': 'ðð Afrique & Asie', 'callback': 'cat_africa_asia'},
}

# Variables globales
application = None
google_sheet = None


def get_google_sheet():
    """Connexion Ã  Google Sheets avec les credentials depuis variable d'env"""
    global google_sheet
    if google_sheet is None:
        try:
            creds_json = os.environ.get('GOOGLE_CREDENTIALS')
            if creds_json:
                creds_dict = json.loads(creds_json)
                credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                gc = gspread.authorize(credentials)
                google_sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1
                logger.info("â Connexion Google Sheets Ã©tablie")
            else:
                logger.warning("â ï¸ GOOGLE_CREDENTIALS non dÃ©fini")
        except Exception as e:
            logger.error(f"â Erreur Google Sheets: {e}")
    return google_sheet


def get_user_data(user_id: int) -> dict:
    """RÃ©cupÃ¨re les donnÃ©es d'un utilisateur depuis Google Sheets"""
    sheet = get_google_sheet()
    if not sheet:
        return None
    try:
        records = sheet.get_all_records()
        for record in records:
            if str(record.get('user_id')) == str(user_id):
                return record
        return None
    except Exception as e:
        logger.error(f"â Erreur lecture user {user_id}: {e}")
        return None


def save_user_data(user_id: int, username: str, leagues: list = None, is_premium: bool = False):
    """Sauvegarde ou met Ã  jour les donnÃ©es d'un utilisateur"""
    sheet = get_google_sheet()
    if not sheet:
        return False
    try:
        leagues_str = ','.join(leagues) if leagues else ''
        records = sheet.get_all_records()
        
        for i, record in enumerate(records):
            if str(record.get('user_id')) == str(user_id):
                row_num = i + 2
                sheet.update(f'A{row_num}:D{row_num}', [[str(user_id), username, leagues_str, str(is_premium)]])
                logger.info(f"â User {user_id} mis Ã  jour")
                return True
        
        sheet.append_row([str(user_id), username, leagues_str, str(is_premium)])
        logger.info(f"â Nouveau user {user_id} ajoutÃ©")
        return True
    except Exception as e:
        logger.error(f"â Erreur sauvegarde user {user_id}: {e}")
        return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Message de bienvenue engageant"""
    user = update.effective_user
    
    welcome_message = (
        f"â½ <b>Bienvenue sur FootBrief, {user.first_name} !</b> ð\n\n"
        f"ð Ton assistant personnel pour les <b>rÃ©sumÃ©s de matchs</b> de football !\n\n"
        f"ð± <b>Comment Ã§a marche ?</b>\n"
        f"1ï¸â£ Choisis tes championnats favoris\n"
        f"2ï¸â£ ReÃ§ois chaque jour les rÃ©sumÃ©s des matchs\n"
        f"3ï¸â£ Reste informÃ© sans effort ! ðª\n\n"
        f"ð <b>PrÃªt Ã  commencer ?</b> Clique sur le bouton ci-dessous !"
    )
    
    keyboard = [[InlineKeyboardButton("â½ Choisir mes ligues", callback_data="menu_ligues")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    save_user_data(user.id, user.username or user.first_name)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode="HTML")


async def menu_ligues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu des catÃ©gories de ligues avec emojis"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "ðï¸ <b>Choisis une catÃ©gorie</b>\n\n"
        "SÃ©lectionne la rÃ©gion qui t'intÃ©resse :"
    )
    
    keyboard = [
        [InlineKeyboardButton("ð Europe Top 5", callback_data="cat_europe_top")],
        [InlineKeyboardButton("ðªðº Europe Autres", callback_data="cat_europe_other")],
        [InlineKeyboardButton("ð AmÃ©riques", callback_data="cat_americas")],
        [InlineKeyboardButton("ðð Afrique & Asie", callback_data="cat_africa_asia")],
        [InlineKeyboardButton("â Terminer la sÃ©lection", callback_data="finish_selection")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les championnats d'une catÃ©gorie avec drapeaux"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace('cat_', '')
    user_id = query.from_user.id
    
    user_data = get_user_data(user_id)
    selected_leagues = []
    if user_data and user_data.get('selected_leagues'):
        selected_leagues = user_data['selected_leagues'].split(',')
    
    category_names = {
        'europe_top': 'ð Europe Top 5',
        'europe_other': 'ðªðº Europe Autres',
        'americas': 'ð AmÃ©riques',
        'africa_asia': 'ðð Afrique & Asie',
    }
    
    message = f"<b>{category_names.get(category, 'Championnats')}</b>\n\nSÃ©lectionne tes championnats :"
    
    keyboard = []
    for league_id, league_info in LEAGUES.items():
        if league_info['category'] == category:
            is_selected = league_id in selected_leagues
            check = "â " if is_selected else ""
            btn_text = f"{check}{league_info['name']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_{league_id}")])
    
    keyboard.append([InlineKeyboardButton("â¬ï¸ Retour aux catÃ©gories", callback_data="menu_ligues")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def toggle_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle la sÃ©lection d'une ligue"""
    query = update.callback_query
    await query.answer()
    
    league_id = query.data.replace('toggle_', '')
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    user_data = get_user_data(user_id)
    selected_leagues = []
    if user_data and user_data.get('selected_leagues'):
        selected_leagues = user_data['selected_leagues'].split(',')
    
    if league_id in selected_leagues:
        selected_leagues.remove(league_id)
    else:
        selected_leagues.append(league_id)
    
    save_user_data(user_id, username, selected_leagues)
    
    category = LEAGUES[league_id]['category']
    
    category_names = {
        'europe_top': 'ð Europe Top 5',
        'europe_other': 'ðªðº Europe Autres',
        'americas': 'ð AmÃ©riques',
        'africa_asia': 'ðð Afrique & Asie',
    }
    
    message = f"<b>{category_names.get(category, 'Championnats')}</b>\n\nSÃ©lectionne tes championnats :"
    
    keyboard = []
    for lid, league_info in LEAGUES.items():
        if league_info['category'] == category:
            is_selected = lid in selected_leagues
            check = "â " if is_selected else ""
            btn_text = f"{check}{league_info['name']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_{lid}")])
    
    keyboard.append([InlineKeyboardButton("â¬ï¸ Retour aux catÃ©gories", callback_data="menu_ligues")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def finish_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirme la sÃ©lection avec message de succÃ¨s"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    selected_leagues = []
    if user_data and user_data.get('selected_leagues'):
        selected_leagues = user_data['selected_leagues'].split(',')
    
    if selected_leagues:
        league_names = [LEAGUES[lid]['name'] for lid in selected_leagues if lid in LEAGUES]
        leagues_text = "\n".join([f"  â¢ {name}" for name in league_names])
        
        message = (
            f"ð <b>Parfait !</b> â\n\n"
            f"â½ Tu recevras les rÃ©sumÃ©s pour :\n{leagues_text}\n\n"
            f"ð¬ Les rÃ©sumÃ©s arrivent chaque matin Ã  9h !\n\n"
            f"ð¡ <i>Utilise /ligues pour modifier ta sÃ©lection</i>"
        )
    else:
        message = (
            f"â ï¸ <b>Aucun championnat sÃ©lectionnÃ©</b>\n\n"
            f"Clique sur le bouton ci-dessous pour choisir tes ligues favorites !"
        )
    
    keyboard = [[InlineKeyboardButton("â½ Modifier mes ligues", callback_data="menu_ligues")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def ligues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /ligues - AccÃ¨s direct au menu des ligues"""
    message = (
        "ðï¸ <b>Gestion de tes championnats</b>\n\n"
        "SÃ©lectionne une catÃ©gorie pour voir les championnats disponibles :"
    )
    
    keyboard = [
        [InlineKeyboardButton("ð Europe Top 5", callback_data="cat_europe_top")],
        [InlineKeyboardButton("ðªðº Europe Autres", callback_data="cat_europe_other")],
        [InlineKeyboardButton("ð AmÃ©riques", callback_data="cat_americas")],
        [InlineKeyboardButton("ðð Afrique & Asie", callback_data="cat_africa_asia")],
        [InlineKeyboardButton("â Voir ma sÃ©lection", callback_data="finish_selection")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help - Aide"""
    message = (
        "â¹ï¸ <b>Aide FootBrief</b>\n\n"
        "ð <b>Commandes disponibles :</b>\n"
        "  â¢ /start - DÃ©marrer le bot\n"
        "  â¢ /ligues - GÃ©rer tes championnats\n"
        "  â¢ /help - Afficher cette aide\n\n"
        "â½ <b>Fonctionnement :</b>\n"
        "Choisis tes championnats favoris et reÃ§ois "
        "chaque matin un rÃ©sumÃ© des matchs de la veille !\n\n"
        "ð¬ <b>Questions ?</b>\n"
        "Contacte @footbrief_support"
    )
    
    await update.message.reply_text(message, parse_mode="HTML")


async def webhook_handler(request: Request):
    """GÃ¨re les requÃªtes webhook de Telegram"""
    global application
    try:
        data = await request.json()
        logger.info(f"ð¨ Webhook reÃ§u: {json.dumps(data, indent=2)[:500]}")
        
        if application:
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"â Erreur webhook: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def health_check(request: Request):
    """Health check pour Koyeb"""
    return PlainTextResponse("OK")


async def root(request: Request):
    """Page d'accueil"""
    return JSONResponse({
        "service": "FootBrief Telegram Bot",
        "status": "running",
        "version": "2.0.0",
        "endpoints": {
            "webhook": WEBHOOK_PATH,
            "health": "/health"
        }
    })


@asynccontextmanager
async def lifespan(app):
    """Gestion du cycle de vie de l'application"""
    global application
    
    logger.info("ð DÃ©marrage de l'application...")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("ligues", ligues_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(menu_ligues, pattern="^menu_ligues$"))
    application.add_handler(CallbackQueryHandler(show_category, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(toggle_league, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(finish_selection, pattern="^finish_selection$"))
    
    await application.initialize()
    await application.start()
    
    get_google_sheet()
    
    logger.info("â Application prÃªte!")
    
    yield
    
    logger.info("ð ArrÃªt de l'application...")
    await application.stop()
    await application.shutdown()


routes = [
    Route("/", endpoint=root),
    Route("/health", endpoint=health_check),
    Route(WEBHOOK_PATH, endpoint=webhook_handler, methods=["POST"]),
]

app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
