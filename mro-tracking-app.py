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

# --- CSS (UPDATED DESIGN) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    
    /* TRANSPARENT CARD / PALE ORANGE BORDER */
    .job-card {
        padding: 15px; 
        border-radius: 10px; 
        margin-bottom: 10px; 
        background-color: transparent !important; 
        border: 2px solid #FFCC80; 
    }
    
    /* GREEN BORDER FOR ACTIVE JOBS */
    .border-active {
        border: 2px solid #2ECC71 !important;
    }

    .small-text {font-size: 0.85rem; opacity: 0.9;}
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
        # Added .order("id") for stability
        res = supabase.table("jobs_table").select("*").eq("owner_email", user_email).order("id").execute()
        return res.data if res.data else []
    except: return []

def add_job(job_data):
    try:
        job_data.pop('id', None) 
        supabase.table("jobs_table").insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving task: {e}")
        return False

# --- NEW FOLDER FUNCTIONS (ADDED) ---

def get_folders(user_email):
    """Fetch all folders for the user"""
    try:
        res = supabase.table("folders_table").select("*").eq("owner_email", user_email).order("created_at").execute()
        return res.data if res.data else []
    except: return []

def create_folder(name, user_email):
    """Create a new folder"""
    try:
        supabase.table("folders_table").insert({"name": name, "owner_email": user_email}).execute()
        return True
    except: return False

def delete_folder(folder_id):
    """Delete a folder (jobs inside will have folder_id set to NULL automatically via SQL)"""
    try:
        supabase.table("folders_table").delete().eq("id", folder_id).execute()
        return True
    except: return False

def rename_folder(folder_id, new_name):
    """Rename an existing folder"""
    try:
        supabase.table("folders_table").update({"name": new_name}).eq("id", folder_id).execute()
        return True
    except: return False

def move_job_to_folder(job_id, folder_id):
    """Assign a job to a folder (or remove it if folder_id is None)"""
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
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_first_name']} {st.session_state['user_last_name']}**")
        st.caption(f"🏢 {st.session_state['user_company']}")
        if st.button("Logout", type="primary"):
            st.session_state['logged_in'] = False
            # Clear persistent cache on logout
            if 'df_persistent' in st.session_state: del st.session_state['df_persistent']
            st.rerun()
        st.markdown("---")

    st.title("✈️ MRO Control Tower")

    with st.expander("📂 Data Source", expanded=True):
        uploaded_file = st.file_uploader("Excel/CSV File", type=['xlsx', 'csv'])

    # --- PERSISTENCE LOGIC (300k ROWS) ---
    df_raw = None

    if uploaded_file is not None:
        # Case 1: New manual import
        df_raw = load_data(uploaded_file)
        if df_raw is not None:
            # Massive save to Supabase
            save_imported_data(df_raw, st.session_state['user_email'])
            # Update local cache
            st.session_state['df_persistent'] = df_raw
            st.success(f"✅ Data synchronized: {len(df_raw)} rows saved.")
    else:
        # Case 2: No upload, check session cache or database
        if 'df_persistent' not in st.session_state or st.session_state['df_persistent'] is None:
            with st.spinner("🔄 Retrieving saved data..."):
                st.session_state['df_persistent'] = load_stored_data(st.session_state['user_email'])
        
        df_raw = st.session_state['df_persistent']

    # Continue only if data exists
    if df_raw is None:
        st.info("👋 Welcome! Please import a file to activate the tools.")
        return

    # --- TABS DISPLAY (UPDATED WITH FOLDERS) ---
    tab_visu, tab_schedule, tab_folders = st.tabs(["📊 Visualization", "📅 Schedule", "📁 Folders"])

    # --- TAB 1: VISUALIZATION ---
    with tab_visu:
        # 1. Configuration (Expander)
        with st.expander("⚙️ Filter & Column Configuration", expanded=False):
            c1, c2, c3 = st.columns([1, 1, 2])
            cols_date = [c for c in df_raw.columns if 'date' in c.lower()]
            default_date = cols_date[0] if cols_date else df_raw.columns[0]
            
            date_col = c1.selectbox("Reference Date Column", df_raw.columns, index=list(df_raw.columns).index(default_date))
            master_filter_cols = c2.multiselect("Define Master Filters", [c for c in df_raw.columns if c != date_col])
            
            # Select All Logic (From previous step)
            all_cols = list(df_raw.columns)
            display_opts = ["(Select All)"] + all_cols
            user_selection = c3.multiselect("Columns to Display", options=display_opts, default=all_cols)
            
            if "(Select All)" in user_selection:
                displayed_columns = all_cols
            else:
                displayed_columns = user_selection

        # 2. Reset Function
        def reset_all_filters():
            for key in list(st.session_state.keys()):
                if key.startswith("dyn_"):
                    del st.session_state[key]
            if "period_radio" in st.session_state:
                del st.session_state["period_radio"]

        # 3. Header & Reset Button
        col_title, col_reset = st.columns([4, 1])
        with col_title:
            st.markdown("##### 🔍 Master Filters")
        with col_reset:
            st.button("🔄 Reset Filters", on_click=reset_all_filters, use_container_width=True)

        # 4. Filters Calculation
        df_final = df_raw.copy()
        current_filters_config = {}

        if master_filter_cols:
            filt_cols = st.columns(len(master_filter_cols))
            for i, col_name in enumerate(master_filter_cols):
                val_counts = df_final[col_name].astype(str).value_counts()
                options = ["ALL"] + [f"{val} ({count})" for val, count in val_counts.items()]
                
                selected = filt_cols[i].selectbox(f"{col_name}", options, key=f"dyn_{col_name}")
                
                if selected != "ALL":
                    clean_val = selected.rpartition(' (')[0]
                    df_final = df_final[df_final[col_name].astype(str) == clean_val]
                    current_filters_config[col_name] = clean_val
        
        st.markdown("---")
        
        # 5. Period & Display
        c_time, c_kpi = st.columns([2, 1])
        with c_time:
            period = st.radio(
                "Period:", 
                ["View All", "7 Days", "30 Days", "60 Days", "180 Days"], 
                horizontal=True,
                key="period_radio"
            )
            days_map = {"View All": 0, "7 Days": 7, "30 Days": 30, "60 Days": 60, "180 Days": 180}
            days = days_map[period]
            df_final = filter_date(df_final, date_col, days)
            current_filters_config["retention_days"] = days
            current_filters_config["date_column"] = date_col

        with c_kpi:
            st.metric("Displayed Rows", len(df_final), delta=f"out of {len(df_raw)} total")
        
        st.dataframe(df_final, column_order=displayed_columns, use_container_width=True, height=500, hide_index=True)
        st.session_state['active_filters'] = current_filters_config

    # --- TAB 2: SCHEDULE (Renamed from Planning) ---
    with tab_schedule:
        # Load folders for the dropdown
        folders = get_folders(st.session_state['user_email'])
        folder_options = {0: "📂 No Folder"} 
        for f in folders:
            folder_options[f['id']] = f"📁 {f['name']}"

        col_form, col_list = st.columns([1, 1.5])
        
        # --- LEFT COLUMN: NEW REPORT FORM ---
        with col_form:
            st.subheader("🚀 New Report")
            with st.form("new_job_form"):
                job_name = st.text_input("Report Name")
                recipients = st.text_input("Recipient Emails (comma separated)")
                
                st.write("**Delivery Configuration**")
                
                selected_days = st.multiselect(
                    "Days of the Week", 
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    default=["Monday"]
                )
                
                recurrence = st.selectbox(
                    "Interval", 
                    ["Every week", "Every 2 weeks", "Every 4 weeks"]
                )
                
                # --- NEW: Select Initial Folder ---
                initial_folder = st.selectbox(
                    "Assign to Folder", 
                    options=list(folder_options.keys()), 
                    format_func=lambda x: folder_options[x]
                )

                days_str = ", ".join(selected_days)
                final_frequency_str = f"{days_str} ({recurrence})"
                
                send_time = st.time_input("Delivery Time", value=time(8, 0))
                fmt = st.selectbox("Format", ["Excel (.xlsx)", "CSV"])
                
                if st.form_submit_button("💾 Save Schedule"):
                    if job_name and recipients and selected_days:
                        new_job = {
                            "task_name": job_name,
                            "recipient": recipients,
                            "frequency": final_frequency_str,
                            "hour": str(send_time),
                            "format": fmt,
                            "owner_email": st.session_state['user_email'],
                            "filters_config": st.session_state.get('active_filters', {}),
                            "active": False,
                            # Add folder ID to creation
                            "folder_id": initial_folder if initial_folder > 0 else None
                        }
                        if add_job(new_job):
                            st.success("Schedule saved!")
                            st.rerun()
                    else: 
                        st.error("Please fill in the name, emails, and choose at least one day.")

        # --- RIGHT COLUMN: SCHEDULED REPORTS LIST ---
        with col_list:
            st.subheader("📋 My Scheduled Reports")
            my_jobs = load_jobs(st.session_state['user_email'])
            
            if not my_jobs:
                st.info("No reports scheduled.")
            else:
                for job in my_jobs:
                    target_id = int(job['id'])
                    border_class = "border-active" if job['active'] else ""
                    icon_status = "🟢 Active" if job['active'] else "🟠 Inactive"
                    
                    # Resolve Folder Name
                    curr_fid = job.get('folder_id')
                    curr_fid = curr_fid if curr_fid else 0
                    folder_label = folder_options.get(curr_fid, "📂 No Folder")

                    with st.container():
                        st.markdown(f"""
                        <div class="job-card {border_class}">
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                                <div>
                                    <strong style="font-size:1.1em;">{job['task_name']}</strong><br>
                                    <span style="font-size:0.8em; color:#666;">{folder_label}</span>
                                </div>
                                <span>{icon_status}</span>
                            </div>
                            <div class="small-text">
                                📅 <b>{job['frequency']}</b> at {job['hour']}<br>
                                📧 {job['recipient']} | 📁 {job['format']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        c_act, c_view, c_del = st.columns([1.2, 2, 0.8])
                        
                        # 1. LEFT: ACTIVATE / STOP
                        with c_act:
                            btn_label = "⏸️ Stop" if job['active'] else "▶️ Run"
                            if st.button(btn_label, key=f"tog_btn_{target_id}"):
                                supabase.table("jobs_table").update({"active": not job['active']}).eq("id", target_id).execute()
                                st.rerun()

                        # 2. MIDDLE: FILTERS & FOLDER MOVE
                        with c_view:
                            with st.expander("⚙️ Manage"):
                                # --- MOVE TO FOLDER LOGIC (Simulates Drag & Drop) ---
                                st.write("**Move to Folder:**")
                                new_folder = st.selectbox(
                                    "Select Folder", 
                                    options=list(folder_options.keys()), 
                                    format_func=lambda x: folder_options[x],
                                    index=list(folder_options.keys()).index(curr_fid) if curr_fid in folder_options else 0,
                                    key=f"move_{target_id}",
                                    label_visibility="collapsed"
                                )
                                # Auto-save logic
                                if new_folder != curr_fid:
                                    if move_job_to_folder(target_id, new_folder):
                                        st.toast(f"Moved to {folder_options[new_folder]}!")
                                        st.rerun()
                                
                                st.divider()
                                st.write("**Filters Config:**")
                                st.json(job['filters_config'])

                        # 3. RIGHT: DELETE (TRASH)
                        with c_del:
                            if st.button("🗑️", key=f"del_btn_{target_id}", help="Delete Report"):
                                res = supabase.table("jobs_table").delete().eq("id", target_id).execute()
                                if res.data:
                                    st.success("Deleted!")
                                    st.rerun()
                                else:
                                    st.error("Error deleting.")

    # --- TAB 3: FOLDERS (NEW) ---
    with tab_folders:
        st.subheader("📂 Folder Management")
        
        # 1. Create New Folder
        with st.form("create_folder"):
            c_new, c_sub = st.columns([3, 1])
            new_fname = c_new.text_input("New Folder Name", placeholder="e.g. Monthly Reports, Client A...")
            if c_sub.form_submit_button("➕ Create Folder"):
                if new_fname:
                    if create_folder(new_fname, st.session_state['user_email']):
                        st.success("Folder created!")
                        st.rerun()
        
        st.markdown("---")
        
        # 2. List Folders
        my_folders = get_folders(st.session_state['user_email'])
        my_jobs = load_jobs(st.session_state['user_email']) # Need jobs to show content

        if not my_folders:
            st.info("No folders yet. Create one above!")
        else:
            for folder in my_folders:
                fid = folder['id']
                fname = folder['name']
                
                # Count jobs in this folder
                jobs_in_folder = [j for j in my_jobs if j.get('folder_id') == fid]
                count = len(jobs_in_folder)
                
                # Folder Card (Expander)
                with st.expander(f"📁 **{fname}** ({count} reports)", expanded=False):
                    
                    # --- RENAME / DELETE SECTION ---
                    c_ren, c_btn, c_del_f = st.columns([2, 1, 1])
                    new_name_input = c_ren.text_input("Rename", value=fname, key=f"ren_txt_{fid}", label_visibility="collapsed")
                    
                    if c_btn.button("💾 Rename", key=f"ren_btn_{fid}"):
                        if new_name_input != fname:
                            rename_folder(fid, new_name_input)
                            st.rerun()
                            
                    if c_del_f.button("🗑️ Delete Folder", key=f"del_fold_{fid}", type="primary"):
                        delete_folder(fid)
                        st.rerun()
                    
                    st.divider()
                    
                    # --- LIST CONTENTS ---
                    if not jobs_in_folder:
                        st.caption("Empty folder.")
                    else:
                        for j in jobs_in_folder:
                            st.markdown(f"📄 **{j['task_name']}** - <small>{j['frequency']}</small>", unsafe_allow_html=True)


# =============================================================================
# DATA STORAGE HELPERS
# =============================================================================

def save_imported_data(df, user_email):
    """Massive save: handles dates AND NaN/empty values"""
    try:
        # 1. Clear old data
        supabase.table("raw_data_table").delete().eq("owner_email", user_email).execute()
        
        # 2. Cleaning and conversion
        df_save = df.copy()
        
        for col in df_save.columns:
            if pd.api.types.is_datetime64_any_dtype(df_save[col]):
                df_save[col] = df_save[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Replace NaN with None for JSON compliance
        df_save = df_save.where(pd.notnull(df_save), None)
        
        # 3. Prepare dictionaries
        all_rows = [{"owner_email": user_email, "row_data": row} for row in df_save.to_dict(orient='records')]
        
        # 4. Batch send (chunks of 5000)
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
    """Retrieve large volumes via pagination"""
    try:
        all_data = []
        page_size = 10000 
        start = 0
        
        while True:
            res = supabase.table("raw_data_table") \
                .select("row_data") \
                .eq("owner_email", user_email) \
                .range(start, start + page_size - 1) \
                .execute()
            
            if not res.data:
                break
            
            all_data.extend([item['row_data'] for item in res.data])
            if len(res.data) < page_size:
                break
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