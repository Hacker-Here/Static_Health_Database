import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------- WHO Outbreak API ----------
WHO_API_URL = (
    "https://www.who.int/api/emergencies/diseaseoutbreaknews"
    "?sf_provider=dynamicProvider372&sf_culture=en"
    "&$orderby=PublicationDateAndTime%20desc"
    "&$expand=EmergencyEvent"
    "&$select=Title,TitleSuffix,OverrideTitle,UseOverrideTitle,regionscountries,"
    "ItemDefaultUrl,FormattedDate,PublicationDateAndTime"
    "&%24format=json&%24top=10&%24count=true"
)

# Cache for static JSON data
data_cache = {}

# ================== HELPERS ==================
def get_who_outbreak_data():
    """Fetch outbreak news directly from WHO API."""
    try:
        response = requests.get(WHO_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "value" not in data or not data["value"]:
            return None

        outbreaks = []
        for item in data["value"][:5]:  # only latest 5
            title = item.get("OverrideTitle") or item.get("Title")
            date = item.get("FormattedDate", "Unknown date")
            url = "https://www.who.int" + item.get("ItemDefaultUrl", "")
            outbreaks.append(f"🦠 {title} ({date})\n🔗 {url}")

        return outbreaks
    except Exception as e:
        print(f"Error fetching WHO outbreak data: {e}")
        return None


# ================== WEBHOOK ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    intent = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    params = req.get('queryResult', {}).get('parameters', {})

    reply = "I'm sorry, I couldn't find that information. Please try again."

    # --------- Dynamic Data: WHO Outbreaks ---------
    if intent == 'disease_outbreak.general':
        outbreaks = get_who_outbreak_data()
        if not outbreaks:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(outbreaks)

    return jsonify({'fulfillmentText': reply})


# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
