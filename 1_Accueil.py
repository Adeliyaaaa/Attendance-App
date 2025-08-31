import pandas as pd
import streamlit as st
import datetime
from datetime import date
import re
from pathlib import Path
import os
import dotenv
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1
from unidecode import unidecode

load_dotenv()

# PAGE STREAMLIT 
st.set_page_config(layout="wide") # vérifier si je peux changer le layout 
st.session_state["page"] = "Accueil"
st.logo("https://www.capa84.com/wp-content/uploads/2022/07/0000000006_480x480.webp", size="large")

st.title("CAPA84 Avignon")
st.markdown(f"<h1 class='sub-title'>Ice Time ⛸️</h1>" , unsafe_allow_html=True)

# Fichier -> Importer -> Importer -> parcourir -> double cliquer sur le nouveau fichier -> Remplacer la feuille de calcul -> Im^porter les données
#sheet_id = os.getenv('sheet_id')
sheet_id = st.secrets["SHEET_ID"]
csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


# GOOGLE SHEET API 
# 1. Connexion
# 1) Scopes d'accès (Drive + Sheets pour ouvrir par URL)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# 2) Client gspread à partir de st.secrets
@st.cache_resource
def make_gs_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

gc = make_gs_client()

# 3) Ouvrir le Google Sheet

sh = gc.open_by_url(st.secrets["GOOGLE_SHEET_URL"])

# 6. Choisir un onglet
ws = sh.sheet1   # ou sh.worksheet Feuille 1")

# 7. Colonnes dans Google Sheets
headers = ws.row_values(1)  # toujours une liste de strings

# Rajouter la colonne date d'aujourd'hui 
current_date = date.today()
date_jour = date.today().strftime("%d/%m/%Y")

if date_jour not in headers:
    ws.update_cell(1, len(headers) + 1, date_jour)
    headers.append(date_jour)

if date_jour not in headers:
    # Ajouter une nouvelle colonne à la fin avec le nom current_date
    ws.update_cell(1, len(headers) + 1, date_jour)

jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
jour_semaine = jours[current_date.weekday()]  # lundi=0 ... dimanche=6
date_aujourdhui = f"{jour_semaine} {current_date.strftime('%d/%m/%Y')}"

st.markdown(f"<h2 class='sub-title'>{date_aujourdhui}</h2>", unsafe_allow_html=True)

# 9. Colonnes sur google sheet 
col_nom = 1
col_group = 2
col_date = headers.index(date_jour) + 1

# Chargement du Data Frame
@st.cache_resource
def load_csv(path: str, show_spinner=False) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df

df = load_csv(csv_url)

# GROUPE
def groupe_patinage(val: str) -> str:
    # Cas vides / NaN
    if pd.isna(val):
        return None

    s = str(val)

    # S'il y a un | mais il y a aussi |Option
    m = re.findall(r'(?<=\|)\s*(?!Option).*?(?=\s\(\d+)', s)
    if m:
        return m[-1].strip()

    # Sinon → tout jusqu'à " (chiffres"
    m = re.search(r'.*?(?=\s*\(\d+)', s)
    if m:
        return m.group(0).strip()

    # Si rien ne matche, renvoyer la chaîne nettoyée
    return s.strip()

@st.cache_data(ttl=3600, show_spinner=False) 
def update_df(df: pd.DataFrame) -> pd.DataFrame:
    # Groupe:
    df['groupe'] = df["Produits d'adhésion"].apply(groupe_patinage)
    # nom  et prénom de l'adhérent
    df["adherent"] = df["Fiche d'adhésion"].apply(
        lambda x: (m.group(0).upper().strip() if (m := re.search(r'(?<= : ).*?(?= - )', re.sub(r"\s+", " ", unidecode(x)))) else None))
    df= df[['adherent', 'groupe']].dropna().reset_index().sort_values('groupe')
    df.drop(columns = 'index', inplace = True)
    if df["groupe"].dtype != "category":
        df["groupe"] = df["groupe"].astype("category")
    if df["adherent"].dtype != "category":
        df["adherent"] = df["adherent"].astype("category")
    return df

df_updated = update_df(df)


@st.cache_data(ttl=900, show_spinner=False) 
def get_group_list(df: pd.DataFrame) -> list:
    groupes = df_updated["groupe"].astype(str).sort_values().unique().tolist()
    return groupes

groupes = get_group_list(df_updated)
groupe_with_blank = [" "] + groupes

# mettre en cache les adhérents par groupe : 
# Sélecteur GROUPE
choix_groupe = st.selectbox("Sélectionnez un groupe :", groupe_with_blank)

@st.cache_data(ttl=3600, show_spinner=False)
def get_adherents(df_updated, groupe):
    adherents = df_updated.loc[df_updated["groupe"] == groupe, "adherent"].sort_values().unique().tolist()
    return adherents

# Noms qui sont déjà enregistrés dans  Google Sheet
noms_existants = ws.col_values(col_nom)   

if choix_groupe != " ":
    adherents = get_adherents(df_updated, choix_groupe)
    # État initial stocké une fois pour toutes
    state_key_df = f"presence_df_{choix_groupe}"
    if state_key_df not in st.session_state:
        st.session_state[state_key_df] = pd.DataFrame({
            "Adhérent": adherents,
            "Présent": False
        })

    with st.form(key=f"presence_form_{choix_groupe}", clear_on_submit=False):
        edited = st.data_editor(
            st.session_state[state_key_df],
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            key=f"presence_table_{choix_groupe}",
            column_config={
                "Adhérent": st.column_config.TextColumn("Adhérent", disabled=True),
                "Présent": st.column_config.CheckboxColumn("Présent", default=False),
            },
        )
        submitted = st.form_submit_button("Enregistrer")

    if submitted:
        # Sauvegarde (en session, BDD, CSV, etc.)
        st.session_state[state_key_df] = edited
        liste_presence = edited.loc[edited["Présent"], "Adhérent"].tolist()
        
        for personne in liste_presence : 
            if personne not in noms_existants:
                # Ajout d’un nouvel adhérent avec groupe + Oui dans la colonne date
                new_row = [""] * len(headers)   # crée une ligne vide
                new_row[col_nom-1] = personne   # NOM
                new_row[col_group-1] = choix_groupe   # GROUP
                new_row[col_date-1] = "Oui"     # Présence
                ws.append_row(new_row, value_input_option="USER_ENTERED")
            else:
                # Mettre à jour la présence dans la colonne du jour
                cell = ws.find(personne)
                #ws.update_cell(cell.row, col_date, "Oui")

        st.markdown("<h3>Enregistré</h3>", unsafe_allow_html=True)
        
