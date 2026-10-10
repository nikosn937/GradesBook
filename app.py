import streamlit as st
import pymssql
import pandas as pd
import bcrypt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import datetime

# ==============================================================================
# 1. ΣΥΝΔΕΣΗ ΜΕ SQL SERVER (ARVIXE) ΜΕΣΩ PYMSSQL
# ==============================================================================
def get_connection():
    server = st.secrets["DB_SERVER"]
    port = int(st.secrets.get("DB_PORT", 1433))
    database = st.secrets["DB_NAME"]
    username = st.secrets["DB_USER"]
    password = st.secrets["DB_PASSWORD"]
    
    return pymssql.connect(
        server=server,
        port=port,
        user=username,
        password=password,
        database=database,
        charset="UTF-8",
        as_dict=False
    )

def run_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
        if result is None:
            result = []
        
    if commit:
        conn.commit()
        
    cursor.close()
    conn.close()
    return result

# ==============================================================================
# 2. ΥΠΗΡΕΣΙΑ ΑΠΟΣΤΟΛΗΣ EMAIL (SMTP)
# ==============================================================================
def send_email(to_email, subject, body):
    try:
        smtp_server = st.secrets["email"]["SMTP_SERVER"]
        smtp_port = int(st.secrets["email"]["SMTP_PORT"])
        sender_email = st.secrets["email"]["SENDER_EMAIL"]
        sender_password = st.secrets["email"]["SENDER_PASSWORD"]
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Σφάλμα αποστολής email: {e}")
        return False

# ==============================================================================
# 3. ΑΥΘΕΝΤΙΚΟΠΟΙΗΣΗ & SECURITY (AUTH, RESET, VERIFY)
# ==============================================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def login_user(email, password):
    user = run_query(
        "SELECT UserID, FullName, PasswordHash, IsVerified FROM dbo.Users WHERE Email = %s",
        (email,), fetchone=True
    )
    if user:
        if not user[3]:  # IsVerified == 0
            return None, "Το email σας δεν έχει επαληθευτεί. Παρακαλώ ελέγξτε τα εισερχόμενά σας."
        if check_password(password, user[2]):
            return {"id": user[0], "name": user[1], "email": email}, "Καλώς ήρθατε!"
        return None, "Λανθασμένος κωδικός πρόσβασης."
    return None, "Δεν βρέθηκε λογαριασμός με αυτό το email."

def register_user(fullname, email, password):
    existing = run_query("SELECT UserID FROM dbo.Users WHERE Email = %s", (email,), fetchone=True)
    if existing:
        return False, "Το email χρησιμοποιείται ήδη."
    
    pwd_hash = hash_password(password)
    # Αποθηκεύουμε τον χρήστη (εδώ τον ορίζουμε ως IsVerified = 1 για άμεση πρόσβαση, 
    # ή μπορούμε να στείλουμε token επαλήθευσης αν απαιτείται αυστηρό verification).
    run_query(
        "INSERT INTO dbo.Users (FullName, Email, PasswordHash, IsVerified) VALUES (%s, %s, %s, 1)",
        (fullname, email, pwd_hash), commit=True
    )
    return True, "Η εγγραφή ολοκληρώθηκε επιτυχώς! Μπορείτε να συνδεθείτε."

# ==============================================================================
# 4. INTERFACE / UI APP
# ==============================================================================
st.set_page_config(page_title="Online Βαθμολόγιο", page_icon="📝", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"  # 'login', 'register', 'forgot'

if "flash_msg" in st.session_state:
    st.success(st.session_state.flash_msg)
    del st.session_state["flash_msg"]

# ------------------------------------------------------------------------------
# ΣΕΛΙΔΕΣ ΣΥΝΔΕΣΗΣ / ΕΓΓΡΑΦΗΣ / ΕΠΑΝΑΦΟΡΑΣ ΚΩΔΙΚΟΥ
# ------------------------------------------------------------------------------
if st.session_state.user is None:
    st.title("📝 Δυναμικό Online Βαθμολόγιο")
    
    # Επιλογή λειτουργίας auth μέσω κουμπιών/tabs
    col_nav1, col_nav2, col_nav3 = st.columns(3)
    if col_nav1.button("🔑 Σύνδεση", use_container_width=True):
        st.session_state.auth_mode = "login"
        st.rerun()
    if col_nav2.button("👤 Εγγραφή Εκπαιδευτικού", use_container_width=True):
        st.session_state.auth_mode = "register"
        st.rerun()
    if col_nav3.button("🔄 Ξεχάσατε τον κωδικό;", use_container_width=True):
        st.session_state.auth_mode = "forgot"
        st.rerun()
        
    st.divider()

    # 1. ΣΥΝΔΕΣΗ
    if st.session_state.auth_mode == "login":
        st.subheader("Σύνδεση στο λογαριασμό σας")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Κωδικός Πρόσβασης", type="password")
            submitted = st.form_submit_button("Σύνδεση", type="primary")
            
            if submitted:
                user, msg = login_user(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.flash_msg = f"Καλώς ήρθατε, {user['name']}!"
                    st.rerun()
                else:
                    st.error(msg)

    # 2. ΕΓΓΡΑΦΗ
    elif st.session_state.auth_mode == "register":
        st.subheader("Δημιουργία Νέου Λογαριασμού")
        with st.form("register_form"):
            fullname = st.text_input("Ονοματεπώνυμο")
            reg_email = st.text_input("Email")
            reg_pass = st.text_input("Κωδικός Πρόσβασης", type="password")
            submitted = st.form_submit_button("Εγγραφή")
            
            if submitted:
                if fullname and reg_email and reg_pass:
                    ok, msg = register_user(fullname, reg_email, reg_pass)
                    if ok:
                        st.success(msg)
                        st.session_state.auth_mode = "login"
                    else:
                        st.error(msg)
                else:
                    st.warning("Παρακαλώ συμπληρώστε όλα τα πεδία.")

    # 3. ΞΕΧΑΣΑ ΤΟΝ ΚΩΔΙΚΟ (FORGOT PASSWORD)
    elif st.session_state.auth_mode == "forgot":
        st.subheader("Επαναφορά Κωδικού Πρόσβασης")
        st.caption("Εισάγετε το email σας για να σας αποστείλουμε οδηγίες επαναφοράς.")
        
        with st.form("forgot_form"):
            reset_email = st.text_input("Email Λογαριασμού")
            submitted = st.form_submit_button("Αποστολή Οδηγιών")
            
            if submitted:
                user = run_query("SELECT UserID, FullName FROM dbo.Users WHERE Email = %s", (reset_email,), fetchone=True)
                if user:
                    token = secrets.token_urlsafe(32)
                    expires = datetime.datetime.now() + datetime.timedelta(hours=1)
                    
                    run_query(
                        "UPDATE dbo.Users SET ResetToken = %s, ResetTokenExpires = %s WHERE UserID = %s",
                        (token, expires, user[0]), commit=True
                    )
                    
                    # Προσομοίωση / Αποστολή email
                    reset_link = f"Εισάγετε αυτόν τον κωδικό επαναφοράς στην εφαρμογή: **{token}**"
                    email_body = f"Γεια σας {user[1]},\n\nΖητήσατε επαναφορά κωδικού.\nΟ κωδικός επαναφοράς σας είναι: {token}\n\nΑν δεν το ζητήσατε εσείς, αγνοήστε αυτό το μήνυμα."
                    
                    if send_email(reset_email, "Επαναφορά Κωδικού - Online Βαθμολόγιο", email_body):
                        st.success("✉️ Σας στάλθηκε email με τις οδηγίες επαναφοράς!")
                        st.session_state.pending_reset_email = reset_email
                    else:
                        # Fallback αν δεν έχει ρυθμιστεί σωστά το SMTP
                        st.warning("⚠️ Δεν ήταν δυνατή η αποστολή email (ελέγξτε τα secrets). Για δοκιμή, ο κωδικός σας είναι:")
                        st.code(token)
                        st.session_state.pending_reset_email = reset_email
                else:
                    st.error("Δεν βρέθηκε χρήστης με αυτό το email.")

        # Φόρμα εισαγωγής Token και νέου κωδικού
        if "pending_reset_email" in st.session_state:
            st.divider()
            st.subheader("Ορισμός Νέου Κωδικού")
            with st.form("new_pass_form"):
                entered_token = st.text_input("Κωδικός Επαναφοράς (Token)")
                new_password = st.text_input("Νέος Κωδικός Πρόσβασης", type="password")
                confirm_password = st.text_input("Επιβεβαίωση Νέου Κωδικού", type="password")
                sub_reset = st.form_submit_button("Αλλαγή Κωδικού", type="primary")
                
                if sub_reset:
                    if new_password != confirm_password:
                        st.error("Οι κωδικοί δεν ταιριάζουν.")
                    elif len(new_password) < 6:
                        st.error("Ο κωδικός πρέπει να έχει τουλάχιστον 6 χαρακτήρες.")
                    else:
                        u_data = run_query(
                            "SELECT UserID, ResetTokenExpires FROM dbo.Users WHERE Email = %s AND ResetToken = %s",
                            (st.session_state.pending_reset_email, entered_token.strip()), fetchone=True
                        )
                        if u_data:
                            # Έλεγχος αν έληξε το token
                            if datetime.datetime.now() <= u_data[1]:
                                new_hash = hash_password(new_password)
                                run_query(
                                    "UPDATE dbo.Users SET PasswordHash = %s, ResetToken = NULL, ResetTokenExpires = NULL WHERE UserID = %s",
                                    (new_hash, u_data[0]), commit=True
                                )
                                st.success("🎉 Ο κωδικός σας άλλαξε επιτυχώς! Μπορείτε να συνδεθείτε.")
                                del st.session_state["pending_reset_email"]
                                st.session_state.auth_mode = "login"
                                st.rerun()
                            else:
                                st.error("Ο κωδικός επαναφοράς έχει λήξει. Ζητήστε νέο.")
                        else:
                            st.error("Λανθασμένος κωδικός επαναφοράς.")

# ------------------------------------------------------------------------------
# ΚΥΡΙΩΣ ΕΦΑΡΜΟΓΗ (ΜΕΤΑ ΤΗ ΣΥΝΔΕΣΗ - ΠΡΟΣΘΗΚΗ ΑΛΛΑΓΗΣ ΚΩΔΙΚΟΥ ΣΤΟ SIDEBAR)
# ------------------------------------------------------------------------------
else:
    user_id = st.session_state.user["id"]
    
    # Sidebar
    st.sidebar.title(f"👨‍🏫 {st.session_state.user['name']}")
    
    # Modal ή Expandable για Αλλαγή Κωδικού
    with st.sidebar.expander("🔒 Αλλαγή Κωδικού"):
        with st.form("change_pwd_sidebar"):
            old_pwd = st.text_input("Τρέχων Κωδικός", type="password")
            new_pwd = st.text_input("Νέος Κωδικός", type="password")
            sub_change = st.form_submit_button("Αλλαγή")
            
            if sub_change:
                db_user = run_query("SELECT PasswordHash FROM dbo.Users WHERE UserID = %s", (user_id,), fetchone=True)
                if db_user and check_password(old_pwd, db_user[0]):
                    if len(new_pwd) >= 6:
                        new_h = hash_password(new_pwd)
                        run_query("UPDATE dbo.Users SET PasswordHash = %s WHERE UserID = %s", (new_h, user_id), commit=True)
                        st.sidebar.success("Ο κωδικός άλλαξε!")
                    else:
                        st.sidebar.error("Ο κωδικός πρέπει να έχει τουλάχιστον 6 χαρακτήρες.")
                else:
                    st.sidebar.error("Λανθασμένος τρέχων κωδικός.")

    if st.sidebar.button("Αποσύνδεση"):
        st.session_state.user = None
        st.rerun()

    menu = st.sidebar.radio("Πλοήγηση", ["Διαχείριση Σχολείων & Μαθημάτων", "Τα Βαθμολόγιά μου"])

    # (Εδώ συνεχίζει κανονικά η υπόλοιπη εφαρμογή για Σχολεία, Μαθήματα, Κατηγορίες, Μαθητές, Βαθμούς όπως είχαμε συμφωνήσει)
