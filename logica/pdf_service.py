# pdf_service.py
import os
import shutil
from typing import List

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from get_embedding_function import get_embedding_function

BASE = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE, "data1")
CHROMA_PATH = os.path.join(BASE, "chroma_db_mejorada123")
COLLECTION_NAME = "tic_unl_v1"

# Crear carpeta de PDFs si no existe
os.makedirs(DATA_PATH, exist_ok=True)


def load_documents() -> List[Document]:
    return PyPDFDirectoryLoader(DATA_PATH).load()


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
        length_function=len
    )
    return splitter.split_documents(documents)


def calculate_chunk_ids(chunks: List[Document]) -> List[Document]:
    last_page_id, idx = None, 0
    for c in chunks:
        source = c.metadata.get("source")
        page = c.metadata.get("page")
        page_id = f"{source}:{page}"
        idx = idx + 1 if page_id == last_page_id else 0
        c.metadata["id"] = f"{page_id}:{idx}"
        last_page_id = page_id
    return chunks


def add_to_chroma(chunks: List[Document]) -> None:
    db = Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embedding_function(),
        collection_name=COLLECTION_NAME,
        collection_metadata={"hnsw:space": "cosine"}
    )

    chunks_with_ids = calculate_chunk_ids(chunks)
    existing = db.get(include=[])
    existing_ids = set(existing.get("ids", []))
    new_chunks = [c for c in chunks_with_ids if c.metadata["id"] not in existing_ids]

    if new_chunks:
        new_ids = [c.metadata["id"] for c in new_chunks]
        db.add_documents(new_chunks, ids=new_ids)
        db.persist()


def process_all_pdfs():
    docs = load_documents()
    chunks = split_documents(docs)
    add_to_chroma(chunks)


def clear_database():
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)
