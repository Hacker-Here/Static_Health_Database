import json
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
SYNONYMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_names.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

# WHO Outbreak News Page
WHO_OUTBREAKS_PAGE = "https://www.who.int/emergencies/disease-outbreak-news"

# Cache for static JSON data
data_cache = {}

# ================== HELPERS ==================
def get_data_from_github(url):
    """Fetch and cache JSON data from GitHub raw URLs."""
    if url in data_cache:
        return data_cache[url]
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        data_cache[url] = data
        return data
    except Exception as e:
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

def scrape_who_outbreak_links():
    """Scrape WHO outbreak news page and return only links."""
    try:
        resp = requests.get(WHO_OUTBREAKS_PAGE, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = soup.find_all("div", class_="list-view--item vertical-list-item")
        links = []

        for art in articles[:10]:  # Top 10 outbreak links
            title_tag = art.find("a")
            if title_tag and title_tag.get("href"):
                link = "https://www.who.int" + title_tag["href"]
                links.append(link)

        return links
    except Exception as e:
        print(f"Error scraping WHO outbreak links: {e}")
        return []

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

    # --------- Dynamic Data: WHO Outbreak Links ---------
    elif intent == 'disease_outbreak.general':
        links = scrape_who_outbreak_links()
        if links:
            reply = "🌍 Latest WHO Outbreak News Links:\n" + "\n".join(links)
        else:
            reply = "⚠️ Unable to fetch outbreak links from WHO right now."

    return jsonify({'fulfillmentText': reply})

# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
