#!/usr/bin/env python3
"""Quick profiling script to measure startup time of agent2 TUI."""

import time
import sys

def main():
    print("Starting profiling...")
    
    # Phase 1: Import time
    start = time.time()
    import agent2
    import_time = time.time() - start
    print(f"Phase 1 - Import agent2: {import_time:.3f}s")
    
    # Phase 2: Load config
    start = time.time()
    from agent2.app.config import load_config, get_last_model
    config = load_config()
    config_time = time.time() - start
    print(f"Phase 2 - Load config: {config_time:.3f}s")
    print(f"  Default model: {config.default}")
    
    # Phase 3: Create LLM
    start = time.time()
    from agent2.llm import create_llm
    model = get_last_model() or config.default
    print(f"  Using model: {model}")
    llm = create_llm(model)
    llm_time = time.time() - start
    print(f"Phase 3 - Create LLM: {llm_time:.3f}s")
    
    # Phase 4: Load context (rules + skills)
    start = time.time()
    from agent2.context import load_context
    ctx = load_context()
    context_time = time.time() - start
    print(f"Phase 4 - Load context: {context_time:.3f}s")
    print(f"  Rules text length: {len(ctx.rules_text)} chars")
    print(f"  Skills count: {len(ctx.skills)}")
    
    # Phase 5: MCP initialization (if configured)
    start = time.time()
    mcp_time = 0
    if config.mcp_servers:
        print(f"  MCP servers configured: {list(config.mcp_servers.keys())}")
        try:
            from agent2.mcp import MCPManager, MCPServerConfig
            import asyncio
            import concurrent.futures
            
            servers = {
                k: MCPServerConfig.model_validate(v)
                for k, v in config.mcp_servers.items()
            }
            manager = MCPManager(servers)
            
            async def init_mcp():
                discovered = await manager.connect()
                await manager.close(keep_tools=True)
                return discovered
            
            # Run MCP initialization
            try:
                asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    mcp_tools = pool.submit(lambda: asyncio.run(init_mcp())).result()
            except RuntimeError:
                mcp_tools = asyncio.run(init_mcp())
            
            mcp_time = time.time() - start
            print(f"Phase 5 - MCP initialization: {mcp_time:.3f}s")
            print(f"  MCP tools discovered: {len(mcp_tools)}")
        except Exception as e:
            mcp_time = time.time() - start
            print(f"Phase 5 - MCP initialization failed: {mcp_time:.3f}s")
            print(f"  Error: {e}")
    else:
        print("Phase 5 - No MCP servers configured")
    
    # Total time
    total_time = import_time + config_time + llm_time + context_time + mcp_time
    print(f"\nTotal estimated startup time: {total_time:.3f}s")
    print(f"  Import: {import_time:.3f}s ({import_time/total_time*100:.1f}%)")
    print(f"  Config: {config_time:.3f}s ({config_time/total_time*100:.1f}%)")
    print(f"  LLM: {llm_time:.3f}s ({llm_time/total_time*100:.1f}%)")
    print(f"  Context: {context_time:.3f}s ({context_time/total_time*100:.1f}%)")
    print(f"  MCP: {mcp_time:.3f}s ({mcp_time/total_time*100:.1f}%)")

if __name__ == "__main__":
    main()