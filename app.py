import os
import json
import requests
import re
from flask import Flask, request, jsonify, Response
from twilio.twiml.messaging_response import MessagingResponse
from google.cloud import dialogflow_v2 as dialogflow
from google.oauth2 import service_account

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
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

# ---------- GOOGLE DIALOGFLOW CONFIG ----------
PROJECT_ID = os.environ.get("DIALOGFLOW_PROJECT_ID", "")
LANGUAGE_CODE = "en-US"

if "GOOGLE_CREDS_JSON" not in os.environ:
    raise Exception("❌ GOOGLE_CREDS_JSON not found in environment variables!")

creds_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
session_client = dialogflow.SessionsClient(credentials=credentials)

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
        headers = {"User-Agent": "Mozilla/5.0"}
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

def get_dialogflow_reply(user_id, text):
    """Send user input to Dialogflow and get response."""
    safe_session = user_id.replace("whatsapp:", "").replace("+", "")
    session = session_client.session_path(PROJECT_ID, safe_session)

    text_input = dialogflow.TextInput(text=text, language_code=LANGUAGE_CODE)
    query_input = dialogflow.QueryInput(text=text_input)

    try:
        response = session_client.detect_intent(
            request={"session": session, "query_input": query_input}
        )
        # Debugging logs
        print("Dialogflow session:", session)
        print("Detected intent:", response.query_result.intent.display_name)
        print("Fulfillment text:", response.query_result.fulfillment_text)
        return response.query_result.fulfillment_text or "Sorry, I didn’t understand that."
    except Exception as e:
        print(f"Dialogflow error: {e}")
        return "⚠️ Error reaching chatbot service."

# ================== TWILIO WHATSAPP ENDPOINT ==================
@app.route("/twilio", methods=["POST"])
def whatsapp_reply():
    """Receive WhatsApp message from Twilio, forward to Dialogflow, return reply."""
    try:
        incoming_msg = request.form.get("Body", "")
        from_number = request.form.get("From", "")

        if not incoming_msg:
            reply_text = "Please type something to get information."
        else:
            # Clean incoming message
            incoming_msg_clean = re.sub(r'[\r\n]+', ' ', incoming_msg)
            incoming_msg_clean = re.sub(r'\s+', ' ', incoming_msg_clean).strip()

            print("From WhatsApp:", from_number)
            print("Original message:", incoming_msg)
            print("Cleaned message:", incoming_msg_clean)

            reply_text = get_dialogflow_reply(from_number, incoming_msg_clean)

        twiml = MessagingResponse()
        twiml.message(reply_text)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        print("Twilio webhook general error:", e)
        twiml = MessagingResponse()
        twiml.message("⚠️ Something went wrong on the server.")
        return Response(str(twiml), mimetype="application/xml")

# ================== DIALOGFLOW WEBHOOK ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Dialogflow webhook for custom intents (symptoms, prevention, outbreaks)."""
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

    elif intent in ['disease_outbreaks.general', 'disease_outbreaks.specific']:
        disease = None
        if params.get('disease-name'):
            disease = params['disease-name'][0]

        items = get_who_outbreak_data()
        if not items:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            if disease:
                filtered = [i for i in items if disease.lower() in i.lower()]
                if filtered:
                    reply = f"🌍 Latest {disease.title()} outbreaks:\n\n" + "\n\n".join(filtered[:3])
                else:
                    reply = f"No recent WHO outbreak news found for {disease.title()}."
            else:
                reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(items[:3])

    return jsonify({'fulfillmentText': reply})

# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
