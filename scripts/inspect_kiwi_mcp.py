import asyncio
import json
import httpx
import os
from dotenv import load_dotenv

import sys
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# We will try both endpoints
URLS_TO_TRY = ["https://mcp.kiwi.com/sse", "https://mcp.kiwi.com"]

async def inspect_mcp():
    print(f"Connecting to Kiwi MCP...")
    
    headers = {
        "User-Agent": "Tripzy/1.0",
        "Accept": "text/event-stream"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in URLS_TO_TRY:
            print(f"Trying {url}...")
            try:
                # 1. Connect to SSE
                async with client.stream("GET", url, headers=headers, timeout=None) as response:
                    print(f"Status: {response.status_code}")
                    if response.status_code != 200:
                        continue
                    
                    print(f"Connected to SSE at {url}")
                    
                    # Store session ID / endpoint
                    post_endpoint = None
                    
                    async def send_rpc(endpoint):
                        # Wait a bit to ensure SSE is fully ready
                        await asyncio.sleep(1)
                        print(f"Sending tools/list to {endpoint}...")
                        rpc_request = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/list",
                            "params": {}
                        }
                        try:
                            r = await client.post(endpoint, json=rpc_request)
                            print(f"POST Status: {r.status_code}")
                            if r.status_code != 202:
                                print(f"POST Response: {r.text}")
                        except Exception as e:
                            print(f"POST Error: {e}")

                    # Read SSE stream
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        if line.startswith("event: endpoint"):
                            pass
                        elif line.startswith("data: "):
                            data = line[len("data: "):].strip()
                            
                            # Check if it's the endpoint (URL)
                            if (data.startswith("/") or data.startswith("http")) and not post_endpoint:
                                print(f"Received Endpoint: {data}")
                                post_endpoint = data
                                if post_endpoint.startswith("/"):
                                    base_url = "https://mcp.kiwi.com"
                                    final_endpoint = f"{base_url}{post_endpoint}"
                                else:
                                    final_endpoint = post_endpoint
                                
                                # Launch the POST request as a background task
                                asyncio.create_task(send_rpc(final_endpoint))
                            
                            # Check if it's a JSON-RPC message (response)
                            elif data.startswith("{"):
                                try:
                                    msg = json.loads(data)
                                    # print(f"\nReceived JSON-RPC Message: {json.dumps(msg, indent=2)}")
                                    
                                    # If it's the result of our call
                                    if msg.get("id") == 1 and "result" in msg:
                                        tools = msg["result"].get("tools", [])
                                        print(f"\nFound {len(tools)} tools:")
                                        for tool in tools:
                                            print(f"- {tool['name']}: {tool.get('description', 'No description')}")
                                            input_schema = tool.get('inputSchema', {})
                                            print(f"  Schema: {json.dumps(input_schema, indent=2)}")
                                        
                                        # We are done
                                        return
                                except json.JSONDecodeError:
                                    print(f"Received non-JSON data: {data}")
            except Exception as e:
                print(f"Error connecting to {url}: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_mcp())
