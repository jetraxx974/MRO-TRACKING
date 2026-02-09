import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import hashlib
from supabase import create_client, Client

# --- 1. CONFIGURATION & CONNEXION SUPABASE ---
st.set_page_config(layout="wide", page_title="AeroControl Tower", page_icon="✈️")

# Récupération des secrets (Configurés dans Streamlit Cloud)
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ Erreur de connexion Supabase. Vérifiez vos 'Secrets' dans Streamlit Cloud.")
    st.stop()

# --- CSS (DESIGN) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    .login-container {padding: 30px; border-radius: 10px; background-color: #f0f2f6; border: 1px solid #d1d5db; max-width: 400px; margin: auto;}
    .job-card {padding: 10px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #e0e0e0; transition: transform 0.1s;}
    .job-card:hover {border-color: #aaa;}
    .status-active {border-left: 5px solid #2ecc71; background-color: #f0fff4;}
    .status-inactive {border-left: 5px solid #95a5a6; background-color: #f9f9f9;}
    .small-text {font-size: 0.85rem; color: #555;}
    .stButton button {width: 100%;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# MODULE SÉCURITÉ & BASE DE DONNÉES (SUPABASE)
# =============================================================================

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def save_user(email, password, first_name, last_name, company):
    """Inscription nouvel utilisateur dans Supabase"""
    hashed_pw = make_hashes(password)
    
    # Mapping exact avec tes tables Supabase
    data = {
        "email": email,
        "password": hashed_pw, 
        "first_name": first_name,
        "last_name": last_name,
        "company": company,
        "Status": False # False = Gratuit (0), True = Payant (1) - Attention majuscule 'S'
    }
    
    try:
        supabase.table("users_table").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Erreur technique lors de l'inscription : {e}")
        return False

def login_user(email, password):
    """Connexion via Supabase"""
    hashed_pw = make_hashes(password)
    try:
        # On cherche l'utilisateur par email
        response = supabase.table("users_table").select("*").eq("email", email).execute()
        user_data = response.data
        
        # Vérification
        if user_data:
            stored_pw = user_data[0].get('password', '') 
            if stored_pw == hashed_pw:
                return user_data[0] # On retourne tout l'objet user
    except Exception as e:
        st.error(f"Erreur de connexion (Vérifiez la Policy SELECT dans Supabase) : {e}")
    return None

# --- GESTION DES JOBS VIA SUPABASE ---

def load_jobs(user_email):
    """Récupère toutes les tâches appartenant à l'utilisateur connecté"""
    try:
        # On filtre les résultats : SELECT * FROM jobs_table WHERE owner_email = user_email
        response = supabase.table("jobs_table").select("*").eq("owner_email", user_email).execute()
        
        # Supabase renvoie une liste d'objets (dictionnaires)
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Erreur lors de la récupération de vos tâches : {e}")
        return []

def add_job(job_data):
    """Enregistre une nouvelle planification (ID géré par Supabase)"""
    try:
        # SÉCURITÉ : On retire 'id' s'il est présent dans le dictionnaire
        # car c'est Supabase (int8 Identity) qui doit le générer.
        job_data.pop('id', None)
        
        # Envoi vers Supabase
        supabase.table("jobs_table").insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'enregistrement de la tâche : {e}")
        return False

def update_job_status(job_id, status):
    """Active ou désactive une tâche via son ID (int8)"""
    try:
        # On s'assure que job_id est un entier pour coller au type int8
        supabase.table("jobs_table").update({"active": status}).eq("id", int(job_id)).execute()
    except Exception as e:
        st.error(f"Erreur lors de la mise à jour : {e}")

def delete_job(job_id):
    """Supprime une tâche via son ID (int8)"""
    try:
        # On s'assure que job_id est un entier
        supabase.table("jobs_table").delete().eq("id", int(job_id)).execute()
    except Exception as e:
        st.error(f"Erreur lors de la suppression : {e}")

# =============================================================================
# FONCTIONS LOGIQUE MÉTIER (Visualisation)
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

# =============================================================================
# APPLICATION PRINCIPALE
# =============================================================================

def run_mro_app():
    # Sidebar Info Utilisateur
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_first_name']} {st.session_state['user_last_name']}**")
        st.caption(f"🏢 {st.session_state['user_company']}")
        
        status_label = "Premium 💎" if st.session_state.get('user_status') else "Gratuit  standard"
        st.info(f"Plan : {status_label}")
        
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

    # --- ONGLET 1 : VISUALISATION ---
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

    # --- ONGLET 2 : PLANIFICATION (Connecté à Jobs_Table) ---
    with tab_plan:
        col_form, col_list = st.columns([1, 1.5])
        
        with col_form:
            st.subheader("🚀 Créer un nouveau rapport")
            with st.form("new_job_form"):
                job_name = st.text_input("Nom du rapport (ex: Suivi Hebdo)")
                recipients = st.text_input("Emails des destinataires (séparés par des virgules)")
                freq = st.selectbox("Fréquence", ["Quotidien", "Hebdomadaire", "Mensuel"])
                send_time = st.time_input("Heure d'envoi", value=time(8, 0))
                fmt = st.selectbox("Format du fichier", ["Excel (.xlsx)", "CSV"])
                
                submit = st.form_submit_button("💾 Enregistrer la planification")
                
                if submit:
                    if job_name and recipients:
                        # On prépare l'objet pour Supabase
                        new_job = {
                            "task_name": job_name,
                            "recipient": recipients,
                            "frequency": freq,
                            "hour": str(send_time),
                            "format": fmt,
                            "owner_email": st.session_state['user_email'], # LIEN CRUCIAL
                            "filters_config": st.session_state.get('active_filters', {}),
                            "active": False # Désactivé par défaut
                        }
                        if add_job(new_job):
                            st.success("Rapport ajouté à votre liste !")
                            st.rerun()
                    else:
                        st.error("Champs manquants")

        with col_list:
            st.subheader("📋 Mes rapports programmés")
            # On charge UNIQUEMENT les jobs de l'utilisateur
            my_jobs = load_jobs(st.session_state['user_email'])
            
            if not my_jobs:
                st.info("Vous n'avez pas encore de rapports planifiés.")
            else:
                for job in my_jobs:
                    # Design de la carte selon l'état Actif/Inactif
                    status_color = "#2ecc71" if job['active'] else "#95a5a6"
                    
                    with st.container():
                        # On affiche chaque job dans une "box"
                        st.markdown(f"""
                        <div style="border-left: 5px solid {status_color}; padding:10px; background:#f9f9f9; margin-bottom:10px; border-radius:5px">
                            <b>{job['task_name']}</b> | 🔄 {job['frequency']} à {job['hour']}<br>
                            <small>📧 Dest: {job['recipient']}</small>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Boutons d'action pour CHAQUE job
                        c1, c2, c3 = st.columns([1, 1, 2])
                        if c1.button("🗑️ Supprimer", key=f"del_{job['id']}"):
                            supabase.table("jobs_table").delete().eq("id", job['id']).execute()
                            st.rerun()
                            
                        btn_label = "⏸️ Désactiver" if job['active'] else "▶️ Activer"
                        if c2.button(btn_label, key=f"tog_{job['id']}"):
                            supabase.table("jobs_table").update({"active": not job['active']}).eq("id", job['id']).execute()
                            st.rerun()

# =============================================================================
# POINT D'ENTRÉE & LOGIN
# =============================================================================

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_email'] = None

    # ECRAN DE CONNEXION / INSCRIPTION
    if not st.session_state['logged_in']:
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.title("🔒 AeroTrack")
            
            choice = st.selectbox("Action", ["Se Connecter", "S'inscrire (Nouveau)"])
            
            if choice == "Se Connecter":
                with st.form("login_form"):
                    email = st.text_input("Email")
                    password = st.text_input("Mot de passe", type='password')
                    if st.form_submit_button("Entrer"):
                        user = login_user(email, password)
                        if user:
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = user['email']
                            st.session_state['user_first_name'] = user['first_name']
                            st.session_state['user_last_name'] = user['last_name']
                            st.session_state['user_company'] = user['company']
                            st.session_state['user_status'] = user['Status']
                            st.success("Connexion...")
                            st.rerun()
                        else:
                            st.error("Email ou mot de passe incorrect.")
            
            else: # INSCRIPTION COMPLÈTE
                with st.form("signup_form"):
                    st.subheader("Inscription Client")
                    c_a, c_b = st.columns(2)
                    new_first = c_a.text_input("Prénom")
                    new_last = c_b.text_input("Nom")
                    new_company = st.text_input("Entreprise")
                    new_email = st.text_input("Email pro")
                    new_password = st.text_input("Mot de passe", type='password')
                    
                    if st.form_submit_button("Créer mon compte"):
                        if new_email and new_password:
                            if save_user(new_email, new_password, new_first, new_last, new_company):
                                st.success("Compte créé ! Connectez-vous.")
                            else:
                                st.error("Erreur (Email déjà pris ?)")
                        else:
                            st.warning("Tout remplir SVP.")
    
    else:
        run_mro_app()

if __name__ == "__main__":
    main()