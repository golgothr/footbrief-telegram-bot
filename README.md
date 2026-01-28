# FootBrief Telegram Bot â½

Bot Telegram pour les rÃ©sumÃ©s de matchs de football avec modÃ¨le freemium.

## FonctionnalitÃ©s

- ð **Gratuit**: 1 championnat au choix
- ð **Premium**: Tous les championnats + alertes temps rÃ©el
- ð RÃ©sumÃ©s automatiques des matchs
- ð 15+ championnats disponibles (Europe, AmÃ©riques, Afrique/Asie)

## Championnats disponibles

### Europe Top 5
- ð«ð· Ligue 1
- ð´ó §ó ¢ó ¥ó ®ó §ó ¿ Premier League
- ðªð¸ La Liga
- ð©ðª Bundesliga
- ð®ð¹ Serie A

### Europe Autres
- ðµð¹ Liga Portugal
- ð³ð± Eredivisie
- ð§ðª Pro League
- ð¹ð· SÃ¼per Lig

### AmÃ©riques
- ð§ð· BrasileirÃ£o
- ð¦ð· Liga Argentina
- ð²ð½ Liga MX
- ðºð¸ MLS

### Afrique & Asie
- ð¸ð¦ Saudi Pro League
- ð¯ðµ J-League
- ð¨ð³ Chinese Super League

## Installation

### PrÃ©requis

- Python 3.10+
- Compte Google Cloud avec accÃ¨s Sheets API
- Token Telegram Bot (via @BotFather)

### Variables d'environnement

```bash
TELEGRAM_TOKEN=votre_token_telegram
GOOGLE_SHEET_ID=id_de_votre_sheet
GOOGLE_CREDENTIALS={"type":"service_account",...}
```

### Installation locale

```bash
# Cloner le repo
git clone https://github.com/golgothr/footbrief-telegram-bot.git
cd footbrief-telegram-bot

# Installer les dÃ©pendances
pip install -r requirements.txt

# Lancer le bot
python bot.py
```

## DÃ©ploiement

### Koyeb

1. Connectez votre repo GitHub
2. Ajoutez les variables d'environnement
3. SÃ©lectionnez le type "Worker"
4. DÃ©ployez!

### Railway

1. Nouveau projet depuis GitHub
2. Ajoutez les variables d'environnement
3. Railway dÃ©tecte automatiquement le Procfile
4. DÃ©ployez!

### Render

1. Nouveau "Background Worker"
2. Connectez votre repo GitHub
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Ajoutez les variables d'environnement
6. DÃ©ployez!

## Structure Google Sheet

La premiÃ¨re ligne doit contenir les headers:

| user_id | username | first_name | is_premium | selected_league | free_selection_used | updated_at |
|---------|----------|------------|------------|-----------------|---------------------|------------|

## Commandes du bot

- `/start` - DÃ©marrer et voir le menu
- `/menu` - Afficher le menu principal
- `/help` - Aide

## Licence

MIT License

## Support

Pour toute question: @footbrief_support
