import traceback
from typing import Any, Dict, List

from neo4j import GraphDatabase
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_neo4j import Neo4jChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from models.custom_retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

# ============ CONFIG ============
CHROMA_PATH = "db_emb/public/Knowledge_vectors"
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
        num_ctx=4062, 
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
    # Create Chroma retriever
    chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

    # Create BM25 retriever (Hybrid Search)
    print("🔄 Initializing BM25 Retriever from existing vectorstore...")
    try:
        # Fetch all documents from Chroma to build BM25 index
        # valid_documents_only=True might be needed if using newer chroma versions, but .get() usually works
        collection_data = vectorstore.get() 
        documents = []
        if collection_data['documents']:
            for i in range(len(collection_data['documents'])):
                documents.append(Document(
                    page_content=collection_data['documents'][i],
                    metadata=collection_data['metadatas'][i] if collection_data['metadatas'] else {}
                ))
        
        if documents:
            bm25_retriever = BM25Retriever.from_documents(documents)
            bm25_retriever.k = 10
            
            # Combine in Ensemble (50% Semantic, 50% Keyword)
            retriever = EnsembleRetriever(
                retrievers=[chroma_retriever, bm25_retriever],
                weights=[0.5, 0.5]
            )
            print(f"✅ Ensemble Retriever active (Docs: {len(documents)})")
        else:
            print("⚠️ No documents found in store, falling back to pure Vector retrieval.")
            retriever = chroma_retriever
            
    except Exception as e:
        print(f"⚠️ BM25 Init failed ({e}), falling back to pure Vector retrieval.")
        retriever = chroma_retriever

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
        ("system", """You are a strictly constrained AI assistant. Your answer must be grounded ONLY in the provided context.

RULES:
1. STRICT GROUNDING: Answer ONLY using facts from the context. If the answer is not there, say "I cannot find the answer in the provided documents."
2. NO HALLUCINATIONS: Do not guess, infer, or use outside knowledge.
3. DIRECT STYLE: Be concise. Do NOT use transition words like "Additionally", "Furthermore", or "Moreover". Start directly with the answer.
4. CITATIONS: Cite the "Source" and "Page" for every fact used.
5. FORMAT: Use bullet points for lists.

Context:
{context}"""),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    rag_chain = (
        RunnablePassthrough.assign(
            context=RunnableLambda(lambda x: x["standalone_query"]) 
                    | _retriever 
                    | (lambda docs: "\n\n".join(
                        f"Source: {d.metadata.get('source', 'Unknown')} | Page: {d.metadata.get('page', 'N/A')}\nContent: {d.page_content}" 
                        for d in docs
                    ))
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
        for i, doc in enumerate(docs):
            print(f"--- Chunk {i+1} ---")
            print(doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content)
            print("-----------------")
        
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
