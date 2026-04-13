from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from dotenv import load_dotenv
import os

load_dotenv()

llm = HuggingFaceEndpoint(
    repo_id="HuggingFaceTB/SmolLM3-3B",
    task="text-generation",
)

model = ChatHuggingFace(llm=llm)

res = model.invoke("what is capital of Pakistan?")

print(res.content)