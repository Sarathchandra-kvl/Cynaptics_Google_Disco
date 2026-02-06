import os
import re
from typing import Annotated, List, TypedDict, Union
from typing_extensions import TypedDict

from langchain_groq import ChatGroq
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# Load .env from server directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

# --- Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

# Initialize LLM
llm = ChatGroq(temperature=0, model_name="openai/gpt-oss-120b", api_key=GROQ_API_KEY)

# Initialize Tools
web_search_tool = TavilySearchResults(k=3)
# Firecrawl setup
try:
    from firecrawl import Firecrawl
except ImportError:
    try:
        from firecrawl import FirecrawlApp as Firecrawl
    except ImportError:
        Firecrawl = None

# Initialize Tools
web_search_tool = TavilySearchResults(k=3)
firecrawl_app = Firecrawl(api_key=FIRECRAWL_API_KEY) if (Firecrawl and FIRECRAWL_API_KEY) else None


# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    tab_context: str
    generated_dashboard_code: str
    next_step: str

# --- Nodes ---

def router_node(state: AgentState):
    """
    Decides the next step: 'chat', 'search', or 'generate_dashboard'.
    """
    messages = state["messages"]
    last_message = messages[-1].content
    tab_context = state.get("tab_context", "")
    
    # 1. Check for "Proactive Analysis" condition (Generic/Greetings)
    is_generic = len(messages) <= 1 and len(last_message.split()) < 5
    if is_generic:
         return {"next_step": "analyze_tabs"}

    system_prompt = (
        "You are an intelligent browser assistant. You have access to the user's open tabs.\n"
        f"Context (Open Tabs): {tab_context}\n\n"
        "Determine the user's intent based on the last message.\n"
        "1. If the user wants to create a dashboard, visualize data, or needs a dedicated interface, output 'generate_dashboard'.\n"
        "2. If the user needs information from the web (research) to answer a question or build a dashboard, output 'search'.\n"
        "3. Otherwise, for general chat, output 'chat'.\n"
        "Return ONLY the keyword: 'chat', 'search', 'generate_dashboard', or 'analyze_tabs'."
    )
    
    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=last_message)])
    decision = response.content.strip().lower()
    
    if "analyze" in decision:
        return {"next_step": "analyze_tabs"}
    elif "search" in decision:
        return {"next_step": "search"}
    elif "dashboard" in decision or "generate" in decision:
        # FORCE SEARCH for dashboards to ensure we have data.
        # Only skip if separate "no search" intention is detected (rare).
        print("router_node: Detected dashboard request -> Routing to SEARCH first.")
        return {"next_step": "search"}
    else:
        return {"next_step": "chat"}

def analyze_tabs_node(state: AgentState):
    """
    Proactively analyzes tabs to suggest a Todo List.
    """
    tab_context = state.get("tab_context", "")
    prompt = (
        "You are a productivity expert. Analyze the user's open tabs and suggest a 'Todo List' or 'Next Actions'.\n"
        "Be specific. If they have coding tabs, suggest coding tasks. If news, suggest reading.\n"
        "Format as a Markdown list.\n"
        f"Open Tabs: {tab_context}"
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response], "next_step": "done"}

def search_node(state: AgentState):
    """
    Performs web search using Firecrawl Agent Mode for deep research.
    """
    messages = state["messages"]
    query = messages[-1].content
    
    # Refine query for the agent - AGGRESSIVE DATA GATHERING
    refine_prompt = (
        f"You are a Lead Research Architect. Convert this user request into a MASSIVE, EXHAUSTIVE research directive for an autonomous deep-web agent.\n"
        f"User Request: {query}\n"
        "GOALS:\n"
        "1.  **Hard Data**: Gather quantitative stats, percentage growth, financial figures, dates, and names.\n"
        "2.  **Breadth & Depth**: Find conflicting viewpoints, geopolitical context, technical deep-dives, and timeline events.\n"
        "3.  **Format**: We need RAW structured facts, not just summaries. Get distinct articles/sources.\n"
        "4.  **Scope**: If the topic is broad, cover all major angles. If specific, get minute details.\n"
        "Output ONLY the single-paragraph optimized prompt."
    )
    research_prompt = llm.invoke([HumanMessage(content=refine_prompt)]).content
    
    gathered_info = ""
    
    if firecrawl_app:
        try:
            # Using Firecrawl Agent Mode
            if hasattr(firecrawl_app, 'agent'):
                print(f"Starting Firecrawl Agent with prompt: {research_prompt}")
                result = firecrawl_app.agent(prompt=research_prompt, model="spark-1-mini")
                
                # Check for .data attribute (as per v1 docs) or use result directly
                data = getattr(result, "data", result)
                gathered_info = f"Firecrawl Deep Research Results:\n{data}"
            else:
                 # Fallback for older SDK versions
                 print("Firecrawl 'agent' method not found, falling back to comprehensive search.")
                 params = {
                    'pageOptions': {'onlyMainContent': True},
                    'limit': 5
                 }
                 results = firecrawl_app.search(research_prompt, params=params)
                 gathered_info = f"Firecrawl Search Results:\n{results}"

        except Exception as e:
            print(f"Firecrawl Error: {str(e)}")
            gathered_info = f"Firecrawl failed: {e}. Falling back to Tavily."
            results = web_search_tool.invoke(research_prompt)
            gathered_info += f"\nTavily Results: {results}"
    else:
        results = web_search_tool.invoke(research_prompt)
        gathered_info = f"Tavily Results: {results}"
    
    # --- LOGGING DATA FOR USER ---
    try:
        import time
        timestamp = int(time.time())
        log_file = os.path.join(os.path.dirname(__file__), "research_logs", f"research_{timestamp}.txt")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"PROMPT: {research_prompt}\n\nDATA:\n{gathered_info}")
        print(f"--- LOGGING SUCCESS ---")
        print(f"Saved research data to: {os.path.abspath(log_file)}")
    except Exception as e:
        print(f"Failed to log research data: {e}")
    # -----------------------------
    
    return {"messages": [AIMessage(content=f"Deep Research Data: {gathered_info}")]}


def chat_node(state: AgentState):
    """
    Handles general chat interactions.
    """
    messages = state["messages"]
    tab_context = state.get("tab_context", "")
    system_msg = f"You are a helpful browser assistant. Context: {tab_context}"
    # Use the LLM to generate a response
    response = llm.invoke([SystemMessage(content=system_msg)] + messages[-5:])
    return {"messages": [response], "next_step": "done"}


from langchain_google_genai import ChatGoogleGenerativeAI

# Initialize Gemini LLM (if key exists)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
gemini_llm = None
if GOOGLE_API_KEY:
    gemini_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=GOOGLE_API_KEY,
        convert_system_message_to_human=True
    )

def generation_node(state: AgentState):
    messages = state["messages"]
    # Context info is now the Deep Research Data
    context_info = messages[-1].content if messages else ""
    user_request = messages[-2].content if len(messages) > 1 else ""
    
    prompt = (
        "You are an Elite Frontend Engineer at Google Design Lab.\n"
        "Create a SINGLE FILE HTML React dashboard using Babel standalone and Tailwind CSS.\n"
        "The goal is to build a 'Nexus News' style interface: A stunning, premium content aggregator.\n\n"
        f"DATA SOURCE (Use this content): {context_info}\n\n"
        f"USER REQUEST: {user_request}\n\n"
        "DESIGN SPECS (Pixel Perfect):\n"
        "1.  **Theme**: Deep Dark Mode. Bg: `bg-slate-900`. Cards: `bg-slate-800` or `bg-zinc-900`. Text: `text-slate-100`.\n"
        "2.  **Hero Section**: The top item must be a 'Hero Card' spanning full width. Use a subtle gradient background (e.g., `bg-gradient-to-r from-slate-800 to-slate-900`). Title large (`text-4xl`), bold.\n"
        "3.  **Typography**: Use system sans-serif ('Inter'). Headers bold/extrabold. Subtitles `text-slate-400`.\n"
        "4.  **Layout**: Responsive Grid. `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`. max-width-7xl mx-auto.\n"
        "5.  **Components**:\n"
        "    -   **Tags/Pills**: Use rounded-full pills for categories (e.g., `bg-blue-600/20 text-blue-400 text-xs px-3 py-1`).\n"
        "    -   **Floating Action**: Add a fixed button at bottom-right for 'Share' or 'Menu'.\n"
        "    -   **Search Bar**: A floating glassmorphism search bar at the top.\n"
        "    -   **Skeleton Loading**: No skeletons, just use available data. If data is text, structure it into clean readable articles.\n"
        "6.  **Interactivity**: `hover:scale-[1.02] transition-all duration-300` on cards.\n"
        "7.  **Data Integration**: You MUST use the 'Firecrawl Deep Research Results'. Do not use placeholders like 'Lorem Ipsum'. Extract real titles, summaries, and facts from the provided data.\n"
        "8.  **Output**: ONLY the raw HTML code. Do not wrap in markdown code blocks. Valid HTML5."
    )
    
    code = None
    
    # 1. Try Gemini API First (User Preference)
    if gemini_llm:
        try:
            print("Generating dashboard with Gemini 1.5 Pro...")
            response = gemini_llm.invoke([HumanMessage(content=prompt)])
            code = response.content
            # Cleanup Markdown
            code = re.sub(r'^```html', '', code, flags=re.MULTILINE)
            code = re.sub(r'^```jsx', '', code, flags=re.MULTILINE)
            code = re.sub(r'^```', '', code, flags=re.MULTILINE)
            code = code.strip()
        except Exception as e:
            print(f"Gemini API failed, falling back to Groq: {e}")
    
    # 2. Fallback to Groq if Gemini failed or key missing
    if not code:
        try:
            print("Generating dashboard with Groq...")
            response = llm.invoke([HumanMessage(content=prompt)])
            code = response.content
            code = re.sub(r'^```html', '', code, flags=re.MULTILINE)
            code = re.sub(r'^```', '', code, flags=re.MULTILINE)
            code = code.strip()
        except Exception as e:
            code = f"<h1>Error generating dashboard: {e}</h1>"
    
    return {"generated_dashboard_code": code, "messages": [AIMessage(content="I have generated a deep research dashboard for you.")], "next_step": "done"}

# --- Graph Definition ---
workflow = StateGraph(AgentState)

workflow.add_node("router", router_node)
workflow.add_node("analyze_tabs", analyze_tabs_node) # New Node
workflow.add_node("search", search_node)
workflow.add_node("chat", chat_node)
workflow.add_node("generate_dashboard", generation_node)

workflow.set_entry_point("router")

workflow.add_conditional_edges(
    "router",
    lambda state: state["next_step"],
    {
        "chat": "chat",
        "search": "search",
        "analyze_tabs": "analyze_tabs",
        "generate_dashboard": "generate_dashboard"
    }
)

workflow.add_edge("analyze_tabs", END)
workflow.add_edge("search", "generate_dashboard")
workflow.add_edge("chat", END)
workflow.add_edge("generate_dashboard", END)

app = workflow.compile()
