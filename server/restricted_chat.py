import os
import traceback
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from neo4j import GraphDatabase

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_neo4j import Neo4jChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage

# --- 1. CONFIGURATION ---
# Use absolute path to avoid directory resolution issues
CHROMA_PATH = r"C:\Users\shreyas\Aerothon\expirements\db_root\public\Knowledge_vectors"
MODEL_NAME = "llama3.1:8b-instruct-q4_K_M"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "password")

# --- 2. INITIALIZE FastAPI & MODELS ---
app = FastAPI(title="Secure Hybrid RAG API")

# Explicit base_url prevents random port ResponseErrors
llm = ChatOllama(model=MODEL_NAME, temperature=0, num_ctx=8192, base_url=OLLAMA_BASE_URL)
embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)

vectorstore = Chroma(
    persist_directory=CHROMA_PATH, 
    embedding_function=embeddings,
    collection_name="Knowledge_Store"
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

# --- 3. SCHEMA & RAG LOGIC ---
def initialize_neo4j_schema():
    """Pre-defines relationships to stop Neo4j 'UnknownRelationship' warnings."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session() as session:
        session.run("""
            MERGE (s:Session {id: 'schema_init'})
            MERGE (m:Message {content: 'init', role: 'system'})
            MERGE (s)-[:LAST_MESSAGE]->(m)
            MERGE (m)-[:NEXT]->(m)
            DETACH DELETE s, m
        """)
    driver.close()

initialize_neo4j_schema()

# Separate chain for standalone query generation
context_q_prompt = ChatPromptTemplate.from_messages([
    ("system", "Rephrase the user's last question into a standalone question based on history."),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
standalone_query_chain = context_q_prompt | llm | StrOutputParser()

# Main QA Chain
qa_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a professional Document Analyst. Use the provided context to answer questions precisely or provide comprehensive summaries.

    GUIDELINES:
    1. FACT RETRIEVAL: Provide direct answers grounded in context.
    2. SUMMARIZATION: Synthesize details into a structured overview. Use bullet points.
    3. INTEGRITY: Use ONLY provided context. If missing, say materials are insufficient.
    4. CITATION: Always mention source and page numbers.

    Context:
    {context}"""),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

rag_chain = (
    RunnablePassthrough.assign(
        context=RunnableLambda(lambda x: x["standalone_query"]) | retriever | (lambda docs: "\n\n".join(d.page_content for d in docs))
    )
    | qa_prompt
    | llm
)

# --- 4. API DATA MODELS ---
class ChatRequest(BaseModel):
    user_input: str
    session_id: str = "default_user"

# --- 5. ENDPOINTS ---

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Retrieves conversation thread from Neo4j."""
    try:
        history = Neo4jChatMessageHistory(
            url=NEO4J_URI, username=NEO4J_AUTH[0], password=NEO4J_AUTH[1], session_id=session_id
        )
        return {
            "session_id": session_id, 
            "history": [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content} for m in history.messages]
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Processes RAG query with history rephrasing and metadata extraction."""
    try:
        history = Neo4jChatMessageHistory(
            url=NEO4J_URI, username=NEO4J_AUTH[0], password=NEO4J_AUTH[1], session_id=request.session_id
        )
        
        # 1. Rephrase question if history exists
        if history.messages:
            standalone_query = standalone_query_chain.invoke({"input": request.user_input, "chat_history": history.messages})
        else:
            standalone_query = request.user_input

        # 2. Get Documents for metadata extraction
        docs = retriever.invoke(standalone_query)
        
        # 3. Run RAG Chain
        response = rag_chain.invoke({
            "input": request.user_input, 
            "standalone_query": standalone_query, 
            "chat_history": history.messages
        })
        
        # 4. Save to Neo4j
        history.add_user_message(request.user_input)
        history.add_ai_message(response.content)
        
        sources = [f"- {d.metadata.get('source')} (Page: {d.metadata.get('page')})" for d in docs]
        
        return {"answer": response.content, "sources": list(set(sources))}

    except Exception as e:
        # Prints the full error to your terminal for debugging
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)