from streamlit.elements.lib.layout_utils import TextAlignment
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client
import graphviz
import os
from dotenv import load_dotenv

# --- 1. KONFIGURASI HALAMAN (Mobile Friendly) ---
st.set_page_config(
    page_title="Silsilah Keluarga", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# JavaScript untuk Memaksa Zoom di Android (Chrome/Brave)
st.components.v1.html(
    """
    <script>
        // Mencari tag viewport yang sudah ada atau membuat baru
        var meta = document.querySelector('meta[name="viewport"]');
        if (!meta) {
            meta = document.createElement('meta');
            meta.name = "viewport";
            document.getElementsByTagName('head')[0].appendChild(meta);
        }
        // Paksa skala agar bisa di-zoom (user-scalable=yes)
        meta.content = "width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes";
        
        // Opsional: Memaksa zoom lewat event touch (jika browser sangat kaku)
        document.addEventListener('touchstart', function(event) {
            if (event.touches.length > 1) {
                event.preventDefault();
            }
        }, { passive: false });
    </script>
    """,
    height=0, # Agar tidak memakan ruang di UI
)

# 1. Fungsi untuk Merender Graphviz dengan Fitur Zoom & Pan Otomatis
def st_graphviz_zoomable(dot_string):
    html_code = f"""
    <div id="graph" style="text-align: center;"></div>
    <script src="https://d3js.org/d3.v5.min.js"></script>
    <script src="https://unpkg.com/@hpcc-js/wasm@0.3.11/dist/index.min.js"></script>
    <script src="https://unpkg.com/d3-graphviz@3.0.5/build/d3-graphviz.js"></script>
    <script>
        d3.select("#graph")
        .graphviz()
        .width(window.innerWidth)
        .height(600)
        .fit(true)
        .zoom(true) // Menyalakan fitur Zoom & Pan secara Native
        .renderDot(`{dot_string}`);
    </script>
    <style>
        #graph svg {{
            width: 100%;
            height: auto;
            cursor: move;
        }}
    </style>
    """
    return components.html(html_code, height=620)

# --- 2. KONFIGURASI SUPABASE ---
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Kredensial Supabase tidak ditemukan. Pastikan file .env sudah dikonfigurasi.")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# --- 3. FUNGSI AMBIL DATA (Dengan Order) ---
def get_family_data():
    try:
        # Mengambil data dengan urutan generasi dan urutan anak
        response = supabase.table("family_tree")\
            .select("*")\
            .order("gen")\
            .order("child_order")\
            .execute()
        return response.data
    except Exception as e:
        st.error(f"Gagal mengambil data dari Supabase: {e}")
        return []

# --- 4. FUNGSI REKURSIF (Lineage) ---
def get_all_connected_lineage(member_id, all_data):
    relevant_ids = set()

    def trace_up(m_id):
        if not m_id or m_id in relevant_ids: return
        curr = next((m for m in all_data if m['fam_id'] == m_id), None)
        if curr:
            relevant_ids.add(m_id)
            trace_up(curr.get('father_id'))
            trace_up(curr.get('mother_id'))

    def trace_down(m_id):
        curr_children = [m['fam_id'] for m in all_data if m.get('father_id') == m_id or m.get('mother_id') == m_id]
        for c_id in curr_children:
            if c_id not in relevant_ids:
                relevant_ids.add(c_id)
                trace_down(c_id)

    trace_up(member_id)
    trace_down(member_id)
    return relevant_ids

# --- 5. ANTARMUKA UTAMA ---
# st.title("🌳 Silsilah Keluarga", text_alignment: TextAlignment.CENTER)
st.html("<h1 style='text-align: center;'>🌳 Silsilah Keluarga</h1>")

data = get_family_data()

if not data:
    st.warning("Data tidak ditemukan atau tabel kosong.")
else:
    # Kontrol Navigasi
    if st.button("🔄 Reset"):
        st.rerun()

    member_names = sorted([m['name'] for m in data])
    search_query = st.selectbox("Pilih Anggota Keluarga:", [""] + member_names)

    # col1, col2 = st.columns([3, 1])
    # with col1:
    #     member_names = sorted([m['name'] for m in data])
    #     search_query = st.selectbox("Pilih Anggota Keluarga:", [""] + member_names)
    # with col2:
    #     if st.button("🔄 Reset"):
    #         st.rerun()

    # Inisialisasi Graphviz dengan Garis Siku (Orthogonal)
    dot = graphviz.Digraph(graph_attr={
        'rankdir': 'TB',
        'splines': 'ortho',  # Membuat garis siku-siku rapi
        'nodesep': '0.8',
        'ranksep': '1.0',
        'bgcolor': 'white'
    })

    # Penentuan ID yang ditampilkan
    if search_query:
        selected = next(m for m in data if m['name'] == search_query)
        sel_id = selected['fam_id']

        mode = st.radio("Tampilan:", ["Keluarga Inti", "Garis Keturunan Lengkap"], horizontal=True)

        if mode == "Garis Keturunan Lengkap":
            relevant_ids = get_all_connected_lineage(sel_id, data)
        else:
            relevant_ids = {sel_id}
            # Tambah Orang Tua & Pasangan (spouse_id)
            for key in ['father_id', 'mother_id', 'spouse_id']:
                if selected.get(key): relevant_ids.add(selected[key])

            # Tambah Saudara & Anak
            f_id, m_id = selected.get('father_id'), selected.get('mother_id')
            relevant_ids.update([m['fam_id'] for m in data if (f_id and m.get('father_id') == f_id) or (m_id and m.get('mother_id') == m_id)])
            children = [m['fam_id'] for m in data if m.get('father_id') == sel_id or m.get('mother_id') == sel_id]
            relevant_ids.update(children)
            # Tambah pasangan dari anak-anak
            for c_id in children:
                c_node = next(m for m in data if m['fam_id'] == c_id)
                if c_node.get('father_id'): relevant_ids.add(c_node['father_id'])
                if c_node.get('mother_id'): relevant_ids.add(c_node['mother_id'])
    else:
        relevant_ids = {m['fam_id'] for m in data}

    # --- 6. PENGGAMBARAN NODE (KOTAK) ---
    for m in data:
        if m['fam_id'] in relevant_ids:
            is_target = (search_query and m['name'] == search_query)
            # Warna Pastel
            fill = "#FFF176" if is_target else ("#B3E5FC" if m['gend'] == 'L' else "#F8BBD0")

            # Label HTML dengan Tabel (Bold & Center)
            label_html = f"""<
                <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">
                    <TR><TD ALIGN="CENTER"><B>{m['name']}</B></TD></TR>
                    <TR><TD ALIGN="CENTER"><FONT POINT-SIZE="14">Gen {m['gen']}</FONT></TD></TR>
                </TABLE>
            >"""

            dot.node(m['fam_id'], label_html, style="filled", fillcolor=fill,
                    shape="box", width="2.0", fontname="Arial")

    # --- 7. PENGGAMBARAN EDGE (GARIS PERNIKAHAN) ---
    processed_couples = set()
    for m in data:
        if m['fam_id'] in relevant_ids:
            f_id = m.get('father_id')
            m_id = m.get('mother_id')

            if f_id and m_id and f_id in relevant_ids and m_id in relevant_ids:
                couple_id = f"marriage_{f_id}_{m_id}"
                if couple_id not in processed_couples:
                    dot.node(couple_id, label="", shape="point", width="0.01")
                    dot.edge(f_id, couple_id, arrowhead="none", color="#757575")
                    dot.edge(m_id, couple_id, arrowhead="none", color="#757575")
                    processed_couples.add(couple_id)
                dot.edge(couple_id, m['fam_id'], color="#424242")

            elif f_id and f_id in relevant_ids:
                dot.edge(f_id, m['fam_id'], color="#424242")
            elif m_id and m_id in relevant_ids:
                dot.edge(m_id, m['fam_id'], color="#424242")

    # Tampilkan Chart
    # st.graphviz_chart(dot, use_container_width=True)  
    st_graphviz_zoomable(dot.source)