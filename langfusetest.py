import os
from dotenv import load_dotenv
from langfuse import get_client

load_dotenv()

langfuse = get_client()

# Verify authentication
print("auth_check:", langfuse.auth_check())

# Create a trace implicitly by creating a root observation (span)
with langfuse.start_as_current_observation(as_type="span", name="smoke-test-span"):
    # Add a nested observation
    with langfuse.start_as_current_observation(as_type="generation", name="smoke-test-generation"):
        pass

# Ensure events are sent (Langfuse exports async)
try:
    langfuse.flush()
except Exception:
    pass

print("✅ Sent smoke trace (check Langfuse → Tracing)")
