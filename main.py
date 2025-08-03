import os
import requests
import json
import vertexai
from vertexai.generative_models import GenerativeModel
import time
from datetime import datetime


# --- Quote loading and cycling logic ---
import glob

QUOTES_DIR = os.path.join(os.path.dirname(__file__), "quotes")
COUNTER_FILE = os.path.join(os.path.dirname(__file__), "quote_index.txt")


def load_all_quotes():
    quotes = []
    for file_path in sorted(glob.glob(os.path.join(QUOTES_DIR, "*.json"))):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "quotes" in data:
                    quotes.extend(data["quotes"])
                elif isinstance(data, list):
                    quotes.extend(data)
        except Exception as e:
            print(f"Fehler beim Laden von {file_path}: {e}")
    return quotes


def get_quote_index(max_index):
    try:
        with open(COUNTER_FILE, "r") as f:
            idx = f.read().strip()
            if not idx:
                idx = 0
            else:
                idx = int(idx)

            if idx < 0 or idx >= max_index:
                idx = 0
    except Exception:
        idx = 0
    return idx


def save_quote_index(idx):
    try:
        with open(COUNTER_FILE, "w") as f:
            f.write(str(idx))
    except Exception as e:
        print(f"Fehler beim Speichern des Zählerstandes: {e}")


ALL_QUOTES = load_all_quotes()


def get_stoic_quote():
    """Liefert das nächste stoische Zitat aus der lokalen Liste und erhöht den Zähler."""
    if not ALL_QUOTES:
        print("Keine Zitate gefunden!")
        return None
    idx = get_quote_index(len(ALL_QUOTES))
    quote = ALL_QUOTES[idx]
    next_idx = (idx + 1) % len(ALL_QUOTES)
    save_quote_index(next_idx)
    return quote


def get_interpretation_and_translation(quote, author):
    """
    Übersetzt und interpretiert das Zitat mit Gemini.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = "us-central1"
    vertexai.init(project=project_id, location=location)

    model = GenerativeModel(os.environ.get("VERTEX_AI_MODEL", "gemini-2.5-flash-lite"))

    prompt = f"""
    Bitte übersetze das folgende Zitat ins Deutsche und interpretiere es.
    Gib die Antwort als JSON-Objekt zurück, das die folgenden Schlüssel enthält: "translation", "interpretation", "example".

    Originalzitat: "{quote}" - {author}

    Die Interpretation sollte in einfachen deutschen Worten sein und erklären, was das Zitat bedeutet.
    Das Beispiel sollte eine alltägliche Situation beschreiben, die die Bedeutung des Zitats veranschaulicht.
    """

    try:
        response = model.generate_content(prompt)
        # Die Antwort ist möglicherweise in einer Markdown-Codeblock-Formatierung eingeschlossen
        # Wir müssen sie bereinigen, um reines JSON zu erhalten
        cleaned_response = (
            response.text.strip().replace("```json", "").replace("```", "")
        )
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"Fehler bei der Interaktion mit dem Gemini-Modell: {e}")
        return None


def send_signal_message(content):
    """Sendet die formatierte Nachricht an die Signal-API."""
    signal_cli_url = os.environ.get("SIGNAL_CLI_URL")
    sender_number = os.environ.get("SENDER_NUMBER")
    recipient_number = os.environ.get("RECIPIENT_NUMBER")

    if not all([signal_cli_url, sender_number, recipient_number]):
        print("Umgebungsvariablen für Signal sind nicht gesetzt.")
        print(content)
        return

    headers = {"Content-Type": "application/json"}
    payload = {
        "message": content,
        "number": sender_number,
        "recipients": [recipient_number],
    }

    try:
        response = requests.post(
            signal_cli_url, headers=headers, data=json.dumps(payload)
        )
        response.raise_for_status()
        print(f"Nachricht erfolgreich gesendet! Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Senden der Signal-Nachricht: {e}")


def main():
    """
    Hauptfunktion, die von Google Cloud Run aufgerufen wird.
    """
    quote_data = get_stoic_quote()

    if quote_data:
        # Support both dicts with 'text' and 'author', or 'quote' and 'author'
        original_quote = quote_data.get("text") or quote_data.get("quote")
        author = quote_data.get("author")

        if original_quote and author:
            interpreted_data = get_interpretation_and_translation(
                original_quote, author
            )

            if interpreted_data:
                formatted_message = (
                    f'"{original_quote}"\n- {author}\n\n'
                    f"Übersetzung:\n{interpreted_data['translation']}\n\n"
                    f"Interpretation:\n{interpreted_data['interpretation']}\n\n"
                    f"Beispiel:\n{interpreted_data['example']}"
                )
                send_signal_message(formatted_message)
                return "Nachricht erfolgreich verarbeitet und gesendet.", 200

    return "Fehler bei der Verarbeitung der Anfrage.", 500


if __name__ == "__main__":
    # Keep the script running and check every hour
    while True:
        current_time = datetime.now()

        trigger_hour = os.environ.get("TRIGGER_HOUR")

        if trigger_hour is None or current_time.hour == int(trigger_hour):
            main()

        if trigger_hour is None:
            break

        # Sleep for 1 hour (3600 seconds)
        time.sleep(3600)
