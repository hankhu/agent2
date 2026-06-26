"""Example 04: Memory — working memory and long-term memory.

Demonstrates:
- WorkingMemory for conversation history management
- LongTermMemory for semantic search (TF-IDF based)
- Integrating memory with agents

Usage:
    uv run examples/04_memory.py
"""

import asyncio

from agent2.memory import WorkingMemory, LongTermMemory
from agent2.llm.message import Message


async def demo_working_memory():
    """Demonstrate working memory (conversation history)."""
    print("=" * 60)
    print("Working Memory Demo")
    print("=" * 60)

    memory = WorkingMemory(max_messages=10)

    # Simulate a conversation
    await memory.add("What is machine learning?", role="user")
    await memory.add(
        "Machine learning is a subset of AI that enables systems to learn from data.",
        role="assistant",
    )
    await memory.add("What are the main types?", role="user")
    await memory.add(
        "The main types are: supervised learning, unsupervised learning, "
        "and reinforcement learning.",
        role="assistant",
    )

    # Search memory
    results = await memory.search("types of learning")
    print(f"\nSearch for 'types of learning': {len(results)} results")
    for r in results:
        print(f"  [{r.score:.2f}] {r.content[:80]}...")

    # Get messages ready for LLM
    messages = memory.get_messages_for_llm("You are a helpful AI.")
    print(f"\nMessages for LLM: {len(messages)} messages")
    for m in messages:
        print(f"  [{m.role.value}] {(m.content or '')[:60]}...")


async def demo_long_term_memory():
    """Demonstrate long-term memory (semantic search)."""
    print("\n" + "=" * 60)
    print("Long-Term Memory Demo")
    print("=" * 60)

    memory = LongTermMemory(embedding_provider="tfidf")

    # Store some knowledge
    facts = [
        "Python is a high-level programming language created by Guido van Rossum.",
        "Rust is a systems programming language focused on safety and performance.",
        "JavaScript is primarily used for web development in browsers.",
        "Machine learning uses algorithms to learn patterns from data.",
        "Docker is a platform for containerizing applications.",
        "Kubernetes orchestrates container deployment at scale.",
        "PostgreSQL is a powerful open-source relational database.",
        "Redis is an in-memory data store used for caching.",
    ]

    print("\nStoring facts...")
    for fact in facts:
        await memory.add(fact)
    print(f"Stored {memory.size} items")

    # Search for related information
    queries = [
        "programming language for web",
        "database systems",
        "container orchestration",
    ]

    for query in queries:
        print(f"\n🔍 Search: '{query}'")
        results = await memory.search(query, top_k=3)
        for r in results:
            print(f"  [{r.score:.3f}] {r.content}")

    # Get formatted context for prompt injection
    context = await memory.get_context("What language should I use for AI?")
    print(f"\n📋 Context for RAG:\n{context}")


async def main():
    await demo_working_memory()
    await demo_long_term_memory()


if __name__ == "__main__":
    asyncio.run(main())
