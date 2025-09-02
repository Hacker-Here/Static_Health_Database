import json
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup  # ✅ Added for WHO scraping

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
SYNONYMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_names.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

# ---------- WHO OUTBREAKS PAGE ----------
WHO_OUTBREAKS_URL = "https://www.who.int/emergencies/disease-outbreak-news"

# Cache for static JSON data
data_cache = {}

# ================== HELPERS ==================
def get_data_from_github(url):
    """Fetch and cache JSON data from GitHub raw URLs."""
    if url in data_cache:
        return data_cache[url]
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        data_cache[url] = data
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from GitHub: {e}")
        return None

def find_disease_info(disease_name, info_type):
    """Look up static disease info (symptoms or prevention)."""
    if info_type == "symptoms":
        data = get_data_from_github(SYMPTOMS_URL)
        if data:
            for item in data.get("diseases_with_symptoms", []):
                if item["name"].lower() == disease_name.lower():
                    return item.get("symptoms", [])
    elif info_type == "prevention":
        data = get_data_from_github(PREVENTION_URL)
        if data:
            for item in data.get("diseases_with_prevention_measures", []):
                if item["name"].lower() == disease_name.lower():
                    return item.get("prevention_measures", [])
    return None

def get_who_outbreaks():
    """Scrape WHO Disease Outbreak News HTML page for latest items."""
    try:
        resp = requests.get(WHO_OUTBREAKS_URL, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all("div", class_="list-view--item vertical-list-item")

        items = []
        for art in articles[:10]:  # top 10 latest
            title_tag = art.find("a")
            date_tag = art.find("div", class_="timestamp")

            title = title_tag.get_text(strip=True) if title_tag else "No title"
            link = "https://www.who.int" + title_tag["href"] if title_tag else ""
            date = date_tag.get_text(strip=True) if date_tag else ""

            items.append({
                "Title": title,
                "Link": link,
                "PublicationDate": date
            })

        return items

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

    # --------- Static Data: Symptoms ---------
    if intent == 'ask_symptoms':
        disease_list = params.get('disease-name')
        if disease_list:
            disease = disease_list[0]
            symptoms = find_disease_info(disease, "symptoms")
            if symptoms:
                reply = f"🤒 Common symptoms of {disease.title()} are: {', '.join(symptoms)}."
            else:
                reply = f"I don't have information on the symptoms of {disease.title()}."

    # --------- Static Data: Prevention ---------
    elif intent == 'ask_preventions':
        disease_list = params.get('disease-name')
        if disease_list:
            disease = disease_list[0]
            prevention = find_disease_info(disease, "prevention")
            if prevention:
                reply = f"🛡 To prevent {disease.title()}, you can: {', '.join(prevention)}."
            else:
                reply = f"I don't have information on prevention measures for {disease.title()}."

    # --------- Dynamic Data: WHO Outbreaks ---------
    elif intent in ['disease_outbreaks.general', 'disease_outbreaks.specific']:
        disease = None
        if params.get('disease-name'):
            disease = params['disease-name'][0]  # Extract disease name if provided

        items = get_who_outbreaks()
        if not items:
            reply = "⚠️ Unable to fetch outbreak data from WHO right now."
        else:
            if disease:  # Disease-specific outbreaks
                filtered = [i for i in items if disease.lower() in i.get("Title", "").lower()]
                if filtered:
                    lines = [f"- {i['Title']} ({i.get('PublicationDate', '')})\n🔗 {i['Link']}" for i in filtered[:3]]
                    reply = f"🌍 Latest {disease.title()} Outbreaks:\n" + "\n".join(lines)
                else:
                    reply = f"No recent WHO outbreak news found for {disease.title()}."
            else:  # General outbreaks
                lines = [f"- {i['Title']} ({i.get('PublicationDate', '')})\n🔗 {i['Link']}" for i in items[:3]]
                reply = "🌍 Latest WHO Outbreaks:\n" + "\n".join(lines)

    return jsonify({'fulfillmentText': reply})

# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
