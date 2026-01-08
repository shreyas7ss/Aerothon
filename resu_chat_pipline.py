import os
from typing import List
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage

# --- CONFIGURATION ---
# Point this to your 'db_root/public/Knowledge_vectors' or wherever ingestion saved it
CHROMA_PATH = "db_root/public/Knowledge_vectors" 

llm = ChatOllama(model="llama3.1", temperature=0)
embeddings = OllamaEmbeddings(model="nomic-embed-text")

# 1. Load the Chroma Vector Store (This is your primary search tool)
vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# --- 2. PROMPTS ---
context_q_prompt = ChatPromptTemplate.from_messages([
    ("system", "Given the history, rephrase the user's last question into a standalone question."),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

qa_prompt = ChatPromptTemplate.from_messages([
    ("system", "Use the context to answer. If unsure, say you don't know.\n\nContext:\n{context}"),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

# --- 3. THE CHAIN ---
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

rag_chain = (
    RunnablePassthrough.assign(
        context=lambda x: (context_q_prompt | llm | StrOutputParser() if x.get("chat_history") else x["input"]) 
        | retriever | format_docs
    )
    | qa_prompt
    | llm
)

# --- 4. CHAT WITH LOCAL HISTORY ---
chat_history = [] 

def chat(user_input: str):
    # Retrieve docs manually to pull that metadata (Source/Page)
    docs = retriever.invoke(user_input)
    
    # Run AI
    response = rag_chain.invoke({"input": user_input, "chat_history": chat_history})
    
    # Extract Metadata for the citation
    sources = []
    for doc in docs:
        src = doc.metadata.get("source", "Unknown")
        pg = doc.metadata.get("page", "N/A")
        sources.append(f"- {src} (Page: {pg})")
    
    # Save to history for the next turn
    chat_history.extend([HumanMessage(content=user_input), AIMessage(content=response.content)])
    
    return f"{response.content}\n\n**Sources:**\n" + "\n".join(set(sources))

# Test
print(chat("What is the main topic of the Apple 10-K?"))