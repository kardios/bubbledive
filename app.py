import streamlit as st
from openai import OpenAI
import json
import re
import time

# --- Constants & Configuration ---
class Config:
    PAGE_TITLE = "BubbleDive SparkMap"
    APP_TITLE = "🌊 BubbleDive: SparkMap"
    APP_CAPTION = "Distill any topic into its most powerful insights. Click bubbles to dive deeper."
    # REFACTOR: Set to the single, specified model
    MODEL = "gpt-4.1"
    MAX_TOOLTIP_LEN = 120
    MINDMAP_BG_COLOR = "#f7faff"
    ROOT_NODE_COLOR = "#93c5fd"
    CHILD_NODE_COLOR = "#ffffff"
    LINK_COLOR = "#b8cfff"
    NODE_BORDER_COLOR = "#528fff"

client = OpenAI()

st.set_page_config(page_title=Config.PAGE_TITLE, layout="wide")


# --- Data Processing & Helper Functions ---

def truncate_text(text, max_len):
    if not text: return ""
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= max_len: return text
    cutoff = text[:max_len].rfind(" ")
    return text[:cutoff] + "..." if cutoff > 0 else text[:max_len] + "..."

def process_tree_tooltips(tree, max_len):
    tree = dict(tree)
    tree['tooltip'] = truncate_text(tree.get('tooltip', ''), max_len)
    if 'children' in tree:
        tree['children'] = [process_tree_tooltips(child, max_len) for child in tree['children']]
    return tree

def flatten_tree_to_nodes_links(tree, parent=None, nodes=None, links=None):
    if nodes is None: nodes = []
    if links is None: links = []
    node_id = tree.get("name")
    nodes.append({
        "id": node_id, "tooltip": tree.get("tooltip", ""), "type": tree.get("type", ""),
        "parent": parent["id"] if parent else None,
        "parent_tooltip": parent["tooltip"] if parent else None
    })
    if parent:
        links.append({"source": parent["id"], "target": node_id})
    for child in tree.get("children", []) or []:
        child_node_info = {"id": child.get("name"), "tooltip": child.get("tooltip", "")}
        flatten_tree_to_nodes_links(child, child_node_info, nodes, links)
    return nodes, links

def robust_json_extract(raw_text):
    match = re.search(r'```json\s*(\{[\s\S]+\})\s*```|(\{[\s\S]+\})', raw_text)
    if not match: return None
    json_str = match.group(1) or match.group(2)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        st.error("Failed to decode the JSON from the AI's response."); st.code(json_str)
        return None

def create_text_representation(node, level=0):
    text = ""
    indent = "    " * level
    tooltip = f" - {node.get('tooltip', '')}" if node.get('tooltip') else ""
    text += f"{indent}- {node.get('name', 'Untitled')}{tooltip}\n"
    if 'children' in node and node['children']:
        for child in node['children']:
            text += create_text_representation(child, level + 1)
    return text


# --- AI & Prompting Functions ---

def get_sparkmap_prompt(concept, context=""):
    context_instruction = f"Context: {context}. " if context else ""
    return (
        f"You are a master educator. Your task is to create a SparkMap about '{concept}'. {context_instruction}"
        "A SparkMap distills any topic into its 5 to 7 most powerful, perspective-shifting insights. "
        "Each main bubble must deliver an 'aha!' moment. For each, provide a short label (max 8 words) and a 1-sentence tooltip. "
        "For each main insight, add 2–3 sub-bubbles (examples, analogies, misconceptions). "
        "Output the entire map as a valid JSON object wrapped in ```json markdown. The JSON must have this structure: {'name': '...', 'tooltip': '...', 'children': [...]}. "
        "End with clickable source references."
    )

def get_context_condensation_prompt(context_obj):
    return (
        "You are a learning assistant. Given the following information from a mindmap, generate a single, specific topic or phrase (max 10 words) "
        f"that focuses on the 'Clicked Bubble', using the Parent and Topic for context. This phrase will become the root of a new SparkMap.\n\n"
        f"Topic: {context_obj.get('root_label', '')}\n{context_obj.get('root_tooltip', '')}\n\n"
        f"Parent: {context_obj.get('parent_label', '')}\n{context_obj.get('parent_tooltip', '')}\n\n"
        f"Clicked Bubble: {context_obj.get('clicked_label', '')}\n{context_obj.get('clicked_tooltip', '')}\n\n"
        "Instructions: Output ONLY a concise topic phrase—no questions, sentences, or summaries."
    )

# REFACTOR: Reverted to the user's original API call formulations.
def generate_sparkmap_from_api(prompt):
    """Calls the API to generate the main SparkMap data and citations."""
    try:
        response = client.responses.create(
            model=Config.MODEL,
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            input=prompt,
        )
        output_text, citations = "", []
        for item in response.output:
            if getattr(item, "type", "") == "message":
                for content in getattr(item, "content", []):
                    if getattr(content, "type", "") == "output_text":
                        output_text = getattr(content, "text", "")
                        if hasattr(content, "annotations"):
                            citations = content.annotations
        return output_text, citations
    except Exception as e:
        st.error(f"An error occurred with the OpenAI API: {e}")
        return None, []

def condense_context_from_api(prompt):
    """Calls the API to condense the context into a new topic."""
    try:
        response = client.responses.create(
            model=Config.MODEL,
            input=prompt,
        )
        topic = response.output[0].content[0].text.strip().split('\n')[0]
        return topic
    except Exception as e:
        st.error(f"An error occurred while condensing context: {e}")
        return None

# --- Visualization & HTML Generation (No changes in this section) ---
def create_mindmap_html(tree_data):
    nodes, links = flatten_tree_to_nodes_links(tree_data)
    center_title = tree_data.get("name", "Root")
    nodes_json, links_json, center_title_js = json.dumps(nodes), json.dumps(links), json.dumps(center_title)
    return f"""
    <div id="mindmap-container"></div>
    <style>
        #mindmap-container {{ width: 100%; height: 880px; min-height: 700px; background: {Config.MINDMAP_BG_COLOR}; border-radius: 18px; border: 1px solid #e0e0e0; }}
        .mindmap-tooltip {{ position: absolute; pointer-events: none; z-index: 10; background: #fff; border: 1.5px solid {Config.NODE_BORDER_COLOR}; border-radius: 8px; padding: 10px 13px; font-size: 1em; color: #2c4274; box-shadow: 0 2px 12px rgba(60,100,180,0.15); opacity: 0; transition: opacity 0.18s; max-width: 280px; word-break: break-word; white-space: pre-line; }}
    </style>
    <script src="[https://d3js.org/d3.v7.min.js](https://d3js.org/d3.v7.min.js)"></script>
    <script>
    (()=>{{const nodes={nodes_json},links={links_json},rootID={center_title_js},containerEl=document.getElementById("mindmap-container"),width=containerEl.clientWidth,height=containerEl.clientHeight,svg=d3.select(containerEl).append("svg").attr("width","100%").attr("height","100%").attr("viewBox",`0 0 ${{width}} ${{height}}`),container=svg.append("g");svg.call(d3.zoom().scaleExtent([.3,3]).on("zoom",e=>container.attr("transform",e.transform)));const link=container.append("g").selectAll("line").data(links).enter().append("line").attr("stroke","{Config.LINK_COLOR}").attr("stroke-width",2.5),node=container.append("g").selectAll("g").data(nodes).enter().append("g").attr("class","node-group").style("cursor","pointer");node.append("circle").attr("r",d=>d.id===rootID?120:70).attr("fill",d=>d.id===rootID?"{Config.ROOT_NODE_COLOR}":"{Config.CHILD_NODE_COLOR}").attr("stroke","{Config.NODE_BORDER_COLOR}").attr("stroke-width",3),node.append("text").attr("text-anchor","middle").attr("dominant-baseline","central").style("font-size",d=>d.id===rootID?"22px":"16px").style("font-weight","bold").style("pointer-events","none").each(function(d){{const t=d3.select(this),e=d.id.split(/\\s+/),o=d.id===rootID?20:15,s=1.1;let a=[],n=t.append("tspan").attr("x",0).attr("y",0);for(let d=0;d<e.length;d++)a.push(e[d]),n.text(a.join(" ")),n.node().getComputedTextLength()>8*o&&(a.pop(),n.text(a.join(" ")),a=[e[d]],n=t.append("tspan").attr("x",0).attr("dy",s+"em").text(e[d]));const l=t.selectAll("tspan").size();t.selectAll("tspan").attr("y",(t,d)=>-(.5*(l-1)-d)*s+"em")}});const tooltip=d3.select("body").append("div").attr("class","mindmap-tooltip");node.on("mouseover",(t,e)=>{{if(e.tooltip)return;tooltip.style("opacity",1).html(`<b>${{e.id}}</b><br>${{e.tooltip}}`).style("left",t.pageX+15+"px").style("top",t.pageY+"px")}}).on("mousemove",t=>{{tooltip.style("left",t.pageX+15+"px").style("top",t.pageY+"px")}}).on("mouseout",()=>tooltip.style("opacity",0)),node.on("click",(t,e)=>{{if(e.id===rootID)return;const o={{clicked_label:e.id,clicked_tooltip:e.tooltip,parent_label:e.parent,parent_tooltip:e.parent_tooltip,root_label:rootID,root_tooltip:nodes.find(t=>t.id===rootID)?.tooltip||""}};window.parent.location.href=`?context=${{encodeURIComponent(JSON.stringify(o))}}`}});const simulation=d3.forceSimulation(nodes).force("link",d3.forceLink(links).id(t=>t.id).distance(t=>t.source.id===rootID?250:160).strength(1.2)).force("charge",d3.forceManyBody().strength(-1200)).force("center",d3.forceCenter(width/2,height/2)).force("collision",d3.forceCollide().radius(t=>(t.id===rootID?120:70)+10));simulation.on("tick",()=>{{link.attr("x1",t=>t.source.x).attr("y1",t=>t.source.y).attr("x2",t=>t.target.x).attr("y2",t=>t.target.y),node.attr("transform",t=>`translate(${{t.x}},${{t.y}})`)}),node.call(d3.drag().on("start",(t,e)=>{{t.active||simulation.alphaTarget(.3).restart(),e.fx=e.x,e.fy=e.y}}).on("drag",(t,e)=>{{e.fx=t.x,e.fy=t.y}}).on("end",(t,e)=>{{t.active||simulation.alphaTarget(0),e.fx=null,e.fy=null}}))}})();
    </script>"""

def create_downloadable_html(mindmap_html, citations, topic):
    citations_html = "<h3>References</h3>\n<ul>" + "".join([f'<li><a href="{getattr(c, "url", "#")}" target="_blank">{getattr(c, "title", "Source")}</a></li>' for c in citations]) + "</ul>"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>BubbleDive SparkMap - {topic}</title><style>body{{font-family:sans-serif;margin:0;background:{Config.MINDMAP_BG_COLOR}}} .container{{max-width:1400px;margin:2rem auto;padding:1rem;background:#fff;border-radius:10px}}</style></head><body><div class="container"><h1>BubbleDive SparkMap: {topic}</h1>{mindmap_html}<hr>{citations_html}</div></body></html>"""


# --- Main Application Logic ---

def main():
    st.title(Config.APP_TITLE)
    st.caption(Config.APP_CAPTION)
    if st.button("🔄 Start New Map"):
        st.query_params.clear(); st.rerun()

    topic = ""
    if context_param := st.query_params.get("context"):
        try:
            context_obj = json.loads(context_param)
            with st.spinner("Condensing context for the next dive..."):
                prompt = get_context_condensation_prompt(context_obj)
                # REFACTOR: Using the reverted API call for context
                topic = condense_context_from_api(prompt)
                if topic:
                    st.query_params.clear(); st.query_params["topic"] = topic
        except (json.JSONDecodeError, TypeError):
            st.warning("Invalid context in URL. Please start a new map.")
            st.stop()
    else:
        topic = st.query_params.get("topic", "")

    user_topic = st.text_input("Enter a topic to explore:", value=topic, key="topic_input")
    if not user_topic:
        st.info("Enter a topic to generate your SparkMap."); st.stop()

    session_key = f"sparkmap_{user_topic.lower().strip()}"
    if session_key not in st.session_state:
        with st.spinner("🧠 Generating your SparkMap... This can take a moment."):
            start_time = time.perf_counter()
            prompt = get_sparkmap_prompt(user_topic)
            # REFACTOR: Using the reverted API call for map generation
            response_text, citations = generate_sparkmap_from_api(prompt)
            if not response_text:
                st.error("Could not generate a map. Please try again."); st.stop()

            tree_data = robust_json_extract(response_text)
            if not tree_data:
                st.error("Failed to parse the SparkMap from the model's output."); st.code(response_text); st.stop()

            processed_tree = process_tree_tooltips(tree_data, Config.MAX_TOOLTIP_LEN)
            safe_filename = re.sub(r'[\W_]+', '_', user_topic)
            mindmap_html = create_mindmap_html(processed_tree)
            st.session_state[session_key] = {
                "mindmap_html": mindmap_html, "citations": citations,
                "download_html": create_downloadable_html(mindmap_html, citations, user_topic).encode('utf-8'),
                "download_txt": create_text_representation(tree_data).encode('utf-8'),
                "filename_html": f"{safe_filename}_SparkMap.html", "filename_txt": f"{safe_filename}_SparkMap.txt",
                "generation_time": time.perf_counter() - start_time
            }

    map_data = st.session_state[session_key]
    st.components.v1.html(map_data["mindmap_html"], height=900, scrolling=False)

    col1, col2, col3 = st.columns([1, 1, 3])
    with col1: st.download_button("💾 Download HTML", map_data["download_html"], map_data["filename_html"], "text/html")
    with col2: st.download_button("📝 Download TXT", map_data["download_txt"], map_data["filename_txt"], "text/plain")
    with col3: st.write(f"**✨ Generated in:** {map_data['generation_time']:.2f} seconds")

    if map_data["citations"]:
        st.markdown("---"); st.subheader("References")
        for i, cite in enumerate(map_data["citations"], 1):
            st.markdown(f"{i}. [{getattr(cite, 'title', 'Source')}]({getattr(cite, 'url', '#')})")
    
    st.markdown("---")
    st.caption("BubbleDive © 2025. Click any bubble to expand it. Refreshing the page keeps your current map.")

if __name__ == "__main__":
    main()
