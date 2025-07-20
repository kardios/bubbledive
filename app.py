import streamlit as st
from openai import OpenAI
import json
import re
import time

# --- Page Configuration ---
# Sets the title and layout for the Streamlit page.
st.set_page_config(page_title="BubbleDive SparkMap", layout="wide")
st.title("🌊 BubbleDive: SparkMap")
st.caption("Distill any topic into its most powerful insights. Click bubbles to dive deeper.")

# --- Reset Button ---
# Clears query parameters and reruns the app to start fresh.
if st.button("🔄 Start a New SparkMap"):
    st.query_params.clear()
    st.rerun()

# Initialize the OpenAI client
client = OpenAI()

def truncate_tooltip(tooltip, max_len=120):
    """Truncates a tooltip string to a maximum length, breaking at a word boundary."""
    if not tooltip:
        return ""
    tooltip = tooltip.replace("\n", " ").replace("\r", " ").strip()
    if len(tooltip) <= max_len:
        return tooltip
    cutoff = tooltip[:max_len].rfind(" ")
    return tooltip[:cutoff] + "..." if cutoff > 0 else tooltip[:max_len] + "..."

def process_tree_tooltips(tree, max_len=120):
    """Recursively processes and truncates all tooltips in the mindmap data tree."""
    tree = dict(tree)
    tree['tooltip'] = truncate_tooltip(tree.get('tooltip', ''), max_len)
    if 'children' in tree and tree['children'] is not None:
        tree['children'] = [process_tree_tooltips(child, max_len) for child in tree['children']]
    return tree

def flatten_tree_to_nodes_links(tree, parent_name=None, parent_tooltip=None, nodes=None, links=None):
    """Converts the hierarchical tree data into flat lists of nodes and links for D3.js."""
    if nodes is None: nodes = []
    if links is None: links = []

    this_id = tree.get("name")
    tooltip = tree.get("tooltip", "")
    node_type = tree.get("type", "")

    nodes.append({"id": this_id, "tooltip": tooltip, "type": node_type,
                  "parent": parent_name, "parent_tooltip": parent_tooltip})

    if parent_name:
        links.append({"source": parent_name, "target": this_id})

    for child in tree.get("children", []) or []:
        flatten_tree_to_nodes_links(child, this_id, tooltip, nodes, links)

    return nodes, links

def tree_to_text(node, level=0):
    """Recursively converts the mindmap tree to an indented text format."""
    text = ""
    indent = "  " * level
    name = node.get('name', 'N/A')
    tooltip = node.get('tooltip', '')

    text += f"{indent}- {name}\n"
    if tooltip:
        text += f"{indent}  ({tooltip})\n"

    if 'children' in node and node['children'] is not None:
        for child in node['children']:
            text += tree_to_text(child, level + 1)
    return text


def create_multilevel_mindmap_html(tree, center_title="Root"):
    """Generates the HTML and D3.js code for the interactive mindmap."""
    nodes, links = flatten_tree_to_nodes_links(tree)
    for n in nodes:
        n["group"] = 0 if n["id"] == center_title else 1

    nodes_json = json.dumps(nodes)
    links_json = json.dumps(links)
    center_title_js = center_title.replace("\\", "\\\\").replace("`", "\\`").replace('"', '\\"')

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
    const rootID = "{center_title_js}";

    function getNodeColor(type, id) {{
        if (id === rootID) return "#93c5fd"; // Lighter blue for the central node
        return "#fff"; // White for other nodes
    }}

    const svg = d3.select("#mindmap").append("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", `0 0 ${{width}} ${{height}}`)
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
        .attr("r", d => d.id === rootID ? 130 : 75)
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
            let contextObj = {{
                clicked_label: d.id,
                clicked_tooltip: d.tooltip,
                parent_label: d.parent,
                parent_tooltip: d.parent_tooltip,
                root_label: rootID,
                root_tooltip: nodes.find(n=>n.id===rootID)?.tooltip || ""
            }};
            if (d.parent === rootID) {{
                contextObj.parent_label = "";
                contextObj.parent_tooltip = "";
            }}
            const contextString = encodeURIComponent(JSON.stringify(contextObj));
            window.location.href = `?context=${{contextString}}`;
        }});

    node.append("text")
        .attr("text-anchor", "middle")
        .style("pointer-events", "none")
        .each(function(d) {{
            const text = d3.select(this);
            const maxChars = 16;
            const maxLines = 4;
            const fontSize = d.id === rootID ? 24 : 20; // in px
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

            if (lines.length > maxLines) {{
                lines = lines.slice(0, maxLines);
                lines[maxLines - 1] += "...";
            }}

            text.style("font-size", fontSize + "px");
            const startDy = -((lines.length - 1) / 2) * 1.1;

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
        .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.source.id === rootID ? 270 : 180))
        .force("charge", d3.forceManyBody().strength(-1400))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(d => (d.id === rootID ? 130 : 75) + 5));

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

def full_html_wrap(mindmap_html, citations, title="BubbleDive SparkMap"):
    """Wraps the mindmap in a full HTML document for download."""
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
    """Creates the detailed prompt for the AI model to generate the SparkMap."""
    context_instruction = f"Context: {context}. " if context else ""
    return (
        f"You are a master educator. Your task is to create a SparkMap mindmap about '{concept}'. {context_instruction}"
        "A SparkMap distills any topic into its 5 to 7 most powerful, perspective-shifting insights. "
        "Each main bubble must deliver an 'aha!' moment: a surprising fact, myth-buster, or insight that changes how a smart person sees the topic. "
        "For each main bubble, provide a short, striking label (max 8 words) and a 1-sentence tooltip that explains why it matters or is surprising. "
        "For each main insight, add 2–3 sub-bubbles: each must be an example, famous misconception, analogy, bold comparison, or surprising detail (not just background or generic info). "
        "If and only if a sub-bubble’s idea is complex, you may add 1–2 supporting details beneath it—do not add a third level unless it makes the map significantly more enlightening. "
        "Do not overload any single branch. If you cannot find 7 main insights, fewer is better; never pad with weak ideas. "
        "At least one main bubble should compare or contrast this topic with others, or highlight a dramatic trend or change over time. "
        "Use the ‘Spark Test’: Would an expert say ‘I didn’t know that!’ or ‘That changes my perspective’? If not, replace it with something stronger. "
        "Keep all tooltips short, punchy, and designed to spark further curiosity. "
        "Output the entire map as valid JSON: {{'name': '...', 'tooltip': '...', 'children': [...]}}. "
        "End with clickable source references."
    )

def condense_bubble_context(clicked_label, clicked_tooltip, parent_label, parent_tooltip, root_label, root_tooltip):
    """Uses the AI to generate a concise new topic from the context of a clicked bubble."""
    prompt = (
        "You are a learning assistant. Given the following information from a mindmap, generate a single, specific topic or phrase (max 10 words) that focuses on the 'Clicked Bubble', using the Parent and Topic for context if needed. This phrase will become the root of a new SparkMap.\n\n"
        f"Clicked Bubble:\n{clicked_label}\n{clicked_tooltip}\n\n"
        f"Parent:\n{parent_label}\n{parent_tooltip}\n\n"
        f"Topic:\n{root_label}\n{root_tooltip}\n\n"
        "Instructions:\n"
        "- Focus on the Clicked Bubble.\n"
        "- Use Parent and Topic only to clarify meaning or specify context.\n"
        "- Output only a concise topic phrase—no questions, no sentences, no summaries."
    )
    response = client.responses.create(
        model="gpt-4.1",
        input=prompt,
    )
    topic = response.output[0].content[0].text.strip().split('\n')[0]
    return topic


def robust_json_extract(raw):
    """Extracts a JSON object from a string, even if it's embedded in other text."""
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

def get_query_param(key):
    """Safely retrieves a query parameter from Streamlit's query_params."""
    val = st.query_params.get(key, "")
    if isinstance(val, list):
        return val[0] if val else ""
    return str(val)

# ---- Main Application Logic ----
context_json = get_query_param("context")
if context_json:
    try:
        context_obj = json.loads(context_json)
        with st.spinner("Condensing for next dive..."):
            topic = condense_bubble_context(
                context_obj.get("clicked_label", ""),
                context_obj.get("clicked_tooltip", ""),
                context_obj.get("parent_label", ""),
                context_obj.get("parent_tooltip", ""),
                context_obj.get("root_label", ""),
                context_obj.get("root_tooltip", ""),
            )
    except Exception as e:
        st.warning(f"Could not parse context: {e}. Showing as plain text.")
        topic = context_json
else:
    topic = get_query_param("concept")

if not topic or not topic.strip():
    topic = st.text_input("Enter a topic:", value="", key="concept_input")
    if not topic.strip():
        st.info("Enter a topic and press Enter to generate a SparkMap.")
        st.stop()
else:
    topic = st.text_input("Enter a topic:", value=topic, key="concept_input")

ss_key = f"sparkmap_{topic}"
ss_cit_key = f"sparkmap_cit_{topic}"
ss_html_key = f"sparkmap_html_{topic}"
ss_txt_key = f"sparkmap_txt_{topic}" # New session state key for text file
ss_time_key = f"sparkmap_time_{topic}"

if ss_key not in st.session_state:
    prompt = prompt_expand_concept_sparkmap(topic.strip())
    t0 = time.perf_counter()
    with st.spinner("Generating SparkMap... This may take a moment."):
        try:
            response = client.responses.create(
                model="gpt-4.1",
                tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                input=prompt,
            )
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
        except Exception as e:
            st.error(f"Failed to generate SparkMap from the model: {e}")
            st.stop()

    t1 = time.perf_counter()

    tree = robust_json_extract(output_text)
    if not tree:
        st.error("Could not extract a valid SparkMap from the model's output.")
        st.code(output_text)
        st.stop()

    tree = process_tree_tooltips(tree, max_len=120)
    mindmap_html = create_multilevel_mindmap_html(tree, center_title=tree.get("name", "Root"))
    
    # Generate the text representation
    text_file_content = tree_to_text(tree)

    safe_filename = re.sub(r'[^A-Za-z0-9_]+', '', topic.replace(' ', '_'))
    html_file = full_html_wrap(mindmap_html, citations, title=f"BubbleDive SparkMap - {topic}").encode("utf-8")

    st.session_state[ss_key] = mindmap_html
    st.session_state[ss_cit_key] = citations
    st.session_state[ss_html_key] = html_file
    st.session_state[ss_txt_key] = text_file_content.encode("utf-8") # Store encoded text file
    st.session_state[ss_time_key] = t1 - t0

mindmap_html = st.session_state[ss_key]
citations = st.session_state[ss_cit_key]
html_file = st.session_state[ss_html_key]
txt_file = st.session_state[ss_txt_key]
elapsed = st.session_state[ss_time_key]

st.components.v1.html(mindmap_html, height=900, scrolling=False)

st.markdown(f"**Generation time:** {elapsed:.2f} seconds")

safe_filename = re.sub(r'[^A-Za-z0-9_]+', '', topic.replace(' ', '_'))

# --- Download Buttons ---
col1, col2 = st.columns(2)
with col1:
    st.download_button(
        label="Download SparkMap as HTML",
        data=html_file,
        file_name=f"{safe_filename}_BubbleDive_SparkMap.html",
        mime="text/html",
        use_container_width=True
    )
with col2:
    st.download_button(
        label="Download SparkMap as TXT",
        data=txt_file,
        file_name=f"{safe_filename}_BubbleDive_SparkMap.txt",
        mime="text/plain",
        use_container_width=True
    )


if citations:
    st.markdown("### References")
    for idx, cite in enumerate(citations, 1):
        url = getattr(cite, "url", "#")
        title = getattr(cite, "title", url)
        snippet = getattr(cite, "snippet", "")
        st.markdown(f"{idx}. [{title}]({url})" + (f" – {snippet}" if snippet else ""))

st.markdown("---")
st.caption("BubbleDive © 2025. Click any bubble to expand it (except the center one).")
