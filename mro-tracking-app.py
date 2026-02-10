import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import hashlib
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

# --- CSS (UPDATED DESIGN & COMPACT LAYOUT) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    
    /* STYLE DES CARTES */
    .job-card {
        padding: 10px 15px; 
        border-radius: 8px; 
        margin-bottom: 8px; 
        background-color: rgba(255, 255, 255, 0.05) !important; 
        border: 1px solid #FFCC80; 
        transition: all 0.3s ease;
    }
    
    /* BORDURE VERTE POUR ACTIFS */
    .border-active {
        border: 1px solid #2ECC71 !important;
        background-color: rgba(46, 204, 113, 0.05) !important;
    }

    .small-text {font-size: 0.8rem; opacity: 0.8;}
    
    /* BOUTONS COMPACTS */
    div[data-testid="column"] .stButton button {
        border-radius: 5px;
        padding: 2px 8px;
        font-size: 0.85rem;
    }

    /* NAVIGATION STYLE */
    .stRadio > div {
        display: flex;
        justify-content: flex-start;
        gap: 20px;
        margin-bottom: 20px;
    }

    /* STICKY COLUMN */
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) {
        max-height: 90vh;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# SECURITY & DATABASE MODULE
# =============================================================================

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def save_user(email, password, first_name, last_name, company):
    hashed_pw = make_hashes(password)
    data = {
        "email": email, "password": hashed_pw, 
        "first_name": first_name, "last_name": last_name, 
        "company": company, "Status": False
    }
    try:
        supabase.table("users_table").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Signup error: {e}")
        return False

def login_user(email, password):
    hashed_pw = make_hashes(password)
    try:
        res = supabase.table("users_table").select("*").eq("email", email).execute()
        if res.data and res.data[0].get('password') == hashed_pw:
            return res.data[0]
    except Exception as e:
        st.error(f"Login error: {e}")
    return None

# --- JOB FUNCTIONS ---

def load_jobs(user_email):
    try:
        res = supabase.table("jobs_table").select("*").eq("owner_email", user_email).order("id", desc=True).execute()
        return res.data if res.data else []
    except: return []

def check_duplicate_name(task_name, user_email, exclude_id=None):
    try:
        query = supabase.table("jobs_table").select("id").eq("owner_email", user_email).eq("task_name", task_name)
        if exclude_id:
            query = query.neq("id", exclude_id)
        res = query.execute()
        return len(res.data) > 0
    except: return False

def add_job(job_data):
    try:
        job_data.pop('id', None) 
        supabase.table("jobs_table").insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving task: {e}")
        return False

def update_job(job_id, update_data):
    try:
        supabase.table("jobs_table").update(update_data).eq("id", job_id).execute()
        return True
    except Exception as e:
        st.error(f"Update error: {e}")
        return False

# --- FOLDER FUNCTIONS ---

def get_folders(user_email):
    try:
        res = supabase.table("folders_table").select("*").eq("owner_email", user_email).order("created_at").execute()
        return res.data if res.data else []
    except: return []

def create_folder(name, user_email):
    try:
        existing = supabase.table("folders_table").select("id").eq("owner_email", user_email).eq("name", name).execute()
        if existing.data: return False
        supabase.table("folders_table").insert({"name": name, "owner_email": user_email}).execute()
        return True
    except: return False

def delete_folder(folder_id):
    try:
        supabase.table("folders_table").delete().eq("id", folder_id).execute()
        return True
    except: return False

def rename_folder(folder_id, new_name):
    try:
        supabase.table("folders_table").update({"name": new_name}).eq("id", folder_id).execute()
        return True
    except: return False

def move_job_to_folder(job_id, folder_id):
    try:
        fid = folder_id if folder_id and folder_id > 0 else None
        supabase.table("jobs_table").update({"folder_id": fid}).eq("id", job_id).execute()
        return True
    except: return False

# =============================================================================
# BUSINESS LOGIC
# =============================================================================

@st.cache_data
def load_data(uploaded_file):
    if uploaded_file is None: return None
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_file, dtype=str, keep_default_na=False)
        
        for col in df.columns:
            if 'date' in col.lower():
                df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
            else:
                try: df[col] = pd.to_numeric(df[col], errors='ignore')
                except: pass
        return df.fillna("")
    except Exception as e:
        st.error(f"Import error: {e}")
        return None

def filter_date(df, date_col, days):
    if days == 0 or not days or date_col not in df.columns: return df
    try:
        temp_df = df.copy()
        temp_df[date_col] = pd.to_datetime(temp_df[date_col], dayfirst=True, errors='coerce')
        cutoff = datetime.now() - timedelta(days=days)
        return df.loc[temp_df[temp_df[date_col] >= cutoff].index]
    except: return df

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def run_mro_app():
    # --- SESSION STATE ---
    if 'edit_mode' not in st.session_state:
        st.session_state['edit_mode'] = False
        st.session_state['edit_job_id'] = None
        st.session_state['edit_job_data'] = {}
    
    # Navigation State (pour permettre la redirection)
    if 'current_view' not in st.session_state:
        st.session_state['current_view'] = "Visualization"

    # --- SIDEBAR ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_first_name']} {st.session_state['user_last_name']}**")
        st.caption(f"🏢 {st.session_state['user_company']}")
        
        if st.session_state['edit_mode']:
            st.info("✏️ **EDITING REPORT**")
            
        if st.button("Logout", type="primary"):
            st.session_state['logged_in'] = False
            if 'df_persistent' in st.session_state: del st.session_state['df_persistent']
            st.rerun()
        st.markdown("---")

    st.title("✈️ MRO Control Tower")

    # --- DATA SOURCE ---
    with st.expander("📂 Data Source", expanded=True):
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

    # --- NAVIGATION (REPLACES TABS FOR REDIRECT CAPABILITY) ---
    # On utilise un radio button horizontal qui agit comme des onglets mais qu'on peut contrôler
    view_options = ["Visualization", "Schedule & Edit", "Folders"]
    
    # Callback pour synchroniser le bouton radio avec le state
    def update_view():
        st.session_state['current_view'] = st.session_state['nav_radio']

    selected_view = st.radio(
        "", 
        options=view_options, 
        index=view_options.index(st.session_state['current_view']),
        horizontal=True,
        key="nav_radio",
        on_change=update_view,
        label_visibility="collapsed"
    )

    # --- VIEW 1: VISUALIZATION ---
    if st.session_state['current_view'] == "Visualization":
        
        # 1. Configuration Filter
        with st.expander("⚙️ Filter & Column Configuration", expanded=False):
            c1, c2, c3 = st.columns([1, 1, 2])
            cols_date = [c for c in df_raw.columns if 'date' in c.lower()]
            default_date = cols_date[0] if cols_date else df_raw.columns[0]
            
            date_col = c1.selectbox("Reference Date Column", df_raw.columns, index=list(df_raw.columns).index(default_date))
            
            # Key added to multiselect to allow clearing it via session state
            master_filter_cols = c2.multiselect(
                "Define Master Filters", 
                [c for c in df_raw.columns if c != date_col],
                key="master_cols_select"
            )
            
            all_cols = list(df_raw.columns)
            display_opts = ["(Select All)"] + all_cols
            user_selection = c3.multiselect("Columns to Display", options=display_opts, default=all_cols)
            
            if "(Select All)" in user_selection:
                displayed_columns = all_cols
            else:
                displayed_columns = user_selection

        # 2. Reset Function (Updated: Clears Master Filters line too)
        def reset_all_filters():
            # Clear dynamic filters
            for key in list(st.session_state.keys()):
                if key.startswith("dyn_"): del st.session_state[key]
            # Clear period
            if "period_radio" in st.session_state: del st.session_state["period_radio"]
            # Clear master column selection (Removes the line)
            if "master_cols_select" in st.session_state: del st.session_state["master_cols_select"]

        col_title, col_reset = st.columns([4, 1])
        with col_title: st.markdown("##### 🔍 Master Filters")
        with col_reset: st.button("🔄 Reset Filters", on_click=reset_all_filters, use_container_width=True)

        df_final = df_raw.copy()
        current_filters_config = {}

        if master_filter_cols:
            filt_cols = st.columns(len(master_filter_cols))
            for i, col_name in enumerate(master_filter_cols):
                # MULTI-SELECT VALUES LOGIC
                val_counts = df_final[col_name].astype(str).value_counts()
                # Create clean options dict to map back "Value (Count)" -> "Value"
                clean_options = [val for val in val_counts.index]
                display_options = [f"{val} ({count})" for val, count in val_counts.items()]
                
                # We map display back to clean values
                selected_display = filt_cols[i].multiselect(f"{col_name}", display_options, key=f"dyn_{col_name}")
                
                if selected_display:
                    # Extract clean values from "Value (Count)"
                    selected_clean = [s.rpartition(' (')[0] for s in selected_display]
                    df_final = df_final[df_final[col_name].astype(str).isin(selected_clean)]
                    current_filters_config[col_name] = selected_clean

        st.markdown("---")
        c_time, c_kpi = st.columns([2, 1])
        with c_time:
            period = st.radio("Period:", ["View All", "7 Days", "30 Days", "60 Days", "180 Days"], horizontal=True, key="period_radio")
            days_map = {"View All": 0, "7 Days": 7, "30 Days": 30, "60 Days": 60, "180 Days": 180}
            days = days_map[period]
            df_final = filter_date(df_final, date_col, days)
            current_filters_config["retention_days"] = days
            current_filters_config["date_column"] = date_col

        with c_kpi: st.metric("Displayed Rows", len(df_final), delta=f"out of {len(df_raw)} total")
        st.dataframe(df_final, column_order=displayed_columns, use_container_width=True, height=500, hide_index=True)
        st.session_state['active_filters'] = current_filters_config

    # --- VIEW 2: SCHEDULE & EDIT ---
    elif st.session_state['current_view'] == "Schedule & Edit":
        folders = get_folders(st.session_state['user_email'])
        folder_options = {0: "📂 No Folder"} 
        for f in folders: folder_options[f['id']] = f"📁 {f['name']}"

        col_form, col_list = st.columns([1, 1.4])
        
        # --- LEFT: FORM ---
        with col_form:
            # NEW BUTTON LOGIC: Cancel edit mode and clear form
            if st.button("➕ NEW REPORT", use_container_width=True, type="primary"):
                st.session_state['edit_mode'] = False
                st.session_state['edit_job_id'] = None
                st.rerun()

            if st.session_state['edit_mode']:
                st.subheader("✏️ Edit Report")
                edit_data = st.session_state['edit_job_data']
                def_name = edit_data.get('task_name', '')
                def_recip = edit_data.get('recipient', '')
                def_msg = edit_data.get('custom_message', '')
                def_hour = datetime.strptime(edit_data.get('hour', '08:00:00'), '%H:%M:%S').time()
                
                old_freq_str = edit_data.get('frequency', '')
                try:
                    old_days_part = old_freq_str.split('(')[0].strip()
                    old_rec_part = old_freq_str.split('(')[1].replace(')', '').strip()
                    def_days = [d.strip() for d in old_days_part.split(',')]
                    valid_recs = ["Every week", "Every 2 weeks", "Every 4 weeks"]
                    idx_rec = valid_recs.index(old_rec_part) if old_rec_part in valid_recs else 0
                except:
                    def_days = ["Monday"]; idx_rec = 0
                def_fid = edit_data.get('folder_id') if edit_data.get('folder_id') else 0
            else:
                st.subheader("🚀 New Report")
                def_name = ""; def_recip = ""; def_msg = ""
                def_hour = time(8, 0); def_days = ["Monday"]; idx_rec = 0; def_fid = 0

            with st.form("job_form", border=True):
                job_name = st.text_input("Report Name", value=def_name)
                recipients = st.text_input("Recipient Emails", value=def_recip)
                st.caption("Custom Message")
                custom_msg = st.text_area("Message", value=def_msg, height=100, max_chars=2000)
                
                st.write("**Delivery Configuration**")
                selected_days = st.multiselect("Days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], default=def_days)
                recurrence = st.selectbox("Interval", ["Every week", "Every 2 weeks", "Every 4 weeks"], index=idx_rec)
                initial_folder = st.selectbox("Assign to Folder", options=list(folder_options.keys()), format_func=lambda x: folder_options[x], index=list(folder_options.keys()).index(def_fid) if def_fid in folder_options else 0)

                c_time, c_fmt = st.columns(2)
                send_time = c_time.time_input("Time", value=def_hour)
                fmt = c_fmt.selectbox("Format", ["Excel (.xlsx)", "CSV"])
                
                btn_txt = "💾 Update Report" if st.session_state['edit_mode'] else "💾 Save Schedule"
                
                if st.form_submit_button(btn_txt, use_container_width=True):
                    if job_name and recipients and selected_days:
                        exclude_id = st.session_state['edit_job_id'] if st.session_state['edit_mode'] else None
                        if check_duplicate_name(job_name, st.session_state['user_email'], exclude_id):
                            st.error(f"⚠️ '{job_name}' already exists!")
                        else:
                            days_str = ", ".join(selected_days)
                            final_frequency_str = f"{days_str} ({recurrence})"
                            job_payload = {
                                "task_name": job_name, "recipient": recipients, "custom_message": custom_msg,
                                "frequency": final_frequency_str, "hour": str(send_time), "format": fmt,
                                "folder_id": initial_folder if initial_folder > 0 else None
                            }
                            
                            if not st.session_state['edit_mode']:
                                job_payload.update({"owner_email": st.session_state['user_email'], "filters_config": st.session_state.get('active_filters', {}), "active": False})
                                if add_job(job_payload): st.success("Saved!"); st.rerun()
                            else:
                                if update_job(st.session_state['edit_job_id'], job_payload):
                                    st.success("Updated!"); st.session_state['edit_mode'] = False; st.session_state['edit_job_id'] = None; st.rerun()
                    else: st.error("Fill mandatory fields.")

        # --- RIGHT: LIST WITH INTEGRATED BUTTONS ---
        with col_list:
            st.subheader("📋 My Scheduled Reports")
            my_jobs = load_jobs(st.session_state['user_email'])
            
            if not my_jobs: st.info("No reports.")
            else:
                for job in my_jobs:
                    target_id = int(job['id'])
                    is_active = job['active']
                    border_class = "border-active" if is_active else ""
                    icon_status = "🟢" if is_active else "🟠"
                    folder_label = folder_options.get(job.get('folder_id', 0) or 0, "📂 No Folder")

                    with st.container():
                        st.markdown(f"""<div class="job-card {border_class}"></div>""", unsafe_allow_html=True)
                        # Trick to put content 'inside' the card visual: use negative margin CSS or just clean layout
                        # We used a container above. Let's use columns for layout INSIDE the container area.
                        
                        # Layout: Info (70%) | Buttons (30%)
                        c_info, c_btns = st.columns([2.5, 1])
                        
                        with c_info:
                            st.markdown(f"**{job['task_name']}** {icon_status}")
                            st.caption(f"{folder_label} | {job['frequency']} @ {job['hour']}")
                            st.caption(f"📧 {job['recipient']}")
                        
                        with c_btns:
                            # Grid for buttons
                            b1, b2, b3, b4 = st.columns(4)
                            
                            # 1. RUN/STOP
                            with b1:
                                btn_icon = "⏸️" if is_active else "▶️"
                                if st.button(btn_icon, key=f"tog_{target_id}", help="Toggle Active"):
                                    supabase.table("jobs_table").update({"active": not is_active}).eq("id", target_id).execute()
                                    st.rerun()
                            
                            # 2. EDIT (Set Edit Mode + Scroll Up effectively)
                            with b2:
                                if st.button("✏️", key=f"edt_{target_id}", help="Edit"):
                                    st.session_state['edit_mode'] = True
                                    st.session_state['edit_job_id'] = target_id
                                    st.session_state['edit_job_data'] = job
                                    st.rerun()
                            
                            # 3. FILTERS (Popover)
                            with b3:
                                with st.popover("🔍", help="See Filters"):
                                    st.write("**Filters:**")
                                    st.json(job['filters_config'])
                                    
                            # 4. DELETE (Confirmation Popover)
                            with b4:
                                with st.popover("🗑️", help="Delete"):
                                    st.write("Are you sure?")
                                    if st.button("YES, Delete", key=f"conf_del_{target_id}", type="primary"):
                                        supabase.table("jobs_table").delete().eq("id", target_id).execute()
                                        st.rerun()
                        
                        st.divider()

    # --- VIEW 3: FOLDERS ---
    elif st.session_state['current_view'] == "Folders":
        st.subheader("📂 Folder Management")
        
        search_query = st.text_input("🔍 Search Folders or Reports", placeholder="Type a name...")

        with st.expander("➕ Create New Folder", expanded=False):
            with st.form("create_folder"):
                c_new, c_sub = st.columns([3, 1])
                new_fname = c_new.text_input("New Folder Name")
                if c_sub.form_submit_button("Create"):
                    if new_fname:
                        if create_folder(new_fname, st.session_state['user_email']):
                            st.success("Folder created!")
                            st.rerun()
                        else: st.error("Exists already!")
        
        st.markdown("---")
        
        all_folders = get_folders(st.session_state['user_email'])
        all_jobs = load_jobs(st.session_state['user_email'])
        
        if search_query:
            q = search_query.lower()
            filtered_folders = []
            for f in all_folders:
                jobs_in = [j for j in all_jobs if j.get('folder_id') == f['id']]
                if q in f['name'].lower() or any(q in j['task_name'].lower() for j in jobs_in):
                    filtered_folders.append(f)
        else:
            filtered_folders = all_folders

        if not filtered_folders and not search_query: st.info("No folders found.")
        
        for folder in filtered_folders:
            fid = folder['id']
            fname = folder['name']
            jobs_in = [j for j in all_jobs if j.get('folder_id') == fid]
            if search_query:
                jobs_in = [j for j in jobs_in if search_query.lower() in j['task_name'].lower() or search_query.lower() in fname.lower()]
            
            with st.expander(f"📁 **{fname}** ({len(jobs_in)})", expanded=(True if search_query else False)):
                c_ren, c_btn, c_del_f = st.columns([2, 1, 1])
                new_name = c_ren.text_input("Rename", value=fname, key=f"ren_{fid}", label_visibility="collapsed")
                if c_btn.button("💾 Rename", key=f"bsave_{fid}"):
                    if new_name != fname: 
                        rename_folder(fid, new_name); st.rerun()
                
                # FOLDER DELETE CONFIRMATION
                with c_del_f:
                    with st.popover("🗑️ Delete", help="Delete this folder"):
                        st.write("Delete folder?")
                        st.caption("Reports inside will be uncategorized.")
                        if st.button("YES", key=f"conf_del_fold_{fid}", type="primary"):
                            delete_folder(fid); st.rerun()
                
                st.divider()
                
                if not jobs_in: st.caption("No reports.")
                else:
                    for j in jobs_in:
                        jid = j['id']
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"📄 **{j['task_name']}**")
                        
                        # REDIRECTION EDIT LOGIC
                        if c2.button("✏️ Edit", key=f"fold_edit_{jid}"):
                            st.session_state['edit_mode'] = True
                            st.session_state['edit_job_id'] = jid
                            st.session_state['edit_job_data'] = j
                            st.session_state['current_view'] = "Schedule & Edit" # Force redirection
                            st.rerun()

        if not search_query or "no folder" in search_query.lower():
            orphans = [j for j in all_jobs if not j.get('folder_id') or j.get('folder_id') == 0]
            if orphans:
                st.markdown("### 📂 Uncategorized")
                for j in orphans:
                     st.markdown(f"📄 **{j['task_name']}**")

# =============================================================================
# DATA STORAGE HELPERS (UNCHANGED)
# =============================================================================

def save_imported_data(df, user_email):
    try:
        supabase.table("raw_data_table").delete().eq("owner_email", user_email).execute()
        df_save = df.copy()
        for col in df_save.columns:
            if pd.api.types.is_datetime64_any_dtype(df_save[col]):
                df_save[col] = df_save[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_save = df_save.where(pd.notnull(df_save), None)
        all_rows = [{"owner_email": user_email, "row_data": row} for row in df_save.to_dict(orient='records')]
        chunk_size = 5000
        total = len(all_rows)
        progress_bar = st.progress(0, text="Mass Synchronization...")
        for i in range(0, total, chunk_size):
            chunk = all_rows[i : i + chunk_size]
            supabase.table("raw_data_table").insert(chunk).execute()
            pct = min((i + chunk_size) / total, 1.0)
            progress_bar.progress(pct, text=f"Uploading data: {int(pct*100)}%")
        progress_bar.empty()
        return True
    except Exception as e:
        st.error(f"Save error: {e}")
        return False

def load_stored_data(user_email):
    try:
        all_data = []
        page_size = 10000 
        start = 0
        while True:
            res = supabase.table("raw_data_table").select("row_data").eq("owner_email", user_email).range(start, start + page_size - 1).execute()
            if not res.data: break
            all_data.extend([item['row_data'] for item in res.data])
            if len(res.data) < page_size: break
            start += page_size
        return pd.DataFrame(all_data) if all_data else None
    except Exception as e:
        st.error(f"Retrieval error: {e}")
        return None

# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

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
                                "user_company": u['company'], "user_status": u['Status']
                            })
                            st.rerun()
                        else: st.error("Incorrect email or password.")
            else:
                with st.form("signup"):
                    fn = st.text_input("First Name")
                    ln = st.text_input("Last Name")
                    cp = st.text_input("Company")
                    em = st.text_input("Work Email")
                    pw = st.text_input("Password", type='password')
                    if st.form_submit_button("Create my account"):
                        if em and pw:
                            if save_user(em, pw, fn, ln, cp): st.success("Account created! Please log in.")
                        else: st.warning("Please fill in mandatory fields.")
    else:
        run_mro_app()

if __name__ == "__main__":
    main()