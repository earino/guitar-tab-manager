"""
LMStudio client wrapper for local LLM access.

Uses OpenAI-compatible API at localhost:1234.
"""

import json
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

import config


class LMStudioClient:
    """Client for interacting with LMStudio's local LLM."""

    def __init__(self, base_url: str = None, timeout: int = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed. Run: pip install openai")

        self.base_url = base_url or config.LMSTUDIO_URL
        self.timeout = timeout or config.LMSTUDIO_TIMEOUT

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="not-needed",  # LMStudio doesn't require API key
            timeout=self.timeout,
        )

    def is_available(self) -> bool:
        """Check if LMStudio is running and accessible."""
        try:
            # Try to list models as a health check
            self.client.models.list()
            return True
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Get list of available models in LMStudio."""
        try:
            response = self.client.models.list()
            return [m.id for m in response.data]
        except Exception:
            return []

    def chat(self, prompt: str, system_prompt: str = None, temperature: float = 0.7) -> str:
        """
        Send a chat completion request.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)

        Returns the assistant's response text.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model="local-model",  # LMStudio uses this as default
            messages=messages,
            temperature=temperature,
        )

        return response.choices[0].message.content

    def analyze_tab(self, content: str, song: str, artist: str) -> dict:
        """
        Analyze a guitar tab for mood, themes, and tempo.

        Returns a dict with: mood, themes, tempo_feel, description
        """
        system_prompt = """You are a music analyst. Analyze the given guitar tab/chord sheet and provide:
1. mood: List of 1-3 mood descriptors (e.g., melancholic, uplifting, energetic, peaceful, nostalgic)
2. themes: List of 1-3 themes in the lyrics/song (e.g., love, loss, travel, freedom, heartbreak)
3. tempo_feel: One of: slow, medium-slow, medium, medium-fast, fast
4. description: A brief 1-sentence description of the song's feel

Respond ONLY with valid JSON in this format:
{"mood": ["melancholic", "nostalgic"], "themes": ["loss", "memory"], "tempo_feel": "slow", "description": "A reflective ballad about cherishing past moments."}"""

        prompt = f"""Analyze this guitar tab:

Song: {song}
Artist: {artist}

Content:
{content[:3000]}  # Truncate very long tabs
"""

        try:
            response = self.chat(prompt, system_prompt=system_prompt, temperature=0.3)

            # Parse JSON response
            # Handle potential markdown code blocks
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
                response = response.rsplit("```", 1)[0]

            result = json.loads(response)

            # Validate structure
            return {
                "mood": result.get("mood", []),
                "themes": result.get("themes", []),
                "tempo_feel": result.get("tempo_feel", "medium"),
                "description": result.get("description", ""),
            }

        except (json.JSONDecodeError, KeyError) as e:
            # Return empty result on parse failure
            return {
                "mood": [],
                "themes": [],
                "tempo_feel": "medium",
                "description": f"Analysis failed: {e}",
            }

    def get_embedding_model(self) -> str:
        """Find an embedding model from loaded models."""
        models = self.get_models()
        for model in models:
            if "embed" in model.lower():
                return model
        return None

    def embed(self, text: str, model: str = None) -> list[float]:
        """
        Get embedding vector for text.

        Note: Requires an embedding model loaded in LMStudio.
        """
        if model is None:
            model = self.get_embedding_model()
            if model is None:
                raise RuntimeError("No embedding model found. Load one in LMStudio (e.g., text-embedding-nomic-embed-text-v1.5)")

        try:
            response = self.client.embeddings.create(
                model=model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise RuntimeError(f"Embedding failed: {e}")

    def embed_batch(self, texts: list[str], batch_size: int = 10, model: str = None) -> list[list[float]]:
        """
        Get embeddings for multiple texts.

        Processes in batches for efficiency.
        """
        if model is None:
            model = self.get_embedding_model()
            if model is None:
                raise RuntimeError("No embedding model found. Load one in LMStudio (e.g., text-embedding-nomic-embed-text-v1.5)")

        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = self.client.embeddings.create(
                    model=model,
                    input=batch,
                )
                embeddings.extend([d.embedding for d in response.data])
            except Exception as e:
                # On failure, append None for each in batch
                embeddings.extend([None] * len(batch))

        return embeddings


def get_client() -> Optional[LMStudioClient]:
    """
    Get an LMStudio client if available.

    Returns None if LMStudio is not running.
    """
    try:
        client = LMStudioClient()
        if client.is_available():
            return client
    except Exception:
        pass
    return None


def require_client() -> LMStudioClient:
    """
    Get an LMStudio client, raising an error if not available.
    """
    client = get_client()
    if client is None:
        raise RuntimeError(
            "LMStudio is not available. Please:\n"
            "  1. Start LMStudio\n"
            "  2. Load a model\n"
            "  3. Enable the local server (Settings > Local Server)\n"
            f"  4. Ensure it's running at {config.LMSTUDIO_URL}"
        )
    return client
