import os
import shutil
import uuid
import socket
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from neo4j import GraphDatabase

import pymupdf4llm
from docx2python import docx2python

# ---------------- CONFIG ---------------- #
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
NEO4J_AUTH = (NEO4J_USER, NEO4J_PASSWORD)

DB_NAME = "neo4j"
# Updated directory names as requested
CHROMA_ROOT = "secure_DB" 
UPLOAD_DIR = "secure_uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- UTIL ---------------- #
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ---------------- FASTAPI LIFESPAN ---------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    app.state.neo4j_driver = driver
    try:
        driver.verify_connectivity()
        with driver.session(database=DB_NAME) as session:
            session.run("CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
        print(f"✅ Neo4j Ready | 🚀 Server: http://{get_local_ip()}:8000")
    except Exception as e:
        print(f"❌ Neo4j Startup Failed: {e}")
        raise
    yield
    driver.close()

app = FastAPI(title="Secure Knowledge Ingestion API", lifespan=lifespan)

# ---------------- VECTOR STORE ---------------- #
def get_or_create_vector_db(sensitivity: str):
    persist_path = os.path.join(CHROMA_ROOT, sensitivity, "Knowledge_vectors")
    return Chroma(
        collection_name="Knowledge_Store",
        persist_directory=persist_path,
        embedding_function=OllamaEmbeddings(model="nomic-embed-text")
    )

# ---------------- BACKGROUND INGESTION ---------------- #
def process_document_task(neo4j_driver, file_path: str, filename: str, sensitivity: str, category: str):
    doc_id = str(uuid.uuid4())
    print(f"⚙️ Ingestion Started: {filename}")

    try:
        extracted_docs = []
        
        # ---- Extract with Page Awareness ----
        if filename.lower().endswith(".pdf"):
            # page_chunks=True enables metadata preservation per page
            pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
            for page in pages:
                content = page.get("text") or page.get("metadata", {}).get("text", "")
                page_num = page.get("metadata", {}).get("page", 0) + 1
                extracted_docs.append(Document(
                    page_content=content, 
                    metadata={"source": filename, "page": page_num, "doc_id": doc_id}
                ))
        elif filename.lower().endswith(".docx"):
            with docx2python(file_path) as doc:
                extracted_docs.append(Document(
                    page_content=doc.text, 
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id}
                ))
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                extracted_docs.append(Document(
                    page_content=f.read(), 
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id}
                ))

        # ---- Chunk (Preserving Metadata) ----
        # Using 800/100 split for better precision as discussed earlier
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        final_chunks = splitter.split_documents(extracted_docs)
        print(f"📄 {filename}: {len(final_chunks)} chunks created.")

        # ---- Vector DB ----
        vector_db = get_or_create_vector_db(sensitivity)
        batch_size = 500
        for i in range(0, len(final_chunks), batch_size):
            vector_db.add_documents(final_chunks[i:i + batch_size])

        # ---- Neo4j ----
        with neo4j_driver.session(database=DB_NAME) as session:
            session.run("""
                MERGE (d:Document {id: $id})
                SET d.name = $name, d.sensitivity = $sens, d.status = 'processed'
                MERGE (c:Category {name: $cat})
                MERGE (d)-[:BELONGS_TO]->(c)
            """, id=doc_id, name=filename, sens=sensitivity, cat=category)

        print(f"✅ Ingestion Finished: {filename}")

    except Exception as e:
        print(f"❌ Ingestion Failed [{filename}]: {e}")

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
            results.append({"file": file.filename, "status": "skipped", "reason": "already exists"})
            continue
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        background_tasks.add_task(
            process_document_task, 
            app.state.neo4j_driver, 
            file_path, 
            file.filename, 
            sensitivity, 
            category
        )
        results.append({"file": file.filename, "status": "queued"})
        
    return {"message": "Files uploaded to secure_uploads. Processing in background.", "results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)