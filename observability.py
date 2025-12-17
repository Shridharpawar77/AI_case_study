import os
from langfuse import Langfuse

_langfuse = None

def get_langfuse() -> Langfuse:
    global _langfuse
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    return _langfuse
