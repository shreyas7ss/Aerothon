import os
import shutil
import uuid
import socket
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from neo4j import GraphDatabase
import pymupdf4llm
from docx2python import docx2python

# --- CONFIGURATION ---
NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_AUTH = ("neo4j", "your_password") 
DB_NAME = "neo4j" 
CHROMA_ROOT = "db_root"
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        app.state.neo4j_driver.verify_connectivity()
        with app.state.neo4j_driver.session(database=DB_NAME) as session:
            session.run("CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
        print(f"✅ Neo4j Ready | 🚀 Server: http://{get_local_ip()}:8000")
    except Exception as e:
        print(f"❌ Neo4j Failed: {e}")
        raise e
    yield
    app.state.neo4j_driver.close()

app = FastAPI(title="Knowledge Ingestion API", lifespan=lifespan)

def get_or_create_vector_db(sensitivity: str):
    persist_path = os.path.join(CHROMA_ROOT, sensitivity, "Knowledge_vectors")
    return Chroma(
        collection_name="Knowledge_Store",
        persist_directory=persist_path, 
        embedding_function=OllamaEmbeddings(model="nomic-embed-text")
    )

# --- BACKGROUND TASK WITH BATCHING ---
def process_document_task(file_path: str, filename: str, sensitivity: str, category: str):
    """Processes documents with safety batching to prevent 5461 limit errors."""
    doc_id = str(uuid.uuid4())
    print(f"⚙️ Background Ingestion Started: {filename}")
    
    try:
        # Step 1: Extraction
        if filename.lower().endswith(".pdf"):
            text = pymupdf4llm.to_markdown(file_path)
        elif filename.lower().endswith(".docx"):
            with docx2python(file_path) as doc: text = doc.text
        else:
            with open(file_path, "r", encoding="utf-8") as f: text = f.read()

        # Step 2: Semantic Chunking
        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        chunks = splitter.split_text(text)
        print(f"📄 Document split into {len(chunks)} chunks.")

        # Step 3: Vector Store with Manual Batching
        vector_db = get_or_create_vector_db(sensitivity)
        langchain_docs = [
            Document(page_content=c, metadata={"doc_id": doc_id, "source": filename}) 
            for c in chunks
        ]
        
        # FIX: We use a batch size of 5000 to stay safely under the 5461 SQLite limit
        max_batch = 5000
        for i in range(0, len(langchain_docs), max_batch):
            batch = langchain_docs[i : i + max_batch]
            print(f"📦 Adding batch {i // max_batch + 1} ({len(batch)} chunks) to Chroma...")
            vector_db.add_documents(batch)

        # Step 4: Graph Storage (Neo4j)
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session(database=DB_NAME) as session:
            session.run("""
                MERGE (d:Document {id: $id})
                SET d.name = $name, d.sensitivity = $sens, d.status = 'processed'
                MERGE (c:Category {name: $cat})
                MERGE (d)-[:BELONGS_TO]->(c)
            """, id=doc_id, name=filename, sens=sensitivity, cat=category)
        driver.close()
        
        print(f"✅ Background Ingestion Finished: {filename}")
        
    except Exception as e:
        print(f"❌ Error processing {filename}: {str(e)}")

@app.post("/ingest")
async def ingest_pipeline(
    background_tasks: BackgroundTasks, 
    files: List[UploadFile] = File(...), 
    sensitivity: str = Form("public"),
    category: str = Form("general")
):
    results = []
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        if os.path.exists(file_path):
            results.append({"file": file.filename, "status": "skipped", "reason": "Already exists"})
            continue
            
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        background_tasks.add_task(process_document_task, file_path, file.filename, sensitivity, category)
        results.append({"file": file.filename, "status": "upload_success"})

    return {"message": "Files received. Processing batches in background.", "results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)