import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import hashlib
import io
import time as pytime
import secrets
import string
from supabase import create_client, Client

# --- 1. CONFIGURATION & SUPABASE CONNECTION ---
st.set_page_config(layout="wide", page_title="AeroControl Tower", page_icon="✈️")

# Retrieve secrets
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ Supabase connection error. Check your 'Secrets' in Streamlit Cloud.")
    st.stop()

# --- CSS (DESIGN, ANIMATIONS, STICKY & VISITOR) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    
    /* CARTES */
    .job-card {
        padding: 10px 14px; 
        border-radius: 8px; 
        margin-bottom: 8px; 
        background-color: rgba(255, 255, 255, 0.05) !important; 
        border-left: 5px solid #FFCC80; 
        border-top: 1px solid rgba(255,255,255,0.1);
        border-right: 1px solid rgba(255,255,255,0.1);
        border-bottom: 1px solid rgba(255,255,255,0.1);
        transition: all 0.2s ease;
    }
    .job-card-active {
        border-left: 5px solid #2ECC71; 
        background-color: rgba(46, 204, 113, 0.05) !important;
        border-top: 1px solid rgba(46, 204, 113, 0.2);
        border-right: 1px solid rgba(46, 204, 113, 0.2);
        border-bottom: 1px solid rgba(46, 204, 113, 0.2);
    }
    .job-card-flash {
        animation: flash-blue 1s ease-in-out 3;
        border-left: 5px solid #3498DB !important;
    }
    @keyframes flash-blue {
        0% { border-left-color: #3498DB; background-color: rgba(52, 152, 219, 0.2); }
        50% { border-left-color: #fff; background-color: rgba(52, 152, 219, 0.4); }
        100% { border-left-color: #3498DB; background-color: rgba(255, 255, 255, 0.05); }
    }

    /* VISITOR SPECIFIC */
    .visitor-card {
        border: 1px solid #444;
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }

    /* KEY DISPLAY */
    .key-box {
        background-color: #1C2833;
        border: 1px dashed #5D6D7E;
        padding: 15px;
        border-radius: 5px;
        text-align: center;
        font-family: monospace;
        font-size: 1.2em;
        margin-top: 10px;
        color: #85C1E9;
    }

    /* UTILS */
    .small-text { font-size: 0.8rem !important; opacity: 0.9; line-height: 1.4; }
    div[data-testid="column"] .stButton button {
        border-radius: 4px; padding: 0px 8px; font-size: 0.8rem; height: 30px; min-height: 30px;
    }
    .stRadio > div { gap: 15px; margin-bottom: 10px; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) {
        position: sticky; top: 3.5rem; max-height: 88vh; overflow-y: auto; padding-right: 10px; z-index: 99;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(1)::-webkit-scrollbar { width: 0px; background: transparent; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# SECURITY & DATABASE MODULE
# =============================================================================

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def save_user(email, password, first_name, last_name, company, role):
    hashed_pw = make_hashes(password)
    data = {
        "email": email, "password": hashed_pw, 
        "first_name": first_name, "last_name": last_name, 
        "company": company, "role": role, "Status": True 
    }
    try:
        supabase.table("users_table").insert(data).execute()
        return True
    except: return False

def login_user(email, password):
    hashed_pw = make_hashes(password)
    try:
        res = supabase.table("users_table").select("*").eq("email", email).execute()
        if res.data and res.data[0].get('password') == hashed_pw: return res.data[0]
    except: pass
    return None

# --- ACCESS CONTROL HELPERS ---
def grant_viewer_access(viewer_email, folder_key):
    """Links a viewer to a folder if the key matches."""
    try:
        folder_res = supabase.table("folders_table").select("id, name").eq("access_key", folder_key).execute()
        if not folder_res.data:
            return False, "Invalid Key"
        
        folder_id = folder_res.data[0]['id']
        folder_name = folder_res.data[0]['name']
        
        data = {"viewer_email": viewer_email, "folder_id": folder_id}
        supabase.table("viewer_access").insert(data).execute()
        return True, folder_name
    except Exception as e:
        if "duplicate" in str(e) or "unique" in str(e):
             return True, "Already Accessed"
        return False, str(e)

def get_viewer_folders(viewer_email):
    """Get folders unlocked by this viewer"""
    try:
        access_res = supabase.table("viewer_access").select("folder_id").eq("viewer_email", viewer_email).execute()
        if not access_res.data: return []
        
        ids = [r['folder_id'] for r in access_res.data]
        folders_res = supabase.table("folders_table").select("*").in_("id", ids).execute()
        return folders_res.data
    except: return []

# --- JOB FUNCTIONS ---
def load_jobs(user_email):
    try:
        res = supabase.table("jobs_table").select("*").eq("owner_email", user_email).order("id", desc=True).execute()
        return res.data if res.data else []
    except: return []

def load_folder_jobs(folder_id):
    try:
        res = supabase.table("jobs_table").select("*").eq("folder_id", folder_id).eq("active", True).execute()
        return res.data if res.data else []
    except: return []

def check_duplicate_name(task_name, user_email, exclude_id=None):
    try:
        query = supabase.table("jobs_table").select("id").eq("owner_email", user_email).eq("task_name", task_name)
        if exclude_id: query = query.neq("id", exclude_id)
        res = query.execute()
        return len(res.data) > 0
    except: return False

def add_job(job_data):
    try:
        job_data.pop('id', None) 
        res = supabase.table("jobs_table").insert(job_data).execute()
        if res.data: return res.data[0]['id']
        return True
    except: return False

def update_job(job_id, update_data):
    try:
        supabase.table("jobs_table").update(update_data).eq("id", job_id).execute()
        return True
    except: return False

# --- FOLDER FUNCTIONS (AUTOMATIC KEY) ---
def get_folders(user_email):
    try:
        res = supabase.table("folders_table").select("*").eq("owner_email", user_email).order("created_at").execute()
        return res.data if res.data else []
    except: return []

def generate_secure_key(length=10):
    """Generates a random secure key"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

def create_folder(name, user_email):
    """Creates folder with AUTOMATIC key generation"""
    try:
        # Check duplicate
        existing = supabase.table("folders_table").select("id").eq("owner_email", user_email).eq("name", name).execute()
        if existing.data: return False, None
        
        # Generate Key
        auto_key = generate_secure_key()
        
        supabase.table("folders_table").insert({
            "name": name, 
            "owner_email": user_email, 
            "access_key": auto_key
        }).execute()
        return True, auto_key
    except Exception as e: return False, None

def delete_folder(folder_id):
    try:
        supabase.table("folders_table").delete().eq("id", folder_id).execute()
        return True
    except: return False

def rename_folder_data(folder_id, new_name, new_key):
    try:
        supabase.table("folders_table").update({"name": new_name, "access_key": new_key}).eq("id", folder_id).execute()
        return True
    except: return False

def move_job_to_folder(job_id, folder_id):
    try:
        fid = folder_id if folder_id and folder_id > 0 else None
        supabase.table("jobs_table").update({"folder_id": fid}).eq("id", job_id).execute()
        return True
    except: return False

# =============================================================================
# EXPORT ENGINE & DATA PROCESSING
# =============================================================================
@st.cache_data
def load_data(uploaded_file):
    if uploaded_file is None: return None
    try:
        if uploaded_file.name.endswith('.csv'): df = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)
        else: df = pd.read_excel(uploaded_file, dtype=str, keep_default_na=False)
        for col in df.columns:
            if 'date' in col.lower(): df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
            else:
                try: df[col] = pd.to_numeric(df[col], errors='ignore')
                except: pass
        return df.fillna("")
    except: return None

def filter_date(df, date_col, days):
    if days == 0 or not days or date_col not in df.columns: return df
    try:
        temp_df = df.copy()
        temp_df[date_col] = pd.to_datetime(temp_df[date_col], dayfirst=True, errors='coerce')
        cutoff = datetime.now() - timedelta(days=days)
        return df.loc[temp_df[temp_df[date_col] >= cutoff].index]
    except: return df

def process_report_dataframe(df_raw, job_config):
    """Processes filters and returns a CLEAN DATAFRAME"""
    try:
        df = df_raw.copy()
        filters = job_config.get('filters_config', {})
        if filters is None: filters = {}
        
        # 1. Master Filters
        for col, selected_vals in filters.items():
            if col not in ["retention_days", "date_column", "display_columns", "custom_code"] and col in df.columns:
                if isinstance(selected_vals, list):
                    if selected_vals: df = df[df[col].astype(str).isin(selected_vals)]
                else:
                    if selected_vals and selected_vals != "ALL": df = df[df[col].astype(str) == selected_vals]

        # 2. Date
        days = filters.get("retention_days", 0)
        date_col = filters.get("date_column")
        if days and days > 0 and date_col and date_col in df.columns:
             df = filter_date(df, date_col, days)
             
        # 3. Code
        code = filters.get("custom_code")
        if code:
            try: df = df.query(code)
            except: pass
            
        # 4. Columns
        cols = filters.get("display_columns")
        if cols:
            valid_cols = [c for c in cols if c in df.columns]
            if valid_cols: df = df[valid_cols]
            
        return df
    except Exception as e:
        return None

def generate_report_file(df_raw, job_config):
    try:
        df = process_report_dataframe(df_raw, job_config)
        if df is None: return None, "Error processing data", None
        
        fmt = job_config.get('format', 'Excel (.xlsx)')
        output = io.BytesIO()
        
        if "CSV" in fmt:
            df.to_csv(output, index=False)
            mime = "text/csv"; ext = ".csv"
        else:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Report')
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; ext = ".xlsx"
            
        output.seek(0)
        return output, mime, ext
    except Exception as e:
        return None, str(e), None

# =============================================================================
# DATA STORAGE HELPERS
# =============================================================================
def save_imported_data(df, user_email):
    try:
        supabase.table("raw_data_table").delete().eq("owner_email", user_email).execute()
        df_save = df.copy()
        for col in df_save.columns:
            if pd.api.types.is_datetime64_any_dtype(df_save[col]): df_save[col] = df_save[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_save = df_save.where(pd.notnull(df_save), None)
        all_rows = [{"owner_email": user_email, "row_data": row} for row in df_save.to_dict(orient='records')]
        chunk_size = 5000
        total = len(all_rows)
        progress = st.progress(0, text="Syncing...")
        for i in range(0, total, chunk_size):
            chunk = all_rows[i : i + chunk_size]
            supabase.table("raw_data_table").insert(chunk).execute()
            progress.progress(min((i + chunk_size) / total, 1.0))
        progress.empty()
        return True
    except: return False

def load_stored_data(target_email):
    try:
        all_data = []
        start = 0
        while True:
            res = supabase.table("raw_data_table").select("row_data").eq("owner_email", target_email).range(start, start + 9999).execute()
            if not res.data: break
            all_data.extend([item['row_data'] for item in res.data])
            if len(res.data) < 10000: break
            start += 10000
        return pd.DataFrame(all_data) if all_data else None
    except: return None

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def run_mro_app():
    user_role = st.session_state.get('user_role', 'viewer')
    
    # --- SESSION STATE INIT ---
    if 'edit_mode' not in st.session_state: st.session_state['edit_mode'] = False
    if 'current_view' not in st.session_state: 
        st.session_state['current_view'] = "Visualization" if user_role != 'viewer' else "Visitor"

    # Blinking State
    if 'last_updated_id' not in st.session_state: st.session_state['last_updated_id'] = None
    if 'last_updated_time' not in st.session_state: st.session_state['last_updated_time'] = 0

    # Persistence
    if 'visu_saved_master_cols' not in st.session_state: st.session_state['visu_saved_master_cols'] = []
    if 'visu_saved_period' not in st.session_state: st.session_state['visu_saved_period'] = "View All"
    if 'visu_saved_custom_code' not in st.session_state: st.session_state['visu_saved_custom_code'] = ""
    if 'visu_saved_filters_values' not in st.session_state: st.session_state['visu_saved_filters_values'] = {}
    
    # --- SIDEBAR ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_first_name']} {st.session_state['user_last_name']}**")
        st.caption(f"🛡️ Role: {user_role.upper()} | {st.session_state['user_company']}")
        
        if user_role != 'viewer' and st.session_state['edit_mode']:
            st.warning("✏️ **EDIT MODE ACTIVE**")
            
        if st.button("Logout", type="primary"):
            st.session_state['logged_in'] = False
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        st.markdown("---")

    st.title("✈️ MRO Control Tower")

    # --- ADMIN / USER LOGIC ---
    if user_role in ['admin', 'user']:
        
        with st.expander("📂 Data Source", expanded=False):
            uploaded_file = st.file_uploader("Excel/CSV File", type=['xlsx', 'csv'])
        
        df_raw = None
        if uploaded_file is not None:
            df_raw = load_data(uploaded_file)
            if df_raw is not None:
                save_imported_data(df_raw, st.session_state['user_email'])
                st.session_state['df_persistent'] = df_raw
                st.success(f"✅ Data synchronized: {len(df_raw)} rows.")
        else:
            if 'df_persistent' not in st.session_state or st.session_state['df_persistent'] is None:
                with st.spinner("🔄 Retrieving saved data..."):
                    st.session_state['df_persistent'] = load_stored_data(st.session_state['user_email'])
            df_raw = st.session_state['df_persistent']

        if df_raw is None:
            st.info("👋 Welcome! Please import a file to activate the tools.")
            return
            
        if 'visu_saved_display_cols' not in st.session_state:
            st.session_state['visu_saved_display_cols'] = list(df_raw.columns)

        # MENU
        view_options = ["Visualization", "Schedule & Edit", "Folders", "Visitor (Preview)"]
        def update_view(): st.session_state['current_view'] = st.session_state['nav_radio']
        if st.session_state['current_view'] not in view_options: st.session_state['current_view'] = "Visualization"
        selected_view = st.radio("", options=view_options, index=view_options.index(st.session_state['current_view']), horizontal=True, key="nav_radio", on_change=update_view, label_visibility="collapsed")

        # --- VISUALIZATION ---
        if st.session_state['current_view'] == "Visualization":
            with st.expander("⚙️ Filter & Column Configuration", expanded=True):
                c1, c2, c3 = st.columns([1, 1, 2])
                cols_date = [c for c in df_raw.columns if 'date' in c.lower()]
                default_date = cols_date[0] if cols_date else df_raw.columns[0]
                date_col = c1.selectbox("Reference Date Column", df_raw.columns, index=list(df_raw.columns).index(default_date))
                
                master_filter_cols = c2.multiselect("Define Master Filters", [c for c in df_raw.columns if c != date_col], default=st.session_state['visu_saved_master_cols'], key="master_cols_select")
                
                all_cols = list(df_raw.columns)
                display_opts = ["(Select All)"] + all_cols
                user_selection = c3.multiselect("Columns to Display", options=display_opts, default=st.session_state['visu_saved_display_cols'], key="visu_columns_select")
                if "(Select All)" in user_selection: displayed_columns = all_cols
                else: displayed_columns = user_selection

            with st.expander("🧑‍💻 Advanced Filter (Python/SQL)"):
                st.caption("Write a Pandas query string.")
                custom_query = st.text_area("Custom Code", value=st.session_state['visu_saved_custom_code'], height=70, key="visu_custom_code")

            def reset_all_filters():
                for key in list(st.session_state.keys()):
                    if key.startswith("dyn_"): del st.session_state[key]
                st.session_state['visu_saved_master_cols'] = []
                st.session_state['visu_saved_period'] = "View All"
                st.session_state['visu_saved_custom_code'] = ""
                st.session_state['visu_saved_display_cols'] = list(df_raw.columns)
                st.session_state['visu_saved_filters_values'] = {}
                if "master_cols_select" in st.session_state: del st.session_state["master_cols_select"]
                if "visu_columns_select" in st.session_state: del st.session_state["visu_columns_select"]
                if "visu_custom_code" in st.session_state: del st.session_state["visu_custom_code"]
                if "period_radio" in st.session_state: del st.session_state["period_radio"]

            col_title, col_reset = st.columns([4, 1])
            with col_title: st.markdown("##### 🔍 Master Filters")
            with col_reset: st.button("🔄 Reset Filters", on_click=reset_all_filters, use_container_width=True)

            df_final = df_raw.copy()
            current_filters_config = {}

            if master_filter_cols:
                filt_cols = st.columns(len(master_filter_cols))
                for i, col_name in enumerate(master_filter_cols):
                    val_counts = df_final[col_name].astype(str).value_counts()
                    display_options = [f"{val} ({count})" for val, count in val_counts.items()]
                    saved_defaults = st.session_state['visu_saved_filters_values'].get(col_name, [])
                    valid_defaults = [opt for opt in saved_defaults if opt in display_options]
                    
                    selected_display = filt_cols[i].multiselect(f"{col_name}", display_options, key=f"dyn_{col_name}", default=valid_defaults)
                    st.session_state['visu_saved_filters_values'][col_name] = selected_display
                    
                    if selected_display:
                        selected_clean = [s.rpartition(' (')[0] for s in selected_display]
                        df_final = df_final[df_final[col_name].astype(str).isin(selected_clean)]
                        current_filters_config[col_name] = selected_clean

            st.markdown("---")
            if custom_query:
                try: df_final = df_final.query(custom_query); current_filters_config['custom_code'] = custom_query
                except Exception as e: st.error(f"⚠️ Syntax Error: {e}")

            c_time, c_kpi = st.columns([2, 1])
            with c_time:
                period = st.radio("Period:", ["View All", "7 Days", "30 Days", "60 Days", "180 Days"], index=["View All", "7 Days", "30 Days", "60 Days", "180 Days"].index(st.session_state['visu_saved_period']), horizontal=True, key="period_radio")
                days_map = {"View All": 0, "7 Days": 7, "30 Days": 30, "60 Days": 60, "180 Days": 180}
                days = days_map[period]
                df_final = filter_date(df_final, date_col, days)
                current_filters_config["retention_days"] = days; current_filters_config["date_column"] = date_col; current_filters_config["display_columns"] = displayed_columns

            with c_kpi: st.metric("Displayed Rows", len(df_final), delta=f"out of {len(df_raw)} total")
            st.dataframe(df_final, column_order=displayed_columns, use_container_width=True, height=500, hide_index=True)
            
            st.session_state['visu_saved_master_cols'] = master_filter_cols
            st.session_state['visu_saved_display_cols'] = displayed_columns
            st.session_state['visu_saved_custom_code'] = custom_query
            st.session_state['visu_saved_period'] = period
            st.session_state['active_filters'] = current_filters_config

        # --- SCHEDULE & EDIT ---
        elif st.session_state['current_view'] == "Schedule & Edit":
            folders = get_folders(st.session_state['user_email'])
            folder_options = {0: "📂 No Folder"} 
            for f in folders: folder_options[f['id']] = f"📁 {f['name']}"

            col_form, col_list = st.columns([1, 1.4])
            with col_form:
                if st.button("➕ NEW REPORT", use_container_width=True):
                    st.session_state['edit_mode'] = False; st.session_state['edit_job_id'] = None; st.session_state['edit_job_data'] = {}; st.rerun()

                if st.session_state['edit_mode']:
                    st.subheader("✏️ Edit Report")
                    edit_data = st.session_state['edit_job_data']
                    def_name = edit_data.get('task_name', ''); def_recip = edit_data.get('recipient', ''); def_subj = edit_data.get('email_subject', ''); def_msg = edit_data.get('custom_message', '')
                    def_hour = datetime.strptime(edit_data.get('hour', '08:00:00'), '%H:%M:%S').time()
                    old_freq_str = edit_data.get('frequency', '')
                    try:
                        old_days_part = old_freq_str.split('(')[0].strip(); old_rec_part = old_freq_str.split('(')[1].replace(')', '').strip()
                        def_days = [d.strip() for d in old_days_part.split(',')]; idx_rec = ["Every week", "Every 2 weeks", "Every 4 weeks"].index(old_rec_part)
                    except: def_days = ["Monday"]; idx_rec = 0
                    def_fid = edit_data.get('folder_id', 0)
                    current_saved_filters = edit_data.get('filters_config', {})
                else:
                    st.subheader("🚀 New Report")
                    def_name = ""; def_recip = ""; def_subj = ""; def_msg = ""; def_hour = time(8, 0); def_days = ["Monday"]; idx_rec = 0; def_fid = 0; current_saved_filters = {}

                active_visu_filters = st.session_state.get('active_filters', {})
                if 'form_filters' not in st.session_state: st.session_state['form_filters'] = current_saved_filters

                with st.expander("⚙️ Filter Import Configuration", expanded=True):
                    c_imp, c_prev = st.columns([1, 1])
                    with c_imp:
                        if st.button("📥 Import Active Filters", use_container_width=True):
                            st.session_state['form_filters'] = active_visu_filters
                            st.session_state['flash_success'] = True
                            if st.session_state['edit_mode']: st.session_state['edit_job_data']['filters_config'] = active_visu_filters
                            st.rerun()
                    with c_prev:
                        lbl = "Config Preview:"; 
                        if st.session_state.get('flash_success'): lbl += " <span class='flash-success'>●</span>"; del st.session_state['flash_success']
                        st.markdown(lbl, unsafe_allow_html=True); st.json(st.session_state['form_filters'], expanded=False)

                with st.form("job_form", border=True):
                    job_name = st.text_input("Report Name", value=def_name)
                    recipients = st.text_input("Recipient Emails", value=def_recip)
                    st.caption("ℹ️ Use commas to separate multiple emails")
                    subject = st.text_input("Email Subject", value=def_subj)
                    custom_msg = st.text_area("Message", value=def_msg, height=80, max_chars=2000)
                    st.write("**Delivery Configuration**")
                    selected_days = st.multiselect("Days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], default=def_days)
                    recurrence = st.selectbox("Interval", ["Every week", "Every 2 weeks", "Every 4 weeks"], index=idx_rec)
                    initial_folder = st.selectbox("Folder", options=list(folder_options.keys()), format_func=lambda x: folder_options[x], index=list(folder_options.keys()).index(def_fid) if def_fid in folder_options else 0)
                    c_time, c_fmt = st.columns(2)
                    send_time = c_time.time_input("Time", value=def_hour)
                    fmt = c_fmt.selectbox("Format", ["Excel (.xlsx)", "CSV"])
                    
                    if st.form_submit_button("💾 Save/Update", use_container_width=True):
                        if job_name and recipients and selected_days:
                            exclude_id = st.session_state['edit_job_id'] if st.session_state['edit_mode'] else None
                            if check_duplicate_name(job_name, st.session_state['user_email'], exclude_id): st.error("Exists!")
                            else:
                                freq = f"{', '.join(selected_days)} ({recurrence})"
                                payload = {
                                    "task_name": job_name, "recipient": recipients, "email_subject": subject, "custom_message": custom_msg,
                                    "frequency": freq, "hour": str(send_time), "format": fmt, "folder_id": initial_folder if initial_folder > 0 else None,
                                    "filters_config": st.session_state.get('form_filters', {})
                                }
                                if not st.session_state['edit_mode']:
                                    payload.update({"owner_email": st.session_state['user_email'], "active": False})
                                    nid = add_job(payload)
                                    if nid: st.success("Saved!"); st.session_state['form_filters'] = {}; st.session_state['last_updated_id'] = nid; st.session_state['last_updated_time'] = pytime.time(); st.rerun()
                                else:
                                    if update_job(st.session_state['edit_job_id'], payload):
                                        st.success("Updated!"); st.session_state['last_updated_id'] = st.session_state['edit_job_id']; st.session_state['last_updated_time'] = pytime.time()
                                        st.session_state['edit_mode'] = False; st.session_state['edit_job_id'] = None; st.session_state['form_filters'] = {}; st.rerun()
                        else: st.error("Fill mandatory fields.")

            with col_list:
                c_head, c_search = st.columns([1, 1])
                with c_head: st.subheader("📋 Scheduled")
                with c_search: search_sched = st.text_input("🔍 Search reports", label_visibility="collapsed")
                my_jobs = load_jobs(st.session_state['user_email'])
                if search_sched: my_jobs = [j for j in my_jobs if search_sched.lower() in j['task_name'].lower()]

                if not my_jobs: st.info("No reports.")
                for job in my_jobs:
                    target_id = int(job['id']); is_active = job['active']
                    card_class = "job-card-active" if is_active else "job-card"
                    if st.session_state.get('last_updated_id') == target_id:
                        if pytime.time() - st.session_state.get('last_updated_time', 0) < 3: card_class += " job-card-flash"
                    
                    folder_label = folder_options.get(job.get('folder_id', 0) or 0, "No Folder")
                    with st.container():
                        st.markdown(f"""<div class="{card_class}"></div>""", unsafe_allow_html=True)
                        c_info, c_btns = st.columns([2.5, 1.2])
                        with c_info:
                            st.markdown(f"**{job['task_name']}** {'🟢' if is_active else '🟠'}")
                            st.markdown(f"<div class='small-text'>{folder_label} | {job['frequency']} @ {job['hour']}<br>📧 {job['recipient']}</div>", unsafe_allow_html=True)
                        with c_btns:
                            if st.button("⏸️" if is_active else "▶️", key=f"tog_{target_id}", use_container_width=True):
                                supabase.table("jobs_table").update({"active": not is_active}).eq("id", target_id).execute(); st.rerun()
                            b_edit, b_exp, b_del = st.columns(3)
                            with b_edit:
                                if st.button("✏️", key=f"edt_{target_id}", disabled=is_active):
                                    st.session_state['edit_mode'] = True; st.session_state['edit_job_id'] = target_id; st.session_state['edit_job_data'] = job
                                    st.session_state['form_filters'] = job.get('filters_config', {}); st.rerun()
                            with b_exp:
                                if st.button("⚡", key=f"prepexp_{target_id}", help="Export"):
                                    with st.spinner("."):
                                        fd, m, e = generate_report_file(df_raw, job)
                                        if fd: st.download_button("⬇️", data=fd, file_name=f"{job['task_name']}{e}", mime=m, key=f"dl_{target_id}")
                                        else: st.error("Err")
                            with b_del:
                                with st.popover("🗑️", disabled=is_active):
                                    if st.button("YES", key=f"conf_del_{target_id}", type="primary"): supabase.table("jobs_table").delete().eq("id", target_id).execute(); st.rerun()
                        st.divider()

        # --- FOLDERS (AUTOMATIC KEY) ---
        elif st.session_state['current_view'] == "Folders":
            st.subheader("📂 Folder Management")
            search_query = st.text_input("🔍 Search Folders or Reports", placeholder="Type a name...")
            
            with st.expander("➕ Create New Folder", expanded=False):
                with st.form("create_folder"):
                    c_new, c_sub = st.columns([3, 1])
                    new_fname = c_new.text_input("New Folder Name")
                    
                    if c_sub.form_submit_button("Create & Generate Key"):
                        if new_fname:
                            success, generated_key = create_folder(new_fname, st.session_state['user_email'])
                            if success:
                                st.success("Folder created successfully!")
                                st.markdown(f"""
                                <div class="key-box">
                                    🔑 KEY: {generated_key}
                                </div>
                                """, unsafe_allow_html=True)
                                st.caption("⚠️ Copy this key and send it to your client. It allows access to this folder.")
                            else: st.error("Exists already!")
            
            st.markdown("---")
            all_folders = get_folders(st.session_state['user_email']); all_jobs = load_jobs(st.session_state['user_email'])
            if search_query:
                q = search_query.lower(); filtered_folders = []
                for f in all_folders:
                    jobs_in = [j for j in all_jobs if j.get('folder_id') == f['id']]
                    if q in f['name'].lower() or any(q in j['task_name'].lower() for j in jobs_in): filtered_folders.append(f)
            else: filtered_folders = all_folders

            if not filtered_folders: st.info("No folders.")
            for folder in filtered_folders:
                fid = folder['id']; fname = folder['name']
                jobs_in = [j for j in all_jobs if j.get('folder_id') == fid]
                if search_query: jobs_in = [j for j in jobs_in if search_query.lower() in j['task_name'].lower()]
                
                with st.expander(f"📁 **{fname}** ({len(jobs_in)})", expanded=(True if search_query else False)):
                    c_ren, c_rkey, c_btn, c_del_f = st.columns([2, 1, 1, 1])
                    new_n = c_ren.text_input("Rename", value=fname, key=f"ren_{fid}")
                    # Show key partially masked or full? Let's show full for admin convenience in edit
                    new_k = c_rkey.text_input("Key", value=folder.get('access_key',''), key=f"key_{fid}")
                    if c_btn.button("💾", key=f"bsave_{fid}"):
                        rename_folder_data(fid, new_n, new_k); st.rerun()
                    with c_del_f:
                        with st.popover("🗑️"):
                            if st.button("YES", key=f"del_f_{fid}", type="primary"): delete_folder(fid); st.rerun()
                    
                    st.divider()
                    for j in jobs_in:
                        jid = j['id']
                        c1, c2, c3 = st.columns([3, 1, 1])
                        c1.markdown(f"📄 **{j['task_name']}**")
                        with c2:
                            if st.button("✏️", key=f"f_ed_{jid}"):
                                st.session_state['edit_mode'] = True; st.session_state['edit_job_id'] = jid; st.session_state['edit_job_data'] = j
                                st.session_state['form_filters'] = j.get('filters_config', {}); st.session_state['current_view'] = "Schedule & Edit"; st.rerun()
                        with c3:
                            if st.button("⚡", key=f"f_ex_{jid}"):
                                with st.spinner("."):
                                    fd, m, e = generate_report_file(df_raw, j)
                                    if fd: st.download_button("⬇️", data=fd, file_name=f"{j['task_name']}{e}", mime=m, key=f"f_dl_{jid}")

            if not search_query:
                orphans = [j for j in all_jobs if not j.get('folder_id') or j.get('folder_id') == 0]
                if orphans:
                    st.markdown("### 📂 Uncategorized"); 
                    for j in orphans: st.markdown(f"📄 **{j['task_name']}**")

    # --- VISITOR (PREVIEW) ---
    if user_role != 'viewer' and st.session_state['current_view'] == "Visitor (Preview)":
        st.info("ℹ️ This is how your clients will see the Visitor page.")

    # =========================================================================
    # VISITOR INTERFACE (VIEWER ROLE)
    # =========================================================================
    if user_role == 'viewer':
        st.subheader(f"👋 Welcome, {st.session_state['user_first_name']}")
        
        with st.expander("🔓 Unlock a Folder", expanded=False):
            with st.form("unlock_form"):
                key_input = st.text_input("Enter Access Key (provided by your administrator)", type="password")
                if st.form_submit_button("Unlock Access"):
                    success, msg = grant_viewer_access(st.session_state['user_email'], key_input)
                    if success: st.success(f"Successfully unlocked: {msg}"); st.rerun()
                    else: 
                        if msg == "Already Accessed": st.info("You already have access to this folder.")
                        else: st.error("Invalid Key.")

        st.markdown("---")
        my_folders = get_viewer_folders(st.session_state['user_email'])
        
        if not my_folders:
            st.info("You haven't unlocked any folders yet. Enter a key above.")
        else:
            selected_folder_name = st.selectbox("📁 Select Folder", [f['name'] for f in my_folders])
            selected_folder_id = next(f['id'] for f in my_folders if f['name'] == selected_folder_name)
            
            folder_owner_res = supabase.table("folders_table").select("owner_email").eq("id", selected_folder_id).execute()
            if folder_owner_res.data:
                owner_email = folder_owner_res.data[0]['owner_email']
                with st.spinner("Loading secure data..."):
                    df_owner_raw = load_stored_data(owner_email)
                
                if df_owner_raw is not None:
                    folder_jobs = load_folder_jobs(selected_folder_id)
                    if not folder_jobs: st.warning("No active reports in this folder.")
                    else:
                        selected_job_name = st.selectbox("📄 Select Report", [j['task_name'] for j in folder_jobs])
                        selected_job = next(j for j in folder_jobs if j['task_name'] == selected_job_name)
                        st.markdown("### Report Preview")
                        df_viewer = process_report_dataframe(df_owner_raw, selected_job)
                        if df_viewer is not None:
                             st.dataframe(df_viewer, use_container_width=True, height=600)
                             fd, m, e = generate_report_file(df_owner_raw, selected_job)
                             if fd: st.download_button("⬇️ Download Excel/CSV", data=fd, file_name=f"{selected_job['task_name']}{e}", mime=m)
                        else: st.error("Error processing this report configuration.")
                else: st.error("Data source unavailable.")


# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.title("🔒 AeroTrack Access")
            choice = st.selectbox("Action", ["Login", "Sign Up"])
            
            if choice == "Login":
                with st.form("login"):
                    e = st.text_input("Email")
                    p = st.text_input("Password", type='password')
                    if st.form_submit_button("Connect"):
                        u = login_user(e, p)
                        if u:
                            st.session_state.update({
                                "logged_in": True, "user_email": u['email'], 
                                "user_first_name": u['first_name'], "user_last_name": u['last_name'], 
                                "user_company": u['company'], "user_role": u.get('role', 'viewer')
                            })
                            st.rerun()
                        else: st.error("Authentication failed.")
            else:
                with st.form("signup"):
                    st.write("Create a new account")
                    fn = st.text_input("First Name")
                    ln = st.text_input("Last Name")
                    cp = st.text_input("Company")
                    em = st.text_input("Work Email")
                    pw = st.text_input("Password", type='password')
                    
                    # PLUS DE CHOIX DE RÔLE ICI
                    
                    if st.form_submit_button("Create Account"):
                        if em and pw:
                            # Par défaut, on inscrit tout le monde en 'viewer' (sécurité maximale)
                            if save_user(em, pw, fn, ln, cp, 'viewer'): 
                                st.success("Account created! Please log in.")
                                st.info("Note: Your account has 'Viewer' access by default. Contact your administrator to upgrade your rights.")
                        else:
                            st.error("Please fill all fields.")
    else:
        run_mro_app()

if __name__ == "__main__":
    main()