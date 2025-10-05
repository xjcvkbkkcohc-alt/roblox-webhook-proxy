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
            # Замени на URL твоего развернутого приложения в Render
            render_app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://localhost:5000')
            if render_app_url.startswith('https://'):
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

        # --- Шаг 2: Получение всех деталей игры (параллельные запросы) ---
        details, votes, thumbnail_url = {}, {}, None
        
        # Запрос основной информации
        try:
            game_details_res = requests.get(GAMES_API.format(universe_id), timeout=10)
            game_details_res.raise_for_status()
            game_data = game_details_res.json().get('data')
            if not game_data:
                raise ValueError("API вернул пустой список данных для деталей игры")
            details = game_data[0]
            logging.info("Успешно получены детали игры.")
        except (requests.RequestException, ValueError, IndexError) as e:
            logging.error(f"Ошибка при запросе деталей игры: {e}")
            return jsonify({"error": "Failed to fetch game details"}), 502

        # Запрос голосов
        try:
            game_votes_res = requests.get(VOTES_API.format(universe_id), timeout=10)
            game_votes_res.raise_for_status()
            votes_data = game_votes_res.json().get('data')
            if not votes_data:
                 raise ValueError("API вернул пустой список данных для голосов")
            votes = votes_data[0]
            logging.info("Успешно получены голоса (лайки/дизлайки).")
        except (requests.RequestException, ValueError, IndexError) as e:
            logging.error(f"Ошибка при запросе голосов: {e}")
            # Не критичная ошибка, можно продолжить без этих данных
            votes = {} # Устанавливаем пустой словарь, чтобы избежать ошибок ниже

        # Запрос превью
        try:
            thumbnail_res = requests.get(THUMBNAIL_API.format(universe_id), timeout=10)
            thumbnail_res.raise_for_status()
            thumbnail_data = thumbnail_res.json().get('data')
            if not thumbnail_data:
                raise ValueError("API вернул пустой список данных для превью")
            thumbnail_url = thumbnail_data[0]['imageUrl']
            logging.info("Успешно получено превью игры.")
        except (requests.RequestException, ValueError, IndexError) as e:
            logging.error(f"Ошибка при запросе превью: {e}")
            thumbnail_url = "https://www.roblox.com/images/Default-Profile.png" # Запасное изображение

        # --- Шаг 3: Сборка эмбеда для Discord ---
        logging.info("Начинаю сборку эмбеда...")
        game_name = details.get('name', 'N/A')
        price = details.get('price')
        price_str = "Free" if price is None or price == 0 else f"{price} Robux"
        js_code = f"```js\nRoblox.GameLauncher.joinGameInstance({place_id}, \"{job_id}\");\n```"

        payload = {
            "embeds": [{
                "author": { "name": "Obsidian Project", "icon_url": "https://i.imgur.com/example.png" }, # Заменил на рабочий URL
                "title": "Obsidian Serverside",
                "color": 11290873,
                "thumbnail": { "url": thumbnail_url },
                "fields": [
                    {"name": "Game", "value": f"[{game_name}](https://www.roblox.com/games/{place_id})", "inline": True},
                    {"name": "Active Players", "value": format_number(details.get('playing')), "inline": True},
                    {"name": "Players In Server", "value": f"{player_count}/{max_players}", "inline": True},
                    {"name": "Game Visits", "value": format_number(details.get('visits')), "inline": True},
                    {"name": "Creator", "value": details.get('creator', {}).get('name', 'N/A'), "inline": True},
                    {"name": "Favorites", "value": format_number(details.get('favoritedCount')), "inline": True},
                    {"name": "Likes", "value": format_number(votes.get('upVotes')), "inline": True},
                    {"name": "Dislikes", "value": format_number(votes.get('downVotes')), "inline": True},
                    {"name": "Universe ID", "value": str(universe_id), "inline": True},
                    {"name": "JavaScript", "value": js_code, "inline": False},
                ],
                "footer": { "text": "Protected by Rewq" }
            }]
        }
        logging.info("Эмбед успешно собран.")

        # --- Шаг 4: Отправка в Discord ---
        try:
            response = requests.post(discord_webhook_url, json=payload, timeout=15)
            response.raise_for_status() # Проверяем, что Discord принял вебхук (код 2xx)
            logging.info(f"Вебхук успешно отправлен в Discord со статусом {response.status_code}.")
            return jsonify({"success": "Webhook sent!"}), 200
        except requests.RequestException as e:
            logging.error(f"Ошибка при отправке вебхука в Discord: {e}")
            return jsonify({"error": "Failed to send webhook to Discord"}), 502

    except Exception as e:
        # Общий обработчик для непредвиденных ошибок
        logging.critical(f"Произошла непредвиденная ошибка в handle_webhook: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred"}), 500

if __name__ == '__main__':
    # Запускаем поток для поддержания активности
    threading.Thread(target=keep_alive, daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
