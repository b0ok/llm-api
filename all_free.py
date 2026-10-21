import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# name: (base_url, key env var, model)
PROVIDERS = {
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-flash-lite-latest"),
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "qwen/qwen3.8-27b"),
    "mistral":    ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "minimax/minimax-m3.1-flash:free"),
    "ollama-qwen":  ("http://localhost:11434/v1", "OLLAMA", "qwen2.5:7b"),  # local; set OLLAMA=1 in .env to enable
    "ollama-llama": ("http://localhost:11434/v1", "OLLAMA", "llama3.2"),
}


def ask(prompt, temperature=0.7, max_tokens=150, system="You are a helpful assistant."):
    for name, (url, key_var, model) in PROVIDERS.items():
        key = os.getenv(key_var)
        if not key:
            print(f"--- {name}: skipped (no {key_var})")
            continue
        try:
            r = OpenAI(api_key=key, base_url=url, timeout=30, max_retries=0).chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            print(f"--- {name} ({model})\n{r.choices[0].message.content}\n")
        except Exception as e:
            print(f"--- {name}: failed ({e.__class__.__name__}: {e})\n")


if __name__ == "__main__":
    prompt = input("You: ")
    for t in (0, 1.0):  # compare temperatures across every provider
        print(f"\n===== temperature={t} =====")
        ask(prompt, temperature=t)
