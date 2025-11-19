import streamlit as st
import networkx as nx
from pyvis.network import Network
import pandas as pd
import tempfile
import os

# -----------------------------------------------------------------------------
# PART 1: DATA LOADING FROM CSV
# -----------------------------------------------------------------------------

@st.cache_data
def load_methodologies_from_csv(filepath):
    """
    Loads the methodologies CSV and transforms it into the required structure.
    Uses multiple fallback strategies to handle malformed CSV files.
    
    Expected CSV columns:
    - Method: Name of the methodology
    - Domain of Origin: The originating field
    - Primary Application Domains: Comma-separated list of fields where it's used
    
    Returns a list of dictionaries compatible with the visualization function.
    """
    knowledge_base = []
    
    # Strategy 1: Try with different encoding and error handling
    try:
        df = pd.read_csv(
            filepath, 
            quotechar='"', 
            escapechar='\\',
            encoding='utf-8',
            on_bad_lines='skip',  # Skip problematic lines
            engine='python'  # More flexible parser
        )
        st.sidebar.success(f"✅ Loaded {len(df)} rows with strategy 1")
    except Exception as e1:
        st.warning(f"Strategy 1 failed: {e1}")
        
        # Strategy 2: Manual line-by-line parsing
        try:
            import csv
            knowledge_base = []
            
            with open(filepath, 'r', encoding='utf-8') as f:
                # Try to determine if file has header
                sample = f.read(1024)
                f.seek(0)
                has_header = csv.Sniffer().has_header(sample)
                
                reader = csv.reader(f, quotechar='"', skipinitialspace=True)
                
                if has_header:
                    headers = next(reader)
                else:
                    headers = ['Method', 'Domain of Origin', 'Primary Application Domains']
                
                for line_num, row in enumerate(reader, start=2):
                    try:
                        if len(row) < 3:
                            continue
                        
                        # Handle cases where there are more than 3 fields
                        # Join extra fields into the last column
                        if len(row) > 3:
                            method = row[0].strip()
                            origin = row[1].strip()
                            # Join remaining fields as they're all part of adopted domains
                            domains = ', '.join(row[2:]).strip()
                        else:
                            method = row[0].strip()
                            origin = row[1].strip()
                            domains = row[2].strip()
                        
                        if not method or not origin or not domains:
                            continue
                        
                        # Parse domains
                        adopted_by = [field.strip() for field in domains.split(',') if field.strip()]
                        
                        entry = {
                            "name": method,
                            "origin": origin,
                            "description": f"Originated in {origin}. Applied in: {len(adopted_by)} domains",
                            "adopted_by": adopted_by
                        }
                        knowledge_base.append(entry)
                        
                    except Exception as row_error:
                        st.sidebar.warning(f"Skipping line {line_num}: {row_error}")
                        continue
            
            st.sidebar.success(f"✅ Loaded {len(knowledge_base)} methods with strategy 2 (manual parsing)")
            return knowledge_base
            
        except Exception as e2:
            st.error(f"Strategy 2 also failed: {e2}")
            import traceback
            st.error(traceback.format_exc())
            return []
    
    # If strategy 1 succeeded, process the dataframe
    if 'df' in locals():
        # Validate required columns
        required_cols = ['Method', 'Domain of Origin', 'Primary Application Domains']
        
        # Check if columns exist (case-insensitive)
        actual_cols = {col.lower(): col for col in df.columns}
        col_mapping = {}
        
        for req_col in required_cols:
            found = False
            for actual_col_lower, actual_col in actual_cols.items():
                if req_col.lower() == actual_col_lower:
                    col_mapping[req_col] = actual_col
                    found = True
                    break
            if not found:
                st.error(f"Missing column: {req_col}. Found: {df.columns.tolist()}")
                return []
        
        # Transform data
        for idx, row in df.iterrows():
            try:
                method = row[col_mapping['Method']]
                origin = row[col_mapping['Domain of Origin']]
                domains = row[col_mapping['Primary Application Domains']]
                
                # Handle NaN or empty values
                if pd.isna(method) or pd.isna(origin) or pd.isna(domains):
                    continue
                
                # Parse the comma-separated application domains
                domains_str = str(domains)
                adopted_by = [field.strip() for field in domains_str.split(',') if field.strip()]
                
                entry = {
                    "name": str(method).strip(),
                    "origin": str(origin).strip(),
                    "description": f"Originated in {origin}. Applied in: {len(adopted_by)} domains",
                    "adopted_by": adopted_by
                }
                knowledge_base.append(entry)
            except Exception as row_error:
                continue
        
        return knowledge_base
    
    return knowledge_base

# -----------------------------------------------------------------------------
# PART 2: VISUALIZATION IMPLEMENTATION
# -----------------------------------------------------------------------------

def build_graph(data, filter_origin=None, filter_method=None, min_connections=0):
    """
    Constructs a NetworkX graph from the knowledge base.
    Distinguishes between 'Method' nodes and 'Field' nodes.
    
    Parameters:
    - data: List of methodology dictionaries
    - filter_origin: If specified, only show methods from this origin
    - filter_method: If specified, only show this specific method
    - min_connections: Minimum number of adoption connections to include a method
    """
    G = nx.DiGraph()

    for entry in data:
        method = entry['name']
        origin = entry['origin']
        adopters = entry['adopted_by']
        desc = entry['description']

        # Apply filters
        if filter_origin and origin != filter_origin:
            continue
        
        if filter_method and method != filter_method:
            continue
        
        if len(adopters) < min_connections:
            continue

        # 1. Add Origin Field Node with simple tooltip
        if origin not in G:
            origin_tooltip = f"🔬 ORIGIN DOMAIN\n{origin}"
            G.add_node(
                origin, 
                group='Field', 
                title=origin_tooltip, 
                shape='dot', 
                size=25, 
                color='#FF6B6B'
            )

        # 2. Add Method Node with formatted tooltip
        # Create a clean, readable tooltip
        adopters_preview = adopters[:8]  # Show first 8
        adopters_text = "\n".join([f"  • {a}" for a in adopters_preview])
        
        if len(adopters) > 8:
            adopters_text += f"\n  • ... and {len(adopters) - 8} more domains"
        
        tooltip = f"""📦 METHOD: {method}

🔬 Origin: {origin}

📊 Applied in {len(adopters)} domains:
{adopters_text}"""
        
        G.add_node(
            method, 
            group='Method', 
            title=tooltip, 
            shape='square', 
            size=20, 
            color='#4ECDC4'
        )

        # 3. Edge: Origin -> Method (Solid)
        G.add_edge(
            origin, 
            method, 
            title="Originated In", 
            color='#555555', 
            width=2, 
            dashes=False
        )

        # 4. Add Adopter Nodes and Edges
        for adopter in adopters:
            if adopter not in G:
                G.add_node(
                    adopter, 
                    group='Field', 
                    title=f"<b>Field: {adopter}</b>", 
                    shape='dot', 
                    size=20, 
                    color='#FF6B6B'
                )
            
            # Edge: Method -> Adopter (Dashed)
            G.add_edge(
                method, 
                adopter, 
                title="Adopted By", 
                color='#aaaaaa', 
                width=1, 
                dashes=True
            )

    return G

def render_pyvis(G):
    """
    Converts NetworkX graph to PyVis and configures physics/interactivity.
    """
    # Initialize PyVis Network
    nt = Network(
        height="750px", 
        width="100%", 
        bgcolor="#222222", 
        font_color="white", 
        directed=True
    )
    
    # Import from NetworkX
    nt.from_nx(G)

    # Physics Configuration (ForceAtlas2Based for clustering)
    nt.set_options("""
    var options = {
      "nodes": {
        "font": {
          "size": 16,
          "face": "tahoma"
        }
      },
      "edges": {
        "color": {
          "inherit": true
        },
        "smooth": {
          "type": "continuous",
          "forceDirection": "none"
        }
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -100,
          "centralGravity": 0.005,
          "springLength": 230,
          "springConstant": 0.18
        },
        "maxVelocity": 146,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": {
          "enabled": true,
          "iterations": 200
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 200
      }
    }
    """)
    
    return nt

def calculate_statistics(data):
    """
    Calculate summary statistics from the methodology data.
    """
    if not data:
        return {}
    
    origins = [entry['origin'] for entry in data]
    origin_counts = pd.Series(origins).value_counts()
    
    all_adopters = []
    for entry in data:
        all_adopters.extend(entry['adopted_by'])
    
    adopter_counts = pd.Series(all_adopters).value_counts()
    
    return {
        'total_methods': len(data),
        'total_origins': len(set(origins)),
        'total_adopting_fields': len(set(all_adopters)),
        'top_origins': origin_counts.head(5),
        'top_adopters': adopter_counts.head(5)
    }

# -----------------------------------------------------------------------------
# STREAMLIT APP LAYOUT
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Epistemological Flow", layout="wide")

# Main Title
st.title("🕸️ The Genealogy of Scientific Methods")
st.markdown(
    """
    > *"Science is a disunity... a patchwork of trading zones."* — Peter Galison
    
    This visualization maps the **cross-pollination** of scientific methodologies across disciplines.
    """
)

# File Upload or Default Path
st.sidebar.title("📊 Data Configuration")
uploaded_file = st.sidebar.file_uploader(
    "Upload CSV file (or use default)", 
    type=['csv'],
    help="CSV should have columns: Method, Domain of Origin, Primary Application Domains"
)

# Load data
if uploaded_file is not None:
    KNOWLEDGE_BASE = load_methodologies_from_csv(uploaded_file)
else:
    # Try to load from default path
    default_path = "methodologies.csv"
    if os.path.exists(default_path):
        KNOWLEDGE_BASE = load_methodologies_from_csv(default_path)
        st.sidebar.success(f"✅ Loaded {len(KNOWLEDGE_BASE)} methodologies from {default_path}")
    else:
        st.error(f"Please upload a CSV file or ensure '{default_path}' exists in the working directory.")
        st.stop()

# Calculate statistics
if KNOWLEDGE_BASE:
    stats = calculate_statistics(KNOWLEDGE_BASE)
else:
    st.error("No data loaded. Please check your CSV file format.")
    st.stop()

# Sidebar Statistics
st.sidebar.markdown("---")
st.sidebar.markdown("### 📈 Dataset Statistics")
if stats:
    st.sidebar.metric("Total Methodologies", stats.get('total_methods', 0))
    st.sidebar.metric("Origin Domains", stats.get('total_origins', 0))
    st.sidebar.metric("Adopting Fields", stats.get('total_adopting_fields', 0))
else:
    st.sidebar.warning("Unable to calculate statistics")

# Sidebar Filters
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Filters")

# Get unique origins and methods
all_origins = sorted(list(set([entry['origin'] for entry in KNOWLEDGE_BASE])))
all_methods = sorted([entry['name'] for entry in KNOWLEDGE_BASE])

filter_origin = st.sidebar.selectbox(
    "Filter by Origin Domain",
    options=["All"] + all_origins,
    index=0
)

filter_method = st.sidebar.selectbox(
    "Filter by Specific Method",
    options=["All"] + all_methods,
    index=0
)

min_connections = st.sidebar.slider(
    "Minimum Adoption Connections",
    min_value=0,
    max_value=10,
    value=0,
    help="Show only methods adopted by at least this many fields"
)

# Sidebar Legend
st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Legend")
st.sidebar.markdown("🔴 **Circle:** Scientific Field")
st.sidebar.markdown("🟦 **Square:** Methodology")
st.sidebar.markdown("➖ **Solid Line:** Origin")
st.sidebar.markdown("--- **Dashed Line:** Adoption")

# Apply filters
filter_origin_val = None if filter_origin == "All" else filter_origin
filter_method_val = None if filter_method == "All" else filter_method

# Build and Render Graph
graph = build_graph(
    KNOWLEDGE_BASE, 
    filter_origin=filter_origin_val,
    filter_method=filter_method_val,
    min_connections=min_connections
)

# Check if graph has nodes
if graph.number_of_nodes() == 0:
    st.warning("⚠️ No methodologies match the current filters. Please adjust your selection.")
else:
    st.info(
        f"📊 Displaying **{len([n for n in graph.nodes() if graph.nodes[n]['group'] == 'Method'])} methods** "
        f"across **{len([n for n in graph.nodes() if graph.nodes[n]['group'] == 'Field'])} fields**. "
        f"Hover over nodes for details. Drag to rearrange."
    )
    
    pyvis_network = render_pyvis(graph)

    # Save and Display
    try:
        # Create a temporary file to save the HTML
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
            pyvis_network.save_graph(tmp_file.name)
            
            # Read the HTML file back
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                html_data = f.read()
                
        # Render in Streamlit
        st.components.v1.html(html_data, height=800, scrolling=False)

        # Cleanup
        os.remove(tmp_file.name)

    except Exception as e:
        st.error(f"Error rendering graph: {e}")

# Expandable Statistics Section
with st.expander("📊 View Detailed Statistics"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Top 5 Origin Domains")
        st.dataframe(
            stats['top_origins'].reset_index().rename(columns={'index': 'Domain', 0: 'Methods Count'}),
            hide_index=True
        )
    
    with col2:
        st.markdown("#### Top 5 Adopting Fields")
        st.dataframe(
            stats['top_adopters'].reset_index().rename(columns={'index': 'Field', 0: 'Adoptions Count'}),
            hide_index=True
        )

# Data Table View
with st.expander("📋 View Raw Data Table"):
    df_display = pd.DataFrame(KNOWLEDGE_BASE)
    st.dataframe(
        df_display[['name', 'origin', 'adopted_by']], 
        hide_index=True,
        use_container_width=True
    )

# Footer
st.markdown("---")
st.caption(
    "Visualization of cross-disciplinary methodology transfer. "
    "Built with Streamlit, NetworkX, and PyVis. "
    "Data represents the epistemological migration of scientific methods across domains."
)