"""Optional adapter for clients exposing the OpenAI chat-completions interface."""

import math


class OpenAICompatibleModel:
    def __init__(
        self,
        client,
        model: str,
        *,
        input_per_million: float | None = None,
        output_per_million: float | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        response_schema: dict | None = None,
    ):
        if not model:
            raise ValueError("model is required")
        if any(
            rate is not None and (not math.isfinite(rate) or rate < 0)
            for rate in (input_per_million, output_per_million)
        ):
            raise ValueError("invalid token rate")
        self.client = client
        self.model = model
        self.input_per_million = input_per_million
        self.output_per_million = output_per_million
        self.last_usage = None
        if temperature is not None and (
            not math.isfinite(temperature) or not 0 <= temperature <= 2
        ):
            raise ValueError("invalid temperature")
        if seed is not None and (type(seed) is not int or not 0 <= seed < 2**31):
            raise ValueError("invalid seed")
        if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
            raise ValueError("invalid token limit")
        self.options = {}
        if temperature is not None:
            self.options["temperature"] = temperature
        if seed is not None:
            self.options["seed"] = seed
        if max_tokens is not None:
            self.options["max_tokens"] = max_tokens
        if json_mode:
            self.options["response_format"] = {"type": "json_object"}
        if response_schema is not None:
            if json_mode:
                raise ValueError("choose JSON mode or a response schema")
            self.options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "morph_response",
                    "strict": True,
                    "schema": response_schema,
                },
            }

    def complete(self, prompt: str) -> str:
        self.last_usage = None
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}], **self.options
        )
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if (
            type(input_tokens) is int
            and input_tokens >= 0
            and type(output_tokens) is int
            and output_tokens >= 0
        ):
            cost = None
            if self.input_per_million is not None and self.output_per_million is not None:
                cost = (
                    input_tokens * self.input_per_million + output_tokens * self.output_per_million
                ) / 1_000_000
            self.last_usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            }
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("empty model response")
        return response.choices[0].message.content
