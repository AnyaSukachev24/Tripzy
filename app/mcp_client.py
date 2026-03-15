
import asyncio
import json
import logging
import os
import httpx
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class KiwiMCPClient:
    def __init__(self):
        self.base_url_candidates = ["https://mcp.kiwi.com/sse", "https://mcp.kiwi.com"]
        self.rpc_endpoint: Optional[str] = None
        self.session_id: Optional[str] = None
        self.client = httpx.AsyncClient(timeout=60.0)
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.request_counter = 0
        self.sse_task: Optional[asyncio.Task] = None
        self.connected_event = asyncio.Event()
        self._shutdown = False

    async def connect(self):
        """Establishes SSE connection and discovers RPC endpoint."""
        if self.sse_task and not self.sse_task.done():
            return  # Already connected

        # Try candidates
        for url in self.base_url_candidates:
            try:
                # We need to start the listener loop
                self.sse_task = asyncio.create_task(self._sse_loop(url))
                # Wait for connection confirmation (endpoint received)
                try:
                    await asyncio.wait_for(self.connected_event.wait(), timeout=10.0)
                    logger.info(f"Connected to Kiwi MCP at {url}")
                    return
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for endpoint from {url}, trying next...")
                    if self.sse_task:
                        self.sse_task.cancel()
                        self.sse_task = None
            except Exception as e:
                logger.error(f"Failed to connect to {url}: {e}")
        
        logger.error("Could not connect to any Kiwi MCP endpoint.")

    async def _sse_loop(self, url: str):
        """Background loop to read SSE events."""
        headers = {
            "User-Agent": "Tripzy/1.0",
            "Accept": "text/event-stream"
        }
        retry_delay = 1.0
        
        while not self._shutdown:
            try:
                async with self.client.stream("GET", url, headers=headers, timeout=None) as response:
                    if response.status_code != 200:
                        logger.error(f"SSE Error Status: {response.status_code}")
                        await asyncio.sleep(retry_delay)
                        continue
                        
                    async for line in response.aiter_lines():
                        if not line or self._shutdown: 
                            continue
                        
                        if line.startswith("event: endpoint"):
                            pass
                        elif line.startswith("data: "):
                            data = line[len("data: "):].strip()
                            
                            # Endpoint Discovery
                            if (data.startswith("/") or data.startswith("http")) and not self.rpc_endpoint:
                                if data.startswith("/"):
                                    self.rpc_endpoint = f"https://mcp.kiwi.com{data}"
                                else:
                                    self.rpc_endpoint = data
                                
                                # Extract Session ID if present
                                if "sessionId=" in self.rpc_endpoint:
                                    self.session_id = self.rpc_endpoint.split("sessionId=")[1]
                                
                                logger.info(f"Discovered RPC Endpoint: {self.rpc_endpoint}")
                                self.connected_event.set()
                            
                            # JSON-RPC Handling
                            elif data.startswith("{"):
                                try:
                                    msg = json.loads(data)
                                    self._handle_rpc_message(msg)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                logger.error(f"SSE Loop Error: {e}")
                await asyncio.sleep(retry_delay)

    def _handle_rpc_message(self, msg: Dict[str, Any]):
        """Resolves pending futures based on RPC response."""
        msg_id = msg.get("id")
        if msg_id in self.pending_requests:
            future = self.pending_requests.pop(msg_id)
            if not future.done():
                if "error" in msg:
                    future.set_exception(Exception(f"RPC Error: {msg['error']}"))
                else:
                    future.set_result(msg.get("result"))

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a tool on the MCP server."""
        if not self.rpc_endpoint:
            await self.connect()
            if not self.rpc_endpoint:
                raise Exception("Not connected to Kiwi MCP")

        self.request_counter += 1
        req_id = self.request_counter
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[req_id] = future

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            logger.info(f"Sending RPC {req_id}: {tool_name}")
            resp = await self.client.post(self.rpc_endpoint, json=request)
            if resp.status_code not in [200, 202]:
                 raise Exception(f"HTTP Error {resp.status_code}: {resp.text}")
            
            # Wait for response via SSE
            result = await asyncio.wait_for(future, timeout=60.0)
            return result
        except TimeoutError:
            if req_id in self.pending_requests:
                del self.pending_requests[req_id]
            raise Exception("Timeout waiting for tool response")
        except Exception as e:
            if req_id in self.pending_requests:
                del self.pending_requests[req_id]
            raise e

    async def cleanup(self):
        """Closes connections."""
        self._shutdown = True
        if self.sse_task:
            self.sse_task.cancel()
        await self.client.aclose()

    def call_tool_sync(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper that manages a full lifecycle in a new event loop."""
        async def _run():
            try:
                await self.connect()
                return await self.call_tool(tool_name, arguments)
            finally:
                await self.cleanup()
        
        return asyncio.run(_run())


# Singleton Instance (for Async apps)
_kiwi_client_instance = None

def get_kiwi_client():
    global _kiwi_client_instance
    if not _kiwi_client_instance:
        _kiwi_client_instance = KiwiMCPClient()
    return _kiwi_client_instance
