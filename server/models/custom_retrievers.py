from typing import List
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from collections import defaultdict

class EnsembleRetriever(BaseRetriever):
    retrievers: List[BaseRetriever]
    weights: List[float]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None
    ) -> List[Document]:
        """
        Get documents from all retrievers and combine using Reciprocal Rank Fusion.
        """
        
        # 1. Gather results from all retrievers
        all_results = []
        for retriever in self.retrievers:
            try:
                # Use invoke if available, else get_relevant_documents
                if hasattr(retriever, "invoke"):
                    docs = retriever.invoke(query)
                else:
                    docs = retriever.get_relevant_documents(query)
                all_results.append(docs)
            except Exception as e:
                print(f"⚠️ Retriever error in Ensemble: {e}")
                all_results.append([])

        # 2. RRF (Reciprocal Rank Fusion) Scoring
        # Score = sum(weight * (1 / (rank + k)))
        rrf_score = defaultdict(float)
        k = 60
        
        for i, docs in enumerate(all_results):
            weight = self.weights[i] if i < len(self.weights) else 1.0
            for rank, doc in enumerate(docs):
                # Key validation: Use page_content as unique key
                # (Assuming strictly identical content means identical doc for ranking purposes)
                doc_key = doc.page_content
                score = weight * (1 / (rank + k))
                rrf_score[doc_key] += score

        # 3. Deduplicate and Sort
        # We need to map content back to the Document object (first occurrence wins metadata)
        unique_docs = {}
        for docs in all_results:
            for doc in docs:
                if doc.page_content not in unique_docs:
                    unique_docs[doc.page_content] = doc
        
        # Sort distinct documents by their RRF score
        sorted_docs = sorted(
            unique_docs.values(),
            key=lambda d: rrf_score[d.page_content],
            reverse=True
        )
        
        # Return top K (hardcoded max or implicit)
        # We'll return all ranked docs; usually downstream restricts K
        return sorted_docs
