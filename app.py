import streamlit as st
from openai import OpenAI
import json
import re
import time

st.set_page_config(page_title="BubbleDive Spark Map", layout="wide")
st.title("🌊 BubbleDive: Spark Map")
st.caption("Distill any topic into its five most powerful insights. Click bubbles to dive deeper.")

client = OpenAI()

def truncate_tooltip(tooltip, max_len=120):
    if not tooltip:
        return ""
    tooltip = tooltip.replace("\n", " ").replace("\r", " ").strip()
    if len(tooltip) <= max_len:
        return tooltip
    cutoff = tooltip[:max_len].rfind(" ")
    return tooltip[:cutoff] + "..." if cutoff > 0 else tooltip[:max_len] + "..."

def process_tree_tooltips(tree, max_len=120):
    tree = dict(tree)
    tree['tooltip'] = truncate_tooltip(tree.get('tooltip', ''), max_len)
    if 'children' in tree:
        tree['children'] = [process_tree_tooltips(child, max_len) for child in tree['children']]
    return tree

def robust_json_extract(raw):
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r'(\{[\s\S]+\})', raw)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

def flatten_tree_to_nodes_links(tree, parent_name=None, nodes=None, links=None):
    if nodes is None: nodes = []
    if links is None: links = []
    this_id = tree.get("name")
    tooltip = tree.get("tooltip", "")
    node_type = tree.get("type", "")
    nodes.append({"id": this_id, "tooltip": tooltip, "type": node_type})
    if parent_name:
        links.append({"source": parent_name, "target": this_id})
    for child in tree.get("children", []) or []:
        flatten_tree_to_nodes_links(child, this_id, nodes, links)
    return nodes, links

def create_multilevel_mindmap_html(tree, center_title="Root", user_topic=""):
    nodes, links = flatten_tree_to_nodes_links(tree)
    for n in nodes:
        n["group"] = 0 if n["id"] == center_title else 1

    nodes_json = json.dumps(nodes)
    links_json = json.dumps(links)
    mindmap_html = f"""
    <div id="mindmap"></div>
    <style>
    #mindmap {{ width:100%; height:880px; min-height:700px; background:#f7faff; border-radius:18px; }}
    .tooltip-glossary {{
        position: absolute; pointer-events: none; background: #fff; border: 1.5px solid #4f7cda; border-radius: 8px;
        padding: 10px 13px; font-size: 1em; color: #2c4274; box-shadow: 0 2px 12px rgba(60,100,180,0.15); z-index: 10;
        opacity: 0; transition: opacity 0.18s; max-width: 240px; word-break: break-word; white-space: pre-line;
    }}
    </style>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
    const nodes = {nodes_json};
    const links = {links_json};
    const width = 1400, height = 900;
    const rootID = "{center_title.replace('"', '\\"')}";
    const userTopic = "{user_topic.replace('"', '\\"')}";
    function getNodeColor(type, id) {{
        if (id === rootID) return "#3B82F6"; // Central bubble color (blue)
        return "#fff";
    }}

    const svg = d3.select("#mindmap").append("svg")
        .attr("width", width)
        .attr("height", height)
        .style("background", "#f7faff");

    const container = svg.append("g");

    svg.call(
        d3.zoom()
          .scaleExtent([0.3, 2.5])
          .on("zoom", (event) => container.attr("transform", event.transform))
    );

    const link = container.append("g")
        .selectAll("line").data(links).enter().append("line")
        .attr("stroke", "#b8cfff").attr("stroke-width", 2);

    const node = container.append("g")
        .selectAll("g")
        .data(nodes).enter().append("g")
        .attr("class", "node");

    node.append("circle")
        .attr("r", d => d.id === rootID ? 110 : 75)
        .attr("fill", d => getNodeColor(d.type, d.id))
        .attr("stroke", "#528fff").attr("stroke-width", 3)
        .on("mouseover", function(e, d) {{
            if(d.tooltip) {{
                tooltip.style("opacity", 1).html("<b>" + d.id + "</b><br>" + d.tooltip)
                  .style("left", (e.pageX+12)+"px").style("top", (e.pageY-18)+"px");
            }}
        }})
        .on("mousemove", function(e) {{
            tooltip.style("left", (e.pageX+12)+"px").style("top", (e.pageY-18)+"px");
        }})
        .on("mouseout", function(e, d) {{
            tooltip.style("opacity", 0);
        }})
        .on("click", function(e, d) {{
            if (d.id === rootID) return; // Central bubble: do nothing
            const topic = encodeURIComponent(userTopic);
            const label = encodeURIComponent(d.id);
            const tooltip = encodeURIComponent(d.tooltip || "");
            window.open(`?topic=${{topic}}&label=${{label}}&tooltip=${{tooltip}}`, "_blank");
        }});

    node.append("text")
        .attr("text-anchor", "middle")
        .style("font-size", d => d.id === rootID ? "1.4em" : "1.08em")
        .each(function(d) {{
            const text = d3.select(this);
            const maxChars = d.id === rootID ? 24 : 16;
            const label = d.id;
            const words = label.split(' ');
            let lines = [];
            let current = '';
            words.forEach(word => {{
                if ((current + ' ' + word).trim().length > maxChars) {{
                    lines.push(current.trim());
                    current = word;
                }} else {{
                    current += ' ' + word;
                }}
            }});
            if (current.trim()) lines.push(current.trim());
            const startDy = d.id === rootID ? -((lines.length - 1) / 2) * 1.1 : 0;
            lines.forEach((line, i) => {{
                text.append("tspan")
                    .attr("x", 0)
                    .attr("dy", i === 0 ? `${{startDy}}em` : "1.1em")
                    .text(line);
            }});
        }});

    node.call(
      d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended)
    );

    function dragstarted(event, d) {{
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }}
    function dragged(event, d) {{
        d.fx = event.x;
        d.fy = event.y;
    }}
    function dragended(event, d) {{
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }}

    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.source === rootID ? 270 : 180))
        .force("charge", d3.forceManyBody().strength(-1400))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(82));

    simulation.on("tick", () => {{
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("transform", d => `translate(${{d.x}},${{d.y}})`);
    }});

    const tooltip = d3.select("body").append("div")
        .attr("class", "tooltip-glossary");
    </script>
    """
    return mindmap_html

def full_html_wrap(mindmap_html, citations, title="BubbleDive Spark Map"):
    citations_html = "<h3>References</h3>\n<ul>"
    for idx, cite in enumerate(citations, 1):
        url = getattr(cite, "url", "#")
        title_cite = getattr(cite, "title", url)
        snippet = getattr(cite, "snippet", "")
        citations_html += f'<li><a href="{url}" target="_blank">{title_cite}</a>'
        if snippet:
            citations_html += f" – {snippet}"
        citations_html += "</li>"
    citations_html += "</ul>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body {{ background:#f7faff; font-family:sans-serif; padding:0; margin:0; }}
            .container {{ width:100vw; max-width:1600px; margin:0 auto; padding:24px; }}
            h1 {{ margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{title}</h1>
            {mindmap_html}
            <hr>
            {citations_html}
        </div>
    </body>
    </html>
    """
    return html

def prompt_expand_concept_sparkmap(concept, context=""):
    context_instruction = f"Context: {context}. " if context else ""
    return (
        f"You are a master teacher whose goal is to make smart people care about and remember the topic '{concept}'. {context_instruction}"
        "Create a Spark Map that distills the topic into the 5 most powerful insights—each a key idea that changes how people see the subject, reveals something surprising, or corrects a big myth. "
        "For each main bubble, provide a short, striking label (max 8 words) and a 1-sentence tooltip that explains why this is an 'aha!' or perspective shift. "
        "For each main insight, add 2-3 supporting sub-bubbles with memorable examples, surprising facts, analogies, or famous misconceptions. "
        "Keep all tooltips short, punchy, and designed to spark further curiosity—not just summarize. "
        "Do NOT include neutral background or padding; only what sparks learning and interest. "
        "Output as valid JSON: {{'name': '...', 'tooltip': '...', 'children': [...]}}"
        "End with clickable source references."
    )

# ---- Helper to robustly extract param ----
def get_query_param(key):
    val = st.query_params.get(key, "")
    st.write(f"DEBUG: key={key!r} val={val!r} type={type(val)}")  # <--- Debug output
    if isinstance(val, list):
        return val[0] if val else ""
    elif isinstance(val, str):
        return val
    return ""

# ---- Query params ----
topic = get_query_param("topic") or get_query_param("concept")
label = get_query_param("label")
tooltip = get_query_param("tooltip")
context = get_query_param("context")

concept = st.text_input("🔎 Enter a topic or event:", value=topic, key="concept_input")

ss_key = f"sparkmap_{concept}"
ss_cit_key = f"sparkmap_cit_{concept}"
ss_html_key = f"sparkmap_html_{concept}"
ss_time_key = f"sparkmap_time_{concept}"

if not concept.strip():
    st.info("Enter a topic and press Enter to generate a Spark Map.")
    st.stop()

if (
    ss_key not in st.session_state or
    ss_cit_key not in st.session_state or
    ss_html_key not in st.session_state or
    ss_time_key not in st.session_state
):
    prompt = prompt_expand_concept_sparkmap(concept.strip(), context)
    t0 = time.perf_counter()
    with st.spinner("Generating Spark Map..."):
        response = client.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            input=prompt,
        )
    t1 = time.perf_counter()
    output_items = response.output
    output_text = ""
    citations = []
    for item in output_items:
        if getattr(item, "type", "") == "message":
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    output_text = getattr(content, "text", "")
                    if hasattr(content, "annotations"):
                        citations = content.annotations
    tree = robust_json_extract(output_text)
    if not tree:
        st.error("Could not extract Spark Map from model output.")
        st.stop()
    tree = process_tree_tooltips(tree, max_len=120)
    mindmap_html = create_multilevel_mindmap_html(tree, center_title=tree["name"], user_topic=concept)
    html_file = full_html_wrap(mindmap_html, citations, title=f"BubbleDive Spark Map - {concept}").encode("utf-8")

    st.session_state[ss_key] = mindmap_html
    st.session_state[ss_cit_key] = citations
    st.session_state[ss_html_key] = html_file
    st.session_state[ss_time_key] = t1 - t0

mindmap_html = st.session_state[ss_key]
citations = st.session_state[ss_cit_key]
html_file = st.session_state[ss_html_key]
elapsed = st.session_state[ss_time_key]

st.components.v1.html(mindmap_html, height=900, width=1450, scrolling=False)

st.markdown(f"**Generation time:** {elapsed:.2f} seconds")

st.download_button(
    label="Download Spark Map as HTML",
    data=html_file,
    file_name=f"{concept.replace(' ', '_')}_BubbleDive_SparkMap.html",
    mime="text/html"
)

if citations:
    st.markdown("### References")
    for idx, cite in enumerate(citations, 1):
        url = getattr(cite, "url", "#")
        title = getattr(cite, "title", url)
        snippet = getattr(cite, "snippet", "")
        st.markdown(f"{idx}. [{title}]({url})" + (f" – {snippet}" if snippet else ""))

st.markdown("---")
st.caption("BubbleDive © 2025. Click any bubble to expand it in a new tab (except the center one).")
