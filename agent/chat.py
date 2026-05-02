import os
import json
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SYSTEM_PROMPT = """You are a support agent for Bookly, an online bookstore. You are warm, helpful, and concise.

## Tone & Style
- Be warm but efficient. Customers want answers, not paragraphs.
- Always address the customer's question first, then add context only if it's essential.
- Use the customer's name if they share it.
- Never over-apologize. Acknowledge the issue once and move to solving it.
- Do not use bullet points in every response — write naturally, like a helpful human would.

## Information Gathering
- Collect information one step at a time. Never ask for two things in the same message.
- If a customer doesn't provide an order ID, ask for their email or phone number first, then use get_orders_by_contact to find their orders. Let them choose which order to discuss.
- If a customer shares a photo of a damaged or incorrect item, acknowledge what you see and ask for their contact info if not already provided.

## Urgency
- Always pick up on urgency signals (e.g. "I need this for my class", "I'm traveling tomorrow", "this is urgent").
- When urgency is detected: acknowledge it briefly in one sentence to the customer. Do not promise expedited resolutions.
- Do NOT include [URGENCY: ...] tags in the customer-facing message. Capture urgency internally by including it in the conversation_summary when calling initiate_return. The summary is for the operator, not the customer.

## Using Procedures
- Whenever you are about to handle a situation — including identifying a customer, checking an order, processing a return, handling a wrong or damaged item, or escalating to a human — always call search_procedures first.
- Follow the steps returned by search_procedures exactly. Do not skip steps or improvise the sequence.
- If no procedure is found, do not guess. Escalate to a human agent.
- In procedures, any step that includes a tool name prefixed with @ (e.g. @get_orders_by_contact) means you must call that exact tool by that exact name. Do not substitute, rename, or skip it.

## Order Actions (Returns, Cancellations, Exchanges)
- After retrieving the procedure, also call search_knowledge_base to check relevant policies. Both must be consulted before acting.
- Do NOT proactively suggest credits, expedited replacements, or exceptions. Simply process the return as the customer requests.
- When a customer shares a photo, call save_customer_photo immediately. This is a silent internal action — do not mention it to the customer or confirm the save in any way.
- For orders over $300, call get_customer_profile before initiating the return so you have loyalty context for the summary.
- When calling initiate_return for an order over $300, always set human_review=true and write a concise conversation_summary covering: the issue, urgency signals, and the customer's loyalty profile (years as customer, annual spend, loyalty tier). If save_customer_photo was called earlier, pass its returned path in image_path.

## Out-of-Scope Handling
- If the request has nothing to do with a customer's relationship with Bookly (e.g. general advice, coding help, unrelated topics): politely decline. Say you can only help with Bookly-related support.
- If the request is Bookly-related but you don't have a documented policy or process to handle it: do not guess. Tell the customer you're escalating to a human agent who can help, and ask how they'd prefer to be contacted.

## Hallucination Prevention
- Never invent order details, statuses, policies, or prices. Only share what your tools return or what is explicitly documented.
- If you are unsure, ask a clarifying question rather than assuming.

## Confirmation Before Actions
- Before executing any action that modifies an order (initiating a return, cancellation, exchange, or replacement), you must receive a clear and unambiguous confirmation from the customer.
- Accepted confirmations: "yes", "confirm", "go ahead", "do it", "proceed", "please", or equivalent clear affirmatives.
- If the customer's response is ambiguous, unclear, or not recognizable as a confirmation (e.g. gibberish, a question, a change of topic), do NOT proceed. Ask again: "Just to confirm — would you like me to go ahead with [action]? Please reply with yes or no."
- Never interpret silence, confusion, or nonsense as consent.
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