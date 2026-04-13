from langchain_huggingface import HuggingFaceEmbeddings

# Initialize embedding model
embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    # dimension=10,
)

# Generate embedding for a query
vector = embedding.embed_query("What is the Pixel 7 chipset used for?")

# print(vector)
print("Vector length:", len(vector))
print(str(vector))
