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
# Lecture fichier csv capa84
sheet_id = st.secrets["SHEET_ID"]
csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


# DATA FRAME 
# Chargement du Data Frame
@st.cache_resource(ttl=3600)
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
    lambda x: (m.group(0).upper().strip() if (m := re.search(r'(?<=fiche validee : ).*?(?= - )', re.sub(r"\s+", " ", unidecode(x)))) else None))

    df= df[['adherent', 'groupe']].dropna().reset_index().sort_values('groupe')
    df.drop(columns = 'index', inplace = True)

    # Renommer les groupes 
    df['groupe'] = df['groupe'].replace({
        "Loisir Avancé 1h00" : "Loisir Avancé mercredi",
        "Loisir Avancé 1h15" : "Loisir Avancé samedi",
        'Loisirs débutant et intermédiaire 1h15/semaine lundi' : "Loisirs D&I lundi",
        'Loisirs débutant et intermédiaire 1h15/semaine samedi' : "Loisirs D&I samedi",
        'Loisirs débutant et intermédiaire 2h30/semaine' : "Loisirs D&I 2h30/semaine",
        'Initiation 1h/semaine mardi' : "Initiation mardi",
        'Initiation 1h/semaine samedi' : "Initiation samedi"})
    
    df_partiel_1 = df[(df['groupe'] == "2 cours d'essais")
                  | (df['groupe'] == 'Adulte Compétition')
                  | (df['groupe'] == 'Basic Ice')
                  | (df['groupe'] == 'Compétition 1')
                  | (df['groupe'] == 'Compétition 2')
                  | (df['groupe'] == 'Détection')
                  | (df['groupe'] == 'Jardin de glace ( de 3 à 5 ans)')
                  | (df['groupe'] == 'Parasport')
                  | (df['groupe'] == 'Initiation mardi') 
                  | (df['groupe'] == 'Initiation samedi')
                  | (df['groupe'] == 'Loisir Avancé')
                  | (df['groupe'] == 'Loisirs D&I lundi')
                  | (df['groupe'] == 'Loisirs D&I samedi')
                  | (df['groupe'] == 'Loisir Avancé mercredi')
                  | (df['groupe'] == 'Loisir Avancé samedi')
                  ]
    df_partiel_1 = df_partiel_1.dropna(subset='adherent')

    df_partiel_2 = df[df['groupe'] == 'Initiation 2h/semaine']
    df_partiel_2 = df_partiel_2.dropna(subset='adherent')
    # On duplique en deux groupes : 
    # "Initiation mardi","Initiation samedi",
    df_initiation_mardi = df_partiel_2.copy()
    df_initiation_mardi["groupe"] = 'Initiation mardi'
    df_initiation_samedi = df_partiel_2.copy()
    df_initiation_samedi["groupe"] = 'Initiation samedi'
    
    df_partiel_3 = df[df['groupe'] == 'Loisirs D&I 2h30/semaine']
    df_partiel_3 = df_partiel_3.dropna(subset='adherent')
    # On duplique en deux groupes : 
    # Loisirs D&I lundi , Loisirs D&I samedi
    df_loisirs_lundi = df_partiel_3.copy()
    df_loisirs_lundi["groupe"] = 'Loisirs D&I lundi'
    df_loisirs__samedi = df_partiel_3.copy()
    df_loisirs__samedi["groupe"] = 'Loisirs D&I samedi'

    df_partiel_4 = df[df['groupe'] == "Loisir Avancé 2h15"]
    df_partiel_4 = df_partiel_4.dropna(subset='adherent')
    # On duplique en deux groupes : 
    # 'Loisir Avancé mercredi', 'Loisir Avancé samedi'
    df_loisirs_a_mercredi = df_partiel_4.copy()
    df_loisirs_a_mercredi["groupe"] = 'Loisir Avancé mercredi'
    df_loisirs_a_samedi = df_partiel_4.copy()
    df_loisirs_a_samedi["groupe"] = 'Loisir Avancé samedi'

    df_final = pd.concat([df_partiel_1, df_initiation_mardi, df_initiation_samedi, 
                          df_loisirs_lundi, df_loisirs__samedi, df_loisirs_a_mercredi, df_loisirs_a_samedi]).reset_index().drop(columns='index')
    
    if df_final["groupe"].dtype != "category":
        df_final["groupe"] = df_final["groupe"].astype("category")
    if df_final["adherent"].dtype != "category":
        df_final["adherent"] = df_final["adherent"].astype("category")
    
    return df_final

df_updated = update_df(df)


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

def get_headers(ws):
    # headers normalisés (strip)
    return [str(h).strip() for h in ws.row_values(1)]
#headers = ws.row_values(1)
headers = get_headers(ws)


# Rajouter la colonne date d'aujourd'hui 
current_date = date.today()
date_jour = date.today().strftime("%d/%m/%Y") # Date au format fr

if date_jour not in headers:
    ws.update_cell(1, len(headers) + 1, date_jour)
    headers.append(date_jour)

if date_jour not in headers:
    # Ajouter une nouvelle colonne à la fin avec le nom current_date
    ws.add_cols(1)
    #ws.update_cell(1, len(headers) + 1, date_jour)
    next_col = len(ws.row_values(1)) + 1
    ws.update_cell(1, next_col, date_jour)


jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
jour_semaine = jours[current_date.weekday()]  # lundi=0 ... dimanche=6
date_aujourdhui = f"{jour_semaine} {current_date.strftime('%d/%m/%Y')}"

# Afficher la date d'aujourd'hui sur l'appli
st.markdown(f"<h2 class='sub-title'>Nous sommes le {date_aujourdhui}</h2>", unsafe_allow_html=True)

# Sélecteur une autre date : 
choix_date = st.date_input("Séléctionnez une autre date dans le calendrier", value=current_date, format="DD/MM/YYYY")
choix_date_str = choix_date.strftime("%d/%m/%Y")
insert_new_date_index = None

if choix_date_str not in headers: 
    # Trouver la bonne position pour insérer choix_date
    header_dates = []
    for i in range(2, len(headers)): 
        header_dates.append(datetime.datetime.strptime(headers[i], "%d/%m/%Y"))

    for idx, d in enumerate(header_dates): 
        if choix_date < d.date():
            insert_new_date_index = idx + 2  # on insère avant cette colonne
            break

    if insert_new_date_index is not None:
        ws.spreadsheet.batch_update({
        "requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": insert_new_date_index,
                    "endIndex": insert_new_date_index + 1
                },
                "inheritFromBefore": True}}]})
        ws.update_cell(1, insert_new_date_index + 1, choix_date.strftime("%d/%m/%Y")) # 1 = première ligne (en tête)

# Colonnes sur google sheet 
headers = get_headers(ws)
col_nom = 1
col_group = 2
col_date = headers.index(date_jour) + 1
col_another_date = headers.index(choix_date_str) + 1

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
                cell = ws.find(personne, in_column=col_nom)
                if current_date != choix_date: 
                    ws.update_cell(cell.row, col_another_date, "Oui")
                else: 
                    ws.update_cell(cell.row, col_date, "Oui") # col_date = index

        st.markdown("<h3>Enregistré</h3>", unsafe_allow_html=True)
