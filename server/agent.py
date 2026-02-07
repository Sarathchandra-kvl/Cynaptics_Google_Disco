import os
import re
import json
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
    Firecrawl = None
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
    
    # 1. Check for "Proactive Analysis" condition (Generic/Greetings or Auto-Trigger)
    if last_message == "AUTO_ANALYZE_INIT":
         return {"next_step": "analyze_tabs"}

    is_generic = len(messages) <= 1 and len(last_message.split()) < 5
    if is_generic and "analyze" not in last_message.lower():
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
        "You are a helpful GenTab Assistant. Analyze the user's open tabs and suggest 3-4 concrete next steps.\n"
        "Keep it conversational but structured.\n"
        "Format as a simple Markdown list:\n"
        "• **Title**: Reason/Context\n\n"
        f"OPEN TABS:\n{tab_context}"
    )
    
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    return {"messages": [AIMessage(content=content)], "next_step": "done"}

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
            # Using Verified Firecrawl Agent Mode
            if hasattr(firecrawl_app, 'agent'):
                print(f"Starting Firecrawl Agent with prompt: {research_prompt}")
                
                # Use Verified Params from test_firecrawl.py
                result = firecrawl_app.agent(
                    prompt=research_prompt,
                    model="spark-1-mini",
                    timeout=60000 
                )
                
                # Check for .data attribute (verified)
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



from langchain_openai import ChatOpenAI

# Initialize OpenAI LLM (Coding Agent)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
coding_llm = None
if OPENAI_API_KEY:
    coding_llm = ChatOpenAI(
        model="gpt-5",
        temperature=0.2,
        api_key=OPENAI_API_KEY
    )

def generation_node(state: AgentState):
    messages = state["messages"]
    # Context info is now the Deep Research Data
    context_info = messages[-1].content if messages else ""
    user_request = messages[-2].content if len(messages) > 1 else ""
    
    # 1. Determine Dynamic Theme & Layout based on Content
    theme_prompt = (
        f"Analyze the following content and user request:\n"
        f"Request: {user_request}\n"
        f"Content Snippet: {context_info[:500]}...\n\n"
        "Select the single best design theme from this list:\n"
        "- 'NEXUS': News/Politics (Dark, clean, crisp, hero cards, slate-900)\n"
        "- 'CYBERPUNK': Tech/Crypto/Future (Neon accents, black bg, glitch effects, mono fonts)\n"
        "- 'ELEGANT': Art/Literature/History (Serif fonts, cream/paper bg, gold accents, minimalist)\n"
        "- 'CORPORATE': Finance/Business (Blue/Grey, dense data tables, white/light-grey bg, professional)\n"
        "- 'BRUTALIST': Design/Avant-Garde (Bold borders, high contrast, raw aesthetic, large typography)\n"
        "Output ONLY the theme name."
    )
    
    selected_theme = "NEXUS" # Default
    try:
        # Use simpler model or same model to pick theme quickly
        theme_response = llm.invoke([HumanMessage(content=theme_prompt)]).content.strip().upper()
        if theme_response in ['CYBERPUNK', 'ELEGANT', 'CORPORATE', 'BRUTALIST']:
            selected_theme = theme_response
    except:
        pass
        
    print(f"Selected Design Theme: {selected_theme}")

    prompt = (
        f"""You are an Elite Frontend Engineer specializing in "Google Disco" / Bento-Grid aesthetics using React & Tailwind via CDN.
Generate a COMPLETE, SINGLE-FILE HTML Dashboard based on the user's request.
The file must be self-contained (no external local files, use images from Unsplash if needed).

THEME: **GOOGLE DISCO / GLASS BENTO**
- **Core Aesthetic**: Dark mode (slate-950/black), Glassmorphism (bg-white/5 backdrop-blur-xl), Vibrant Gradients (Violet/Fuchsia/Cyan), Rounded-3xl cards.
- **Layout**: Bento Grid (CSS Grid with spanning cells). Highly modular.
- **Typography**: Inter or Outfit. Large, bold headings.
- **Interactions**: Hover effects (scale, border glow), smooth transitions.

USER REQUEST: {user_request}
DEEP RESEARCH DATA: {context_info[:25000]}

REQUIREMENTS:
1.  **Single File**: Output pure HTML with embedded `<script type="text/babel">` for React components.
2.  **Libraries**: Include React, ReactDOM, Babel, and TailwindCSS via CDN links in `<head>`.
    -   Add `<script src="https://cdn.tailwindcss.com"></script>`
    -   Add Google Fonts: `<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">`
    -   Config Tailwind for font-family 'Outfit'.
3.  **Structure**:
    -   `App` component as the main entry.
    -   `Dashboard` component to visualize data using a Bento Grid layout.
    -   `BentoCard` component (glassmorphic, rounded-3xl, border-white/10).
    -   Use `ReactDOM.createRoot(document.getElementById('root')).render(<App />)`
4.  **Styling**: Use Tailwind utility classes for EVERYTHING.
    -   Background: `bg-[#050505]` or `bg-slate-950`.
    -   Cards: `bg-white/5 border border-white/10 hover:border-violet-500/30 transition-all duration-500 group`.
    -   Text: `text-slate-200`, Headings `text-white`, Subheadings `text-slate-400`.
    -   Accents: Gradient text for key metrics (`bg-gradient-to-r from-violet-400 to-fuchsia-400`).
5.  **Data**: Hydrate the dashboard with REAL FACTS from the research data. Do not use placeholder Lorem Ipsum unless absolutely necessary.
6.  **Output Format**: Return ONLY the raw HTML string. NO markdown blocks (```html). NO explanations. Start immediately with `<!DOCTYPE html>`.
"""
    )
    
    code = None
    # 1. Try OpenAI (Coding Agent) First
    if coding_llm:
        try:
            print("Generating Single-File HTML Dashboard with GPT-4o...")
            response = coding_llm.invoke([HumanMessage(content=prompt)])
            code = response.content
            
            # Cleanup Markdown wrappers
            code = re.sub(r'^```html', '', code, flags=re.MULTILINE)
            code = re.sub(r'^```', '', code, flags=re.MULTILINE)
            code = code.strip()
            
        except Exception as e:
            print(f"OpenAI API failed: {e}")
            code = f"<h1>Generation Failed</h1><p>{e}</p>"
    
    # 2. Fallback if OpenAI fails or is not configured
    if not code:
        print("Fallback: OpenAI failed or was not configured. Generating a simple error file.")
        code = json.dumps({"error.html": "<h1>Generation Failed</h1><p>The code generation agent (GPT-4o) could not be run. Please check your OPENAI_API_KEY.</p>"})

    return {"generated_dashboard_code": code, "messages": [AIMessage(content="I have generated the full React project structure.")], "next_step": "done"}


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
