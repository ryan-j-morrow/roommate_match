import streamlit as st
import pandas as pd
import numpy as np
import json 
import datetime
from supabase import create_client, Client


# --------------------------
# THEME / STYLING
# --------------------------
PRIMARY_COLOR = "#BFA2FF"   # light purple
SECONDARY_COLOR = "#F5F0FF"
ACCENT_COLOR = "#7A5FFF"
TEXT_COLOR = "#1F1F1F"
MUTED_TEXT = "#6E6E6E"
BORDER_RADIUS = "10px"

st.set_page_config(
    page_title="Roommate Matcher",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown(f"""
<style>
    html, body, [data-testid="stAppViewContainer"] {{
        background-color: {SECONDARY_COLOR};
        color: {TEXT_COLOR};
        font-family: 'Inter', sans-serif;
    }}

    h1, h2, h3 {{
        color: {ACCENT_COLOR};
        font-weight: 600;
    }}

    .stButton > button {{
        background-color: {PRIMARY_COLOR};
        color: black;
        border-radius: {BORDER_RADIUS};
        padding: 0.5rem 1rem;
        border: none;
    }}

    .stButton > button:hover {{
        background-color: {ACCENT_COLOR};
        color: white;
    }}

    .card {{
        background-color: white;
        padding: 1rem;
        border-radius: {BORDER_RADIUS};
        box-shadow: 0px 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }}

    .section-title {{
        font-size: 1.25rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }}

    hr {{
        border: 1px solid #E4D9FF;
    }}
</style>
""", unsafe_allow_html=True)

# --------------------------
# GOOGLE SHEETS CONNECTION
# --------------------------

SUPABASE_URL = st.secrets['SUPABASE_URL']
SUPABASE_KEY = st.secrets['SUPABASE_PUB_KEY']

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------
# OPTIONS
# --------------------------
age_options = list(range(18, 31))
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
def load_df(table_name):
    response = supabase.table(table_name).select("*").execute()
    return pd.DataFrame(response.data)

def authenticate_user(user_id, password):
    response = supabase.table("user_info") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("password", password) \
        .execute()

    if response.data:
        return response.data[0]  # user found
    return None  # invalid credentials

def log_action(src, dest, action):
    supabase.table("interaction_log").insert({
        "src": src,
        "dest": dest,
        "action": action,
        "timestamp": datetime.datetime.now().isoformat()
    }).execute()

def pivot_weights(df):

    if df.empty:
        return pd.DataFrame()

    df_pivot = (
        df.pivot(index="user_id", columns="question", values="weight")
        .add_prefix("weight_")
        .reset_index()
    )

    return df_pivot

def get_user_weights(weights_df, user_id):
    row = weights_df[weights_df["user_id"] == user_id]
    
    if row.empty:
        return None
    
    return row.iloc[0]

def get_match_state(me):
    logs = load_df("interaction_log")

    sent_df = logs[
        (logs.src == me) &
        (logs.action == "send_request")
    ]

    received_df = logs[
        (logs.dest == me) &
        (logs.action == "send_request")
    ]

    # Convert to sets for fast lookup
    sent = set(sent_df.dest)
    received = set(received_df.src)

    mutual = sent.intersection(received)

    hidden_df = logs[
        (logs.src == me) &
        (logs.action == "hide_user")
    ]
    hidden = set(hidden_df.dest)

    return {
        "sent": sent,
        "received": received,
        "mutual": mutual,
        "hidden": hidden
    }

def is_match(user_a, user_b):
    logs = load_df("interaction_log")

    liked_a_to_b = (
        (logs["src"] == user_a) &
        (logs["dest"] == user_b) &
        (logs["action"] == "send_request")
    )

    liked_b_to_a = (
        (logs["src"] == user_b) &
        (logs["dest"] == user_a) &
        (logs["action"] == "send_request")
    )

    return liked_a_to_b.any() and liked_b_to_a.any()

def is_requested(user_a, user_b):
    logs = load_df("interaction_log")

    requested_a_to_b = (
        (logs["src"] == user_a) &
        (logs["dest"] == user_b) &
        (logs["action"] == "send_request")
    )

    requested_b_to_a = (
        (logs["src"] == user_b) &
        (logs["dest"] == user_a) &
        (logs["action"] == "send_request")
    )

    # A requested B, but B did NOT request A
    return requested_a_to_b.any() and not requested_b_to_a.any()


def is_pending(user_a, user_b):
    logs = load_df("interaction_log")

    requested_b_to_a = (
        (logs["src"] == user_b) &
        (logs["dest"] == user_a) &
        (logs["action"] == "send_request")
    )

    requested_a_to_b = (
        (logs["src"] == user_a) &
        (logs["dest"] == user_b) &
        (logs["action"] == "send_request")
    )

    # B requested A, but A did NOT request B
    return requested_b_to_a.any() and not requested_a_to_b.any()


def check_match(user_a, user_b):
    if is_match(user_a, user_b):
        return "match"
    elif is_pending(user_a, user_b):
        return "pending"
    elif is_requested(user_a, user_b):
        return "requested"
    else:
        return None

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

    # 🚫 If weights missing, skip scoring
    if wA is None or wB is None:
        return None

    for (q, opts) in questions:
        # ✅ SAFE value access
        valA = userA.get(q)
        valB = userB.get(q)

        if valA is None or valB is None:
            continue

        # ✅ SAFE weight access (prevents KeyError)
        weightA = wA.get(f"weight_{q}", 1)
        weightB = wB.get(f"weight_{q}", 1)

        # 🚫 Non-negotiable rule
        if weightA == -1 and valA != valB:
            return None
        if weightB == -1 and valA != valB:
            return None

        # 🔢 Similarity calculation
        if q in ["age", "max_budget"]:
            sim = numeric_similarity(valA, valB)
        else:
            sim = categorical_similarity(valA, valB, opts)

        if sim is None:
            continue

        # ✅ Prevent negative weights from hurting score
        weight = (max(weightA, 0) + max(weightB, 0)) / 2

        if weight == 0:
            continue

        score_sum += sim * weight
        total_weight += weight

    # ✅ Final normalization
    if total_weight == 0:
        return None

    return score_sum / total_weight


def get_data(table_name, user_id):
    response = supabase.table(table_name).select("*").eq("user_id", user_id).execute()
    return response.data[0] if response.data else None


def send_message(src, dest, text):
    supabase.table("message_log").insert({
        "src": src,
        "dest": dest,
        "message": text,
        "timestamp": datetime.datetime.now().isoformat()
    }).execute()


def load_messages(user_a, user_b):
    df = load_df("message_log")

    if df.empty:
        return df

    return df[
        ((df["src"] == user_a) & (df["dest"] == user_b)) |
        ((df["src"] == user_b) & (df["dest"] == user_a))
    ].sort_values("timestamp")

def format_timestamp(current, previous):
    current_dt = pd.to_datetime(current)
    previous_dt = pd.to_datetime(previous) if previous else None

    if previous_dt:
        diff = (current_dt - previous_dt).total_seconds()

        # Within 30 min → no timestamp
        if diff < 1800:
            return None

        # Same day → time only
        if current_dt.date() == previous_dt.date():
            return current_dt.strftime("%I:%M %p")

    now = datetime.datetime.now()

    # Yesterday
    if current_dt.date() == (now.date() - datetime.timedelta(days=1)):
        return f"Yesterday {current_dt.strftime('%I:%M %p')}"

    # Same year
    if current_dt.year == now.year:
        return current_dt.strftime("%B %d")

    # Older
    return current_dt.strftime("%B %d, %Y")

# --------------------------
# SESSION STATE
# --------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "view_user" not in st.session_state:
    st.session_state.view_user = None

if "page" not in st.session_state:
    st.session_state.page = "login"

if "page_idx" not in st.session_state:
    st.session_state.page_idx = 0

if "active_chat" not in st.session_state:
    st.session_state.active_chat = None

PAGE_SIZE = 10


# --------------------------
# Navigation
# --------------------------

if st.session_state.user:
    # Top navigation bar using columns
    with st.container():
        buf0, nav1, buf1, nav2, buf2, nav3, buf3, nav4, buf4, nav5, buf5 = st.columns(11)

        if nav1.button("Finder", width='stretch'):
            st.session_state.page = "finder"
            st.rerun()
        if nav2.button("Matches", width='stretch'):
            st.session_state.page = "matches"
            st.rerun()
        if nav3.button("Messages", width='stretch'):
            st.session_state.page = "chat"
            st.rerun()
        if nav4.button("Profile", width='stretch'):
            st.session_state.page = "my_profile"
            st.rerun()
        if nav5.button("Logout", width='stretch'):
            st.session_state.user = None
            st.session_state.page = "login"
            st.rerun()




# --------------------------
# LOGIN
# --------------------------
if st.session_state.page == "login":
    st.title("Log-In")
    st.markdown("Please enter your user_id and password to sign in or create an account today.")
    st.markdown("---")


    with st.form("login_form", clear_on_submit=False):
        user_id = st.text_input("User_ID")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign In")

    if submit:
        user = authenticate_user(user_id, password)

        if user:
            st.session_state.user = user["user_id"]
            st.success("Login successful")
            st.session_state.page = "finder"
            st.rerun()
        else:
            st.error("Invalid credentials")


    if st.button("Create Account"):
        st.session_state.page = "signup"
        st.rerun()

# --------------------------
# SIGNUP
# --------------------------
elif st.session_state.page == "signup":
    st.title("Create Account")
    st.markdown("Please fill in all fields to create your account and start meeting your future roommates!")
    st.markdown("---")


    with st.form("signup_form"):
        responses = {}
        weights = {}
        non_negotiable = {}

        
        user_id = st.text_input("User ID")
        password = st.text_input("Password", type="password")
        first_name = st.text_input("First Name")
        last_name = st.text_input("Last Name")
        phone = st.text_input("Phone Number")
        email = st.text_input("Email")

        st.subheader("Preferences")


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

            
            if non_negotiable[q]:
                    weights[q] = -1

        colA, colB = st.columns(2)

        with colA:
            submitted = st.form_submit_button("✅ Sign Up")

        with colB:
            cancel = st.form_submit_button("⬅ Cancel")


        if submitted:
            #Check if user already exists
            existing = supabase.table("user_info") \
                .select("user_id") \
                .eq("user_id", user_id) \
                .execute()

            if existing.data:
                st.error("User ID already exists.")
            else:
                #Insert USER INFO
                supabase.table("user_info").insert({
                    "user_id": user_id,
                    "password": password,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                    "email": email,
                    "age": responses["age"],
                    "gender": responses["gender"],
                    "sleep_schedule": responses["sleep_schedule"],
                    "cleanliness_level": responses["cleanliness_level"],
                    "guests_frequency": responses["guests_frequency"],
                    "smoking": responses["smoking"],
                    "noise_tolerance": responses["noise_tolerance"],
                    "max_budget": responses["max_budget"],
                    "pets_comfort": responses["pets_comfort"],
                    "work_from_home": responses["work_from_home"],
                    "social_level": responses["social_level"],
                    "conflict_resolution": responses["conflict_resolution"]
                }).execute()

                # ✅ Insert WEIGHTS (same structure as before, but row-per-question table)
                weight_data = []

                for key, value in weights.items():
                    weight_data.append({
                        "user_id": user_id,
                        "question": key,
                        "weight": value
                    })

                supabase.table("user_weights").insert(weight_data).execute()

                st.success("Account created successfully!")
                st.session_state.page = "login"
                st.rerun()


        if cancel:
            st.session_state.page = "login"
            st.rerun()
# --------------------------
# ROOMMATE FINDER
# --------------------------
elif st.session_state.page == "finder":

    st.title("Find Roommates")
    st.markdown("Find your most compatible future roommates and start requesting to chat with them.")
    st.markdown("---")


    df_info = load_df("user_info")
    df_weights_long = load_df("user_weights")
    df_weights = pivot_weights(df_weights_long)

    me = st.session_state.user

    # ---- Safe lookups ----
    my_info_df = df_info[df_info.user_id == me]
    if my_info_df.empty:
        st.error("User info not found")
        st.stop()
    my_info = my_info_df.iloc[0]

    my_weights = get_user_weights(df_weights, me)
    if my_weights is None:
        st.error("User weights not found")
        st.stop()

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
        for key, value_list in filters.items():

            # Skip empty filters
            if not value_list:
                continue

            if key not in user or pd.isna(user[key]):
                return False

            user_val = user[key]

            # --- Budget (numeric <= any selected max) ---
            if key == "max_budget":
                try:
                    if not any(float(user_val) <= float(v) for v in value_list):
                        return False
                except:
                    return False

            # --- Age (match any selected ages) ---
            elif key == "age":
                try:
                    if str(user_val) not in [str(v) for v in value_list]:
                        return False
                except:
                    return False

            # --- Categorical ---
            else:
                if str(user_val) not in [str(v) for v in value_list]:
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
            # --- NAME (big + bold, keep this style) ---
            st.markdown(f"### 👤 {user.first_name} {user.last_name}")

            # --- COMPATIBILITY (big) ---
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.metric("Compatibility", f"{round(score * 100)}%")

            # --- VIEW PROFILE (NEW BUTTON) ---
            if col2.button("View Profile", key=f"view_{uid}", width='stretch'):
                st.session_state.view_user = uid
                st.session_state.page = "profile"

            # --- REQUEST BUTTON (GREYS OUT INSTEAD OF TEXT) ---
            already_requested = uid in sent

            if uid in received:
                if col3.button("Accept", key=f"accept_{uid}", width='stretch'):
                    log_action(me, uid, "send_request")
                    st.rerun()
            else:
                col3.button(
                    "Requested" if already_requested else "Request",
                    key=f"req_{uid}",
                    width='stretch',
                    disabled=already_requested,
                    on_click=(lambda u=uid: log_action(me, u, "send_request"))
                    if not already_requested else None
                )

            # --- HIDE BUTTON ---
            if col4.button("Hide", key=f"hide_{uid}", width='stretch'):
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
    st.markdown("")
    st.markdown("---")


    df_info = load_df("user_info")
    df_weights_long = load_df("user_weights")
    df_weights = pivot_weights(df_weights_long)
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

            col1, col2, col3, col4, col5 = st.columns([4,1,1,1,1])

            with col1:
                st.metric("Compatibility", f"{round(score*100)}%")
            

            with col2:
                if status == "match":
                    col2.success("Matched")
                if status == "incoming":
                    col2.message("Pending")
                

            with col3:
                if col3.button("View", key=f"match_view_{uid}", width="stretch"):
                    st.session_state.view_user = uid
                    st.session_state.page = "profile"
                    st.rerun()


            with col4:
                if col4.button("Hide", key=f"match_hide_{uid}", width="stretch"):
                    log_action(me, uid, "hide_user")
                    st.rerun()

            with col5:
                if status == "match":
                    if st.button("Message", key=f"msg_{uid}", width='stretch'):
                        st.session_state.active_chat = uid
                        st.session_state.page = "chat"
                elif status == "incoming":
                    if st.button("Accept", key=f"match_accept_{uid}", width='stretch'):
                        log_action(me, uid, "send_request")
                        st.rerun()
                else:
                    if st.button("Requested", key=f"match_pending_{uid}", width='stretch', disabled=True):
                        continue
            st.divider()


# --------------------------
# PROFILE
# --------------------------
elif st.session_state.page == "profile":
    

    df = load_df("user_info")
    user_data = df[df["user_id"] == st.session_state.view_user].iloc[0]
    match = is_match(st.session_state.user,st.session_state.view_user)
    
    st.title(f"{user_data["first_name"]} {user_data["last_name"]}")
    st.caption(f"User_ID: {st.session_state.view_user}")
    st.markdown("---")

    

    cola, colb, colc, cold = st.columns([1,1,1,1])

    me = st.session_state.user
    other = st.session_state.view_user
    mine = me == other

    with colb:
        if match:
            if st.button("Message", key=f"msg_{st.session_state.view_user}", width='stretch'):
                st.session_state.active_chat = st.session_state.view_user
                st.session_state.page = "chat"
    
    with colc:
        if mine:
            pass
        else: 
            if st.button("Hide User", width='stretch'):
                log_action(me, other, "hide_user")
                st.success("User Hidden!")
                st.rerun()


    with cold:

        state = check_match(me, other)

        if state == "match":
            st.button("Matched ✅", disabled=True, width="stretch")

        elif state == "pending":
            if st.button("Accept ✅", width="stretch"):
                log_action(me, other, "send_request")
                st.success("Match confirmed!")
                st.rerun()

        elif state == "requested":
            st.button("Requested ⏳", disabled=True, width="stretch")

        elif mine:
            pass
        else:  # "none"
            if st.button("Request ➕", width="stretch"):
                log_action(me, other, "send_request")
                st.success("Request sent!")
                st.rerun()


    if match:
        st.divider()

        col1, col2 = st.columns([3,1])
        
        with col1:
            st.subheader("Contact Info")
        
        st.write(f"📧 Email: {user_data['email']}")
        st.write(f"📱 Phone: {user_data['phone']}")
    

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
    st.title("Edit Your Profile")
    st.markdown("")
    st.markdown("---")


    user_id = st.session_state.user

    # Load user data
    user_info = get_data("user_info", user_id)

    # Load weights table (long format)
    weights_df = load_df("user_weights")
    user_weights = weights_df[weights_df["user_id"] == user_id]

    weight_dict = dict(zip(user_weights["question"], user_weights["weight"]))

    # --------------------------
    # ACCOUNT SETTINGS
    # --------------------------
    st.subheader("Account Settings")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input("Username", value=user_info["user_id"], disabled=True)
        new_password = st.text_input("New Password", type="password")

    with col2:
        phone = st.text_input("Phone", value=user_info.get("phone", ""))
        email = st.text_input("Email", value=user_info.get("email", ""))

    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        if st.button("Update Account", width="stretch"):
            updates = {
                "phone": phone,
                "email": email
            }

            if new_password:
                updates["password"] = new_password

            supabase.table("user_info").update(updates).eq("user_id", user_id).execute()
            st.success("✅ Account updated!")

    st.markdown("---")

    # --------------------------
    # PERSONAL INFO
    # --------------------------
    st.subheader("Basic Info")

    col1, col2 = st.columns(2)

    with col1:
        first_name = st.text_input("First Name", value=user_info.get("first_name", ""))
        age = st.selectbox("Age", age_options, index=age_options.index(user_info.get("age", 18)))

    with col2:
        last_name = st.text_input("Last Name", value=user_info.get("last_name", ""))
        gender = st.selectbox(
            "Gender",
            gender_options,
            index=gender_options.index(user_info.get("gender", gender_options[0]))
        )

    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        if st.button("Save Basic Info", width="stretch"):
            supabase.table("user_info").update({
                "first_name": first_name,
                "last_name": last_name,
                "age": age,
                "gender": gender
            }).eq("user_id", user_id).execute()

            st.success("✅ Basic info updated!")

    st.markdown("---")

    # --------------------------
    # LIFESTYLE PREFERENCES
    # --------------------------
    st.subheader("Lifestyle Preferences")

    updated_prefs = {}

    cols = st.columns(3)

    for i, (key, options) in enumerate(questions):
        with cols[i % 3]:
            updated_prefs[key] = st.selectbox(
                key.replace("_", " ").title(),
                options,
                index=options.index(user_info.get(key)) if user_info.get(key) in options else 0,
                key=f"pref_{key}"   # ✅ UNIQUE KEY
            )
    
    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        if st.button("Save Preferences", width="stretch"):
            supabase.table("user_info").update(updated_prefs).eq("user_id", user_id).execute()
            st.success("✅ Preferences updated!")

    st.markdown("---")

    # --------------------------
    # IMPORTANCE (WEIGHTS)
    # --------------------------
    st.subheader("What's Important To You")

    st.caption("Adjust how much each factor matters in matching")

    updated_weights = {}

    for key, _ in questions:
        current_weight = weight_dict.get(key, 5)

        is_dealbreaker = current_weight == -1

        col1, col2 = st.columns([3, 1])

        # Slider
        with col1:
            slider_value = st.slider(
                key.replace("_", " ").title(),
                0, 10,
                5 if is_dealbreaker else current_weight,
                key=f"weight_{key}"
            )

        # Dealbreaker checkbox
        with col2:
            dealbreaker = st.checkbox(
                "Dealbreaker",
                value=is_dealbreaker,
                key=f"deal_{key}"
            )

        # ✅ FINAL VALUE LOGIC
        if dealbreaker:
            updated_weights[key] = -1
        else:
            updated_weights[key] = slider_value


    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        if st.button("Save Importance", width="stretch"):
            # Delete old weights
            supabase.table("user_weights").delete().eq("user_id", user_id).execute()

            # Insert new weights
            rows = [
                {"user_id": user_id, "question": q, "weight": w}
                for q, w in updated_weights.items()
            ]

            supabase.table("user_weights").insert(rows).execute()

            st.success("✅ Importance settings updated!")

    st.markdown("---")

    # --------------------------
    # PROFILE SUMMARY
    # --------------------------
    col1, col2, col3 = st.columns([1,2,2])
    with col1:
        if st.button("View My Profile", type='primary', width="stretch"):
            st.session_state.view_user = user_id
            st.session_state.page = "profile"
            st.rerun()

# --------------------------
# CHAT
# --------------------------


elif st.session_state.page == "chat":
    active_chat = get_data("user_info", st.session_state.active_chat)
    partner = active_chat["user_id"]
    partner_name = f"{active_chat["first_name"]} {active_chat["last_name"]}"
    me = st.session_state.user

    if check_match(me, partner) != "match":
        st.error("You can only message matched users.")
        st.stop()

    st.title(f"Chat with {partner_name}")
    st.markdown("")
    st.markdown("---")


    col1, col2 = st.columns([3,1])

    with col2:
        if col2.button("View Profile", key=f"match_view_{partner}", width="stretch"):
            st.session_state.view_user = partner
            st.session_state.page = "profile"
            st.rerun()
    
    st.text("")

    msgs = load_messages(me, partner)

    # Display messages
    prev_time = None

    chat_container = st.container()

    with chat_container:
        for _, row in msgs.iterrows():
            is_me = row["src"] == me

            ts_label = format_timestamp(row["timestamp"], prev_time)
            prev_time = row["timestamp"]

            if ts_label:
                st.markdown(f"<div style='text-align:center;color:gray;font-size:12px'>{ts_label}</div>", unsafe_allow_html=True)

            align = "right" if is_me else "left"
            color = "#DCF8C6" if is_me else "#F1F0F0"

            st.markdown(f"""
                <div style='text-align:{align}; margin:5px'>
                    <div style='display:inline-block;
                                padding:10px;
                                border-radius:10px;
                                background:{color};
                                max-width:60%'>
                        {row["message"]}
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # Input box
    st.text("")

    with st.form("send_msg", clear_on_submit=True):
        msg = st.text_input("Message")
        submitted = st.form_submit_button("Send")

        if submitted and msg:
            send_message(me, partner, msg)
            st.rerun()