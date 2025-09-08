import os
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# Your Dialogflow webhook endpoint
DIALOGFLOW_WEBHOOK = "https://static-health-database-mbyv.onrender.com/webhook"

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()

    # Send user message to Dialogflow webhook
    response = requests.post(DIALOGFLOW_WEBHOOK, json={"query": incoming_msg})
    bot_reply = response.json().get("fulfillmentText", "Sorry, I didn’t get that.")

    # Send reply back to WhatsApp via Twilio
    twilio_resp = MessagingResponse()
    twilio_resp.message(bot_reply)
    return str(twilio_resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)
