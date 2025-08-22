from collections import namedtuple

import openai
from openai import OpenAI

from app.loader import settings

SummaryResponse = namedtuple("SummaryResponse", ["summary", "cost"])


def get_summary_from_openai(text: str, system_prompt: str) -> SummaryResponse:
    client = OpenAI(
        api_key=settings.openai_api_key,
    )
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            model="gpt-4-turbo",
            timeout=settings.openai_timeout_seconds,
        )

        prompt_tokens = chat_completion.usage.prompt_tokens
        completion_tokens = chat_completion.usage.completion_tokens
        summary_text = chat_completion.choices[0].message.content

        cost = ((prompt_tokens / 1000) * settings.price_per_1k_prompt) + (
            (completion_tokens / 1000) * settings.price_per_1k_completion
        )

        return SummaryResponse(summary=summary_text, cost=f"{cost:.4f}")

    except openai.APIError as e:
        raise ConnectionError(f"OpenAI API returned an API Error: {e}")
    except openai.APIConnectionError as e:
        raise ConnectionError(f"Failed to connect to OpenAI API: {e}")
    except openai.RateLimitError as e:
        raise ConnectionError(f"OpenAI API request exceeded rate limit: {e}")
    except openai.Timeout as e:
        raise TimeoutError(f"OpenAI API request timed out: {e}")
