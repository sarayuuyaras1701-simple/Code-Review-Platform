from google import genai

client = genai.Client(api_key="YOUR_KEY")
response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="Hello",
)
print(response.text)