# Your Weekly Football Resume (YWFR) â½

Bot Telegram pour les rÃ©sumÃ©s de matchs de football avec modÃ¨le freemium.

## FonctionnalitÃ©s

- ð **Gratuit**: 1 championnat au choix parmi les Top 5 europÃ©ens
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
GOOGLE_SHEET_ID=1y6qjUmY90MdRqoa5UXOZ2EUgFrXO_7GuaG6CMa7Kwkk
GOOGLE_CREDENTIALS={"type":"service_account",...}
WEBHOOK_URL=https://votre-app.koyeb.app
```

### Google Sheets Setup

1. CrÃ©er un projet Google Cloud
2. Activer Google Sheets API
3. CrÃ©er un Service Account
4. TÃ©lÃ©charger le JSON des credentials
5. Partager la Google Sheet avec l'email du service account:
   `footbrief-bot@footbrief-bot-461615.iam.gserviceaccount.com`

#### Structure de la Sheet

La feuille doit avoir ces colonnes:
| user_id | username | selected_leagues | is_premium |
|---------|----------|------------------|------------|
| 123456  | john_doe | ligue1,laliga    | false      |

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

### Koyeb (recommandÃ©)

1. Connectez votre repo GitHub
2. Type de service: **Web Service** (pas Worker!)
3. Port: **8000**
4. Ajoutez les variables d'environnement:
   - `TELEGRAM_TOKEN`
   - `GOOGLE_SHEET_ID`
   - `GOOGLE_CREDENTIALS` (tout le JSON sur une ligne)
   - `WEBHOOK_URL` (URL de votre app Koyeb)
5. DÃ©ployez!

### Railway

1. Nouveau projet depuis GitHub
2. Configurez les variables d'environnement
3. DÃ©ployez

## Debug Google Sheets

Le bot inclut des logs dÃ©taillÃ©s pour dÃ©bugger les problÃ¨mes Google Sheets:

- `debug_google_credentials()` - VÃ©rifie le parsing des credentials
- Logs `[SAVE_USER]` - Trace les sauvegardes
- Logs `[LOAD_USER]` - Trace les chargements
- Endpoint `/health` - VÃ©rifie le statut de connexion

### Erreurs communes

1. **SpreadsheetNotFound**: La sheet n'existe pas ou le service account n'y a pas accÃ¨s
2. **JSON decode error**: Le GOOGLE_CREDENTIALS n'est pas correctement formatÃ©
3. **APIError 403**: Le service account n'a pas les permissions

## Licence

MIT
