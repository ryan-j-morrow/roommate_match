import streamlit as st
import pandas as pd
import numpy as np
import gspread
import json 
from google.oauth2.service_account import Credentials
import datetime

# --------------------------
# GOOGLE SHEETS CONNECTION
# --------------------------

def connect_gsheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )

    return gspread.authorize(creds)


client = connect_gsheet()
sheet = client.open("roommate_match_demo")

ws_info = sheet.worksheet("UserInfo")
ws_weights = sheet.worksheet("UserWeights")
ws_log = sheet.worksheet("InteractionLog")

# --------------------------
# OPTIONS
# --------------------------
age_options = [str(i) for i in range(18, 31)]
gender_options = ['Male','Female','Non-Binary','Other']
sleep_schedule_options = ['Early bird','Flexible','Night owl']
cleanliness_level_options = ['Very clean','Average','Messy']
guests_frequency_options = ['Never','Occasionally','Often']
smoking_options = ['No','Outside only','Inside']
noise_tolerance_options = ['Low','Medium','High']
max_budget_options = [500,750,1000,1250,1500,1750,2000,2250,2500,2750,3000,3250,3500,3750,4000]
pets_comfort_options = ['Love pets','OK with pets','Prefer no pets']
work_from_home_options = ['No','Sometimes','Yes']
social_level_options = ['Quiet','Moderate','Social']
conflict_resolution_options = ['Avoidant','Direct','Mediated']

questions = [
    ("age", age_options),
    ("gender", gender_options),
    ("sleep_schedule", sleep_schedule_options),
    ("cleanliness_level", cleanliness_level_options),
    ("guests_frequency", guests_frequency_options),
    ("smoking", smoking_options),
    ("noise_tolerance", noise_tolerance_options),
    ("max_budget", max_budget_options),
    ("pets_comfort", pets_comfort_options),
    ("work_from_home", work_from_home_options),
    ("social_level", social_level_options),
    ("conflict_resolution", conflict_resolution_options)
]

# --------------------------
# HELPERS
# --------------------------
def load_df(ws):
    return pd.DataFrame(ws.get_all_records())

def log_action(src, dest, action):
    ws_log.append_row([src, dest, action, str(datetime.datetime.now())])

def get_match_state(me):
    logs = load_df(ws_log)

    sent = logs[(logs.user_id_source == me) & (logs.action == "send_request")]
    received = logs[(logs.user_id_dest == me) & (logs.action == "send_request")]

    mutual = set(sent.user_id_dest).intersection(set(received.user_id_source))

    hidden = logs[(logs.user_id_source == me) & (logs.action == "hide_user")]

    return {
        "sent": set(sent.user_id_dest),
        "received": set(received.user_id_source),
        "mutual": mutual,
        "hidden": set(hidden.user_id_dest)
    }

def categorical_similarity(a, b, options):
    if a is None or b is None:
        return None

    # Normalize strings
    a = str(a).strip()
    b = str(b).strip()
    options = [str(o).strip() for o in options]

    if a == b:
        return 1.0

    if a not in options or b not in options:
        return None   # <-- critical fix

    idx_a = options.index(a)
    idx_b = options.index(b)

    return 1 - abs(idx_a - idx_b) / (len(options) - 1)

def compatibility_score_v2(userA, userB, wA, wB):
    total_weight = 0
    score_sum = 0

    for (q, opts) in questions:
        valA = userA[q]
        valB = userB[q]

        weightA = wA[f"weight_{q}"]
        weightB = wB[f"weight_{q}"]

        if weightA == -1 and valA != valB:
            return None
        if weightB == -1 and valA != valB:
            return None
        
        sim = categorical_similarity(valA, valB, opts)

        if sim is None:
            continue   # skip invalid data safely

        weight = max(weightA, 0) + max(weightB, 0)

        score_sum += sim * weight
        total_weight += weight

    if total_weight == 0:
        return 0

    return score_sum / total_weight

# --------------------------
# SESSION STATE
# --------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "page" not in st.session_state:
    st.session_state.page = "login"

if "page_idx" not in st.session_state:
    st.session_state.page_idx = 0

PAGE_SIZE = 10

# --------------------------
# LOGIN
# --------------------------
if st.session_state.page == "login":
    st.title("Roommate Matcher 🏠")

    uid = st.text_input("User ID")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        df = load_df(ws_info)
        user = df[(df.user_id == uid) & (df.password == pwd)]

        if len(user):
            st.session_state.user = uid
            st.session_state.page = "matches"
            st.rerun()
        else:
            st.error("Invalid login")

    if st.button("Create Account"):
        st.session_state.page = "signup"
        st.rerun()

# --------------------------
# SIGNUP
# --------------------------
elif st.session_state.page == "signup":
    st.header("Create Account")

    with st.form("signup_form"):
        responses = {}
        weights = {}
        non_negotiable = {}

        for q, options in questions:
            st.subheader(q.replace("_", " ").title())

            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                responses[q] = st.selectbox(
                    f"{q}_answer", options, key=f"{q}_answer"
                )

            with col2:
                weights[q] = st.slider(
                    "Importance", 1, 5, 3, key=f"{q}_weight"
                )

            with col3:
                non_negotiable[q] = st.checkbox(
                    "Dealbreaker", key=f"{q}_nonneg"
                )

        colA, colB = st.columns(2)

        with colA:
            submitted = st.form_submit_button("✅ Submit")

        with colB:
            cancel = st.form_submit_button("⬅ Cancel")

        if submitted:
            st.success("Account created!")

            # Store everything in session (or send to Sheets)
            st.session_state.responses = responses
            st.session_state.weights = weights
            st.session_state.non_negotiable = non_negotiable

            # (Later: save to Google Sheets)
            st.session_state.page = "matches"
            st.rerun()

        if cancel:
            st.session_state.page = "login"
            st.rerun()
# --------------------------
# MATCHES
# --------------------------
elif st.session_state.page == "matches":

    st.title("Find Roommates")

    df_info = load_df(ws_info)
    df_weights = load_df(ws_weights)

    me = st.session_state.user

    my_info = df_info[df_info.user_id == me].iloc[0]
    my_weights = df_weights[df_weights.user_id == me].iloc[0]

    state = get_match_state(me)

    # Filters
    st.sidebar.header("Filters")
    min_budget = st.sidebar.selectbox("Min Budget", max_budget_options)
    smoke_pref = st.sidebar.selectbox("Smoking", ["Any"] + smoking_options)

    def passes_filters(user):
        if user.user_id in state["hidden"]:
            return False

        if max_budget_options.index(user.max_budget) < max_budget_options.index(min_budget):
            return False

        if smoke_pref != "Any" and user.smoking != smoke_pref:
            return False

        return True

    # Compute matches
    matches = []

    for _, other in df_info.iterrows():
        if other.user_id == me:
            continue

        if not passes_filters(other):
            continue

        w_other = df_weights[df_weights.user_id == other.user_id].iloc[0]

        score = compatibility_score_v2(my_info, other, my_weights, w_other)

        if score is not None:
            matches.append((other.user_id, score))

    matches.sort(key=lambda x: x[1], reverse=True)

    # Pagination
    start = st.session_state.page_idx * PAGE_SIZE
    end = start + PAGE_SIZE
    page_matches = matches[start:end]

    for uid, score in page_matches:
        user = df_info[df_info.user_id == uid].iloc[0]

        with st.container():
            st.markdown(f"### 👤 {user.first_name} {user.last_name}")

            col1, col2, col3 = st.columns([2,1,1])

            col1.metric("Compatibility", f"{round(score*100)}%")

            if uid in state["mutual"]:
                col1.success("Match ✅")
            elif uid in state["sent"]:
                col1.info("Requested 📩")

            if col2.button("View", key=f"view_{uid}"):
                st.session_state.view = uid
                st.session_state.page = "profile"
                st.rerun()

            if col3.button("Hide", key=f"hide_{uid}"):
                log_action(me, uid, "hide_user")

            st.divider()

    # Pagination buttons
    col1, col2 = st.columns(2)

    if col1.button("Prev") and st.session_state.page_idx > 0:
        st.session_state.page_idx -= 1
        st.rerun()

    if col2.button("Next") and end < len(matches):
        st.session_state.page_idx += 1
        st.rerun()

# --------------------------
# PROFILE
# --------------------------
elif st.session_state.page == "profile":

    df_info = load_df(ws_info)
    me = st.session_state.user
    target = st.session_state.view

    user = df_info[df_info.user_id == target].iloc[0]
    state = get_match_state(me)

    st.header(f"{user.first_name} {user.last_name}")

    # If mutual match → show contact
    if target in state["mutual"]:
        st.success("✅ Matched!")
        st.write(f"📞 {user.phone}")
        st.write(f"📧 {user.email}")

    for q, _ in questions:
        st.write(f"{q}: {user[q]}")

    if target not in state["sent"]:
        if st.button("Request to Chat"):
            log_action(me, target, "send_request")
    else:
        st.info("Request Sent")

    if st.button("Hide User"):
        log_action(me, target, "hide_user")

    if st.button("Back"):
        st.session_state.page = "matches"
        st.rerun()