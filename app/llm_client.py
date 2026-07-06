# """
# Thin wrapper around the Anthropic Messages API.
#
# Centralizing this in one place means every agent (router, SQL generator,
# synthesizer) shares the same client, error handling, and JSON-extraction
# logic instead of re-implementing it three times.
# """
# import json
# import re
#
# import anthropic
# from anthropic import Anthropic
# from app.config import settings
#
# _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
#
#
# def complete(system: str, user: str, model: str, max_tokens: int = 1024) -> str:
#     """Single-turn completion. Returns the concatenated text content."""
#     response = _client.messages.create(
#         model=model,
#         max_tokens=max_tokens,
#         system=system,
#         messages=[{"role": "user", "content": user}],
#     )
#     return "".join(block.text for block in response.content if block.type == "text")
#
#
# def complete_json(system: str, user: str, model: str, max_tokens: int = 1024) -> dict:
#     """
#     Ask the model for JSON-only output and parse it defensively.
#     The system prompt passed in should already instruct "respond with
#     JSON only" - this just strips common wrapping (code fences, stray
#     prose) before parsing, since models occasionally add it anyway.
#     """
#     raw = complete(system, user, model, max_tokens)
#     cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
#     try:
#         return json.loads(cleaned)
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Model did not return valid JSON: {raw!r}") from e


"""
Thin wrapper around Ollama (Local LLM).

Centralizing this in one place means every agent (router, SQL generator,
synthesizer) shares the same client logic instead of re-implementing it.
"""
import json
import re
import ollama


def complete(system: str, user: str, model: str, max_tokens: int = 1024) -> str:
    # FORCE llama3 regardless of what 'model' variable says
    local_model = "llama3"
    print(f"--- Calling Ollama ({local_model}) ---")

    response = ollama.chat(
        model=local_model,  # Use the forced name here
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        options={"num_predict": max_tokens, "temperature": 0}
    )
    return response['message']['content']


def complete_json(system: str, user: str, model: str, max_tokens: int = 1024) -> dict:
    # FORCE llama3 regardless of what 'model' variable says
    local_model = "llama3"
    print(f"--- Calling Ollama JSON ({local_model}) ---")

    response = ollama.chat(
        model=local_model,  # Use the forced name here
        format="json",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        options={"num_predict": max_tokens, "temperature": 0}
    )

    raw = response['message']['content']

    # Strip common wrapping (code fences) just in case
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # If it fails, we try to find any JSON-like structure in the string
        raise ValueError(f"Model did not return valid JSON: {raw!r}") from e


# Log status
print("LLM Client initialized: Using Ollama (Local)")
