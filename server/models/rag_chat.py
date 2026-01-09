import traceback
from typing import Any, Dict, List

from neo4j import GraphDatabase
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
import os
from langchain_neo4j import Neo4jChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

# ============ CONFIG ============
CHROMA_PATH = "db_root/public/Knowledge_vectors"
MODEL_NAME = "llama3.1:8b-instruct-q4_K_M"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "password")
DB_NAME = "neo4j"


# ============ INITIALIZE COMPONENTS ============
def _initialize_components():
    """Initialize LLM, embeddings, and vector store."""
    llm = ChatOllama(
        model=MODEL_NAME, 
        temperature=0, 
        num_ctx=8192, 
        base_url=OLLAMA_BASE_URL
    )
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text", 
        base_url=OLLAMA_BASE_URL
    )
    vectorstore = Chroma(
        persist_directory=CHROMA_PATH, 
        embedding_function=embeddings,
        collection_name="Knowledge_Store"
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": 15})
    return llm, retriever


def _initialize_neo4j_schema():
    """Pre-define Neo4j relationships to prevent warnings."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session(database=DB_NAME) as session:
            session.run("""
                MERGE (s:Session {id: 'schema_init'})
                MERGE (m:Message {content: 'init', role: 'system'})
                MERGE (s)-[:LAST_MESSAGE]->(m)
                MERGE (m)-[:NEXT]->(m)
                DETACH DELETE s, m
            """)
        driver.close()
    except Exception as e:
        print(f"Warning: Neo4j schema init failed: {e}")


# Initialize on module load
_llm, _retriever = _initialize_components()
_initialize_neo4j_schema()


# ============ CHAINS ============
def _get_chains():
    """Create standalone query and QA chains."""
    
    # Standalone query chain (rephrase with history)
    context_q_prompt = ChatPromptTemplate.from_messages([
        ("system", "Rephrase the user's last question into a standalone question based on history."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    standalone_query_chain = context_q_prompt | _llm | StrOutputParser()

    # QA chain with context
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a strictly constrained Document Analyst. Your sole purpose is to answer questions based ONLY on the provided context.

CRITICAL RULES:
1. NO OUTSIDE KNOWLEDGE: You must NOT use any knowledge outside of the provided context. If the answer is not in the context, you MUST say "I cannot find the answer in the provided documents."
2. FACTUAL ACCURACY: Do not hallucinate or make up information. If the context is ambiguous, state the ambiguity.
3. CITATIONS: Always mention the source and page numbers from the context when available.
4. FORMAT: Use bullet points for structured data.

Context:
{context}"""),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    rag_chain = (
        RunnablePassthrough.assign(
            context=RunnableLambda(lambda x: x["standalone_query"]) 
                    | _retriever 
                    | (lambda docs: "\n\n".join(d.page_content for d in docs))
        )
        | qa_prompt
        | _llm
    )
    
    return standalone_query_chain, rag_chain


# ============ RAG CHAT FUNCTION ============
def rag_chat(user_input: str, session_id: str = "default_user") -> Dict[str, Any]:
    """
    Process a RAG query with chat history.
    
    Args:
        user_input: User's query
        session_id: Conversation session ID (default: "default_user")
    
    Returns:
        Dict with "answer" and "sources"
    """
    print(f"\n🔍 RAG_CHAT: Starting query processing for session '{session_id}'")
    try:
        standalone_query_chain, rag_chain = _get_chains()
        
        # Get chat history from Neo4j
        history = Neo4jChatMessageHistory(
            url=NEO4J_URI, 
            username=NEO4J_AUTH[0], 
            password=NEO4J_AUTH[1], 
            session_id=session_id
        )
        
        # Rephrase query based on history
        if history.messages:
            print(f"🔄 Rephrasing query with {len(history.messages)} history message(s)")
            standalone_query = standalone_query_chain.invoke({
                "input": user_input, 
                "chat_history": history.messages
            })
            print(f"➡️ Standalone query: {standalone_query[:100]}...")
        else:
            print("🆕 No history found, using original query")
            standalone_query = user_input

        # Retrieve relevant documents
        print(f"📂 Retrieving documents from public DB...")
        docs = _retriever.invoke(standalone_query)
        print(f"✅ Retrieved {len(docs)} document chunk(s)")
        
        # Generate response via RAG
        print(f"🤖 Generating LLM response...")
        response = rag_chain.invoke({
            "input": user_input, 
            "standalone_query": standalone_query, 
            "chat_history": history.messages
        })
        print(f"✅ Response generated ({len(response.content)} chars)")
        
        # Save to Neo4j history
        print(f"💾 Saving conversation to Neo4j...")
        history.add_user_message(user_input)
        history.add_ai_message(response.content)
        
        # Extract sources
        sources = [f"- {d.metadata.get('source')} (Page: {d.metadata.get('page')})" for d in docs]
        print(f"✅ RAG_CHAT: Complete | Sources: {len(set(sources))}\n")
        
        return {
            "answer": response.content, 
            "sources": list(set(sources))
        }

    except Exception as e:
        print(f"❌ RAG_CHAT: Error - {str(e)}")
        print(traceback.format_exc())
        raise
