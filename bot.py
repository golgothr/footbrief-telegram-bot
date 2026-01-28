#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Your Weekly Football Resume (YWFR) - Telegram Bot
Bot de resumes de matchs de football avec modele freemium
Utilise webhook Telegram + serveur Starlette sur port 8000
Stockage des preferences utilisateur via Teable API
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
import httpx

# Configuration du logging - niveau DEBUG pour plus de details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8557397197:AAGe0JW04sKQFL-JAnY0SUK8g3QL4ACGkus')
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get('PORT', 8000))

# Configuration Teable API
TEABLE_API_URL = os.getenv("TEABLE_API_URL")
TEABLE_TOKEN = os.getenv("TEABLE_TOKEN")

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
FLAG_EU = "\U0001F1EA\U0001F1FA"  # ðªðº

# Championnats disponibles avec leur ID Football-Data
LEAGUES = {
    "ligue1": {"name": f"{FLAG_FR} Ligue 1", "id": "FL1", "premium": False},
    "premier_league": {"name": f"{FLAG_GB} Premier League", "id": "PL", "premium": False},
    "laliga": {"name": f"{FLAG_ES} La Liga", "id": "PD", "premium": True},
    "serie_a": {"name": f"{FLAG_IT} Serie A", "id": "SA", "premium": True},
    "bundesliga": {"name": f"{FLAG_DE} Bundesliga", "id": "BL1", "premium": True},
    "champions_league": {"name": f"{FLAG_EU} Champions League", "id": "CL", "premium": True},
}

# Championnats gratuits
FREE_LEAGUES = ["ligue1", "premier_league"]

# Variable globale pour l'application Telegram
telegram_app = None


async def update_user_preferences(user_id: int, username: str, selected_leagues: list, is_premium: bool = False):
    """
    Met a jour ou cree les preferences utilisateur dans Teable.
    - GET pour chercher si user_id existe
    - PATCH pour mettre a jour si existe
    - POST pour creer si n'existe pas
    """
    headers = {
        "Authorization": f"Bearer {TEABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Convertir la liste des ligues en string JSON
    leagues_str = json.dumps(selected_leagues)
    
    async with httpx.AsyncClient() as client:
        try:
            # 1. Chercher si l'utilisateur existe deja
            search_url = f"https://app.teable.ai/api/table/tbleoX3giJgStjjLCds/record?fieldKeyType=name&filter={{"field":"user_id","operator":"=","value":{user_id}}}"
            
            logger.debug(f"Recherche utilisateur {user_id} dans Teable")
            response = await client.get(search_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])
                
                if records:
                    # Utilisateur existe -> PATCH pour mettre a jour
                    record_id = records[0]["id"]
                    patch_url = f"https://app.teable.ai/api/table/tbleoX3giJgStjjLCds/record/{record_id}?fieldKeyType=name"
                    
                    update_data = {
                        "record": {
                            "fields": {
                                "username": username or "",
                                "selected_leagues": leagues_str,
                                "is_premium": is_premium
                            }
                        }
                    }
                    
                    logger.debug(f"Mise a jour utilisateur {user_id} (record {record_id})")
                    patch_response = await client.patch(patch_url, headers=headers, json=update_data)
                    
                    if patch_response.status_code in [200, 201]:
                        logger.info(f"Preferences mises a jour pour user {user_id}")
                        return True
                    else:
                        logger.error(f"Erreur PATCH Teable: {patch_response.status_code} - {patch_response.text}")
                        return False
                else:
                    # Utilisateur n'existe pas -> POST pour creer
                    create_url = f"https://app.teable.ai/api/table/tbleoX3giJgStjjLCds/record?fieldKeyType=name"
                    
                    create_data = {
                        "records": [{
                            "fields": {
                                "user_id": user_id,
                                "username": username or "",
                                "selected_leagues": leagues_str,
                                "is_premium": is_premium
                            }
                        }]
                    }
                    
                    logger.debug(f"Creation utilisateur {user_id} dans Teable")
                    post_response = await client.post(create_url, headers=headers, json=create_data)
                    
                    if post_response.status_code in [200, 201]:
                        logger.info(f"Utilisateur {user_id} cree dans Teable")
                        return True
                    else:
                        logger.error(f"Erreur POST Teable: {post_response.status_code} - {post_response.text}")
                        return False
            else:
                logger.error(f"Erreur GET Teable: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur Teable: {e}")
            traceback.print_exc()
            return False


async def get_user_preferences(user_id: int) -> dict:
    """
    Recupere les preferences utilisateur depuis Teable.
    Retourne un dict avec selected_leagues et is_premium.
    """
    headers = {
        "Authorization": f"Bearer {TEABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            search_url = f"https://app.teable.ai/api/table/tbleoX3giJgStjjLCds/record?fieldKeyType=name&filter={{"field":"user_id","operator":"=","value":{user_id}}}"
            
            response = await client.get(search_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])
                
                if records:
                    fields = records[0].get("fields", {})
                    leagues_str = fields.get("selected_leagues", "[]")
                    try:
                        selected_leagues = json.loads(leagues_str)
                    except:
                        selected_leagues = []
                    
                    return {
                        "selected_leagues": selected_leagues,
                        "is_premium": fields.get("is_premium", False)
                    }
            
            # Par defaut, retourner les ligues gratuites
            return {
                "selected_leagues": FREE_LEAGUES.copy(),
                "is_premium": False
            }
                
        except Exception as e:
            logger.error(f"Erreur lecture Teable: {e}")
            return {
                "selected_leagues": FREE_LEAGUES.copy(),
                "is_premium": False
            }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour /start - enregistre aussi l'utilisateur dans Teable"""
    user = update.effective_user
    logger.info(f"Commande /start de {user.username} (ID: {user.id})")
    
    # Enregistrer l'utilisateur dans Teable (cree s'il n'existe pas, ignore sinon)
    try:
        username = user.username or user.first_name or ""
        await update_user_preferences(
            user_id=user.id,
            username=username,
            selected_leagues=[],  # Vide par defaut
            is_premium=False
        )
        logger.info(f"Utilisateur {user.id} enregistre dans Teable")
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement dans Teable: {e}")
        # On continue meme si l'enregistrement echoue
    
    welcome_message = f"""
{EMOJI_SOCCER} *Bienvenue sur {SERVICE_NAME}!* {EMOJI_SOCCER}

Je suis votre assistant pour suivre l'actualite du football.

{EMOJI_STAR} *Fonctionnalites:*
- Resumes des matchs de vos championnats preferes
- Selection personnalisee des ligues
- Mode Premium pour plus de championnats

{EMOJI_PIN} *Commandes:*
/start - Afficher ce message
/leagues - Selectionner vos championnats
/resume - Obtenir le resume de la semaine
/premium - Informations sur le mode Premium
/help - Aide et support

Commencez par selectionner vos championnats avec /leagues!
"""
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour /help"""
    help_text = f"""
{EMOJI_TROPHY} *Aide - {SERVICE_NAME}* {EMOJI_TROPHY}

*Comment utiliser le bot:*

1. **/leagues** - Selectionnez les championnats que vous souhaitez suivre
   - Ligue 1 et Premier League sont gratuits
   - Les autres championnats necessitent Premium

2. **/resume** - Recevez un resume des matchs de la semaine pour vos championnats selectionnes

3. **/premium** - Decouvrez les avantages du mode Premium

*Championnats disponibles:*
{FLAG_FR} Ligue 1 (Gratuit)
{FLAG_GB} Premier League (Gratuit)
{FLAG_ES} La Liga (Premium)
{FLAG_IT} Serie A (Premium)
{FLAG_DE} Bundesliga (Premium)
{FLAG_EU} Champions League (Premium)

*Support:* Contactez @golgothr pour toute question.
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour /leagues - Affiche la selection des championnats"""
    user = update.effective_user
    logger.info(f"Commande /leagues de {user.username} (ID: {user.id})")
    
    # Recuperer les preferences actuelles
    prefs = await get_user_preferences(user.id)
    selected = prefs.get("selected_leagues", [])
    is_premium = prefs.get("is_premium", False)
    
    # Construire le clavier
    keyboard = []
    for league_id, league_info in LEAGUES.items():
        is_selected = league_id in selected
        is_locked = league_info["premium"] and not is_premium
        
        if is_locked:
            button_text = f"{EMOJI_STAR} {league_info['name']} (Premium)"
        elif is_selected:
            button_text = f"{EMOJI_CHECK} {league_info['name']}"
        else:
            button_text = f"   {league_info['name']}"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"league_{league_id}")])
    
    keyboard.append([InlineKeyboardButton(f"{EMOJI_CHECK} Valider ma selection", callback_data="validate_leagues")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""
{EMOJI_SOCCER} *Selection des championnats*

Selectionnez les championnats que vous souhaitez suivre.
{EMOJI_CHECK} = selectionne
{EMOJI_STAR} = necessite Premium

{'Vous etes Premium!' if is_premium else 'Mode gratuit - Ligue 1 et Premier League disponibles'}
"""
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les callbacks des boutons inline"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    logger.debug(f"Callback {data} de {user.username} (ID: {user.id})")
    
    if data.startswith("league_"):
        league_id = data.replace("league_", "")
        
        # Recuperer les preferences actuelles
        prefs = await get_user_preferences(user.id)
        selected = prefs.get("selected_leagues", [])
        is_premium = prefs.get("is_premium", False)
        
        # Verifier si la ligue est premium
        if LEAGUES[league_id]["premium"] and not is_premium:
            await query.answer("Cette ligue necessite un abonnement Premium!", show_alert=True)
            return
        
        # Toggle la selection
        if league_id in selected:
            selected.remove(league_id)
        else:
            selected.append(league_id)
        
        # Sauvegarder
        await update_user_preferences(user.id, user.username, selected, is_premium)
        
        # Reconstruire le clavier
        keyboard = []
        for lid, league_info in LEAGUES.items():
            is_selected = lid in selected
            is_locked = league_info["premium"] and not is_premium
            
            if is_locked:
                button_text = f"{EMOJI_STAR} {league_info['name']} (Premium)"
            elif is_selected:
                button_text = f"{EMOJI_CHECK} {league_info['name']}"
            else:
                button_text = f"   {league_info['name']}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"league_{lid}")])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI_CHECK} Valider ma selection", callback_data="validate_leagues")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        
    elif data == "validate_leagues":
        prefs = await get_user_preferences(user.id)
        selected = prefs.get("selected_leagues", [])
        
        if not selected:
            await query.answer("Selectionnez au moins un championnat!", show_alert=True)
            return
        
        leagues_names = [LEAGUES[l]["name"] for l in selected if l in LEAGUES]
        
        message = f"""
{EMOJI_CHECK} *Selection enregistree!*

Vous suivez maintenant:
{chr(10).join([f"- {name}" for name in leagues_names])}

Utilisez /resume pour obtenir le resume de la semaine!
"""
        
        await query.edit_message_text(message, parse_mode='Markdown')


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour /resume - Envoie le resume des matchs"""
    user = update.effective_user
    logger.info(f"Commande /resume de {user.username} (ID: {user.id})")
    
    # Recuperer les preferences
    prefs = await get_user_preferences(user.id)
    selected = prefs.get("selected_leagues", [])
    
    if not selected:
        await update.message.reply_text(
            f"{EMOJI_PIN} Vous n'avez pas encore selectionne de championnats.\n"
            f"Utilisez /leagues pour choisir vos ligues preferees!"
        )
        return
    
    await update.message.reply_text(f"{EMOJI_SOCCER} Generation du resume en cours...")
    
    # Pour l'instant, un message placeholder
    leagues_names = [LEAGUES[l]["name"] for l in selected if l in LEAGUES]
    
    resume_message = f"""
{EMOJI_TROPHY} *{SERVICE_NAME}* {EMOJI_TROPHY}
_Semaine du {datetime.now().strftime('%d/%m/%Y')}_

*Vos championnats:*
{chr(10).join([f"- {name}" for name in leagues_names])}

{EMOJI_SOCCER} *Resumes a venir...*

Les resumes detailles des matchs seront disponibles prochainement!
Restez connecte pour recevoir les analyses de vos championnats preferes.
"""
    
    await update.message.reply_text(resume_message, parse_mode='Markdown')


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour /premium"""
    user = update.effective_user
    prefs = await get_user_preferences(user.id)
    is_premium = prefs.get("is_premium", False)
    
    if is_premium:
        message = f"""
{EMOJI_STAR} *Vous etes Premium!* {EMOJI_STAR}

Merci pour votre soutien!
Vous avez acces a tous les championnats:
- {FLAG_ES} La Liga
- {FLAG_IT} Serie A
- {FLAG_DE} Bundesliga
- {FLAG_EU} Champions League

Profitez de vos resumes complets!
"""
    else:
        message = f"""
{EMOJI_STAR} *{SERVICE_NAME} Premium* {EMOJI_STAR}

Passez a Premium pour debloquer:
- {FLAG_ES} La Liga
- {FLAG_IT} Serie A
- {FLAG_DE} Bundesliga
- {FLAG_EU} Champions League

*Tarifs:*
- 2.99 EUR/mois
- 24.99 EUR/an (2 mois offerts!)

Contactez @golgothr pour vous abonner!
"""
    
    await update.message.reply_text(message, parse_mode='Markdown')


# Routes Starlette
async def health_check(request: Request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.now().isoformat()
    })


async def webhook_handler(request: Request):
    """Handler pour les webhooks Telegram"""
    global telegram_app
    
    try:
        data = await request.json()
        logger.debug(f"Webhook recu: {json.dumps(data, indent=2)[:500]}")
        
        if telegram_app:
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
        
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Erreur webhook: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def index(request: Request):
    """Page d'accueil"""
    return PlainTextResponse(f"{SERVICE_NAME} Bot is running!")


@asynccontextmanager
async def lifespan(app: Starlette):
    """Gestion du cycle de vie de l'application"""
    global telegram_app
    
    logger.info(f"Demarrage de {SERVICE_NAME} Bot...")
    
    # Initialiser l'application Telegram
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("leagues", leagues_command))
    telegram_app.add_handler(CommandHandler("resume", resume_command))
    telegram_app.add_handler(CommandHandler("premium", premium_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    # Initialiser l'application
    await telegram_app.initialize()
    await telegram_app.start()
    
    logger.info(f"{SERVICE_NAME} Bot initialise avec succes!")
    
    yield
    
    # Cleanup
    logger.info("Arret du bot...")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()


# Configuration des routes
routes = [
    Route("/", index),
    Route("/health", health_check),
    Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
]

# Application Starlette
app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan
)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Lancement de {SERVICE_NAME} sur port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
