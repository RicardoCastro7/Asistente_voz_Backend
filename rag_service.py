import os 
import logging
import re

from langchain_community.vectorstores import Chroma
from get_embedding_function import get_embedding_function
from google import genai
from google.genai import types

BASE = os.path.abspath(os.path.dirname(__file__))
CHROMA_PATH = os.path.join(BASE, "chroma_db_mejorada123")
COLLECTION_NAME = "tic_unl_v1"
GEMINI_MODEL = "gemini-2.5-flash-lite"

logger = logging.getLogger(__name__)
client = genai.Client(api_key="AIzaSyAyqTO8aVR0Z_OYbJ4EoBUlkZGXxCgnPIM")  # ya lo tienes

def clean_response(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"^\s*[\*\-\u2022]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[\.\)]\s*", "", text, flags=re.MULTILINE)
    return text.strip()

def _get_chroma_db() -> Chroma:
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embedding_function(),
        collection_name=COLLECTION_NAME,
        collection_metadata={"hnsw:space": "cosine"},
    )

def ask_gemini(query_text: str, prompt_template: str) -> str:
    """
    Hace RAG + llamada a Gemini usando el prompt_template recibido.
    El prompt NO está quemado en este archivo: viene desde la BD.
    """
    try:
        db = _get_chroma_db()

        docs = db.max_marginal_relevance_search(
            query_text,
            k=12,
            lambda_mult=0.25
        )

        logger.debug("[RAG] %d docs recuperados", len(docs))
        for i, d in enumerate(docs[:5]):
            logger.debug(
                "[RAG][%d] src=%s | %s",
                i,
                d.metadata.get("source"),
                d.page_content[:200].replace("\n", " ")
            )

        context_text = "\n\n---\n\n".join(d.page_content for d in docs)

        # 🔥 AQUÍ usamos el prompt que viene de fuera
        prompt = prompt_template.format(
            context=context_text,
            question=query_text
        )

        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=800
            )
        )

        return clean_response((resp.text or "").strip())

    except Exception as e:
        logger.error("[RAG] Error en ask_gemini: %s", e, exc_info=True)
        return f"Error al llamar a Gemini: {str(e)}"

def debug_rag_search(query_text: str):
    db = _get_chroma_db()
    results = db.similarity_search_with_score(query_text, k=5)

    top = [
        {
            "score": float(s),
            "source": d.metadata.get("source"),
            "snippet": d.page_content[:300]
        }
        for d, s in results
    ]

    return {
        "q": query_text,
        "matches": len(top),
        "top": top
    }
