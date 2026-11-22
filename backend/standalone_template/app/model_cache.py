"""Prefetch using this generated manifest's provider and cache configuration."""
import json
from . import bootstrap
from .engine.config import settings
from .embeddings import model, profile, runtime_stats

if __name__=='__main__':
    if settings().embedding_provider=='semantic':model()
    print(json.dumps({'profile':profile(),'runtime':runtime_stats()},indent=2))
