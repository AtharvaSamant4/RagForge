import json
from .embeddings import model, profile, runtime_stats, semantic_embed

if __name__ == "__main__":
    model()
    vectors = semantic_embed(["Customers can return an order.", "A shopper may send a purchase back."])
    print(json.dumps({"profile": profile(), "runtime": runtime_stats(), "dimensions": len(vectors[0]), "paraphrase_similarity": sum(a*b for a,b in zip(*vectors))}, indent=2))
