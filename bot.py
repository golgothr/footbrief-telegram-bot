#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FootBrief Telegram Bot
Bot de rÃ©sumÃ©s de matchs de football avec modÃ¨le freemium
"""

import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    # Afrique & Asie
    'lg_sa': {'name': 'ð¸ð¦ Saudi Pro League', 'category': 'africa_asia'},
    'lg_jp': {'name': 'ð¯ðµ J-League', 'category': 'africa_asia'},
    'lg_cn': {'name': 'ð¨ð³ Chinese Super League', 'category': 'africa_asia'},
}

CATEGORIES = {
    'cat_europe_top': {'name': 'â­ Europe Top 5', 'leagues': ['lg_fr', 'lg_uk', 'lg_es', 'lg_de', 'lg_it']},
    'cat_europe_other': {'name': 'ð Europe Autres', 'leagues': ['lg_pt', 'lg_nl', 'lg_be', 'lg_tr']},
    'cat_americas': {'name': 'ð AmÃ©riques', 'leagues': ['lg_br', 'lg_ar', 'lg_mx', 'lg_us']},
    'cat_africa_asia': {'name': 'ð Afrique & Asie', 'leagues': ['lg_sa', 'lg_jp', 'lg_cn']},
}

# Google Sheets client
sheets_client = None


def init_google_sheets():
    """Initialise la connexion Ã  Google Sheets"""
    global sheets_client
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        if creds_json:
            creds_dict = json.loads(creds_json)
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            sheets_client = gspread.authorize(credentials)
            logger.info("Google Sheets connectÃ© avec succÃ¨s")
        else:
            logger.warning("GOOGLE_CREDENTIALS non dÃ©fini - mode sans persistance")
    except Exception as e:
        logger.error(f"Erreur connexion Google Sheets: {e}")


def get_user_data(user_id: int) -> dict:
    """RÃ©cupÃ¨re les donnÃ©es d'un utilisateur depuis Google Sheets"""
    if not sheets_client:
        return {'is_premium': False, 'selected_league': None, 'free_selection_used': False}
    
    try:
        sheet = sheets_client.open_by_key(GOOGLE_SHEET_ID).sheet1
        records = sheet.get_all_records()
        
        for record in records:
            if str(record.get('user_id')) == str(user_id):
                return {
                    'is_premium': record.get('is_premium', 'false').lower() == 'true',
                    'selected_league': record.get('selected_league'),
                    'free_selection_used': record.get('free_selection_used', 'false').lower() == 'true',
                    'username': record.get('username', ''),
                    'first_name': record.get('first_name', ''),
                }
        return {'is_premium': False, 'selected_league': None, 'free_selection_used': False}
    except Exception as e:
        logger.error(f"Erreur lecture utilisateur: {e}")
        return {'is_premium': False, 'selected_league': None, 'free_selection_used': False}


def save_user_data(user_id: int, username: str, first_name: str, data: dict):
    """Sauvegarde les donnÃ©es d'un utilisateur dans Google Sheets"""
    if not sheets_client:
        return
    
    try:
        sheet = sheets_client.open_by_key(GOOGLE_SHEET_ID).sheet1
        records = sheet.get_all_records()
        
        # Chercher si l'utilisateur existe
        row_index = None
        for i, record in enumerate(records):
            if str(record.get('user_id')) == str(user_id):
                row_index = i + 2  # +2 car index commence Ã  1 et header
                break
        
        row_data = [
            str(user_id),
            username or '',
            first_name or '',
            str(data.get('is_premium', False)).lower(),
            data.get('selected_league', ''),
            str(data.get('free_selection_used', False)).lower(),
            datetime.now().isoformat()
        ]
        
        if row_index:
            # Mise Ã  jour
            sheet.update(f'A{row_index}:G{row_index}', [row_data])
        else:
            # Nouvelle ligne
            sheet.append_row(row_data)
        
        logger.info(f"DonnÃ©es utilisateur {user_id} sauvegardÃ©es")
    except Exception as e:
        logger.error(f"Erreur sauvegarde utilisateur: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Message de bienvenue"""
    user = update.effective_user
    
    # Enregistrer l'utilisateur
    user_data = get_user_data(user.id)
    if not user_data.get('selected_league'):
        save_user_data(user.id, user.username, user.first_name, user_data)
    
    welcome_text = f"""
â½ *Bienvenue sur FootBrief, {user.first_name}!*

Je suis ton assistant pour les rÃ©sumÃ©s de matchs de football.

ð *Offre Gratuite:*
â¢ 1 championnat de ton choix
â¢ RÃ©sumÃ©s quotidiens des matchs

ð *Premium:*
â¢ Tous les championnats
â¢ Alertes en temps rÃ©el
â¢ Statistiques dÃ©taillÃ©es

Choisis une catÃ©gorie pour commencer:
"""
    
    keyboard = [
        [InlineKeyboardButton("â­ Europe Top 5", callback_data="cat_europe_top")],
        [InlineKeyboardButton("ð Europe Autres", callback_data="cat_europe_other")],
        [InlineKeyboardButton("ð AmÃ©riques", callback_data="cat_americas")],
        [InlineKeyboardButton("ð Afrique & Asie", callback_data="cat_africa_asia")],
        [InlineKeyboardButton("ð Passer Premium", callback_data="premium_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /menu - Affiche le menu principal"""
    keyboard = [
        [InlineKeyboardButton("â­ Europe Top 5", callback_data="cat_europe_top")],
        [InlineKeyboardButton("ð Europe Autres", callback_data="cat_europe_other")],
        [InlineKeyboardButton("ð AmÃ©riques", callback_data="cat_americas")],
        [InlineKeyboardButton("ð Afrique & Asie", callback_data="cat_africa_asia")],
        [InlineKeyboardButton("âï¸ Mon abonnement", callback_data="my_subscription")],
        [InlineKeyboardButton("ð Passer Premium", callback_data="premium_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "ð *Menu Principal*\n\nChoisis une catÃ©gorie:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GÃ¨re les callbacks des boutons inline"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = get_user_data(user.id)
    callback_data = query.data
    
    # CatÃ©gories
    if callback_data.startswith('cat_'):
        category = CATEGORIES.get(callback_data)
        if category:
            keyboard = []
            for league_id in category['leagues']:
                league = LEAGUES.get(league_id)
                if league:
                    # Marquer si c'est le championnat sÃ©lectionnÃ©
                    name = league['name']
                    if user_data.get('selected_league') == league_id:
                        name = f"â {name}"
                    keyboard.append([InlineKeyboardButton(name, callback_data=league_id)])
            
            keyboard.append([InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"*{category['name']}*\n\nChoisis un championnat:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # SÃ©lection d'un championnat
    elif callback_data.startswith('lg_'):
        league = LEAGUES.get(callback_data)
        if league:
            # VÃ©rifier les restrictions freemium
            if not user_data.get('is_premium'):
                if user_data.get('free_selection_used') and user_data.get('selected_league') != callback_data:
                    # DÃ©jÃ  un championnat gratuit sÃ©lectionnÃ©
                    keyboard = [
                        [InlineKeyboardButton("ð Passer Premium", callback_data="premium_info")],
                        [InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    current_league = LEAGUES.get(user_data.get('selected_league', ''), {}).get('name', 'Inconnu')
                    await query.edit_message_text(
                        f"â ï¸ *Limite atteinte*\n\n"
                        f"Tu as dÃ©jÃ  sÃ©lectionnÃ© *{current_league}* comme championnat gratuit.\n\n"
                        f"Pour suivre plusieurs championnats, passe en *Premium*! ð",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    return
            
            # Enregistrer la sÃ©lection
            user_data['selected_league'] = callback_data
            user_data['free_selection_used'] = True
            save_user_data(user.id, user.username, user.first_name, user_data)
            
            keyboard = [
                [InlineKeyboardButton("ð Voir les matchs", callback_data=f"matches_{callback_data}")],
                [InlineKeyboardButton("ð Activer les alertes", callback_data=f"alerts_{callback_data}")],
                [InlineKeyboardButton("â¬ï¸ Retour au menu", callback_data="back_main")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"â *{league['name']}* sÃ©lectionnÃ©!\n\n"
                f"Tu recevras maintenant les rÃ©sumÃ©s de ce championnat.\n\n"
                f"Que veux-tu faire?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # Retour au menu principal
    elif callback_data == 'back_main':
        keyboard = [
            [InlineKeyboardButton("â­ Europe Top 5", callback_data="cat_europe_top")],
            [InlineKeyboardButton("ð Europe Autres", callback_data="cat_europe_other")],
            [InlineKeyboardButton("ð AmÃ©riques", callback_data="cat_americas")],
            [InlineKeyboardButton("ð Afrique & Asie", callback_data="cat_africa_asia")],
            [InlineKeyboardButton("âï¸ Mon abonnement", callback_data="my_subscription")],
            [InlineKeyboardButton("ð Passer Premium", callback_data="premium_info")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ð *Menu Principal*\n\nChoisis une catÃ©gorie:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Infos Premium
    elif callback_data == 'premium_info':
        keyboard = [
            [InlineKeyboardButton("ð³ S'abonner (4.99â¬/mois)", callback_data="subscribe_premium")],
            [InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ð *FootBrief Premium*\n\n"
            "AccÃ¨de Ã  tous les avantages:\n\n"
            "â *Tous les championnats* - Plus de 15 ligues\n"
            "â *Alertes temps rÃ©el* - Buts, cartons, rÃ©sultats\n"
            "â *Statistiques dÃ©taillÃ©es* - xG, possession, tirs\n"
            "â *RÃ©sumÃ©s personnalisÃ©s* - Ãquipes favorites\n"
            "â *Sans publicitÃ©*\n\n"
            "ð° *Seulement 4.99â¬/mois*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Mon abonnement
    elif callback_data == 'my_subscription':
        status = "ð Premium" if user_data.get('is_premium') else "ð Gratuit"
        league_name = LEAGUES.get(user_data.get('selected_league', ''), {}).get('name', 'Aucun')
        
        keyboard = []
        if not user_data.get('is_premium'):
            keyboard.append([InlineKeyboardButton("ð Passer Premium", callback_data="premium_info")])
        keyboard.append([InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"âï¸ *Mon Abonnement*\n\n"
            f"ð *Statut:* {status}\n"
            f"â½ *Championnat:* {league_name}\n\n"
            f"{'Passe en Premium pour dÃ©bloquer tous les championnats!' if not user_data.get('is_premium') else 'Merci pour ton soutien! ð'}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Voir les matchs (placeholder)
    elif callback_data.startswith('matches_'):
        league_id = callback_data.replace('matches_', '')
        league = LEAGUES.get(league_id, {})
        
        keyboard = [[InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"ð *Matchs {league.get('name', '')}*\n\n"
            f"ð Chargement des matchs en cours...\n\n"
            f"_(Les rÃ©sumÃ©s seront envoyÃ©s automatiquement aprÃ¨s chaque journÃ©e)_",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Activer les alertes (placeholder)
    elif callback_data.startswith('alerts_'):
        keyboard = [[InlineKeyboardButton("â¬ï¸ Retour", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ð *Alertes activÃ©es!*\n\n"
            "Tu recevras des notifications pour:\n"
            "â¢ DÃ©but des matchs\n"
            "â¢ Buts marquÃ©s\n"
            "â¢ RÃ©sultats finaux\n\n"
            "_(FonctionnalitÃ© Premium - bientÃ´t disponible)_",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Abonnement Premium (placeholder)
    elif callback_data == 'subscribe_premium':
        keyboard = [[InlineKeyboardButton("â¬ï¸ Retour", callback_data="premium_info")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ð³ *Paiement*\n\n"
            "Le systÃ¨me de paiement sera bientÃ´t disponible.\n\n"
            "En attendant, contacte @footbrief_support pour un accÃ¨s Premium! ð",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    await update.message.reply_text(
        "â *Aide FootBrief*\n\n"
        "*Commandes disponibles:*\n"
        "/start - DÃ©marrer le bot\n"
        "/menu - Afficher le menu\n"
        "/help - Cette aide\n\n"
        "*Comment Ã§a marche?*\n"
        "1. Choisis un championnat\n"
        "2. ReÃ§ois les rÃ©sumÃ©s automatiquement\n"
        "3. Passe en Premium pour plus de championnats!\n\n"
        "*Support:* @footbrief_support",
        parse_mode='Markdown'
    )


def main():
    """Point d'entrÃ©e principal"""
    # Initialiser Google Sheets
    init_google_sheets()
    
    # CrÃ©er l'application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # DÃ©marrer le bot
    logger.info("FootBrief Bot dÃ©marrÃ©!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
