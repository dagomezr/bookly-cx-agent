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
- If a customer does not provide an order ID, ask for their email or phone number and use get_orders_by_contact to find their recent orders. Let them choose which order they need help with.
- Any time a customer wants to change the status of an order (return, cancel, exchange), always call search_knowledge_base first to check relevant policies before taking any action.
- Based on what the knowledge base returns, offer the customer the best available alternative (e.g. Bookly Credits) before proceeding. Explain the benefit clearly.
- If the customer still prefers a refund after being offered credits, respect their decision and proceed with initiate_return without further pushback.
- If a customer shares a photo (e.g. of a damaged or incorrect item), acknowledge what you can see in the image and use it to inform your response. Ask for their order ID or contact info if not already provided.
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


async def chat(user_message: str, history: list, image: dict = None) -> str:
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

            # Build the current user message content
            # If an image is attached, send it as a multimodal content block
            if image:
                user_content = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image["media_type"],
                            "data": image["base64"]
                        }
                    },
                    {
                        "type": "text",
                        "text": user_message or "Here is a photo of my issue."
                    }
                ]
            else:
                user_content = user_message

            # Build message list for this turn
            messages = history + [{"role": "user", "content": user_content}]

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