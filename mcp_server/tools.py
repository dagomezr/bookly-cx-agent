import asyncio
import json
import os
from datetime import datetime, timezone
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("bookly-mcp-server")

TASKS_PATH = os.path.join(os.path.dirname(__file__), "..", "tasks.json")


def load_tasks() -> list:
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, "r") as f:
        return json.load(f)


def save_tasks(tasks: list):
    with open(TASKS_PATH, "w") as f:
        json.dump(tasks, f, indent=2)

# --- Load Knowledge Base ---

KB_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.md")
with open(KB_PATH, "r") as f:
    raw_kb = f.read()

KNOWLEDGE_BASE = []
for section in raw_kb.split("\n## "):
    if section.startswith("# "):
        continue
    lines = section.strip().split("\n", 1)
    if len(lines) == 2:
        title, content = lines
        KNOWLEDGE_BASE.append({
            "title": title.strip("# ").strip(),
            "content": content.strip()
        })

# --- Load Procedures ---

PROC_PATH = os.path.join(os.path.dirname(__file__), "procedures.md")
with open(PROC_PATH, "r") as f:
    raw_proc = f.read()

PROCEDURES = []
for section in raw_proc.split("\n## "):
    if section.startswith("# "):
        continue
    lines = section.strip().split("\n", 1)
    if len(lines) == 2:
        title, content = lines
        PROCEDURES.append({
            "title": title.strip("# ").strip(),
            "content": content.strip()
        })

# --- Mock Data ---

MOCK_ORDERS = {
    "test@example.com": [
        {"order_id": "BK-1001", "title": "The Pragmatic Programmer", "date": "2026-04-10", "total": "$45.99"},
        {"order_id": "BK-1002", "title": "Clean Code", "date": "2026-04-18", "total": "$32.50"},
        {"order_id": "BK-1003", "title": "2 Scientific Books (Introduction to Algorithms + The Art of Computer Programming)", "date": "2026-04-25", "total": "$389.95"},
    ],
    "5551234567": [
        {"order_id": "BK-2001", "title": "Atomic Habits", "date": "2026-04-15", "total": "$27.99"},
        {"order_id": "BK-2002", "title": "Deep Work", "date": "2026-04-28", "total": "$24.99"},
        {"order_id": "BK-1003", "title": "2 Scientific Books (Introduction to Algorithms + The Art of Computer Programming)", "date": "2026-04-25", "total": "$389.95"},
    ],
}

MOCK_ORDER_STATUS = {
    "BK-1001": {"status": "Delivered", "delivered_on": "2026-04-13", "carrier": "UPS"},
    "BK-1002": {"status": "In Transit", "estimated_delivery": "2026-05-02", "carrier": "FedEx"},
    "BK-1003": {"status": "Delivered", "delivered_on": "2026-04-28", "carrier": "UPS", "note": "2 items delivered."},
    "BK-2001": {"status": "Delivered", "delivered_on": "2026-04-19", "carrier": "USPS"},
    "BK-2002": {"status": "Processing", "note": "Order is being prepared for shipment."},
}

RETURN_COUNTER = {"count": 100}

CUSTOMER_PROFILES = {
    "test@example.com": {
        "customer_since": "March 2021",
        "years_as_customer": 5,
        "annual_spend": "$1,240",
        "loyalty_club": True,
        "loyalty_tier": "Gold"
    },
    "5551234567": {
        "customer_since": "March 2021",
        "years_as_customer": 5,
        "annual_spend": "$1,240",
        "loyalty_club": True,
        "loyalty_tier": "Gold"
    },
}


# --- Tool Definitions ---

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_orders_by_contact",
            description=(
                "Look up a customer's recent orders (last 30 days) using their email address or phone number. "
                "Use this when the customer does not know their order ID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact": {
                        "type": "string",
                        "description": "The customer's email address or phone number."
                    }
                },
                "required": ["contact"]
            }
        ),
        types.Tool(
            name="get_order_status",
            description="Get the current status of a specific order by order ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The Bookly order ID (e.g. BK-1001)."
                    }
                },
                "required": ["order_id"]
            }
        ),
        types.Tool(
            name="save_customer_photo",
            description=(
                "Internal action — saves the photo the customer shared for this support case. "
                "Call this silently as soon as the customer provides a photo. "
                "Do NOT announce this to the customer or mention it in any way. "
                "Returns the local file path to pass to initiate_return."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_customer_profile",
            description=(
                "Look up a customer's loyalty and purchase history: how long they've been a customer, "
                "annual spend, and whether they are a loyalty club member. "
                "Call this before initiating a return that requires human review, "
                "so the operator has full context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact": {
                        "type": "string",
                        "description": "The customer's email address or phone number."
                    }
                },
                "required": ["contact"]
            }
        ),
        types.Tool(
            name="initiate_return",
            description=(
                "Initiate a return or refund request for a specific order. "
                "Set human_review=true for orders over $300 — this flags the case for operator review. "
                "Include a conversation_summary when human_review is true: 1–3 sentences covering the issue, "
                "urgency signals, and any customer context. "
                "Pass image_path if save_customer_photo was called earlier in this conversation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The Bookly order ID to return."
                    },
                    "reason": {
                        "type": "string",
                        "description": "The reason the customer wants to return the order."
                    },
                    "human_review": {
                        "type": "boolean",
                        "description": "Set to true for orders over $300. Creates a task in the operator inbox for manual review."
                    },
                    "conversation_summary": {
                        "type": "string",
                        "description": "A 1–3 sentence summary of the conversation: issue, urgency, and customer context. Required when human_review is true."
                    },
                    "image_path": {
                        "type": "string",
                        "description": "The file path returned by save_customer_photo, if a photo was saved in this conversation."
                    }
                },
                "required": ["order_id", "reason"]
            }
        ),
        types.Tool(
            name="search_procedures",
            description=(
                "Search Bookly's internal step-by-step procedure library. "
                "Use this to look up how to handle a specific situation — e.g. how to process a return, "
                "how to identify a customer, how to escalate to a human agent. "
                "Call this before taking any multi-step action to ensure you follow the correct process."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The situation or action to look up (e.g. 'return request', 'wrong item received', 'escalate to human')."
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="search_knowledge_base",
            description=(
                "Search Bookly's internal policy knowledge base for information about returns, refunds, "
                "store credits, shipping, damaged items, and account policies. "
                "Use this before answering policy questions or before initiating a return, "
                "to check if Bookly Credits should be offered as an alternative."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic or question to search for in the knowledge base (e.g. 'return policy', 'store credits', 'refund timeline')."
                    }
                },
                "required": ["query"]
            }
        ),
    ]


# --- Tool Handlers ---

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "get_orders_by_contact":
        contact = arguments.get("contact", "").strip().lower()
        # Normalize phone: strip non-digits for lookup
        normalized = ''.join(filter(str.isdigit, contact)) if not '@' in contact else contact
        orders = MOCK_ORDERS.get(contact) or MOCK_ORDERS.get(normalized)

        if not orders:
            result = {
                "found": False,
                "message": "No orders found for the provided contact in the last 30 days."
            }
        else:
            result = {
                "found": True,
                "orders": orders
            }
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "get_customer_profile":
        contact = arguments.get("contact", "").strip().lower()
        normalized = ''.join(filter(str.isdigit, contact)) if '@' not in contact else contact
        profile = CUSTOMER_PROFILES.get(contact) or CUSTOMER_PROFILES.get(normalized)

        if not profile:
            result = {"found": False, "message": "No profile found for this contact."}
        else:
            result = {"found": True, **profile}
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "get_order_status":
        order_id = arguments.get("order_id", "").strip().upper()
        status = MOCK_ORDER_STATUS.get(order_id)

        if not status:
            result = {
                "found": False,
                "message": f"No order found with ID {order_id}."
            }
        else:
            result = {
                "found": True,
                "order_id": order_id,
                **status
            }
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "save_customer_photo":
        images_dir = os.path.join(os.path.dirname(__file__), "..", "images")
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = os.path.join(images_dir, f"pending.{ext}")
            if os.path.exists(candidate):
                result = {"saved": True, "path": f"pending.{ext}"}
                return [types.TextContent(type="text", text=json.dumps(result))]
        result = {"saved": False, "message": "No photo found. Ask the customer to share one first."}
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "initiate_return":
        order_id = arguments.get("order_id", "").strip().upper()
        reason = arguments.get("reason", "")
        human_review = arguments.get("human_review", False)
        conversation_summary = arguments.get("conversation_summary", "")
        image_path = arguments.get("image_path", None)

        RETURN_COUNTER["count"] += 1
        ticket_id = f"RT-{RETURN_COUNTER['count']}"

        if human_review:
            # Find the saved photo directly from disk — don't rely on the agent passing the path correctly
            images_dir = os.path.join(os.path.dirname(__file__), "..", "images")
            image_filename = None
            for ext in ("jpg", "jpeg", "png", "webp"):
                if os.path.exists(os.path.join(images_dir, f"pending.{ext}")):
                    image_filename = f"pending.{ext}"
                    break

            tasks = load_tasks()
            tasks.append({
                "ticket_id": ticket_id,
                "order_id": order_id,
                "reason": reason,
                "summary": conversation_summary,
                "image_filename": image_filename,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "procedure": None
            })
            save_tasks(tasks)

        result = {
            "success": True,
            "return_ticket_id": ticket_id,
            "order_id": order_id,
            "reason": reason,
            "human_review": human_review,
            "message": (
                f"Your return request for order {order_id} has been submitted. "
                f"Your return ticket ID is {ticket_id}. "
                + (
                    "Due to the order amount, a specialist will review this case shortly and reach out to you with next steps."
                    if human_review else
                    "You will receive a prepaid shipping label via email within 24 hours. "
                    "Refunds are processed within 5-7 business days after we receive the item."
                )
            )
        }
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "search_procedures":
        query = arguments.get("query", "").lower()
        query_words = set(query.split())

        matches = []
        for entry in PROCEDURES:
            title_hits = sum(1 for word in query_words if word in entry["title"].lower()) * 3
            content_hits = sum(1 for word in query_words if word in entry["content"].lower())
            score = title_hits + content_hits
            if score > 0:
                matches.append((score, entry))

        matches.sort(key=lambda x: x[0], reverse=True)
        top_matches = [
            f"**{entry['title']}**\n{entry['content']}"
            for _, entry in matches[:2]
        ]

        if top_matches:
            result = {"found": True, "results": top_matches}
        else:
            result = {"found": False, "message": "No procedure found for that query."}
        return [types.TextContent(type="text", text=json.dumps(result))]

    elif name == "search_knowledge_base":
        query = arguments.get("query", "").lower()
        query_words = set(query.split())

        # Simple keyword matching against title + content — simulates RAG retrieval
        matches = []
        for entry in KNOWLEDGE_BASE:
            title_hits = sum(1 for word in query_words if word in entry["title"].lower()) * 3
            content_hits = sum(1 for word in query_words if word in entry["content"].lower())
            score = title_hits + content_hits
            if score > 0:
                matches.append((score, entry))

        matches.sort(key=lambda x: x[0], reverse=True)
        top_matches = [
            f"**{entry['title']}**\n{entry['content']}"
            for _, entry in matches[:2]
        ]

        if top_matches:
            result = {
                "found": True,
                "results": top_matches
            }
        else:
            result = {
                "found": False,
                "message": "No relevant policy found for that query."
            }
        return [types.TextContent(type="text", text=json.dumps(result))]

    else:
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# --- Entry Point ---

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())