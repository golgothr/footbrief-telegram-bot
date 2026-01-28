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

# Championnats disponibles
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
    # AmÃ©riques
    'lg_br': {'name': 'ð§ð· BrasileirÃ£o', 'category': 'americas'},
    'lg_ar': {'name': 'ð¦ð· Liga Argentina', 'category': 'americas'},
    'lg_mx': {'name': 'ð²ð½ Liga MX', 'category': 'americas'},
    'lg_us': {'name': 'ðºð¸ MLS', 'category': 'americas'},
    # CompÃ©titions
    'lg_ucl': {'name': 'ð Champions League', 'category': 'competitions'},
    'lg_uel': {'name': 'ð Europa League', 'category': 'competitions'},
    'lg_uecl': {'name': 'ð Conference League', 'category': 'competitions'},
}

# CatÃ©gories de championnats
CATEGORIES = {
    'europe_top': {'name': 'â­ Europe Top 5', 'emoji': 'â­'},
    'europe_other': {'name': 'ð Europe Autres', 'emoji': 'ð'},
    'americas': {'name': 'ð AmÃ©riques', 'emoji': 'ð'},
    'competitions': {'name': 'ð CompÃ©titions', 'emoji': 'ð'},
}

# Stockage utilisateurs en mÃ©moire (pour dÃ©mo - utiliser une DB en production)
user_data = {}

# Global application instance
telegram_app: Application = None


def get_google_sheets_client():
    """Initialise le client Google Sheets"""
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        if creds_json:
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        else:
            creds = Credentials.from_service_account_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Erreur connexion Google Sheets: {e}")
        return None


def get_user_subscription(user_id: int) -> dict:
    """RÃ©cupÃ¨re les infos d'abonnement d'un utilisateur"""
    if user_id not in user_data:
        user_data[user_id] = {
            'is_premium': False,
            'free_briefs_today': 0,
            'last_brief_date': None,
            'favorite_leagues': []
        }
    
    # Reset compteur si nouveau jour
    today = datetime.now().strftime('%Y-%m-%d')
    if user_data[user_id]['last_brief_date'] != today:
        user_data[user_id]['free_briefs_today'] = 0
        user_data[user_id]['last_brief_date'] = today
    
    return user_data[user_id]


def can_access_brief(user_id: int) -> tuple[bool, str]:
    """VÃ©rifie si l'utilisateur peut accÃ©der Ã  un brief"""
    sub = get_user_subscription(user_id)
    
    if sub['is_premium']:
        return True, ""
    
    if sub['free_briefs_today'] >= 3:
        return False, "ð Vous avez atteint votre limite de 3 briefs gratuits aujourd'hui.\n\nð Passez Premium pour un accÃ¨s illimitÃ©!"
    
    return True, ""


def increment_brief_count(user_id: int):
    """IncrÃ©mente le compteur de briefs"""
    sub = get_user_subscription(user_id)
    if not sub['is_premium']:
        sub['free_briefs_today'] += 1


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user
    logger.info(f"Commande /start de {user.first_name} (ID: {user.id})")
    
    welcome_text = f"""â½ **Bienvenue sur FootBrief, {user.first_name}!**

Je suis votre assistant pour des rÃ©sumÃ©s de matchs de football rapides et complets.

ð **Version Gratuite:**
â¢ 3 briefs par jour
â¢ AccÃ¨s Ã  tous les championnats

ð **Version Premium:**
â¢ Briefs illimitÃ©s
â¢ Alertes personnalisÃ©es
â¢ Analyses dÃ©taillÃ©es

Utilisez le menu ci-dessous pour commencer!"""

    keyboard = [
        [InlineKeyboardButton("ð Voir les Ligues", callback_data="menu_ligues")],
        [InlineKeyboardButton("â­ Mes Favoris", callback_data="menu_favoris")],
        [InlineKeyboardButton("ð Premium", callback_data="menu_premium")],
        [InlineKeyboardButton("â¹ï¸ Aide", callback_data="menu_aide")]
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GÃ¨re tous les callbacks des boutons inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    logger.info(f"Callback '{data}' de l'utilisateur {user_id}")
    
    # Menu principal des ligues
    if data == "menu_ligues":
        await show_categories_menu(query)
    
    # CatÃ©gories
    elif data.startswith("cat_"):
        category = data.replace("cat_", "")
        await show_leagues_in_category(query, category)
    
    # SÃ©lection d'une ligue
    elif data.startswith("lg_"):
        await show_league_matches(query, data, user_id)
    
    # Menu favoris
    elif data == "menu_favoris":
        await show_favorites_menu(query, user_id)
    
    # Menu premium
    elif data == "menu_premium":
        await show_premium_menu(query, user_id)
    
    # Menu aide
    elif data == "menu_aide":
        await show_help_menu(query)
    
    # Retour au menu principal
    elif data == "back_main":
        await show_main_menu(query)
    
    # Retour aux catÃ©gories
    elif data == "back_categories":
        await show_categories_menu(query)


async def show_main_menu(query):
    """Affiche le menu principal"""
    keyboard = [
        [InlineKeyboardButton("ð Voir les Ligues", callback_data="menu_ligues")],
        [InlineKeyboardButton("â­ Mes Favoris", callback_data="menu_favoris")],
        [InlineKeyboardButton("ð Premium", callback_data="menu_premium")],
        [InlineKeyboardButton("â¹ï¸ Aide", callback_data="menu_aide")]
    ]
    
    await query.edit_message_text(
        "â½ **Menu Principal**\n\nQue souhaitez-vous faire?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_categories_menu(query):
    """Affiche le menu des catÃ©gories"""
    keyboard = []
    for cat_id, cat_info in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(
            cat_info['name'],
            callback_data=f"cat_{cat_id}"
        )])
    keyboard.append([InlineKeyboardButton("ð Retour", callback_data="back_main")])
    
    await query.edit_message_text(
        "ð **Choisissez une catÃ©gorie:**",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_leagues_in_category(query, category: str):
    """Affiche les ligues d'une catÃ©gorie"""
    leagues_in_cat = {k: v for k, v in LEAGUES.items() if v['category'] == category}
    
    keyboard = []
    for lg_id, lg_info in leagues_in_cat.items():
        keyboard.append([InlineKeyboardButton(
            lg_info['name'],
            callback_data=lg_id
        )])
    keyboard.append([InlineKeyboardButton("ð Retour", callback_data="back_categories")])
    
    cat_name = CATEGORIES.get(category, {}).get('name', 'Ligues')
    await query.edit_message_text(
        f"**{cat_name}**\n\nSÃ©lectionnez un championnat:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_league_matches(query, league_id: str, user_id: int):
    """Affiche les matchs d'une ligue depuis Google Sheets"""
    # VÃ©rifier accÃ¨s
    can_access, message = can_access_brief(user_id)
    if not can_access:
        keyboard = [[InlineKeyboardButton("ð Passer Premium", callback_data="menu_premium")],
                    [InlineKeyboardButton("ð Retour", callback_data="back_categories")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    league_info = LEAGUES.get(league_id, {})
    league_name = league_info.get('name', 'Ligue inconnue')
    
    # RÃ©cupÃ©rer donnÃ©es Google Sheets
    client = get_google_sheets_client()
    matches_text = ""
    
    if client:
        try:
            sheet = client.open_by_key(GOOGLE_SHEET_ID)
            # Chercher l'onglet correspondant
            worksheet_name = league_id.replace('lg_', '').upper()
            try:
                worksheet = sheet.worksheet(worksheet_name)
                data = worksheet.get_all_records()
                
                if data:
                    for match in data[:5]:  # Limite Ã  5 matchs
                        home = match.get('home', match.get('Home', 'N/A'))
                        away = match.get('away', match.get('Away', 'N/A'))
                        score = match.get('score', match.get('Score', 'N/A'))
                        date = match.get('date', match.get('Date', ''))
                        matches_text += f"\nâ¢ {home} vs {away}: {score}"
                        if date:
                            matches_text += f" ({date})"
                else:
                    matches_text = "\n_Aucun match rÃ©cent disponible_"
            except gspread.WorksheetNotFound:
                matches_text = "\n_DonnÃ©es non disponibles pour cette ligue_"
        except Exception as e:
            logger.error(f"Erreur lecture Sheets: {e}")
            matches_text = "\n_Erreur de chargement des donnÃ©es_"
    else:
        matches_text = "\n_Service temporairement indisponible_"
    
    # IncrÃ©menter compteur
    increment_brief_count(user_id)
    sub = get_user_subscription(user_id)
    remaining = 3 - sub['free_briefs_today'] if not sub['is_premium'] else "â"
    
    text = f"""**{league_name}**

ð **Derniers rÃ©sultats:**{matches_text}

---
_Briefs restants aujourd'hui: {remaining}_"""

    keyboard = [
        [InlineKeyboardButton("ð Actualiser", callback_data=league_id)],
        [InlineKeyboardButton("ð Retour", callback_data="back_categories")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_favorites_menu(query, user_id: int):
    """Affiche le menu des favoris"""
    sub = get_user_subscription(user_id)
    favorites = sub.get('favorite_leagues', [])
    
    if not favorites:
        text = "â­ **Mes Favoris**\n\n_Vous n'avez pas encore de favoris._\n\nNaviguez dans les ligues et ajoutez-en!"
    else:
        text = "â­ **Mes Favoris**\n\n"
        for fav in favorites:
            if fav in LEAGUES:
                text += f"â¢ {LEAGUES[fav]['name']}\n"
    
    keyboard = [[InlineKeyboardButton("ð Retour", callback_data="back_main")]]
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_premium_menu(query, user_id: int):
    """Affiche le menu premium"""
    sub = get_user_subscription(user_id)
    
    if sub['is_premium']:
        text = """ð **Vous Ãªtes Premium!**

â Briefs illimitÃ©s
â Alertes personnalisÃ©es
â Analyses dÃ©taillÃ©es
â Support prioritaire

Merci pour votre soutien!"""
    else:
        text = """ð **Passez Premium!**

ð **Gratuit:**
â¢ 3 briefs/jour
â¢ AccÃ¨s basique

ð **Premium (4.99â¬/mois):**
â¢ Briefs illimitÃ©s
â¢ Alertes personnalisÃ©es
â¢ Analyses dÃ©taillÃ©es
â¢ Support prioritaire

_Paiement sÃ©curisÃ© via Stripe_"""

    keyboard = []
    if not sub['is_premium']:
        keyboard.append([InlineKeyboardButton("ð³ S'abonner", callback_data="subscribe_premium")])
    keyboard.append([InlineKeyboardButton("ð Retour", callback_data="back_main")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_help_menu(query):
    """Affiche le menu d'aide"""
    text = """â¹ï¸ **Aide - FootBrief**

**Commandes:**
â¢ /start - Menu principal
â¢ /help - Cette aide

**Comment Ã§a marche:**
1. Choisissez une catÃ©gorie
2. SÃ©lectionnez un championnat
3. Consultez les derniers rÃ©sultats

**Limites version gratuite:**
â¢ 3 briefs par jour
â¢ Reset Ã  minuit

**Contact:**
@FootBriefSupport

**Version:** 2.0 (Webhook)"""

    keyboard = [[InlineKeyboardButton("ð Retour", callback_data="back_main")]]
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ STARLETTE WEB SERVER ============

async def health_check(request: Request):
    """Endpoint de healthcheck pour Koyeb"""
    return JSONResponse({"status": "healthy", "service": "footbrief-bot"})


async def webhook_handler(request: Request):
    """Endpoint pour recevoir les updates Telegram"""
    global telegram_app
    try:
        data = await request.json()
        logger.info(f"Webhook reÃ§u: {json.dumps(data)[:200]}...")
        
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Erreur webhook: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


async def index(request: Request):
    """Page d'accueil"""
    return PlainTextResponse("FootBrief Telegram Bot - Running")


async def setup_webhook():
    """Configure le webhook Telegram au dÃ©marrage"""
    global telegram_app
    
    # CrÃ©er l'application Telegram
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", lambda u, c: show_help_menu(u.callback_query) if u.callback_query else u.message.reply_text("Utilisez /start pour accÃ©der au menu")))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Initialiser l'application
    await telegram_app.initialize()
    
    # Configurer le webhook
    webhook_url = os.environ.get('WEBHOOK_URL')
    if webhook_url:
        full_webhook_url = f"{webhook_url}{WEBHOOK_PATH}"
        await telegram_app.bot.set_webhook(url=full_webhook_url)
        logger.info(f"Webhook configurÃ©: {full_webhook_url}")
    else:
        # Essayer de rÃ©cupÃ©rer l'URL Koyeb automatiquement
        koyeb_url = os.environ.get('KOYEB_PUBLIC_DOMAIN')
        if koyeb_url:
            full_webhook_url = f"https://{koyeb_url}{WEBHOOK_PATH}"
            await telegram_app.bot.set_webhook(url=full_webhook_url)
            logger.info(f"Webhook configurÃ© via Koyeb: {full_webhook_url}")
        else:
            logger.warning("WEBHOOK_URL non dÃ©finie - webhook non configurÃ©")
    
    logger.info("Bot Telegram initialisÃ© avec succÃ¨s")


async def cleanup_webhook():
    """Nettoie Ã  l'arrÃªt"""
    global telegram_app
    if telegram_app:
        await telegram_app.shutdown()
        logger.info("Bot Telegram arrÃªtÃ©")


@asynccontextmanager
async def lifespan(app):
    """Gestion du cycle de vie de l'application"""
    await setup_webhook()
    yield
    await cleanup_webhook()


# Routes Starlette
routes = [
    Route("/", index),
    Route("/health", health_check),
    Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
]

# Application Starlette
app = Starlette(routes=routes, lifespan=lifespan)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
