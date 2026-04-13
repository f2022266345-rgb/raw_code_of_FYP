from langchain_huggingface import HuggingFaceEmbeddings
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from dotenv import load_dotenv

load_dotenv()

model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2")

documents = [
    "Quantum computing utilizes qubits to perform complex calculations at speeds impossible for classical computers while maintaining superposition and entanglement states in controlled environments.",
    "The Amazon Rainforest is home to millions of species of insects and plants and plays a critical role in regulating the Earth's carbon cycle and oxygen production.",
    "Artificial intelligence models like transformers use self-attention mechanisms to weigh the importance of different words in a sentence regardless of their distance from each other.",
    "The Great Wall of China is a series of fortifications built across the historical northern borders of ancient Chinese states to protect against nomadic groups and invasions.",
    "Black holes are regions of spacetime where gravity is so strong that nothing, including light or other electromagnetic waves, has enough energy to escape their event horizon.",
    "Sustainable agriculture focuses on long-term crop productivity while minimizing environmental impact through crop rotation, organic fertilizers, and integrated pest management techniques.",
    "The Renaissance was a fervent period of European cultural, artistic, political and economic rebirth following the Middle Ages, led by figures like Leonardo da Vinci.",
    "Cryptocurrency relies on blockchain technology which is a decentralized and distributed digital ledger used to record transactions across many computers so that records cannot be altered.",
    "The human heart is a muscular organ that pumps blood through the blood vessels of the circulatory system, providing oxygen and nutrients to tissues while removing waste.",
    "Cybersecurity involves protecting systems, networks, and programs from digital attacks aimed at accessing, changing, or destroying sensitive information or extorting money from users.",
    "Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize foods with the help of chlorophyll and carbon dioxide.",
    "The Industrial Revolution marked a major turning point in history as transition to new manufacturing processes occurred in Europe and the United States in the 18th century.",
    "Mars is often called the Red Planet because iron minerals in the Martian soil oxidize or rust, causing the soil and atmosphere to look red from a distance.",
    "Mount Everest is Earth's highest mountain above sea level, located in the Mahalangur Himal sub-range of the Himalayas on the border between Nepal and China.",
    "The internet is a global system of interconnected computer networks that use the standard Internet Protocol Suite to link several billion devices worldwide for communication.",
    "Renewable energy sources such as solar, wind, and hydroelectric power are essential for reducing greenhouse gas emissions and combating the global climate change crisis.",
    "The Roman Empire was one of the most powerful economic, cultural, and military forces in the world of its time, spanning across three continents at its peak.",
    "DNA or deoxyribonucleic acid is the molecule that carries genetic instructions for the development, functioning, growth, and reproduction of all known organisms and many viruses.",
    "The Sahara Desert is the largest hot desert in the world and the third largest desert overall, covering much of North Africa with shifting sand dunes.",
    "Machine learning is a subset of artificial intelligence that provides systems the ability to automatically learn and improve from experience without being explicitly programmed.",
    "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, named after the engineer Gustave Eiffel whose company designed and built it.",
    "Global warming refers to the long-term rise in the average temperature of the Earth's climate system, primarily caused by human activities like burning fossil fuels.",
    "The Olympic Games are leading international sporting events featuring summer and winter sports competitions in which thousands of athletes from around the world participate.",
    "Vaccines work by stimulating the immune system to recognize and fight pathogens like bacteria or viruses, providing acquired immunity to specific infectious diseases.",
    "Coffee is a brewed drink prepared from roasted coffee beans, the seeds of berries from certain flowering plants in the Coffea genus, enjoyed globally for its caffeine.",
    "The Milky Way is the galaxy that contains our Solar System, with its name describing the galaxy's appearance from Earth as a hazy band of light in the sky.",
    "Democracy is a system of government in which laws, policies, leadership, and major undertakings are decided directly or indirectly by the people through voting.",
    "Ocean acidification is the ongoing decrease in the pH of the Earth's oceans, caused by the uptake of carbon dioxide from the atmosphere due to human activity.",
    "The printing press invented by Johannes Gutenberg revolutionized the spread of information and ideas, leading to the Reformation and the Scientific Revolution.",
    "Augmented reality is an interactive experience of a real-world environment where the objects that reside in the real world are enhanced by computer-generated information.",
    "Buddhism is a widespread Asian religion or philosophy founded by Siddhartha Gautama in northeastern India in the 5th century BC, focusing on spiritual development.",
    "Graphene is a single layer of carbon atoms arranged in a two-dimensional honeycomb lattice, known for its incredible strength and high electrical and thermal conductivity.",
    "The Great Barrier Reef is the world's largest coral reef system composed of over 2,900 individual reefs and 900 islands stretching for over 2,300 kilometers.",
    "Stock markets are venues where buyers and sellers meet to exchange shares of public corporations, acting as a barometer for the overall health of the economy.",
    "A symphony is an extended musical composition in Western classical music, most often written by composers for orchestra and typically divided into four movements.",
    "The United Nations is an intergovernmental organization aiming to maintain international peace and security, develop friendly relations among nations, and achieve cooperation.",
    "Electric vehicles use one or more electric motors for propulsion, drawing power from onboard battery packs that can be recharged at dedicated charging stations.",
    "Thermodynamics is the branch of physics that deals with heat and temperature, and their relation to energy, work, radiation, and properties of matter in systems.",
    "The Taj Mahal is an ivory-white marble mausoleum on the southern bank of the river Yamuna in the Indian city of Agra, built by the Mughal emperor Shah Jahan.",
    "Data science is an interdisciplinary field that uses scientific methods, processes, algorithms and systems to extract knowledge and insights from noisy, structured and unstructured data."
]

qurey = "tell me about Graphene in a single layer"

# Generate embeddings for documents
doc_embeddings = model.embed_documents(documents)

# Generate embedding for the query
query_embedding = model.embed_query(qurey)

similarity_scores = cosine_similarity([query_embedding], doc_embeddings)[0]

index, score =sorted(list(enumerate(similarity_scores)),key=lambda x: x[1])[-1]

print("user qurey:", qurey)
print("most similar document:", documents[index])
print("similarity score:", score)

