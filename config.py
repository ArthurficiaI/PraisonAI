config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": ".praison"
        }
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.2",
            "temperature": 0,
            "max_tokens": 8000,
            "base_url": "http://localhost:11434"
        }
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text",  # Use an actual embedding model available in Ollama
            "base_url": "http://localhost:11434",
            "embedding_dimensions": 1024
        }
    }
}