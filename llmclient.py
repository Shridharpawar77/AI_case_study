import os
from openai import AzureOpenAI

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()  # ✅ ensure env loaded before reading

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")
