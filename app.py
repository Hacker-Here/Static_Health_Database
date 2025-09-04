import json
import requests
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
SYNONYMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_names.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

# WHO Outbreak page
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


def get_who_outbreak_links():
    """Use Selenium to scrape outbreak news links from WHO DON page."""
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=options)
        driver.get(WHO_OUTBREAKS_URL)

        # Wait for JS to load
        driver.implicitly_wait(10)

        # Correct selector
        elements = driver.find_elements(By.CSS_SELECTOR, "a.sf-list-vertical__item-title")

        links = []
        for el in elements[:10]:  # top 10
            links.append({
                "Title": el.text.strip(),
                "Link": el.get_attribute("href")
            })

        driver.quit()
        return links

    except Exception as e:
        print(f"Error scraping WHO outbreak data: {e}")
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
    elif intent == 'disease_outbreak.general':
        items = get_who_outbreak_links()
        if not items:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            lines = [f"- {i['Title']}\n🔗 {i['Link']}" for i in items]
            reply = "🌍 Latest WHO Outbreak News:\n" + "\n".join(lines)

    return jsonify({'fulfillmentText': reply})


# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
