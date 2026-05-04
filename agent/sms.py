import os
from typing import Optional
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "tools.py")


def build_sms_system_prompt(task: dict, memory: dict) -> str:
    procedure_section = (
        f"## Specialist-Approved Resolution\n{task['procedure']}"
        if task.get("procedure")
        else "## Specialist-Approved Resolution\nStandard return policy applies — a full refund will be processed within 5–7 business days of receiving the returned item."
    )

    memory_section = (
        f"## Previous Conversation Summary\n{memory.get('summary', '')}"
        if memory.get("summary")
        else ""
    )

    loyalty_note = ""
    if memory:
        tier = memory.get("loyalty_tier", "")
        spend = memory.get("annual_spend", "")
        since = memory.get("customer_since", "")
        if tier or spend:
            loyalty_note = f"\n## Customer Profile\n- Loyalty tier: {tier}\n- Annual spend: {spend}\n- Customer since: {since}"

    return f"""You are a Bookly support specialist following up with a customer about their return case.

## Your Role
You are initiating this conversation — the customer did not reach out to you. This is a continuation of a support case they already opened. Be warm, direct, and make them feel like you already know their situation — because you do.

## Case Summary
{task.get('summary', 'Customer submitted a return request that has been reviewed by a specialist.')}

{procedure_section}
{memory_section}
{loyalty_note}

## Rules
- Open naturally by referencing the case — never make the customer re-explain what happened.
- Do not mention "AI", "bot", "automated message", or "automated system" at any point.
- This is an SMS thread — keep responses short and conversational. No bullet points, no markdown.
- If the customer has questions you can't answer, tell them a specialist will follow up.
- Once the customer is satisfied, close warmly and let them know they can always reply to this thread if anything else comes up.
"""


async def sms_chat(user_message: Optional[str], history: list, task: dict, memory: dict) -> str:
    """
    SMS agent loop. Same MCP agentic loop as chat.py but with a context-rich
    system prompt built from the approved task and customer memory.

    Pass user_message=None to generate the opening proactive message.
    """
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system_prompt = build_sms_system_prompt(task, memory)

    server_params = StdioServerParameters(
        command="python",
        args=[MCP_SERVER_SCRIPT]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema
                }
                for t in tools_result.tools
            ]

            if user_message is None:
                # Generate opening proactive message — no user turn yet
                messages = [
                    {
                        "role": "user",
                        "content": "[System: Initiate the proactive follow-up message now. Do not wait for the customer to speak first.]"
                    }
                ]
            else:
                messages = history + [{"role": "user", "content": user_message}]

            while True:
                response = await client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=512,
                    system=system_prompt,
                    tools=tools,
                    messages=messages
                )

                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text"):
                            return block.text
                    return "I'll be right with you."

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            result = await session.call_tool(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result.content[0].text if result.content else ""
                            })
                    messages.append({"role": "user", "content": tool_results})
                else:
                    return "Something went wrong. Please try again."