import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import hashlib
from supabase import create_client, Client

# --- 1. CONFIGURATION & CONNEXION SUPABASE ---
st.set_page_config(layout="wide", page_title="AeroControl Tower", page_icon="✈️")

# Récupération des secrets
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ Erreur de connexion Supabase. Vérifiez vos 'Secrets' dans Streamlit Cloud.")
    st.stop()

# --- CSS (DESIGN MIS À JOUR) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    
    /* CARTE TRANSPARENTE / BORDURE ORANGE PALE */
    .job-card {
        padding: 15px; 
        border-radius: 10px; 
        margin-bottom: 10px; 
        background-color: transparent !important; 
        border: 2px solid #FFCC80; 
    }
    
    /* BORDURE VERTE POUR LES ACTIFS */
    .border-active {
        border: 2px solid #2ECC71 !important;
    }

    .small-text {font-size: 0.85rem; opacity: 0.9;}
</style>
""", unsafe_allow_html=True)
# =============================================================================
# MODULE SÉCURITÉ & BASE DE DONNÉES
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
        st.error(f"Erreur inscription : {e}")
        return False

def login_user(email, password):
    hashed_pw = make_hashes(password)
    try:
        res = supabase.table("users_table").select("*").eq("email", email).execute()
        if res.data and res.data[0].get('password') == hashed_pw:
            return res.data[0]
    except Exception as e:
        st.error(f"Erreur connexion : {e}")
    return None

def load_jobs(user_email):
    try:
        res = supabase.table("jobs_table").select("*").eq("owner_email", user_email).execute()
        return res.data if res.data else []
    except: return []

def add_job(job_data):
    try:
        job_data.pop('id', None) 
        supabase.table("jobs_table").insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Erreur enregistrement tâche : {e}")
        return False

# =============================================================================
# LOGIQUE MÉTIER
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
        st.error(f"Erreur import : {e}")
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
# APPLICATION PRINCIPALE
# =============================================================================

def run_mro_app():
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_first_name']} {st.session_state['user_last_name']}**")
        st.caption(f"🏢 {st.session_state['user_company']}")
        if st.button("Déconnexion", type="primary"):
            st.session_state['logged_in'] = False
            # On vide le cache persistant à la déconnexion
            if 'df_persistent' in st.session_state: del st.session_state['df_persistent']
            st.rerun()
        st.markdown("---")

    st.title("✈️ MRO Control Tower")

    with st.expander("📂 Source de Données", expanded=True):
        uploaded_file = st.file_uploader("Fichier Excel/CSV", type=['xlsx', 'csv'])

    # --- LOGIQUE DE PERSISTANCE (300k LIGNES) ---
    df_raw = None

    if uploaded_file is not None:
        # Cas 1 : Nouvel import manuel
        df_raw = load_data(uploaded_file)
        if df_raw is not None:
            # Sauvegarde massive dans Supabase
            save_imported_data(df_raw, st.session_state['user_email'])
            # Mise à jour du cache local
            st.session_state['df_persistent'] = df_raw
            st.success(f"✅ Données synchronisées : {len(df_raw)} lignes enregistrées.")
    else:
        # Cas 2 : Pas d'upload, on regarde dans le cache session ou dans la base
        if 'df_persistent' not in st.session_state or st.session_state['df_persistent'] is None:
            with st.spinner("🔄 Récupération de vos données sauvegardées..."):
                st.session_state['df_persistent'] = load_stored_data(st.session_state['user_email'])
        
        df_raw = st.session_state['df_persistent']

    # On ne continue que si on a des données
    if df_raw is None:
        st.info("👋 Bienvenue ! Veuillez importer un fichier pour activer les outils.")
        return

    # --- AFFICHAGE DES ONGLETS ---
    tab_visu, tab_plan = st.tabs(["📊 Visualisation", "📅 Planification & Envois"])

    # --- ONGLET 1 : VISUALISATION ---
    with tab_visu:
        with st.expander("⚙️ Configuration des filtres & colonnes", expanded=False):
            c1, c2, c3 = st.columns([1, 1, 2])
            cols_date = [c for c in df_raw.columns if 'date' in c.lower()]
            default_date = cols_date[0] if cols_date else df_raw.columns[0]
            
            date_col = c1.selectbox("Colonne Date Référence", df_raw.columns, index=list(df_raw.columns).index(default_date))
            master_filter_cols = c2.multiselect("Définir Master Filters", [c for c in df_raw.columns if c != date_col])
            displayed_columns = c3.multiselect("Colonnes à afficher", options=df_raw.columns, default=list(df_raw.columns))

        st.markdown("##### 🔍 Master Filters")
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
        
        st.markdown("---")
        c_time, c_kpi = st.columns([2, 1])
        with c_time:
            period = st.radio("Période :", ["Tout voir", "7 Jours", "30 Jours", "90 Jours"], horizontal=True)
            days_map = {"Tout voir": 0, "7 Jours": 7, "30 Jours": 30, "90 Jours": 90}
            days = days_map[period]
            df_final = filter_date(df_final, date_col, days)
            current_filters_config["retention_days"] = days
            current_filters_config["date_column"] = date_col

        with c_kpi:
            st.metric("Lignes affichées", len(df_final), delta=f"sur {len(df_raw)} total")
        
        st.dataframe(df_final, column_order=displayed_columns, use_container_width=True, height=500, hide_index=True)
        st.session_state['active_filters'] = current_filters_config
   # --- ONGLET 2 : PLANIFICATION ---
# --- ONGLET 2 : PLANIFICATION ---
    with tab_plan:
        col_form, col_list = st.columns([1, 1.5])
        
        with col_form:
            st.subheader("🚀 Nouveau Rapport")
            with st.form("new_job_form"):
                job_name = st.text_input("Nom du rapport")
                recipients = st.text_input("Emails des destinataires (séparés par des virgules)")
                
                # --- NOUVELLE LOGIQUE DE FRÉQUENCE ---
                st.write("**Configuration de l'envoi**")
                
                # Cases à cocher pour les jours (on peut en sélectionner plusieurs)
                selected_days = st.multiselect(
                    "Jours de la semaine", 
                    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
                    default=["Lundi"]
                )
                
                # Précision de la récurrence
                recurrence = st.selectbox(
                    "Intervalle", 
                    ["Toutes les semaines", "Toutes les 2 semaines", "Toutes les 4 semaines"]
                )
                
                # On combine pour la base de données
                days_str = ", ".join(selected_days)
                final_frequency_str = f"{days_str} ({recurrence})"
                
                send_time = st.time_input("Heure d'envoi", value=time(8, 0))
                fmt = st.selectbox("Format", ["Excel (.xlsx)", "CSV"])
                
                if st.form_submit_button("💾 Enregistrer"):
                    if job_name and recipients and selected_days:
                        new_job = {
                            "task_name": job_name,
                            "recipient": recipients,
                            "frequency": final_frequency_str,
                            "hour": str(send_time),
                            "format": fmt,
                            "owner_email": st.session_state['user_email'],
                            "filters_config": st.session_state.get('active_filters', {}),
                            "active": False
                        }
                        if add_job(new_job):
                            st.success("Planification enregistrée !")
                            st.rerun()
                    else: 
                        st.error("Veuillez remplir le nom, les emails et choisir au moins un jour.")

        with col_list:
            st.subheader("📋 Mes rapports programmés")
            my_jobs = load_jobs(st.session_state['user_email'])
            
            if not my_jobs:
                st.info("Aucun rapport planifié pour le moment.")
            else:
                for job in my_jobs:
                    # Bordure dynamique : vert si actif, orange sinon
                    border_class = "border-active" if job['active'] else ""
                    icon_status = "🟢 Actif" if job['active'] else "🟠 Inactif"
                    
                    with st.container():
                        # Application du style transparent avec bordure
                        st.markdown(f"""
                        <div class="job-card {border_class}">
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                                <strong style="font-size:1.1em;">{job['task_name']}</strong>
                                <span>{icon_status}</span>
                            </div>
                            <div class="small-text">
                                📅 <b>{job['frequency']}</b> à {job['hour']}<br>
                                📧 {job['recipient']} | 📁 {job['format']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        c1, c2, c3 = st.columns([1, 1, 2])
                        if c1.button("🗑️ Supprimer", key=f"del_{job['id']}"):
                            supabase.table("jobs_table").delete().eq("id", job['id']).execute()
                            st.rerun()
                            
                        label = "⏸️ Stop" if job['active'] else "▶️ Activer"
                        if c2.button(label, key=f"tog_{job['id']}"):
                            supabase.table("jobs_table").update({"active": not job['active']}).eq("id", job['id']).execute()
                            st.rerun()
                        
                        with c3.expander("🔍 Voir Filtres"):
                            st.json(job['filters_config'])

# =============================================================================
# SAVE IMPORTED DATA
# =============================================================================
def save_imported_data(df, user_email):
    """Sauvegarde massive par paquets avec conversion des dates pour le JSON"""
    try:
        # 1. On vide les anciennes données
        supabase.table("raw_data_table").delete().eq("owner_email", user_email).execute()
        
        # --- MODIFICATION ICI : On convertit les Timestamps en String ---
        df_save = df.copy()
        for col in df_save.columns:
            # Si la colonne contient des dates, on les transforme en texte ISO
            if pd.api.types.is_datetime64_any_dtype(df_save[col]):
                df_save[col] = df_save[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # 2. Préparation des données (on utilise le DataFrame converti)
        all_rows = [{"owner_email": user_email, "row_data": row} for row in df_save.to_dict(orient='records')]
        
        # 3. Envoi par morceaux (Chunks)
        chunk_size = 5000
        total = len(all_rows)
        progress_bar = st.progress(0, text="Synchronisation avec Supabase...")
        
        for i in range(0, total, chunk_size):
            chunk = all_rows[i : i + chunk_size]
            supabase.table("raw_data_table").insert(chunk).execute()
            pct = min((i + chunk_size) / total, 1.0)
            progress_bar.progress(pct, text=f"Sauvegarde en cours : {int(pct*100)}%")
            
        progress_bar.empty()
        return True
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False

def load_stored_data(user_email):
    """Récupération de gros volumes par pagination (Supabase limite à 1000 par défaut)"""
    try:
        all_data = []
        page_size = 10000 # On récupère 10k par 10k
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
        st.error(f"Erreur de récupération : {e}")
        return None
# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.title("🔒 Accès AeroTrack")
            choice = st.selectbox("Action", ["Connexion", "Inscription"])
            
            if choice == "Connexion":
                with st.form("login"):
                    e = st.text_input("Email")
                    p = st.text_input("Mot de passe", type='password')
                    if st.form_submit_button("Se connecter"):
                        u = login_user(e, p)
                        if u:
                            st.session_state.update({
                                "logged_in": True, "user_email": u['email'],
                                "user_first_name": u['first_name'], "user_last_name": u['last_name'],
                                "user_company": u['company'], "user_status": u['Status']
                            })
                            st.rerun()
                        else: st.error("Email ou mot de passe incorrect.")
            else:
                with st.form("signup"):
                    fn = st.text_input("Prénom")
                    ln = st.text_input("Nom")
                    cp = st.text_input("Entreprise")
                    em = st.text_input("Email professionnel")
                    pw = st.text_input("Mot de passe", type='password')
                    if st.form_submit_button("Créer mon compte"):
                        if em and pw:
                            if save_user(em, pw, fn, ln, cp): st.success("Compte créé ! Connectez-vous.")
                        else: st.warning("Veuillez remplir les champs obligatoires.")
    else:
        run_mro_app()

if __name__ == "__main__":
    main()
    