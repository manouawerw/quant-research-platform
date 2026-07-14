from dotenv import load_dotenv

load_dotenv()

from google import genai

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents="Reply with exactly: Gemini connection successful",
)

print(response.text)