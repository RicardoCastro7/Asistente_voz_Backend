from sentence_transformers import SentenceTransformer
import numpy as np

_EMBEDDING_MODEL = None

class SentenceTransformerEmbeddings:
    def __init__(self, model_name="BAAI/bge-m3"):
        global _EMBEDDING_MODEL
        if _EMBEDDING_MODEL is None:
            _EMBEDDING_MODEL = SentenceTransformer(model_name)
        self.model = _EMBEDDING_MODEL

    def _l2(self, arr: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        return arr / n

    def embed_documents(self, texts):
        vecs = self.model.encode(texts, convert_to_numpy=True)
        return self._l2(vecs).tolist()

    def embed_query(self, text):
        vec = self.model.encode([text], convert_to_numpy=True)
        return self._l2(vec)[0].tolist()

def get_embedding_function():
    return SentenceTransformerEmbeddings()
