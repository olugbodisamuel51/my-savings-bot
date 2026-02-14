import sqlite3
import requests
import datetime
import os
import json
import base64
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ CONFIGURATION (Loaded from Environment Variables)
# ==========================================
# We use os.environ.get() so we can hide these secrets on Render later
MONNIFY_API_KEY = os.environ.get("MONNIFY_API_KEY")
MONNIFY_SECRET = os.environ.get("MONNIFY_SECRET")
MONNIFY_CONTRACT_CODE = os.environ.get("MONNIFY_CONTRACT_CODE")
MY_MONNIFY_WALLET_ACCOUNT = os.environ.get("MY_MONNIFY_WALLET_ACCOUNT")

MY_REAL_BANK_CODE = os.environ.get("MY_REAL_BANK_CODE", "999992") # Default to Opay
MY_REAL_ACCOUNT_NUM = os.environ.get("MY_REAL_ACCOUNT_NUM")
SAVINGS_PERCENTAGE = 0.20
# ==========================================

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('mysavings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS savings 
                 (id INTEGER PRIMARY KEY, amount REAL, date_saved TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HELPER: AUTHENTICATE ---
def get_monnify_token():
    # Detect if we are in Test or Live mode based on the Key format
    if "MK_PROD" in MONNIFY_API_KEY:
        auth_url = "https://api.monnify.com/api/v1/auth/login" # LIVE URL
    else:
        auth_url = "https://sandbox.monnify.com/api/v1/auth/login" # TEST URL
        
    credentials = f"{MONNIFY_API_KEY}:{MONNIFY_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {"Authorization": f"Basic {encoded_credentials}"}
    
    try:
        response = requests.post(auth_url, headers=headers)
        if response.status_code == 200:
            return response.json()['responseBody']['accessToken']
        else:
            print("❌ Auth Failed:", response.text)
            return None
    except Exception as e:
        print("❌ Connection Error:", e)
        return None

# --- HELPER: EXECUTE TRANSFER ---
def transfer_to_spending(amount):
    print(f"\n🚀 Initiating Transfer of ₦{amount}...")
    token = get_monnify_token()
    if not token: return False
    
    # URL depends on Test vs Live
    if "MK_PROD" in MONNIFY_API_KEY:
        transfer_url = "https://api.monnify.com/api/v2/disbursements/single"
    else:
        transfer_url = "https://sandbox.monnify.com/api/v2/disbursements/single"
    
    unique_ref = f"AutoSave_{int(time.time())}"
    
    payload = {
        "amount": amount,
        "reference": unique_ref,
        "narration": "Auto-Transfer Spending Money",
        "destinationBankCode": MY_REAL_BANK_CODE,
        "destinationAccountNumber": MY_REAL_ACCOUNT_NUM,
        "currency": "NGN",
        "sourceAccountNumber": MY_MONNIFY_WALLET_ACCOUNT, 
        "walletId": None
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(transfer_url, json=payload, headers=headers)
        data = response.json()
        if response.status_code == 200 and data.get('requestSuccessful'):
            print("✅ TRANSFER SUCCESSFUL!")
        else:
            print("❌ TRANSFER FAILED:", data)
    except Exception as e:
        print("❌ Error:", e)

# --- WEBHOOK ---
@app.route('/', methods=['GET'])
def home():
    return "🤖 Monnify Savings Bot is Running!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("🔔 Webhook Received")
    
    event_type = data.get('eventType')
    if event_type in ['SUCCESSFUL_TRANSACTION', 'SUCCESSFUL_TRANSACTION_NOTIFICATION']:
        if 'eventData' in data: payment_data = data['eventData']
        else: payment_data = data
            
        amount_paid = payment_data.get('amountPaid')
        email = payment_data.get('customer', {}).get('email')
        
        savings_amount = amount_paid * SAVINGS_PERCENTAGE
        spending_amount = amount_paid - savings_amount
        
        # Log to DB
        conn = sqlite3.connect('mysavings.db')
        c = conn.cursor()
        c.execute("INSERT INTO savings (amount, date_saved, status) VALUES (?, ?, ?)",
                  (savings_amount, str(datetime.date.today()), 'LOCKED'))
        conn.commit()
        conn.close()
        
        transfer_to_spending(spending_amount)
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "ignored"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
