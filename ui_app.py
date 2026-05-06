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

    sent_df = logs[
        (logs.user_id_source == me) &
        (logs.action == "send_request")
    ]

    received_df = logs[
        (logs.user_id_dest == me) &
        (logs.action == "send_request")
    ]

    # Convert to sets for fast lookup
    sent = set(sent_df.user_id_dest)
    received = set(received_df.user_id_source)

    mutual = sent.intersection(received)

    hidden_df = logs[
        (logs.user_id_source == me) &
        (logs.action == "hide")
    ]
    hidden = set(hidden_df.user_id_dest)

    return {
        "sent": sent,
        "received": received,
        "mutual": mutual,
        "hidden": hidden
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

def numeric_similarity(a, b):
    if a is None or b is None:
        return None

    a = float(a)
    b = float(b)

    # Normalize by the larger value (relative difference)
    if max(a, b) == 0:
        return 1

    return 1 - abs(a - b) / max(a, b)

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
        
        if q in ['age', 'max_budget']:
            sim = numeric_similarity(valA, valB)

        else:
            sim = categorical_similarity(valA, valB, opts)

        if sim is None:
            continue   # skip invalid data safely

        weight = (max(weightA, 0) + max(weightB, 0)) / 2

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
# Navigation
# --------------------------

if st.session_state.user:
    # Top navigation bar using columns
    col1, col2, col4, col5 = st.columns([3,2,1,1])

    with col1:
        if st.button("Roommate Finder"):
            st.session_state.page = "finder"
    with col2:
        if st.button("Matches"):
            st.session_state.page = "matches"

    #with col3:
    #    if st.button("Profile"):
    #        st.session_state.page = "profile"

    with col4:
        if st.button("My Profile"):
            st.session_state.page = "my_profile"

    with col5:
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.page = "login"
            st.rerun()



# --------------------------
# LOGIN
# --------------------------
if st.session_state.page == "login":
    st.title("Roommate Matcher 🏠")

    with st.form("login_form", clear_on_submit=False):
        user_id = st.text_input("User_ID")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign In")

    if submit:
        df = load_df(ws_info)
        user_row = df[(df["user_id"] == user_id) & (df["password"] == password)]

        if not user_row.empty:
            st.session_state.user = user_id
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
# ROOMMATE FINDER
# --------------------------
elif st.session_state.page == "finder":

    st.title("Find Roommates")

    df_info = load_df(ws_info)
    df_weights = load_df(ws_weights)

    me = st.session_state.user

    # ---- Safe lookups ----
    my_info_df = df_info[df_info.user_id == me]
    if my_info_df.empty:
        st.error("User info not found")
        st.stop()
    my_info = my_info_df.iloc[0]

    my_weights_df = df_weights[df_weights.user_id == me]
    if my_weights_df.empty:
        st.error("User weights not found")
        st.stop()
    my_weights = my_weights_df.iloc[0]

    state = get_match_state(me)
        
    sent = state["sent"]
    received = state["received"]
    mutual = state["mutual"]
    hidden = state["hidden"]


    # ---- Pre-index weights for performance ----
    weights_map = {row.user_id: row for _, row in df_weights.iterrows()}

    # ---- Filters ----
    st.sidebar.header("Filters")
    filters = {}
    for q, opts in questions:
        filters[q] = st.sidebar.multiselect(q, opts)

    def passes_filters(user, filters):
        """
        Returns True if a candidate user passes all selected filters.
        
        user: dict / pd.Series of candidate profile
        filters: dict of filter criteria selected by current user
        """

        for key, value in filters.items():
            # Skip empty filters
            if value is None or value == "" or value == []:
                continue

            # Skip missing user data
            if key not in user or user[key] is None:
                return False

            # Special handling for budget (numeric <=)
            if key == "max_budget":
                try:
                    if float(user[key]) > float(value):
                        return False
                except:
                    return False

            # Numeric exact match (age if needed)
            elif key in ["age"]:
                try:
                    if int(user[key]) != int(value):
                        return False
                except:
                    return False

            # General categorical match
            else:
                if user[key] != value:
                    return False

        return True
    
    # ---- Compute matches ----
    matches = []

    for _, other in df_info.iterrows():

        uid = other.user_id

        if uid == me:
            continue

        # Hide logic
        if uid in hidden:
            continue

        # Skip already matched (optional)
        if uid in mutual:
             continue

        # Filters
        if not passes_filters(other, filters):
            continue

        w_other = weights_map.get(uid)
        if w_other is None:
            continue

        score = compatibility_score_v2(my_info, other, my_weights, w_other)

        # Non-negotiables auto filtered because score=None
        if score is None:
            continue

        matches.append((uid, score))

    # ---- Sort matches ----
    matches.sort(key=lambda x: x[1], reverse=True)

    # ---- Pagination ----
    start = st.session_state.page_idx * PAGE_SIZE
    end = start + PAGE_SIZE
    page_matches = matches[start:end]

    # ---- Render results ----
    for uid, score in page_matches:
        user_df = df_info[df_info.user_id == uid]
        if user_df.empty:
            continue
        user = user_df.iloc[0]

        with st.container():
            st.markdown(f"### 👤 {user.first_name} {user.last_name}")

            col1, col2, col3 = st.columns([2, 1, 1])

            col1.metric("Compatibility", f"{round(score * 100)}%")

            if uid in mutual:
                col1.success("Match ✅")

            elif uid in received:
                if col2.button("Accept", key=f"accept_{uid}"):
                    log_action(me, uid, "accept_request")
                    st.rerun()

            elif uid in sent:
                col1.info("Requested 📩")

            else:
                if col2.button("Request", key=f"req_{uid}"):
                    log_action(me, uid, "send_request")
                    st.rerun()

            # ALWAYS AVAILABLE
            if col3.button("Hide", key=f"hide_{uid}"):
                log_action(me, uid, "hide_user")
                st.rerun()

            st.divider()

    # ---- Pagination controls ----
    col1, col2 = st.columns(2)

    if col1.button("Prev", disabled=st.session_state.page_idx == 0):
        st.session_state.page_idx -= 1
        st.rerun()

    if col2.button("Next", disabled=end >= len(matches)):
        st.session_state.page_idx += 1
        st.rerun()

# --------------------------
# MATCHES
# --------------------------
elif st.session_state.page == "matches":
    st.title("Your Matches")

    df_info = load_df(ws_info)
    df_weights = load_df(ws_weights)
    me = st.session_state.user

    my_info = df_info[df_info.user_id == me].iloc[0]
    my_weights = df_weights[df_weights.user_id == me].iloc[0]

    state = get_match_state(me)

    hidden = state["hidden"]
    sent = state["sent"]
    received = state["received"]
    mutual = state["mutual"]

    weights_map = {row.user_id: row for _, row in df_weights.iterrows()}

    results = []

    for _, other in df_info.iterrows():
        uid = other.user_id

        if uid == me or uid in hidden:
            continue

        if uid not in mutual and uid not in sent and uid not in received:
            continue

        w_other = weights_map.get(uid)
        if w_other is None:
            continue

        score = compatibility_score_v2(my_info, other, my_weights, w_other)

        if score is None:
            continue

        if uid in mutual:
            status = "match"
        elif uid in received:
            status = "incoming"
        else:
            status = "pending"

        results.append((uid, score, status))

    # SORT: matches first, then incoming, then pending
    status_order = {"match": 0, "incoming": 1, "pending": 2}
    results.sort(key=lambda x: (status_order[x[2]], -x[1]))

    # RENDER
    for uid, score, status in results:
        user = df_info[df_info.user_id == uid].iloc[0]

        with st.container():
            st.markdown(f"### 👤 {user.first_name} {user.last_name}")
            st.metric("Compatibility", f"{round(score*100)}%")

            col1, col2, col3 = st.columns([2,1,1])

            if status == "match":
                col1.success("Matched ✅")

            elif status == "incoming":
                if col2.button("Accept", key=f"match_accept_{uid}"):
                    log_action(me, uid, "accept_request")
                    st.rerun()

            else:
                col1.info("Pending 📩")

            if col2.button("View", key=f"match_view_{uid}"):
                st.session_state.view = uid
                st.session_state.page = "profile"
                st.rerun()

            if col3.button("Hide", key=f"match_hide_{uid}"):
                log_action(me, uid, "hide_user")
                st.rerun()

            st.divider()


# --------------------------
# PROFILE
# --------------------------
elif st.session_state.page == "profile":
    st.title("My Profile")

    df = load_df(ws_info)
    user_data = df[df["user_id"] == st.session_state.user].iloc[0]

    st.markdown("### Personal Info")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Age", user_data["age"])
        st.metric("Gender", user_data["gender"])
        st.metric("Budget", f"${user_data['max_budget']}")

    with col2:
        st.metric("Sleep", user_data["sleep_schedule"])
        st.metric("Cleanliness", user_data["cleanliness_level"])
        st.metric("Social", user_data["social_level"])

    st.markdown("---")

    st.markdown("### Lifestyle")
    st.write(f"🛏 Sleep: {user_data['sleep_schedule']}")
    st.write(f"🧹 Cleanliness: {user_data['cleanliness_level']}")
    st.write(f"🎉 Guests: {user_data['guests_frequency']}")
    st.write(f"🚬 Smoking: {user_data['smoking']}")


# --------------------------
# MY PROFILE
# --------------------------

elif st.session_state.page == "my_profile":
    st.title("Edit Profile")

    df = load_df(ws_info)
    user_idx = df[df["user_id"] == st.session_state.user].index[0]
    user_data = df.loc[user_idx]

    with st.form("edit_profile_form"):
        updated = {}
        for q, opts in questions:
            updated[q] = st.selectbox(q.replace("_", " ").title(), opts, index=opts.index(user_data[q]))

        save = st.form_submit_button("Save Changes")

    if save:
        for key, val in updated.items():
            df.at[user_idx, key] = val

        ws_info.clear()
        ws_info.update([df.columns.values.tolist()] + df.values.tolist())

        st.success("Profile updated!")
        st.session_state.page = "profile"
        st.rerun()