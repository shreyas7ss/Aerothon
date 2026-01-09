import traceback
from typing import Any, Dict, List

from neo4j import GraphDatabase
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_neo4j import Neo4jChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

# ============ CONFIG ============
CHROMA_PATH_PUBLIC = "db_root/public/Knowledge_vectors"
CHROMA_PATH_SECURE = "secure_DB/secure/Knowledge_vectors"
MODEL_NAME = "llama3.1:8b-instruct-q4_K_M"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "password")
DB_NAME = "neo4j"


# ============ INITIALIZE COMPONENTS ============
def _initialize_components():
    """Initialize LLM, embeddings, and dual vector stores."""
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
    
    # Public vectorstore
    vectorstore_public = Chroma(
        persist_directory=CHROMA_PATH_PUBLIC, 
        embedding_function=embeddings,
        collection_name="Knowledge_Store"
    )
    
    # Secure vectorstore
    vectorstore_secure = Chroma(
        persist_directory=CHROMA_PATH_SECURE, 
        embedding_function=embeddings,
        collection_name="Knowledge_Store"
    )
    
    retriever_public = vectorstore_public.as_retriever(search_kwargs={"k": 10})
    retriever_secure = vectorstore_secure.as_retriever(search_kwargs={"k": 10})
    
    return llm, retriever_public, retriever_secure


def _initialize_neo4j_schema():
    """Pre-define Neo4j relationships to prevent warnings."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session(database=DB_NAME) as session:
            session.run("""
                MERGE (s:Session {id: 'schema_init_dual'})
                MERGE (m:Message {content: 'init', role: 'system'})
                MERGE (s)-[:LAST_MESSAGE]->(m)
                MERGE (m)-[:NEXT]->(m)
                DETACH DELETE s, m
            """)
        driver.close()
    except Exception as e:
        print(f"Warning: Neo4j schema init failed: {e}")


# Initialize on module load
_llm, _retriever_public, _retriever_secure = _initialize_components()
_initialize_neo4j_schema()


# ============ DUAL RETRIEVAL ============
def _get_combined_context(query: str) -> str:
    """Retrieve from both public and secure databases."""
    public_docs = _retriever_public.invoke(query)
    secure_docs = _retriever_secure.invoke(query)
    
    all_docs = public_docs + secure_docs
    return "\n\n".join(d.page_content for d in all_docs)


# ============ CHAINS ============
def _get_chains():
    """Create standalone query and QA chains for dual retrieval."""
    
    # Standalone query chain (rephrase with history)
    context_q_prompt = ChatPromptTemplate.from_messages([
        ("system", "Rephrase the user's last question into a standalone question based on history."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    standalone_query_chain = context_q_prompt | _llm | StrOutputParser()

    # QA chain with dual context
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a professional Document Analyst with access to both general and confidential documents. Use the provided context to answer questions precisely.

GUIDELINES:
1. FACT RETRIEVAL: Provide direct answers grounded in context.
2. SUMMARIZATION: Synthesize details into structured overviews. Use bullet points.
3. INTEGRITY: Use ONLY provided context. If missing, say materials are insufficient.
4. CITATION: Always mention source and page numbers.

Context (from both public and secure databases):
{context}"""),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    rag_chain = (
        RunnablePassthrough.assign(
            context=RunnableLambda(lambda x: _get_combined_context(x["standalone_query"]))
        )
        | qa_prompt
        | _llm
    )
    
    return standalone_query_chain, rag_chain


# ============ RAG CHAT DUAL FUNCTION ============
def rag_chat_dual(user_input: str, session_id: str = "default_dual_user") -> Dict[str, Any]:
    """
    Process a RAG query with dual retrieval (public + secure).
    
    Args:
        user_input: User's query
        session_id: Conversation session ID (default: "default_dual_user")
    
    Returns:
        Dict with "answer" and "sources"
    """
    print(f"\n🔍 RAG_CHAT_DUAL: Starting dual query processing for session '{session_id}'")
    try:
        standalone_query_chain, rag_chain = _get_chains()
        
        # Get chat history from Neo4j (separate from single-DB chat)
        history = Neo4jChatMessageHistory(
            url=NEO4J_URI, 
            username=NEO4J_AUTH[0], 
            password=NEO4J_AUTH[1], 
            session_id=f"dual_{session_id}"  # Prefix to separate from single-DB history
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

        # Retrieve relevant documents from both DBs
        print(f"📂 Retrieving from PUBLIC DB...")
        public_docs = _retriever_public.invoke(standalone_query)
        print(f"✅ Retrieved {len(public_docs)} chunk(s) from public")
        
        print(f"🔒 Retrieving from SECURE DB...")
        secure_docs = _retriever_secure.invoke(standalone_query)
        print(f"✅ Retrieved {len(secure_docs)} chunk(s) from secure")
        
        all_docs = public_docs + secure_docs
        print(f"📊 Total: {len(all_docs)} chunk(s) from both DBs")
        
        # Generate response via RAG
        print(f"🤖 Generating LLM response with dual context...")
        response = rag_chain.invoke({
            "input": user_input, 
            "standalone_query": standalone_query, 
            "chat_history": history.messages
        })
        print(f"✅ Response generated ({len(response.content)} chars)")
        
        # Save to Neo4j history
        print(f"💾 Saving conversation to Neo4j (dual session)...")
        history.add_user_message(user_input)
        history.add_ai_message(response.content)
        
        # Extract sources from both DBs
        sources = [f"- {d.metadata.get('source')} (Page: {d.metadata.get('page')})" for d in all_docs]
        print(f"✅ RAG_CHAT_DUAL: Complete | Sources: {len(set(sources))}\n")
        
        return {
            "answer": response.content, 
            "sources": list(set(sources))
        }

    except Exception as e:
        print(f"❌ RAG_CHAT_DUAL: Error - {str(e)}")
        print(traceback.format_exc())
        raise
