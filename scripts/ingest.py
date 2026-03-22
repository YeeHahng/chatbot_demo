#!/usr/bin/env python3
"""
One-time script to chunk and embed narrative documents into ChromaDB.
Run from project root: python scripts/ingest.py
"""
import sys
from pathlib import Path

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from sentence_transformers import SentenceTransformer
from app.config import settings


def main():
    """Load documents, chunk them, embed, and store in ChromaDB."""
    # Step 1: Load embedding model
    print("Loading embedding model...")
    model = SentenceTransformer(settings.embedding_model)

    # Step 2: Create persistent ChromaDB client
    client = chromadb.PersistentClient(path=settings.chroma_path)

    # Step 3: Delete existing collection if it exists, then create fresh
    try:
        client.delete_collection("documents")
        print("Deleted existing collection")
    except Exception:
        pass  # Collection doesn't exist, that's fine

    collection = client.create_collection("documents")
    print("Created fresh collection")

    # Step 4: Read all .txt files from data/documents/
    project_root = Path(__file__).parent.parent
    documents_dir = project_root / "data" / "documents"

    all_chunks = []
    chunk_metadata = []
    file_chunk_counts = {}

    for doc_file in sorted(documents_dir.glob("*.txt")):
        # Skip .gitkeep
        if doc_file.name == ".gitkeep":
            continue

        doc_type = doc_file.stem  # filename without extension
        print(f"\nProcessing {doc_file.name}...")

        # Read file content
        with open(doc_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Step 5: Split by paragraph chunks and filter
        paragraphs = content.split("\n\n")
        filtered_paragraphs = [p.strip() for p in paragraphs if len(p.strip()) >= 30]

        # Build overlapping chunks using a look-back sliding window
        overlap = settings.chunk_overlap
        file_chunks = []
        if overlap == 0:
            file_chunks = filtered_paragraphs
        else:
            for i in range(len(filtered_paragraphs)):
                start = max(0, i - overlap)
                combined = "\n\n".join(filtered_paragraphs[start : i + 1])
                file_chunks.append(combined)

        # Store chunks and metadata for this file
        chunk_index = 0
        for chunk in file_chunks:
            all_chunks.append(chunk)
            chunk_metadata.append({
                "id": f"{doc_type}_{chunk_index}",
                "doc_type": doc_type,
                "chunk_index": chunk_index,
                "building_id": "general",
                "overlap": overlap,
            })
            chunk_index += 1

        file_chunk_counts[doc_type] = len(file_chunks)
        print(f"  Extracted {len(file_chunks)} chunks")

    # Step 6: Embed all chunks at once in a batch
    print(f"\nEmbedding {len(all_chunks)} total chunks...")
    embeddings = model.encode(all_chunks, show_progress_bar=True).tolist()

    # Step 7: Add to collection
    print("Adding chunks to ChromaDB collection...")
    ids = [meta["id"] for meta in chunk_metadata]
    documents = all_chunks
    metadatas = [
        {
            "building_id": meta["building_id"],
            "doc_type": meta["doc_type"],
            "chunk_index": meta["chunk_index"]
        }
        for meta in chunk_metadata
    ]

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    # Step 8: Print summary
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    for doc_type, count in sorted(file_chunk_counts.items()):
        print(f"{doc_type}: {count} chunks")
    print(f"Total: {len(all_chunks)} chunks embedded")
    print("=" * 60)


if __name__ == "__main__":
    main()
