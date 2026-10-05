from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:20128/v1"
)

response = client.chat.completions.create(
    model="big-pickle",
    messages=[
        {
            "role": "user",
            "content": "Say exactly: OmniRoute works"
        }
    ]
)

print(response.choices[0].message.content)