"""
story_paraphraser.py -- Lightly rewrite Reddit stories for platform originality.

Uses the local Ollama LLM (same one already configured in ai_config.py).
Falls back to the original text if Ollama is unavailable so the pipeline
never breaks.
"""

import requests
from ai_config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


_PROMPT_TEMPLATE = """\
You are editing a Reddit AITA story for a YouTube Shorts video.
Lightly rewrite the story so the wording is original while keeping:
- The same events, facts, and timeline
- The same first-person voice and casual conversational tone
- The same approximate length (do NOT make it longer)
- The AITA question at the start
- All names, ages, and relationships

Do NOT:
- Add new events or change what happened
- Change the ending or moral
- Add dramatic commentary or your own opinions
- Include phrases like "Here is the rewritten story:" -- return only the story text

Story:
{text}
"""


def paraphrase_story(text: str) -> str:
    """
    Return a lightly paraphrased version of *text* using Ollama.
    Returns the original *text* unchanged if Ollama is down or returns garbage.
    """
    prompt = _PROMPT_TEMPLATE.format(text=text)
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.6, "num_predict": 1200},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json().get("response", "").strip()

        # Sanity checks: must be a reasonable rewrite
        if not result:
            raise ValueError("Empty response")
        if len(result) < len(text) * 0.4:
            raise ValueError(f"Response too short ({len(result)} vs {len(text)})")
        if len(result) > len(text) * 2.0:
            # LLM went off the rails — truncate to original word count
            orig_words = len(text.split())
            result = " ".join(result.split()[:orig_words])

        print(f"Story paraphrased: {len(text)} -> {len(result)} chars")
        return result

    except requests.ConnectionError:
        print("Paraphraser: Ollama not running, using original text")
        return text
    except requests.Timeout:
        print("Paraphraser: Ollama timed out, using original text")
        return text
    except Exception as e:
        print(f"Paraphraser: failed ({e}), using original text")
        return text
