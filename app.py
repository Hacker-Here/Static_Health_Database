import json
import requests
from flask import Flask, request, jsonify

# Replace these with the correct raw URLs from your GitHub repository
SYNONYMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_names.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_symptoms.json"
PREVENTION_URL = "https://raw.githubusercontent.com/Hacker-Here/Static_Health_Database/main/disease_preventions.json"

app = Flask(__name__)

# Cache to store the data after it's been fetched once
data_cache = {}

def get_data_from_github(url):
    """Fetches and caches JSON data from a GitHub raw URL."""
    if url in data_cache:
        return data_cache[url]
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError if the status code is bad
        data = response.json()
        data_cache[url] = data
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        return None

def find_disease_info(disease_name, info_type):
    """Finds information for a given disease from the loaded data."""
    if info_type == "symptoms":
        data_source = get_data_from_github(SYMPTOMS_URL)
        if data_source:
            for item in data_source.get("diseases_with_symptoms", []):
                if item["name"].lower() == disease_name.lower():
                    return item.get("symptoms", [])
    
    elif info_type == "prevention":
        data_source = get_data_from_github(PREVENTION_URL)
        if data_source:
            for item in data_source.get("diseases_with_prevention_measures", []):
                if item["name"].lower() == disease_name.lower():
                    return item.get("prevention_measures", [])

    return None

@app.route('/webhook', methods=['POST'])
def webhook():
    # Parse the incoming JSON request from Dialogflow
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult', {})
    intent_name = query_result.get('intent', {}).get('displayName', '')
    parameters = query_result.get('parameters', {})
    
    fulfillment_text = "I'm sorry, I couldn't find that information. Please try again."

    # Check for the correct intent name
    if intent_name == 'ask_symptoms':
        # Get the parameter, which is a list. Check if it's not empty.
        disease_list = parameters.get('disease-name')
        if disease_list and len(disease_list) > 0:
            # Extract the actual string from the list
            disease = disease_list[0]
            symptoms = find_disease_info(disease, "symptoms")
            if symptoms:
                fulfillment_text = f"Common symptoms of {disease.title()} are: {', '.join(symptoms)}."
            else:
                fulfillment_text = f"I don't have information on the symptoms of {disease.title()}."
    
    elif intent_name == 'ask_preventions':
        # Get the parameter, which is a list. Check if it's not empty.
        disease_list = parameters.get('disease-name')
        if disease_list and len(disease_list) > 0:
            # Extract the actual string from the list
            disease = disease_list[0]
            prevention = find_disease_info(disease, "prevention")
            if prevention:
                fulfillment_text = f"To prevent {disease.title()}, you can: {', '.join(prevention)}."
            else:
                fulfillment_text = f"I don't have information on prevention measures for {disease.title()}."

    # Return the response in the format Dialogflow expects
    return jsonify({
        'fulfillmentText': fulfillment_text
    })

if __name__ == '__main__':
    app.run(port=5000)
