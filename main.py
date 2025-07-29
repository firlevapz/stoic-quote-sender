import os
import requests
import json
import vertexai
from vertexai.generative_models import GenerativeModel


def get_stoic_quote():
    """Ruft ein stoisches Zitat von der API ab."""
    try:
        response = requests.get("https://stoic-quotes.com/api/quote")
        response.raise_for_status()  # Löst eine Ausnahme für schlechte Statuscodes aus
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Abrufen des Zitats: {e}")
        return None


def get_interpretation_and_translation(quote, author):
    """
    Übersetzt und interpretiert das Zitat mit Gemini.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = "us-central1"
    vertexai.init(project=project_id, location=location)

    model = GenerativeModel("gemini-2.5-pro-001")

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
        print("Fehler: Umgebungsvariablen für Signal sind nicht gesetzt.")
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


def main(request):
    """
    Hauptfunktion, die von Google Cloud Run aufgerufen wird.
    """
    quote_data = get_stoic_quote()

    if quote_data:
        original_quote = quote_data.get("text")
        author = quote_data.get("author")

        if original_quote and author:
            interpreted_data = get_interpretation_and_translation(
                original_quote, author
            )

            if interpreted_data:
                formatted_message = (
                    f"**Heutiges stoisches Zitat:**\n\n"
                    f'"{original_quote}"\n- {author}\n\n'
                    f"**Übersetzung:**\n{interpreted_data['translation']}\n\n"
                    f"**Interpretation:**\n{interpreted_data['interpretation']}\n\n"
                    f"**Beispiel:**\n{interpreted_data['example']}"
                )
                send_signal_message(formatted_message)
                return "Nachricht erfolgreich verarbeitet und gesendet.", 200

    return "Fehler bei der Verarbeitung der Anfrage.", 500


if __name__ == "__main__":
    # Dies ermöglicht das lokale Testen des Skripts
    # Stelle sicher, dass du die Umgebungsvariablen gesetzt hast
    main(None)
