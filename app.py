import os, json, requests
from flask import Flask, request, jsonify, Response
from twilio.twiml.messaging_response import MessagingResponse
from google.cloud import dialogflow_v2 as dialogflow
from google.oauth2 import service_account

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

# ---------- WHO OUTBREAKS API ----------
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
    """Fetch latest WHO Disease Outbreak News items from WHO API."""
    try:
        response = requests.get(WHO_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("items", data)  # "items" contains the outbreak list
    except Exception as e:
        print(f"Error fetching WHO outbreak data: {e}")
        return None

def get_dialogflow_reply(user_id, text):
    """Send user input to Dialogflow and get response."""
    session = session_client.session_path(PROJECT_ID, user_id)
    text_input = dialogflow.TextInput(text=text, language_code=LANGUAGE_CODE)
    query_input = dialogflow.QueryInput(text=text_input)

    try:
        response = session_client.detect_intent(
            request={"session": session, "query_input": query_input}
        )
        return response.query_result.fulfillment_text or "Sorry, I didn’t understand that."
    except Exception as e:
        print(f"Dialogflow error: {e}")
        return "⚠️ Error reaching chatbot service."

# ================== DIALOGFLOW WEBHOOK (used by Dialogflow itself) ==================
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
            disease = params['disease-name'][0]

        items = get_who_outbreaks()
        if not items:
            reply = "⚠️ Unable to fetch outbreak data from WHO right now."
        else:
            if disease:  # Disease-specific outbreaks
                filtered = [i for i in items if disease.lower() in i.get("Title", "").lower()]
                if filtered:
                    lines = [f"- {i['Title']} ({i.get('PublicationDate', '')[:10]})" for i in filtered[:3]]
                    reply = f"🌍 Latest {disease.title()} Outbreaks:\n" + "\n".join(lines)
                else:
                    reply = f"No recent WHO outbreak news found for {disease.title()}."
            else:  # General outbreaks
                lines = [f"- {i['Title']} ({i.get('PublicationDate', '')[:10]})" for i in items[:3]]
                reply = "🌍 Latest WHO Outbreaks:\n" + "\n".join(lines)

    return jsonify({'fulfillmentText': reply})

# ================== TWILIO WHATSAPP ENDPOINT ==================
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Receive WhatsApp message from Twilio, forward to Dialogflow, return reply."""
    incoming_msg = request.form.get("Body", "")
    from_number = request.form.get("From", "")

    reply = get_dialogflow_reply(from_number, incoming_msg)

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(str(twiml), mimetype="application/xml")

# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
