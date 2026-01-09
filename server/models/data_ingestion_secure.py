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


import torch
from transformers import AutoModel, AutoTokenizer
from PIL import Image


# Global model cache to avoid reloading
_MINICPM_MODEL = None
_MINICPM_TOKENIZER = None


# ============ CONFIG ============
MINICPM_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MiniCPM-V")
CHROMA_ROOT = "db_root"
UPLOAD_DIR = "uploads"
IMAGE_STORAGE_DIR = "uploads/images"
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
DB_NAME = "neo4j"


os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)




# ============ IMAGE EXTRACTION ============
def load_minicpm_model():
    """Lazy load MiniCPM-V model and tokenizer."""
    global _MINICPM_MODEL, _MINICPM_TOKENIZER
    if _MINICPM_MODEL is None or _MINICPM_TOKENIZER is None:
        print(f"🔄 Loading MiniCPM-V model from {MINICPM_MODEL_PATH}...")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"🚀 Using device: {device}")
           
            _MINICPM_MODEL = AutoModel.from_pretrained(
                MINICPM_MODEL_PATH,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
                device_map=device
            )
            _MINICPM_TOKENIZER = AutoTokenizer.from_pretrained(
                MINICPM_MODEL_PATH,
                trust_remote_code=True
            )
            _MINICPM_MODEL.eval()
            print("✅ MiniCPM-V loaded successfully.")
        except Exception as e:
            print(f"❌ Failed to load MiniCPM-V: {e}")
            raise e
    return _MINICPM_MODEL, _MINICPM_TOKENIZER


def extract_images_from_pdf(pdf_path: str, doc_id: str, filename: str) -> list:
    """Extract images from PDF and generate text descriptions using MiniCPM-V."""
    image_docs = []
    try:
        model, tokenizer = load_minicpm_model()
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
                   
                    # Generate description using MiniCPM-V
                    description = ""
                    try:
                        img_pil = Image.open(image_path).convert('RGB')
                        msgs = [{'role': 'user', 'content': 'Describe this image in detail.'}]
                       
                        res = model.chat(
                            image=img_pil,
                            msgs=msgs,
                            tokenizer=tokenizer,
                            sampling=True,
                            temperature=0.7
                        )
                       
                        if res:
                            description = f"Image on page {page_num + 1}: {res}"
                        else:
                            description = f"Image on page {page_num + 1} (no description generated)"
                           
                    except Exception as e:
                        print(f"⚠️ MiniCPM inference error: {e}")
                        description = f"Image on page {page_num + 1} at {image_path}"
                   
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
def get_or_create_vector_db(sensitivity: str = "public"):
    persist_path = os.path.join(CHROMA_ROOT, sensitivity, "Knowledge_vectors")
    return Chroma(
        collection_name="Knowledge_Store",
        persist_directory=persist_path,
        embedding_function=OllamaEmbeddings(model="nomic-embed-text")
    )




# ============ INGESTION FUNCTION ============
def process_document(neo4j_driver: Any, file_path: str, filename: str, sensitivity: str = "public", category: str = "general"):
    """
    Process a document: extract, chunk, embed, and store in Chroma + Neo4j.
   
    Args:
        neo4j_driver: Neo4j driver instance
        file_path: Path to the uploaded file
        filename: Original filename
        sensitivity: "public" or "secure" (default: "public")
        category: Document category (default: "general")
    """
    doc_id = str(uuid.uuid4())
    print(f"\n⚙️ PUBLIC INGESTION Started: {filename} | ID: {doc_id} | Category: {category}")


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
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id}
                ))
        else:
            # Plain text file
            with open(file_path, "r", encoding="utf-8") as f:
                extracted_docs.append(Document(
                    page_content=f.read(),
                    metadata={"source": filename, "page": "N/A", "doc_id": doc_id}
                ))


        # Chunk with metadata preservation
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
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


        print(f"✅ PUBLIC INGESTION Finished: {filename}\n")


    except Exception as e:
        print(f"❌ PUBLIC INGESTION Failed [{filename}]: {e}")
        raise
