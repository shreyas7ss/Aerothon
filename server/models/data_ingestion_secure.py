import os
import uuid
from typing import Any
from pathlib import Path
import fitz  # PyMuPDF

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from neo4j import GraphDatabase

import pymupdf4llm
from docx2python import docx2python

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️ pytesseract not available. Image text extraction disabled.")

# ============ CONFIG ============
CHROMA_ROOT = "secure_DB"
UPLOAD_DIR = "secure_uploads"
IMAGE_STORAGE_DIR = "secure_uploads/images"
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
DB_NAME = "neo4j"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)


# ============ IMAGE EXTRACTION ============
def extract_images_from_pdf(pdf_path: str, doc_id: str, filename: str) -> list:
    """Extract images from PDF and generate text descriptions."""
    image_docs = []
    try:
        pdf_document = fitz.open(pdf_path)
        
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Save image
                    image_filename = f"{doc_id}_p{page_num + 1}_img{img_index}.{image_ext}"
                    image_path = os.path.join(IMAGE_STORAGE_DIR, image_filename)
                    
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    # Generate description using OCR
                    description = ""
                    if OCR_AVAILABLE:
                        try:
                            img_pil = Image.open(image_path)
                            ocr_text = pytesseract.image_to_string(img_pil)
                            if ocr_text.strip():
                                description = f"Image on page {page_num + 1} contains: {ocr_text.strip()}"
                            else:
                                description = f"Image/chart/graph on page {page_num + 1} (no text detected)"
                        except:
                            description = f"Image on page {page_num + 1} at {image_path}"
                    else:
                        description = f"Image on page {page_num + 1} stored at {image_path}"
                    
                    image_docs.append(Document(
                        page_content=description,
                        metadata={
                            "source": filename,
                            "page": page_num + 1,
                            "doc_id": doc_id,
                            "type": "image",
                            "image_path": image_path
                        }
                    ))
                except Exception as e:
                    print(f"⚠️ Image extraction error p{page_num + 1}: {e}")
        
        pdf_document.close()
        if image_docs:
            print(f"📷 Extracted {len(image_docs)} images")
    except Exception as e:
        print(f"❌ Image extraction failed: {e}")
    
    return image_docs


# ============ VECTOR STORE ============
def get_or_create_vector_db(sensitivity: str = "secure"):
    persist_path = os.path.join(CHROMA_ROOT, sensitivity, "Knowledge_vectors")
    return Chroma(
        collection_name="Knowledge_Store",
        persist_directory=persist_path,
        embedding_function=OllamaEmbeddings(model="nomic-embed-text")
    )


# ============ INGESTION FUNCTION ============
def process_document(neo4j_driver: Any, file_path: str, filename: str, sensitivity: str = "secure", category: str = "confidential"):
    """
    Process a secure document: extract, chunk, embed, and store in Chroma + Neo4j.
    
    Args:
        neo4j_driver: Neo4j driver instance
        file_path: Path to the uploaded file
        filename: Original filename
        sensitivity: "secure" or other (default: "secure")
        category: Document category (default: "confidential")
    """
    doc_id = str(uuid.uuid4())
    print(f"\n🔒 SECURE INGESTION Started: {filename} | ID: {doc_id} | Category: {category}")

    try:
        extracted_docs = []
        
        # Extract text with page awareness
        if filename.lower().endswith(".pdf"):
            print(f"📄 Extracting text from PDF...")
            # Extract text
            pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
            for page in pages:
                content = page.get("text") or page.get("metadata", {}).get("text", "")
                page_num = page.get("metadata", {}).get("page", 0) + 1
                extracted_docs.append(Document(
                    page_content=content, 
                    metadata={"source": filename, "page": page_num, "doc_id": doc_id, "type": "text"}
                ))
            print(f"✅ Extracted {len(pages)} page(s) of text")
            
            # Extract images
            print(f"📷 Extracting images from PDF...")
            image_docs = extract_images_from_pdf(file_path, doc_id, filename)
            extracted_docs.extend(image_docs)
        elif filename.lower().endswith(".docx"):
            with docx2python(file_path) as doc:
                extracted_docs.append(Document(
                    page_content=doc.text, 
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id, "type": "text"}
                ))
        else:
            # Plain text file
            with open(file_path, "r", encoding="utf-8") as f:
                extracted_docs.append(Document(
                    page_content=f.read(), 
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id, "type": "text"}
                ))

        # Chunk with metadata preservation (800/100 for secure)
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        final_chunks = splitter.split_documents(extracted_docs)
        print(f"📄 {filename}: {len(final_chunks)} chunks created (text + images).")

        # Store in Chroma vector DB
        print(f"💾 Storing {len(final_chunks)} chunk(s) in Chroma vector DB...")
        vector_db = get_or_create_vector_db(sensitivity)
        batch_size = 500
        for i in range(0, len(final_chunks), batch_size):
            vector_db.add_documents(final_chunks[i:i + batch_size])
        print(f"✅ All chunks stored in Chroma")

        # Store metadata in Neo4j
        print(f"📊 Storing metadata in Neo4j...")
        with neo4j_driver.session(database=DB_NAME) as session:
            session.run("""
                MERGE (d:Document {id: $id})
                SET d.name = $name, d.sensitivity = $sens, d.status = 'processed'
                MERGE (c:Category {name: $cat})
                MERGE (d)-[:BELONGS_TO]->(c)
            """, id=doc_id, name=filename, sens=sensitivity, cat=category)
        print(f"✅ Metadata stored in Neo4j")

        print(f"✅ SECURE INGESTION Finished: {filename}\n")

    except Exception as e:
        print(f"❌ SECURE INGESTION Failed [{filename}]: {e}")
        raise
