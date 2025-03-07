import requests
import json

# URL to your endpoint. Adjust the host/port as needed.
api_url = "http://localhost:5009/api/ai_sermon_content"

# Replace with your actual API token.
api_token = "54cb3aed-c710-1bd2-9d6b-a1aef5757ee1"

# Data payload with the provided values.
payload = {
    "ai_summary": "The pastor discusses the biblical account of King Asa from 2 Chronicles, emphasizing his initial reliance on God for victories against formidable foes and his later lapse in faith when he sought help from the king of Syria instead of God. The sermon explores the theme of consistent faithfulness and reliance on God despite past successes or new challenges. The pastor uses King Asa's story to reflect on the human tendency to seek security in worldly assurances rather than divine intervention, urging the congregation to maintain unwavering trust in God through all life's crises.",
    "ai_summary_es": "El pastor discute la cuenta bíblica del Rey Asa de 2 Crónicas, enfatizando su dependencia inicial en Dios para victorias contra enemigos formidables y su posterior pérdida de fe cuando buscó ayuda del rey de Siria en lugar de Dios. El sermón explora el tema de la fidelidad constante y la dependencia en Dios a pesar de los éxitos pasados o nuevos desafíos. El pastor usa la historia del Rey Asa para reflexionar sobre la tendencia humana de buscar seguridad en aseguranzas mundanas en lugar de intervención divina, instando a la congregación a mantener una confianza inquebrantable en Dios a través de todas las crisis de la vida.",
    "bible_books": "2 Chronicles 14, 2 Chronicles 16, Psalm 50:15, 1 Peter 5:7, Philippians 4:6, Psalm 118:8-9, Psalm 146, James 1",
    "bible_books_es": "2 Crónicas 14, 2 Crónicas 16, Salmo 50:15, 1 Pedro 5:7, Filipenses 4:6, Salmo 118:8-9, Salmo 146, Santiago 1",
    "created_at": "2025-03-07 22:18:15",
    "key_quotes": "\"Where is his prayer from earlier? Oh Lord, there is none like you to help.\" | \"If you're a Christian and you have the king of Syria's number in your phone, you need to delete that contact.\"",
    "key_quotes_es": "\"¿Dónde está su oración de antes? Oh Señor, no hay nadie como tú para ayudar.\" | \"Si eres cristiano y tienes el número del rey de Siria en tu teléfono, necesitas borrar ese contacto.\"",
    "sentiment": "Encouraging, Teaching",
    "sentiment_es": "Alentador, Educativo",
    "sermon_guid": "eda9a26f-300b-45d6-9177-a64c83cbb397",
    "sermon_style": "Expository",
    "sermon_style_es": "Expositivo",
    "status": "completed",
    "topics": "Faith and reliance on God, Human tendency to seek worldly assurances, Spiritual growth and maturity, Challenges of maintaining faith",
    "topics_es": "Fe y dependencia en Dios, Tendencia humana a buscar aseguranzas mundanas, Crecimiento espiritual y madurez, Desafíos para mantener la fe",
    "updated_at": "2025-03-07 22:19:07"
}

headers = {
    "Content-Type": "application/json",
    "X-API-Token": api_token
}

try:
    response = requests.post(api_url, data=json.dumps(payload), headers=headers)
    print("Status Code:", response.status_code)
    print("Response JSON:", response.json())
except Exception as e:
    print("An error occurred:", e)
