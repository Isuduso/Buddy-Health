import json
import re
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_classic.chains import RetrievalQA
from langchain_groq import ChatGroq

# 1. Load and parse health_data.txt
def load_health_data(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    raw_arrays = re.findall(r'\[.*?\]', content, re.DOTALL)
    
    documents = []
    for array in raw_arrays:
        entries = json.loads(array)
        for entry in entries:
            text = "\n".join([f"{k}: {v}" for k, v in entry.items()])
            doc = Document(
                page_content=text,
                metadata={"disease": entry.get("Disease/Condition Name", "Unknown")}
            )
            documents.append(doc)
    return documents

docs = load_health_data("health_data.txt")
print(f"✅ Loaded {len(docs)} health entries")

# 2. Split documents
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# 3. Embed using HuggingFace (free, local)
print("⏳ Loading embedding model (first run may take a minute)...")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# 4. Store in Chroma
vectorstore = Chroma.from_documents(chunks, embeddings)
print("✅ Vector store ready")

# 5. Groq LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    temperature=0.2
)

# 6. QA chain
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
    return_source_documents=True
)

# 7. Ask questions
def ask(question):
    print(f"\n🔍 Question: {question}")
    result = qa_chain.invoke(question)
    print(f"💬 Answer: {result['result']}")
    print(f"📄 Sources: {[doc.metadata['disease'] for doc in result['source_documents']]}")
    print("-" * 60)

ask("What are the symptoms of malaria?")
ask("What should I do for a minor burn?")
ask("When should I see a doctor for a headache?")