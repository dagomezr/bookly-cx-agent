import os
import json
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SYSTEM_PROMPT = """You are a friendly and professional customer support agent for Bookly, an online bookstore.

You help customers with:
- Order status inquiries
- Return and refund requests
- General questions about shipping, policies, and account issues

Guidelines:
- Always greet the customer warmly and be empathetic.
- Before looking up an order, always ask for the order ID if not provided.
- Before initiating a return, confirm the order ID and the reason for the return.
- If a question is outside your scope (e.g. product recommendations, complaints about authors), politely let the customer know you can only assist with support topics.
- Never invent order details, return statuses, or policies. Only share information returned by your tools or that you know with certainty.
- If unsure, ask a clarifying question rather than guessing.
"""

MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "tools.py")


async def get_mcp_tools(session: ClientSession) -> list:
    """Fetch available tools from the MCP server and format them for Claude."""
    tools_result = await session.list_tools()
    tools = []
    for tool in tools_result.tools:
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        })
    return tools


async def call_mcp_tool(session: ClientSession, tool_name: str, tool_input: dict) -> str:
    """Call a tool on the MCP server and return the result as a string."""
    result = await session.call_tool(tool_name, tool_input)
    return result.content[0].text if result.content else "No result returned."


async def chat(user_message: str, history: list) -> str:
    """
    Main agent loop:
    1. Send message + history to Claude
    2. If Claude wants to use a tool, call the MCP server and feed result back
    3. Repeat until Claude returns a final text response
    """
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    server_params = StdioServerParameters(
        command="python",
        args=[MCP_SERVER_SCRIPT]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await get_mcp_tools(session)

            # Build message list for this turn
            messages = history + [{"role": "user", "content": user_message}]

            # Agentic loop
            while True:
                response = await client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages
                )

                # If Claude is done, return the final text response
                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text"):
                            return block.text
                    return "I'm sorry, I wasn't able to generate a response."

                # If Claude wants to use a tool
                if response.stop_reason == "tool_use":
                    # Append Claude's response to messages
                    messages.append({"role": "assistant", "content": response.content})

                    # Process all tool calls in this response
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_result = await call_mcp_tool(session, block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_result
                            })

                    # Feed tool results back to Claude
                    messages.append({"role": "user", "content": tool_results})

                else:
                    # Unexpected stop reason
                    return "Something went wrong. Please try again."