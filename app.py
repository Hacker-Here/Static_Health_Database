import os
import requests
from flask import Flask, request, jsonify, Response
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
SYNONYMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_names.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

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
def get_data_from_github(url):
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


def get_who_outbreak_data():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}  # WHO sometimes blocks requests without UA
        response = requests.get(WHO_API_URL, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "value" not in data or not data["value"]:
            return None

        outbreaks = []
        for item in data["value"][:5]:
            title = item.get("OverrideTitle") or item.get("Title")
            date = item.get("FormattedDate", "Unknown date")
            url = "https://www.who.int" + item.get("ItemDefaultUrl", "")
            outbreaks.append(f"🦠 {title} ({date})\n🔗 {url}")
        return outbreaks
    except Exception as e:
        print(f"Error fetching WHO outbreak data: {e}")
        return None


# ================== TWILIO WHATSAPP ENDPOINT ==================
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Handle incoming WhatsApp messages from Twilio"""
    incoming_msg = request.form.get("Body", "").strip().lower()
    reply = "Hi! 👋 You can ask me about disease symptoms, prevention, or latest outbreaks."

    if "symptom" in incoming_msg:
        reply = "Please provide a disease name to get its symptoms."
    elif "prevent" in incoming_msg:
        reply = "Please provide a disease name to get its prevention measures."
    elif "outbreak" in incoming_msg or "disease" in incoming_msg:
        outbreaks = get_who_outbreak_data()
        if not outbreaks:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(outbreaks[:3])

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(str(twiml), mimetype="application/xml")


# ================== DIALOGFLOW ENDPOINT ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    intent = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    params = req.get('queryResult', {}).get('parameters', {})
    reply = "I'm sorry, I couldn't find that information. Please try again."

    if intent == 'ask_symptoms':
        disease_list = params.get('disease-name')
        if disease_list:
            disease = disease_list[0]
            symptoms = find_disease_info(disease, "symptoms")
            if symptoms:
                reply = f"🤒 Common symptoms of {disease.title()} are: {', '.join(symptoms)}."
            else:
                reply = f"I don't have information on the symptoms of {disease.title()}."

    elif intent == 'ask_preventions':
        disease_list = params.get('disease-name')
        if disease_list:
            disease = disease_list[0]
            prevention = find_disease_info(disease, "prevention")
            if prevention:
                reply = f"🛡 To prevent {disease.title()}, you can: {', '.join(prevention)}."
            else:
                reply = f"I don't have information on prevention measures for {disease.title()}."

    elif intent == 'disease_outbreak.general':
        outbreaks = get_who_outbreak_data()
        if not outbreaks:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(outbreaks)

    return jsonify({'fulfillmentText': reply})


# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
