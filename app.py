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
# 0. ΑΥΤΟΜΑΤΟΣ ΕΛΕΓΧΟΣ LINK ΕΠΑΛΗΘΕΥΣΗΣ EMAIL ΑΠΟ URL
# ==============================================================================
st.set_page_config(page_title="Online Βαθμολόγιο", page_icon="📝", layout="wide")

query_params = st.query_params
if "verify_token" in query_params:
    token_to_verify = query_params["verify_token"]
    st.query_params.clear()
    
    # Σύνδεση για την επαλήθευση
    try:
        server = st.secrets["DB_SERVER"]
        port = int(st.secrets.get("DB_PORT", 1433))
        database = st.secrets["DB_NAME"]
        username = st.secrets["DB_USER"]
        password = st.secrets["DB_PASSWORD"]
        
        conn = pymssql.connect(server=server, port=port, user=username, password=password, database=database, charset="UTF-8")
        cursor = conn.cursor()
        cursor.execute("SELECT UserID, IsVerified FROM dbo.Users WHERE VerificationToken = %s", (token_to_verify,))
        user_to_verify = cursor.fetchone()
        
        if user_to_verify:
            if user_to_verify[1] == 1:
                st.success("ℹ️ Ο λογαριασμός σας είναι ήδη επαληθευμένος! Μπορείτε να συνδεθείτε.")
            else:
                cursor.execute("UPDATE dbo.Users SET IsVerified = 1, VerificationToken = NULL WHERE UserID = %s", (user_to_verify[0],))
                conn.commit()
                st.success("🎉 Ο λογαριασμός σας επαληθεύτηκε και ενεργοποιήθηκε επιτυχώς! Μπορείτε πλέον να συνδεθείτε.")
        else:
            st.error("❌ Μη έγκυρος ή ληγμένος σύνδεσμος επαλήθευσης.")
        cursor.close()
        conn.close()
    except Exception as e:
        st.error(f"Σφάλμα κατά την επαλήθευση: {e}")

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
            return None, "⚠️ Το email σας δεν έχει επαληθευτεί. Ελέγξτε τα εισερχόμενά σας και κάντε κλικ στον σύνδεσμο ενεργοποίησης."
        if check_password(password, user[2]):
            return {"id": user[0], "name": user[1], "email": email}, "Καλώς ήρθατε!"
        return None, "Λανθασμένος κωδικός πρόσβασης."
    return None, "Δεν βρέθηκε λογαριασμός με αυτό το email."

def register_user(fullname, email, password):
    existing = run_query("SELECT UserID, IsVerified FROM dbo.Users WHERE Email = %s", (email,), fetchone=True)
    if existing:
        if existing[1] == 1:
            return False, "Το email χρησιμοποιείται ήδη και είναι ενεργό."
        else:
            return False, "Ο λογαριασμός υπάρχει αλλά δεν έχει επαληθευτεί. Ελέγξτε το email σας."
    
    pwd_hash = hash_password(password)
    v_token = secrets.token_urlsafe(32)
    
    run_query(
        """INSERT INTO dbo.Users (FullName, Email, PasswordHash, IsVerified, VerificationToken) 
           VALUES (%s, %s, %s, 0, %s)""",
        (fullname, email, pwd_hash, v_token), commit=True
    )
    
    # Δημιουργία ενεργού link με βάση το deployment URL σου
    verify_url = f"https://gradesbook.streamlit.app/?verify_token={v_token}"
    
    email_body = f"""Γεια σας {fullname},

Σας ευχαριστούμε για την εγγραφή σας στο Online Βαθμολόγιο.
Παρακαλώ κάντε κλικ στον παρακάτω σύνδεσμο για να ενεργοποιήσετε άμεσα τον λογαριασμό σας:

{verify_url}

Αν δεν ζητήσατε εσείς αυτή την εγγραφή, αγνοήστε αυτό το μήνυμα.
"""
    
    if send_email(email, "Επαλήθευση Email - Online Βαθμολόγιο", email_body):
        return True, "🎉 Η εγγραφή σας ολοκληρώθηκε! Σας στάλθηκε email με σύνδεσμο ενεργοποίησης."
    else:
        return True, f"⚠️ Η εγγραφή έγινε, αλλά η αποστολή email απέτυχε. Link ενεργοποίησης: {verify_url}"

# ==============================================================================
# 4. INTERFACE / UI APP
# ==============================================================================
if "user" not in st.session_state:
    st.session_state.user = None

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"

if "flash_msg" in st.session_state:
    st.success(st.session_state.flash_msg)
    del st.session_state["flash_msg"]

# ------------------------------------------------------------------------------
# ΣΕΛΙΔΕΣ ΣΥΝΔΕΣΗΣ / ΕΓΓΡΑΦΗΣ / ΕΠΑΝΑΦΟΡΑΣ ΚΩΔΙΚΟΥ
# ------------------------------------------------------------------------------
if st.session_state.user is None:
    st.title("📝 Δυναμικό Online Βαθμολόγιο")
    
    # Οριζόντια επιλογή λειτουργίας (tabs style)
    auth_choice = st.radio(
        "Επιλογή:",
        ["🔑 Σύνδεση", "👤 Εγγραφή", "🔄 Ξεχάσατε τον κωδικό;"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    if "Σύνδεση" in auth_choice:
        st.session_state.auth_mode = "login"
    elif "Εγγραφή" in auth_choice:
        st.session_state.auth_mode = "register"
    else:
        st.session_state.auth_mode = "forgot"
        
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
                    
                    email_body = f"Γεια σας {user[1]},\n\nΖητήσατε επαναφορά κωδικού.\nΟ κωδικός επαναφοράς σας είναι: {token}\n\nΑν δεν το ζητήσατε εσείς, αγνοήστε αυτό το μήνυμα."
                    
                    if send_email(reset_email, "Επαναφορά Κωδικού - Online Βαθμολόγιο", email_body):
                        st.success("✉️ Σας στάλθηκε email με τις οδηγίες επαναφοράς!")
                        st.session_state.pending_reset_email = reset_email
                    else:
                        st.warning("⚠️ Δεν ήταν δυνατή η αποστολή email. Ο κωδικός επαναφοράς σας είναι:")
                        st.code(token)
                        st.session_state.pending_reset_email = reset_email
                else:
                    st.error("Δεν βρέθηκε χρήστης με αυτό το email.")

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
# ΚΥΡΙΩΣ ΕΦΑΡΜΟΓΗ (ΜΕΤΑ ΤΗ ΣΥΝΔΕΣΗ)
# ------------------------------------------------------------------------------
else:
    user_id = st.session_state.user["id"]
    
    # Sidebar
    st.sidebar.title(f"👨‍🏫 {st.session_state.user['name']}")
    
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

    # --------------------------------------------------------------------------
    # MENU 1: ΔΙΑΧΕΙΡΙΣΗ ΣΧΟΛΕΙΩΝ & ΜΑΘΗΜΑΤΩΝ (ΧΩΡΙΣ ID)
    # --------------------------------------------------------------------------
    if menu == "Διαχείριση Σχολείων & Μαθημάτων":
        st.title("🏛️ Ρυθμίσεις Σχολείων & Μαθημάτων")
        
        col1, col2 = st.columns(2)
        
        # 1. Σχολεία
        with col1:
            st.subheader("Τα Σχολεία μου")
            new_school = st.text_input("Προσθήκη Νέου Σχολείου", placeholder="π.χ. Γυμνάσιο Ακρόπολης")
            if st.button("Προσθήκη Σχολείου"):
                if new_school.strip():
                    run_query("INSERT INTO dbo.Schools (UserID, SchoolName) VALUES (%s, %s)", (user_id, new_school.strip()), commit=True)
                    st.session_state.flash_msg = "Το σχολείο προστέθηκε επιτυχώς!"
                    st.rerun()
            
            schools = run_query("SELECT SchoolID, SchoolName FROM dbo.Schools WHERE UserID = %s", (user_id,), fetchall=True)
            if schools:
                df_schools = pd.DataFrame(schools, columns=["ID", "Όνομα Σχολείου"])[["Όνομα Σχολείου"]]
                st.dataframe(df_schools, use_container_width=True, hide_index=True)

        # 2. Μαθήματα
        with col2:
            st.subheader("Τα Μαθήματά μου")
            new_subject = st.text_input("Προσθήκη Νέου Μαθήματος", placeholder="π.χ. Ιστορία")
            if st.button("Προσθήκη Μαθήματος"):
                if new_subject.strip():
                    run_query("INSERT INTO dbo.Subjects (UserID, SubjectName) VALUES (%s, %s)", (user_id, new_subject.strip()), commit=True)
                    st.session_state.flash_msg = "Το μάθημα προστέθηκε επιτυχώς!"
                    st.rerun()
            
            subjects = run_query("SELECT SubjectID, SubjectName FROM dbo.Subjects WHERE UserID = %s", (user_id,), fetchall=True)
            if subjects:
                df_subjects = pd.DataFrame(subjects, columns=["ID", "Όνομα Μαθήματος"])[["Όνομα Μαθήματος"]]
                st.dataframe(df_subjects, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("➕ Δημιουργία Νέου Βαθμολογίου / Τμήματος")
        
        if schools and subjects:
            school_dict = {str(s[1]): int(s[0]) for s in schools}
            subject_dict = {str(sub[1]): int(sub[0]) for sub in subjects}
            
            with st.form("create_class_form"):
                col_a, col_b, col_c = st.columns(3)
                sel_school = col_a.selectbox("Σχολείο", list(school_dict.keys()))
                sel_subject = col_b.selectbox("Μάθημα", list(subject_dict.keys()))
                class_name = col_c.text_input("Τμήμα", placeholder="π.χ. Γ1")
                
                col_d, col_e = st.columns(2)
                academic_year = col_d.text_input("Σχολικό Έτος", value="2026-2027")
                term = col_e.selectbox("Περίοδος / Τετράμηνο", ["Α' Τετράμηνο", "Β' Τετράμηνο", "Ετήσιο"])
                
                if st.form_submit_button("Δημιουργία Βαθμολογίου"):
                    if class_name.strip():
                        run_query(
                            """INSERT INTO dbo.ClassSubjects (UserID, SchoolID, SubjectID, ClassName, AcademicYear, Term)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (user_id, school_dict[sel_school], subject_dict[sel_subject], class_name.strip(), academic_year, term),
                            commit=True
                        )
                        st.session_state.flash_msg = f"✅ Δημιουργήθηκε επιτυχώς το βαθμολόγιο για το τμήμα {class_name} ({sel_subject})!"
                        st.rerun()
                    else:
                        st.error("Παρακαλώ συμπληρώστε το όνομα του τμήματος.")
        else:
            st.info("Προσθέστε τουλάχιστον ένα Σχολείο και ένα Μάθημα παραπάνω για να δημιουργήσετε βαθμολόγιο.")

    # --------------------------------------------------------------------------
    # MENU 2: ΔΙΑΧΕΙΡΙΣΗ ΒΑΘΜΟΛΟΓΙΩΝ, ΚΑΤΗΓΟΡΙΩΝ & ΜΑΘΗΤΩΝ
    # --------------------------------------------------------------------------
    elif menu == "Τα Βαθμολόγιά μου":
        st.title("📊 Διαχείριση Βαθμολογίου & Μαθητών")
        
        classes_data = run_query(
            """SELECT cs.ClassSubjectID, sch.SchoolName, sub.SubjectName, cs.ClassName, cs.AcademicYear, cs.Term
               FROM dbo.ClassSubjects cs
               JOIN dbo.Schools sch ON cs.SchoolID = sch.SchoolID
               JOIN dbo.Subjects sub ON cs.SubjectID = sub.SubjectID
               WHERE cs.UserID = %s""",
            (user_id,), fetchall=True
        )
        
        if not classes_data:
            st.warning("Δεν έχετε δημιουργήσει ακόμα κάποιο βαθμολόγιο. Μεταβείτε στην καρτέλα 'Διαχείριση Σχολείων & Μαθημάτων'.")
        else:
            class_options = {
                f"{c[1]} | {c[3]} | {c[2]} ({c[5]} - {c[4]})": c[0]
                for c in classes_data
            }
            
            selected_label = st.selectbox("Επιλέξτε Βαθμολόγιο:", list(class_options.keys()))
            class_subject_id = class_options[selected_label]
            
            if "active_tab" not in st.session_state:
                st.session_state.active_tab = "⚙️ 1. Κατηγορίες & Βαρύτητες (%)"
                
            tab_list = ["⚙️ 1. Κατηγορίες & Βαρύτητες (%)", "👥 2. Εισαγωγή Μαθητών (Excel)", "📝 3. Καταχώρηση & Υπολογισμός Βαθμών"]
            
            selected_tab = st.radio(
                "Επιλέξτε Ενότητα:",
                tab_list,
                index=tab_list.index(st.session_state.active_tab) if st.session_state.active_tab in tab_list else 0,
                horizontal=True,
                key="tab_selector"
            )
            st.session_state.active_tab = selected_tab
            st.divider()

            # TAB 1: ΚΑΤΗΓΟΡΙΕΣ & ΒΑΡΥΤΗΤΕΣ
            if selected_tab == "⚙️ 1. Κατηγορίες & Βαρύτητες (%)":
                st.subheader("Ορισμός Κατηγοριών Βαθμολόγησης")
                st.caption("Ορίστε τις κατηγορίες (π.χ. Διαγώνισμα, Συμμετοχή) και τα ποσοστά βαρύτητας. Το άθροισμα πρέπει να είναι 100%.")
                
                with st.form(key="add_category_form"):
                    col_cat1, col_cat2 = st.columns([2, 1])
                    cat_name = col_cat1.text_input("Όνομα Νέας Κατηγορίας", placeholder="π.χ. Διαγώνισμα A' Τετραμήνου")
                    weight = col_cat2.number_input("Βαρύτητα (%)", min_value=1.0, max_value=100.0, value=20.0, step=1.0)
                    
                    submit_add = st.form_submit_button("➕ Προσθήκη Κατηγορίας", type="primary")
                    
                    if submit_add:
                        if cat_name.strip():
                            run_query(
                                "INSERT INTO dbo.GradingCategories (ClassSubjectID, CategoryName, WeightPercentage) VALUES (%s, %s, %s)",
                                (class_subject_id, cat_name.strip(), weight), commit=True
                            )
                            st.session_state.flash_msg = "Η κατηγορία προστέθηκε επιτυχώς!"
                            st.rerun()
                        else:
                            st.error("Παρακαλώ συμπληρώστε όνομα κατηγορίας.")

                st.divider()
                st.subheader("📋 Διαχείριση Υπαρχουσών Κατηγοριών")
                
                categories = run_query(
                    "SELECT CategoryID, CategoryName, WeightPercentage FROM dbo.GradingCategories WHERE ClassSubjectID = %s",
                    (class_subject_id,), fetchall=True
                )
                
                if categories:
                    with st.form(key="edit_categories_form"):
                        updated_categories = []
                        deleted_category_ids = []
                        
                        for cat in categories:
                            cat_id, name_val, weight_val = cat[0], cat[1], float(cat[2])
                            
                            col_name, col_w, col_del = st.columns([3, 2, 1])
                            
                            new_name = col_name.text_input("Όνομα", value=name_val, key=f"cat_name_{cat_id}")
                            new_weight = col_w.number_input("Βαρύτητα (%)", min_value=1.0, max_value=100.0, value=weight_val, step=1.0, key=f"cat_w_{cat_id}")
                            is_deleted = col_del.checkbox("Διαγραφή", key=f"del_chk_{cat_id}")
                            
                            updated_categories.append((cat_id, new_name, new_weight))
                            if is_deleted:
                                deleted_category_ids.append(cat_id)
                        
                        st.markdown("")
                        submit_bulk_save = st.form_submit_button("💾 Αποθήκευση Όλων των Αλλαγών", type="primary")
                    
                    if submit_bulk_save:
                        conn = get_connection()
                        cursor = conn.cursor()
                        try:
                            for cat_id in deleted_category_ids:
                                cursor.execute("DELETE FROM dbo.Grades WHERE CategoryID = %s", (cat_id,))
                                cursor.execute("DELETE FROM dbo.GradingCategories WHERE CategoryID = %s", (cat_id,))
                            
                            for cat_id, new_name, new_weight in updated_categories:
                                if cat_id not in deleted_category_ids:
                                    cursor.execute(
                                        "UPDATE dbo.GradingCategories SET CategoryName = %s, WeightPercentage = %s WHERE CategoryID = %s",
                                        (new_name.strip(), new_weight, cat_id)
                                    )
                                    
                            conn.commit()
                            st.session_state.flash_msg = "💾 Οι αλλαγές στις κατηγορίες αποθηκεύτηκαν επιτυχώς!"
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Σφάλμα κατά την αποθήκευση: {e}")
                        finally:
                            cursor.close()
                            conn.close()
                        st.rerun()

                    current_categories = run_query(
                        "SELECT WeightPercentage FROM dbo.GradingCategories WHERE ClassSubjectID = %s",
                        (class_subject_id,), fetchall=True
                    )
                    total_weight = sum([float(c[0]) for c in current_categories]) if current_categories else 0.0
                    
                    st.markdown("---")
                    if total_weight == 100.0:
                        st.success(f"✅ Συνολική Βαρύτητα: **{total_weight:.1f}%** (Έτοιμο για υπολογισμούς)")
                    else:
                        st.error(f"⚠️ Συνολική Βαρύτητα: **{total_weight:.1f}%**. Πρέπει το άθροισμα να ισούται ακριβώς με **100%**!")
                else:
                    st.info("Δεν έχουν οριστεί κατηγορίες βαθμολόγησης ακόμα.")

            # TAB 2: ΕΙΣΑΓΩΓΗ ΜΑΘΗΤΩΝ (ΧΩΡΙΣ ID)
            elif selected_tab == "👥 2. Εισαγωγή Μαθητών (Excel)":
                st.subheader("Φόρτωση Μαθητών από Αρχείο Excel / CSV")
                st.caption("Το αρχείο Excel πρέπει να περιέχει στήλη με όνομα **'Ονοματεπώνυμο'** (και προαιρετικά **'AM'**).")
                
                uploaded_file = st.file_uploader("Επιλέξτε αρχείο Excel/CSV", type=["xlsx", "xls", "csv"])
                
                if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith('.csv'):
                            df_excel = pd.read_csv(uploaded_file)
                        else:
                            df_excel = pd.read_excel(uploaded_file)
                            
                        st.write("Προεπισκόπηση Αρχείου:", df_excel.head())
                        
                        if "Ονοματεπώνυμο" in df_excel.columns:
                            if st.button("Εισαγωγή Μαθητών στη Βάση", type="primary"):
                                count = 0
                                for _, row in df_excel.iterrows():
                                    full_name = str(row["Ονοματεπώνυμο"]).strip()
                                    am = str(row.get("AM", "")).strip() if "AM" in df_excel.columns and pd.notna(row.get("AM")) else None
                                    
                                    if full_name and full_name != "nan":
                                        run_query(
                                            "INSERT INTO dbo.Students (ClassSubjectID, AM, FullName) VALUES (%s, %s, %s)",
                                            (class_subject_id, am, full_name), commit=True
                                        )
                                        count += 1
                                st.session_state.flash_msg = f"🎉 Εισήχθησαν επιτυχώς {count} μαθητές στη βάση δεδομένων!"
                                st.rerun()
                        else:
                            st.error("Δεν βρέθηκε η στήλη 'Ονοματεπώνυμο' στο αρχείο.")
                    except Exception as e:
                        st.error(f"Σφάλμα κατά την ανάγνωση του αρχείου: {e}")

                students = run_query(
                    "SELECT StudentID, AM, FullName FROM dbo.Students WHERE ClassSubjectID = %s ORDER BY FullName",
                    (class_subject_id,), fetchall=True
                )
                if students:
                    st.write("### Υπάρχοντες Μαθητές")
                    df_std = pd.DataFrame(students, columns=["ID", "A.M.", "Ονοματεπώνυμο"])[["A.M.", "Ονοματεπώνυμο"]]
                    st.dataframe(df_std, use_container_width=True, hide_index=True)

            # TAB 3: ΚΑΤΑΧΩΡΗΣΗ ΒΑΘΜΩΝ (ΧΩΡΙΣ ID, ΜΕ ΔΥΝΑΜΙΚΟ ΥΨΟΣ & MODAL)
            elif selected_tab == "📝 3. Καταχώρηση & Υπολογισμός Βαθμών":
                st.subheader("Πίνακας Βαθμολογίας")
                
                st.markdown(
                    "<h4 style='color: #d9534f; background-color: #fdf7f7; padding: 10px; border-radius: 5px; border-left: 5px solid #d9534f;'>"
                    "⚠️ ΠΡΟΣΟΧΗ: Οι βαθμοί πρέπει να καταχωρούνται στην κλίμακα 0 έως 20 (ΌΧΙ 0 - 10)!"
                    "</h4>",
                    unsafe_allow_html=True
                )
                
                categories = run_query(
                    "SELECT CategoryID, CategoryName, WeightPercentage FROM dbo.GradingCategories WHERE ClassSubjectID = %s",
                    (class_subject_id,), fetchall=True
                )
                students = run_query(
                    "SELECT StudentID, AM, FullName FROM dbo.Students WHERE ClassSubjectID = %s ORDER BY FullName",
                    (class_subject_id,), fetchall=True
                )
                
                if not categories:
                    st.warning("Παρακαλώ ορίστε πρώτα τις Κατηγορίες Βαθμολόγησης στην καρτέλα 1.")
                elif not students:
                    st.warning("Παρακαλώ εισάγετε μαθητές στην καρτέλα 2.")
                else:
                    existing_grades = run_query(
                        """SELECT g.StudentID, g.CategoryID, g.Score 
                           FROM dbo.Grades g
                           JOIN dbo.Students s ON g.StudentID = s.StudentID
                           WHERE s.ClassSubjectID = %s""",
                        (class_subject_id,), fetchall=True
                    )
                    grades_dict = {(g[0], g[1]): float(g[2]) if g[2] is not None else None for g in existing_grades}
                    
                    cat_map = {c[0]: f"{c[1]} ({c[2]}%)" for c in categories}
                    cat_weights = {c[0]: float(c[2]) for c in categories}
                    
                    data = []
                    for std in students:
                        std_id, am, name = std
                        row = {"_StudentID": std_id, "Α.Μ.": am or "", "Ονοματεπώνυμο": name}
                        
                        weighted_sum = 0.0
                        total_weight = 0.0
                        
                        for cat_id in cat_map.keys():
                            score = grades_dict.get((std_id, cat_id), None)
                            col_title = cat_map[cat_id]
                            row[col_title] = score
                            
                            if score is not None:
                                weighted_sum += score * (cat_weights[cat_id] / 100.0)
                                total_weight += (cat_weights[cat_id] / 100.0)
                        
                        if total_weight > 0:
                            row["Γενικός Βαθμός"] = round(weighted_sum / total_weight, 2)
                        else:
                            row["Γενικός Βαθμός"] = None
                            
                        data.append(row)
                    
                    df_editor = pd.DataFrame(data)
                    
                    st.caption("Συμπληρώστε ή τροποποιήστε τους βαθμούς στον πίνακα και πατήστε **'💾 Αποθήκευση Βαθμών'** στο τέλος.")
                    
                    num_rows = len(df_editor)
                    calc_height = (num_rows + 1) * 35 + 40
                    
                    with st.form(key=f"grades_form_{class_subject_id}"):
                        edited_df = st.data_editor(
                            df_editor,
                            column_config={"_StudentID": None},
                            disabled=["Α.Μ.", "Ονοματεπώνυμο", "Γενικός Βαθμός"],
                            hide_index=True,
                            use_container_width=True,
                            height=calc_height,
                            key=f"editor_inside_form_{class_subject_id}"
                        )
                        
                        submit_save = st.form_submit_button("💾 Αποθήκευση Βαθμών", type="primary")
                    
                    @st.dialog("💾 Αποθήκευση Βαθμών σε Εξέλιξη")
                    def process_save_modal(df_data):
                        st.info("Παρακαλώ περιμένετε... Οι βαθμοί αποθηκεύονται στη βάση δεδομένων και υπολογίζεται ο Γενικός Βαθμός.")
                        with st.spinner("Γίνεται εγγραφή στον SQL Server..."):
                            conn = get_connection()
                            cursor = conn.cursor()
                            
                            for _, row in df_data.iterrows():
                                std_id = row["_StudentID"]
                                for cat_id, col_title in cat_map.items():
                                    val = row[col_title]
                                    score_val = float(val) if pd.notna(val) and str(val).strip() != "" else None
                                    
                                    cursor.execute(
                                        """
                                        MERGE dbo.Grades AS target
                                        USING (SELECT %s AS StudentID, %s AS CategoryID) AS source
                                        ON (target.StudentID = source.StudentID AND target.CategoryID = source.CategoryID)
                                        WHEN MATCHED THEN
                                            UPDATE SET Score = %s, UpdatedAt = GETDATE()
                                        WHEN NOT MATCHED THEN
                                            INSERT (StudentID, CategoryID, Score) VALUES (source.StudentID, source.CategoryID, %s);
                                        """,
                                        (std_id, cat_id, score_val, score_val)
                                    )
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            st.session_state.flash_msg = "💾 Οι βαθμοί αποθηκεύτηκαν επιτυχώς!"
                            st.rerun()

                    if submit_save:
                        invalid_entries = []
                        
                        for _, row in edited_df.iterrows():
                            student_name = row["Ονοματεπώνυμο"]
                            for cat_id, col_title in cat_map.items():
                                val = row[col_title]
                                if pd.notna(val) and str(val).strip() != "":
                                    try:
                                        score_val = float(val)
                                        if score_val < 0 or score_val > 20:
                                            invalid_entries.append(f"• **{student_name}**: {score_val} στην κατηγορία '{col_title}'")
                                    except ValueError:
                                        invalid_entries.append(f"• **{student_name}**: Μη έγκυρη τιμή '{val}'")
                        
                        if invalid_entries:
                            st.error("❌ **Η ΑΠΟΘΗΚΕΥΣΗ ΑΚΥΡΩΘΗΚΕ!** Εντοπίστηκαν βαθμοί εκτός ορίων (0 - 20):\n\n" + "\n".join(invalid_entries))
                        else:
                            process_save_modal(edited_df)
