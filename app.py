import streamlit as st  
import os
import mysql.connector
from openai import OpenAI
from dotenv import load_dotenv
import random
import string
import datetime  # for created_date
import pandas as pd  # for CSV upload
from io import StringIO

# ------------------ CONFIG ------------------
st.set_page_config(page_title="AI Location Creator", layout="centered")
load_dotenv()

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    st.error("Please set your OpenAI API key in `.env` or Streamlit secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# MySQL connection details
DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "site_id")

# ------------------ DATABASE CONNECTION CHECK ------------------
try:
    test_conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    test_conn.close()
    st.success("✅ Database connection successful!")
except mysql.connector.Error as err:
    st.error(f"❌ Database connection failed: {err}")
    st.stop()

# ------------------ SESSION STATE ------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "collected_data" not in st.session_state:
    st.session_state.collected_data = {}
if "awaiting_fields" not in st.session_state:
    st.session_state.awaiting_fields = []
if "approval_status" not in st.session_state:
    st.session_state.approval_status = None
if "created_locations" not in st.session_state:
    st.session_state.created_locations = []   # store created bulk locations

required_fields = ["location_name", "location_type", "zone", "aisle", "site_code"]

# ------------------ FUNCTIONS ------------------
def ai_response(prompt):
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly and professional warehouse assistant AI. "
                        "Your job is to collect location details step by step, confirm missing fields, "
                        "explain things clearly, and make the conversation interactive. "
                        "Always guide the user politely, and keep responses concise but helpful."
                    )
                },
                {"role": "user", "content": prompt}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {e}"

def missing_fields():
    return [field for field in required_fields if not st.session_state.collected_data.get(field)]

def generate_location_id():
    while True:
        letters = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        loc_id = f"{letters}{numbers}"

        try:
            conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM location WHERE location_id = %s", (loc_id,))
            exists = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            if exists == 0:
                return loc_id
        except mysql.connector.Error as err:
            st.error(f"❌ Database error while generating ID: {err}")
            return loc_id

def save_to_mysql(data):
    """Save the approved location to MySQL with created_by and created_date."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        
        location_name_clean = data['location_name'].strip()
        created_by = data.get("created_by", "AI")
        created_date = datetime.datetime.now()

        cursor.execute("SELECT COUNT(*) FROM location WHERE LOWER(location_name) = %s", 
                       (location_name_clean.lower(),))
        if cursor.fetchone()[0] > 0:
            st.warning(f"⚠️ A location with a similar name already exists, but will still insert.")

        sql = """
        INSERT INTO location 
        (location_id, location_name, location_type, zone, aisle, site_code, created_by, created_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            data['location_id'],
            location_name_clean,
            data['location_type'].strip(),
            data['zone'].strip(),
            data['aisle'].strip(),
            data['site_code'].strip(),
            created_by,
            created_date
        ))
        conn.commit()
        cursor.close()
        conn.close()

        # also store in session_state for download later
        st.session_state.created_locations.append({
            "location_id": data['location_id'],
            "location_name": location_name_clean,
            "location_type": data['location_type'].strip(),
            "zone": data['zone'].strip(),
            "aisle": data['aisle'].strip(),
            "site_code": data['site_code'].strip(),
            "created_by": created_by,
            "created_date": created_date.strftime("%Y-%m-%d %H:%M:%S")
        })

        return f"✅ Location added to database successfully! Location ID: {data['location_id']}"
    except mysql.connector.Error as err:
        return f"❌ Database Error: {err}"

# ------------------ UI ------------------
st.title("📦 AI Location Creator Chatbot")
st.markdown("Provide location details and the AI will generate a short unique ID automatically.")

# File upload option inside chatbot
uploaded_file = st.file_uploader("📂 Upload a CSV file with location details", type=["csv"])
if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.write("📑 Uploaded data preview:")
        st.dataframe(df.head())

        for _, row in df.iterrows():
            row_data = {
                "location_id": generate_location_id(),
                "location_name": str(row.get("location_name", "")).strip(),
                "location_type": str(row.get("location_type", "")).strip(),
                "zone": str(row.get("zone", "")).strip(),
                "aisle": str(row.get("aisle", "")).strip(),
                "site_code": str(row.get("site_code", "")).strip(),
                "created_by": "CSV Upload"
            }
            msg = save_to_mysql(row_data)
            st.success(msg)

        # After bulk upload, offer CSV download
        if st.session_state.created_locations:
            df_created = pd.DataFrame(st.session_state.created_locations)
            csv_buffer = StringIO()
            df_created.to_csv(csv_buffer, index=False)
            st.download_button(
                label="⬇️ Download Created Locations (CSV)",
                data=csv_buffer.getvalue(),
                file_name="created_locations.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"❌ Error processing uploaded file: {e}")

# Display chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])

# ------------------ USER INPUT ------------------
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "text": user_input})

    if st.session_state.awaiting_fields:
        values = [v.strip() for v in user_input.split(",")]
        for i, field in enumerate(st.session_state.awaiting_fields):
            if i < len(values):
                st.session_state.collected_data[field] = values[i]
        st.session_state.awaiting_fields = []

    missing = missing_fields()
    if missing:
        fields_str = ", ".join([f.replace('_',' ') for f in missing])
        bot_reply = (
            f"I still need the following details: **{fields_str}**.\n\n"
            f"👉 Please provide them in one message, separated by commas, "
            f"in this order:\n`{', '.join(missing)}`"
        )
        st.session_state.awaiting_fields = missing
    else:
        if "location_id" not in st.session_state.collected_data:
            st.session_state.collected_data["location_id"] = generate_location_id()

        if st.session_state.approval_status is None:
            collected_str = "\n".join([f"- **{k.replace('_',' ').title()}**: {v}"
                                        for k, v in st.session_state.collected_data.items()])
            bot_reply = (
                f"Here are the details you provided:\n\n{collected_str}\n\n"
                "✅ Do you want me to create this location in the system? (yes/no)"
            )
            st.session_state.approval_status = "pending"
        elif st.session_state.approval_status == "pending":
            if user_input.lower() in ["yes", "y"]:
                if "created_by" not in st.session_state.collected_data:
                    st.session_state.collected_data["created_by"] = "AI"
                result_msg = save_to_mysql(st.session_state.collected_data)
                bot_reply = result_msg
                st.session_state.approval_status = "approved"
            elif user_input.lower() in ["no", "n"]:
                bot_reply = "❌ Location creation cancelled."
                st.session_state.approval_status = "cancelled"
            else:
                bot_reply = "Please type 'yes' or 'no' to confirm."
        else:
            bot_reply = ai_response(user_input)

    st.session_state.chat_history.append({"role": "assistant", "text": bot_reply})
    st.rerun()
