#!/usr/bin/env python3
import sys
import os
import time
import argparse
from dotenv import load_dotenv

# Try to load environment variables from .env if available
load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    print("❌ Error: 'openai' package is not installed.")
    print("Please install it first: pip install openai")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Verify connection and compatibility with custom LLM endpoints (e.g., DeepSeek, MiMo, or local server)."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        help="The API key for the LLM service. Defaults to LLM_API_KEY or OPENAI_API_KEY env variables."
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
        help="The base URL of the LLM provider (e.g. 'https://api.deepseek.com' or 'https://api.xiaomimimo.com/v1')."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL"),
        help="The model name to test (e.g. 'deepseek-chat' or 'mimo-v2.5-pro')."
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Hello! Please reply in exactly 5 words: 'Connection test was successful!'",
        help="The prompt to send to the model."
    )
    args = parser.parse_args()

    print("==================================================")
    print("        LLM Connection Verification Tool          ")
    print("==================================================")

    # Interactive prompts if arguments are not provided
    api_key = args.api_key
    if not api_key:
        print("💡 API key not found in arguments or .env file.")
        api_key = input("Enter your API key: ").strip()

    base_url = args.base_url
    if not base_url:
        print("\n💡 Base URL not found in arguments or .env file.")
        print("Common base URLs:")
        print("  - DeepSeek: https://api.deepseek.com")
        print("  - MiMo hosted: https://api.xiaomimimo.com/v1")
        print("  - Local vLLM/Ollama: http://localhost:8000/v1")
        base_url = input("Enter the Base URL: ").strip()

    model_name = args.model
    if not model_name:
        print("\n💡 Model name not found in arguments or .env file.")
        print("Common models:")
        print("  - DeepSeek: deepseek-chat")
        print("  - MiMo: mimo-v2.5-pro")
        model_name = input("Enter the Model name: ").strip()

    if not api_key or not base_url or not model_name:
        print("\n❌ Error: API Key, Base URL, and Model Name are all required to proceed.")
        sys.exit(1)

    print("\n--- Connection Settings ---")
    print(f"Base URL:   {base_url}")
    print(f"Model Name: {model_name}")
    # Mask API key for safety
    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"API Key:    {masked_key}")
    print("---------------------------\n")

    print(f"Connecting to {base_url}...")
    try:
        # Initialize OpenAI client with custom base URL and API key
        client = OpenAI(api_key=api_key, base_url=base_url)

        print(f"Sending test prompt: \"{args.prompt}\"")
        start_time = time.time()

        # Send request
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": args.prompt}],
            temperature=0.0,
            max_tokens=50
        )

        duration = time.time() - start_time
        reply = response.choices[0].message.content

        print("\n🟢 Connection and Request SUCCESSFUL!")
        print(f"Response Time: {duration:.2f} seconds")
        print(f"Model Reply:   \"{reply.strip()}\"")
        print("\n==================================================")

    except Exception as e:
        print(f"\n🔴 Request FAILED!")
        print(f"Error Type:  {type(e).__name__}")
        print(f"Error Info:  {e}")
        print("\nTroubleshooting Tips:")
        print("1. Double-check your API key and base URL.")
        print("2. Ensure the base URL does or doesn't end with '/v1' depending on the provider specification.")
        print("3. Check your network connection or VPN if the endpoint is self-hosted.")
        print("==================================================")
        sys.exit(2)


if __name__ == "__main__":
    main()

### ./test_llm.py --api-key <YOUR_KEY> --base-url <BASE_URL> --model <MODEL_NAME>
