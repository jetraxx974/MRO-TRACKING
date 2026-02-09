import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import json
import os
import hashlib # Pour la sécurité des mots de passe

# --- 1. CONFIGURATION GLOBALE ---
st.set_page_config(layout="wide", page_title="AeroControl Tower", page_icon="✈️")

# Fichiers de stockage
JOBS_FILE = "scheduled_jobs.json"
USERS_FILE = "users_db.json"

# --- CSS (DESIGN) ---
st.markdown("""
<style>
    /* Global */
    .block-container {padding-top: 1rem;}
    
    /* Login Box */
    .login-container {
        padding: 30px; border-radius: 10px; background-color: #f0f2f6; 
        border: 1px solid #d1d5db; max-width: 400px; margin: auto;
    }
    
    /* Cards Tâches */
    .job-card {
        padding: 10px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #e0e0e0;
        transition: transform 0.1s;
    }
    .job-card:hover {border-color: #aaa;}
    
    /* Statuts */
    .status-active {border-left: 5px solid #2ecc71; background-color: #f0fff4;}
    .status-inactive {border-left: 5px solid #95a5a6; background-color: #f9f9f9;}
    
    .small-text {font-size: 0.85rem; color: #555;}
    .stButton button {width: 100%;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# MODULE SÉCURITÉ & AUTHENTIFICATION
# =============================================================================

def make_hashes(password):
    """Transforme le mot de passe en code chiffré illisible."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Vérifie si le mot de passe correspond au hash."""
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except: return {}

def save_user(username, password):
    users = load_users()
    if username in users:
        return False # L'utilisateur existe déjà
    
    users[username] = {
        "password": make_hashes(password),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
    return True

def login_user(username, password):
    users = load_users()
    if username in users:
        if check_hashes(password, users[username]['password']):
            return True
    return False

# =============================================================================
# FONCTIONS BACKEND MRO (Ton code original)
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
            if 'date' in col.lower() or 'time' in col.lower():
                df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
            else:
                try: df[col] = pd.to_numeric(df[col], errors='ignore')
                except: pass
        df = df.fillna("")
        return df
    except Exception as e:
        st.error(f"❌ Erreur critique import: {e}")
        return None

def filter_date(df, date_col, days):
    if not days or date_col not in df.columns: return df
    try:
        temp_df = df.copy()
        temp_df[date_col] = pd.to_datetime(temp_df[date_col], dayfirst=True, errors='coerce')
        cutoff = datetime.now() - timedelta(days=days)
        return df.loc[temp_df[temp_df[date_col] >= cutoff].index]
    except: return df

# --- GESTION JSON TACHES ---
def load_jobs():
    if not os.path.exists(JOBS_FILE): return []
    try:
        with open(JOBS_FILE, 'r') as f: return json.load(f)
    except: return []

def save_jobs_list(jobs):
    with open(JOBS_FILE, 'w') as f: json.dump(jobs, f, indent=4)

def add_job(job_data):
    jobs = load_jobs()
    jobs.append(job_data)
    save_jobs_list(jobs)

def update_job_status(index, status):
    jobs = load_jobs()
    if 0 <= index < len(jobs):
        jobs[index]['active'] = status
        save_jobs_list(jobs)

def delete_job(index):
    jobs = load_jobs()
    if 0 <= index < len(jobs):
        del jobs[index]
        save_jobs_list(jobs)

# =============================================================================
# L'APPLICATION PRINCIPALE (MRO APP)
# =============================================================================

def run_mro_app():
    # C'est ta fonction main() originale, renommée pour être appelée après le login
    
    # Sidebar de déconnexion
    with st.sidebar:
        st.write(f"👤 Connecté: **{st.session_state['username']}**")
        if st.button("Déconnexion", type="primary"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.markdown("---")

    if 'date_filter' not in st.session_state: st.session_state['date_filter'] = None
    if 'active_filters' not in st.session_state: st.session_state['active_filters'] = {}

    st.title("✈️ MRO Control Tower")

    with st.expander("📂 Source de Données", expanded=True):
        uploaded_file = st.file_uploader("Fichier Excel/CSV", type=['xlsx', 'csv'])

    if uploaded_file is None:
        st.info("Veuillez importer un fichier.")
        return

    df_raw = load_data(uploaded_file)
    if df_raw is None: return

    tab_visu, tab_plan = st.tabs(["📊 Visualisation", "📅 Planification & Envois"])

    # --- ONGLET 1 ---
    with tab_visu:
        with st.expander("⚙️ Configuration Globale", expanded=False):
            c1, c2, c3 = st.columns([1, 1, 2])
            cols_date = [c for c in df_raw.columns if 'date' in c.lower()]
            default_date = cols_date[0] if cols_date else df_raw.columns[0]
            date_col = c1.selectbox("Colonne Date Référence", df_raw.columns, index=list(df_raw.columns).index(default_date))
            master_filter_cols = c2.multiselect("Définir Master Filters", [c for c in df_raw.columns if c != date_col])
            displayed_columns = c3.multiselect("Colonnes tableau", options=df_raw.columns, default=df_raw.columns)

        st.markdown("##### 🔍 Filtres Actifs")
        df_final = df_raw.copy()
        current_filters_config = {}

        if master_filter_cols:
            filt_cols = st.columns(len(master_filter_cols))
            for i, col_name in enumerate(master_filter_cols):
                val_counts = df_final[col_name].astype(str).value_counts()
                options = ["TOUT"] + [f"{val} ({count})" for val, count in val_counts.items()]
                selected = filt_cols[i].selectbox(f"{col_name}", options, key=f"dyn_{col_name}")
                if selected != "TOUT":
                    clean_val = selected.rpartition(' (')[0]
                    df_final = df_final[df_final[col_name].astype(str) == clean_val]
                    current_filters_config[col_name] = clean_val
        else:
            st.caption("Aucun Master Filter configuré.")

        st.markdown("---")
        c_time, c_kpi = st.columns([2, 1])
        with c_time:
            period = st.radio("Période :", ["Tout", "7 Jours", "30 Jours", "60 Jours", "180 Jours"], horizontal=True, label_visibility="collapsed")
            days_map = {"Tout": None, "7 Jours": 7, "30 Jours": 30, "60 Jours": 60, "180 Jours": 180}
            st.session_state['date_filter'] = days_map[period]
            current_filters_config["date_range"] = st.session_state['date_filter']

        df_final = filter_date(df_final, date_col, st.session_state['date_filter'])
        st.session_state['active_filters'] = current_filters_config

        with c_kpi:
            st.metric("Lignes affichées", len(df_final), delta=f"sur {len(df_raw)} total")
        st.dataframe(df_final, column_order=displayed_columns, use_container_width=True, height=500, hide_index=True)

    # --- ONGLET 2 ---
    with tab_plan:
        col_form, col_list = st.columns([1, 1.5])
        with col_form:
            st.subheader("1. Nouvelle Planification")
            with st.form("new_job_form", clear_on_submit=False): 
                job_name = st.text_input("Nom de la tâche")
                recipients = st.text_input("Destinataires (virgule)", placeholder="a@a.com, b@b.com")
                freq_type = st.selectbox("Fréquence", ["Quotidien", "Hebdomadaire", "Mensuel"])
                
                # Logique simplifiée pour l'affichage
                freq_txt = freq_type 
                
                send_time = st.time_input("Heure", value=time(8, 0))
                full_freq = f"{freq_txt} à {send_time.strftime('%H:%M')}"
                format_export = st.selectbox("Format", ["Excel (.xlsx)", "CSV"])
                
                if st.form_submit_button("💾 Créer"):
                    if job_name and recipients:
                        new_job = {
                            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                            "created_at": datetime.now().strftime("%d/%m/%Y"),
                            "name": job_name,
                            "recipient": [r.strip() for r in recipients.split(',')],
                            "frequency_label": full_freq,
                            "format": format_export,
                            "filters_config": st.session_state['active_filters'],
                            "active": False,
                            "owner": st.session_state['username'] # On lie la tache au user
                        }
                        add_job(new_job)
                        st.success("Tâche créée !")
                        st.rerun()
                    else: st.error("Champs manquants")

        with col_list:
            st.subheader("2. Tâches Planifiées")
            search_query = st.text_input("🔎 Rechercher...", "")
            jobs = load_jobs()
            if search_query: jobs = [j for j in jobs if search_query.lower() in j.get('name', '').lower()]
            
            if not jobs: st.warning("Aucune tâche.")
            else:
                for i, job in enumerate(jobs):
                    job_name = job.get('name', 'N/A')
                    is_active = job.get('active', False)
                    status_class = "status-active" if is_active else "status-inactive"
                    status_icon = "🟢" if is_active else "⚪"
                    recips = ', '.join(job.get('recipient', [])) if isinstance(job.get('recipient'), list) else str(job.get('recipient'))
                    
                    st.markdown(f"""
                    <div class="job-card {status_class}">
                        <div style="display:flex; justify-content:space-between;">
                            <b>{job_name}</b> <span>{status_icon}</span>
                        </div>
                        <div class="small-text">Dest: {recips} <br> Freq: {job.get('frequency_label', 'N/A')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    c1, c2, c3 = st.columns([2, 1, 2])
                    if is_active:
                        if c1.button("Désactiver", key=f"stop_{i}"):
                            update_job_status(i, False)
                            st.rerun()
                    else:
                        if c1.button("Activer", key=f"start_{i}", type="primary"):
                            update_job_status(i, True)
                            st.rerun()
                    if c2.button("🗑️", key=f"del_{i}"):
                        delete_job(i)
                        st.rerun()
                    with c3.expander("Détails"):
                        st.json(job.get('filters_config', {}))

# =============================================================================
# POINT D'ENTRÉE & GESTION DE SESSION (LOGIN/REGISTER)
# =============================================================================

def main():
    # Initialisation de la session
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['username'] = None

    # SI PAS CONNECTÉ : On affiche Login / Sign Up
    if not st.session_state['logged_in']:
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.title("🔒 AeroTrack Login")
            
            choice = st.selectbox("Menu", ["Se Connecter", "S'inscrire"])
            
            if choice == "Se Connecter":
                with st.form("login_form"):
                    username = st.text_input("Utilisateur")
                    password = st.text_input("Mot de passe", type='password')
                    submit = st.form_submit_button("Entrer")
                    
                    if submit:
                        if login_user(username, password):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = username
                            st.success("Connexion réussie !")
                            st.rerun()
                        else:
                            st.error("Utilisateur ou mot de passe incorrect.")
            
            else: # Inscription
                with st.form("signup_form"):
                    st.subheader("Créer un compte")
                    new_user = st.text_input("Nouvel Utilisateur")
                    new_password = st.text_input("Nouveau Mot de passe", type='password')
                    confirm_password = st.text_input("Confirmer Mot de passe", type='password')
                    submit = st.form_submit_button("S'inscrire")
                    
                    if submit:
                        if new_password == confirm_password:
                            if save_user(new_user, new_password):
                                st.success("Compte créé ! Vous pouvez vous connecter.")
                            else:
                                st.warning("Cet utilisateur existe déjà.")
                        else:
                            st.error("Les mots de passe ne correspondent pas.")
    
    # SI CONNECTÉ : On lance l'application MRO
    else:
        run_mro_app()

if __name__ == "__main__":
    main()