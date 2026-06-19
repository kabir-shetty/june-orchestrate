from openai import OpenAI
import base64

def main():
    client = OpenAI(api_key="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")

    response = client.responses.create(
        model="gpt-5",
        input="Say hello"
    )

    print(response.output_text)

main()