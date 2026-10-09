import streamlit as st
import pymssql
import pandas as pd
import bcrypt

# ==============================================================================
# 1. ΣΥΝΔΕΣΗ ΜΕ SQL SERVER (ARVIXE) ΜΕΣΩ PYMSSQL
# ==============================================================================
def get_connection():
    """
    Επιστρέφει σύνδεση με τον SQL Server μέσω pymssql.
    Διαβάζει τα στοιχεία από το st.secrets (.streamlit/secrets.toml)
    """
    server = st.secrets.get("DB_SERVER", "your_server_ip_or_domain")
    database = st.secrets.get("DB_NAME", "your_db_name")
    username = st.secrets.get("DB_USER", "your_db_user")
    password = st.secrets.get("DB_PASSWORD", "your_db_password")
    
    return pymssql.connect(
        server=server,
        user=username,
        password=password,
        database=database,
        charset="UTF-8",
        as_dict=False
    )

def run_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Utility function για ασφαλή εκτέλεση SQL ερωτημάτων."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
        
    if commit:
        conn.commit()
        
    cursor.close()
    conn.close()
    return result

# ==============================================================================
# 2. ΑΥΘΕΝΤΙΚΟΠΟΙΗΣΗ (AUTH)
# ==============================================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def login_user(email, password):
    user = run_query(
        "SELECT UserID, FullName, PasswordHash FROM dbo.Users WHERE Email = %s",
        (email,), fetchone=True
    )
    if user and check_password(password, user[2]):
        return {"id": user[0], "name": user[1], "email": email}
    return None

def register_user(fullname, email, password):
    existing = run_query("SELECT UserID FROM dbo.Users WHERE Email = %s", (email,), fetchone=True)
    if existing:
        return False, "Το email χρησιμοποιείται ήδη."
    
    pwd_hash = hash_password(password)
    run_query(
        "INSERT INTO dbo.Users (FullName, Email, PasswordHash, IsVerified) VALUES (%s, %s, %s, 1)",
        (fullname, email, pwd_hash), commit=True
    )
    return True, "Η εγγραφή ολοκληρώθηκε επιτυχώς!"

# ==============================================================================
# 3. INTERFACE / UI APP
# ==============================================================================
st.set_page_config(page_title="Online Βαθμολόγιο", page_icon="📝", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

# ------------------------------------------------------------------------------
# ΣΕΛΙΔΕΣ ΣΥΝΔΕΣΗΣ / ΕΓΓΡΑΦΗΣ
# ------------------------------------------------------------------------------
if st.session_state.user is None:
    st.title("📝 Δυναμικό Online Βαθμολόγιο")
    tab_login, tab_reg = st.tabs(["Σύνδεση", "Εγγραφή Εκπαιδευτικού"])
    
    with tab_login:
        st.subheader("Σύνδεση στο λογαριασμό σας")
        email = st.text_input("Email", key="log_email")
        password = st.text_input("Κωδικός Πρόσβασης", type="password", key="log_pass")
        if st.button("Σύνδεση", type="primary"):
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                st.success(f"Καλώς ήρθατε, {user['name']}!")
                st.rerun()
            else:
                st.error("Λανθασμένο email ή κωδικός πρόσβασης.")
                
    with tab_reg:
        st.subheader("Δημιουργία Νέου Λογαριασμού")
        fullname = st.text_input("Ονοματεπώνυμο", key="reg_name")
        reg_email = st.text_input("Email", key="reg_email")
        reg_pass = st.text_input("Κωδικός Πρόσβασης", type="password", key="reg_pass")
        if st.button("Εγγραφή"):
            if fullname and reg_email and reg_pass:
                ok, msg = register_user(fullname, reg_email, reg_pass)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("Παρακαλώ συμπληρώστε όλα τα πεδία.")

# ------------------------------------------------------------------------------
# ΚΥΡΙΩΣ ΕΦΑΡΜΟΓΗ (ΜΕΤΑ ΤΗ ΣΥΝΔΕΣΗ)
# ------------------------------------------------------------------------------
else:
    user_id = st.session_state.user["id"]
    
    # Sidebar
    st.sidebar.title(f"👨‍🏫 {st.session_state.user['name']}")
    if st.sidebar.button("Αποσύνδεση"):
        st.session_state.user = None
        st.rerun()

    menu = st.sidebar.radio("Πλοήγηση", ["Διαχείριση Σχολείων & Μαθημάτων", "Τα Βαθμολόγιά μου"])

    # --------------------------------------------------------------------------
    # MENU 1: ΔΙΑΧΕΙΡΙΣΗ ΣΧΟΛΕΙΩΝ & ΜΑΘΗΜΑΤΩΝ
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
                    st.success("Το σχολείο προστέθηκε!")
                    st.rerun()
            
            schools = run_query("SELECT SchoolID, SchoolName FROM dbo.Schools WHERE UserID = %s", (user_id,), fetchall=True)
            if schools:
                df_schools = pd.DataFrame(schools, columns=["ID", "Όνομα Σχολείου"])
                st.dataframe(df_schools, use_container_width=True)

        # 2. Μαθήματα
        with col2:
            st.subheader("Τα Μαθήματά μου")
            new_subject = st.text_input("Προσθήκη Νέου Μαθήματος", placeholder="π.χ. Ιστορία")
            if st.button("Προσθήκη Μαθήματος"):
                if new_subject.strip():
                    run_query("INSERT INTO dbo.Subjects (UserID, SubjectName) VALUES (%s, %s)", (user_id, new_subject.strip()), commit=True)
                    st.success("Το μάθημα προστέθηκε!")
                    st.rerun()
            
            subjects = run_query("SELECT SubjectID, SubjectName FROM dbo.Subjects WHERE UserID = %s", (user_id,), fetchall=True)
            if subjects:
                df_subjects = pd.DataFrame(subjects, columns=["ID", "Όνομα Μαθήματος"])
                st.dataframe(df_subjects, use_container_width=True)

        st.hr()
        st.subheader("➕ Δημιουργία Νέου Βαθμολογίου / Τμήματος")
        
        if schools and subjects:
            school_dict = {s[1]: s[0] for s in schools}
            subject_dict = {sub[1]: sub[0] for sub in subjects}
            
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
                        st.success(f"Δημιουργήθηκε το βαθμολόγιο για το τμήμα {class_name} ({sel_subject})!")
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
            
            tab_cat, tab_students, tab_grades = st.tabs([
                "⚙️ 1. Κατηγορίες & Βαρύτητες (%)", 
                "👥 2. Εισαγωγή Μαθητών (Excel)", 
                "📝 3. Καταχώρηση & Υπολογισμός Βαθμών"
            ])
            
            # ------------------------------------------------------------------
            # TAB 1: ΚΑΤΗΓΟΡΙΕΣ ΒΑΘΜΟΛΟΓΗΣΗΣ & ΒΑΡΥΤΗΤΕΣ
            # ------------------------------------------------------------------
            with tab_cat:
                st.subheader("Ορισμός Κατηγοριών Βαθμολόγησης")
                st.caption("Ορίστε τις κατηγορίες (π.χ. Διαγώνισμα, Συμμετοχή) και τα ποσοστά βαρύτητας. Το άθροισμα πρέπει να είναι 100%.")
                
                col_cat1, col_cat2 = st.columns([2, 1])
                cat_name = col_cat1.text_input("Όνομα Κατηγορίας", placeholder="π.χ. Διαγώνισμα A' Τετραμήνου")
                weight = col_cat2.number_input("Βαρύτητα (%)", min_value=1.0, max_value=100.0, value=20.0, step=1.0)
                
                if st.button("Προσθήκη Κατηγορίας"):
                    if cat_name.strip():
                        run_query(
                            "INSERT INTO dbo.GradingCategories (ClassSubjectID, CategoryName, WeightPercentage) VALUES (%s, %s, %s)",
                            (class_subject_id, cat_name.strip(), weight), commit=True
                        )
                        st.success("Η κατηγορία προστέθηκε!")
                        st.rerun()
                
                categories = run_query(
                    "SELECT CategoryID, CategoryName, WeightPercentage FROM dbo.GradingCategories WHERE ClassSubjectID = %s",
                    (class_subject_id,), fetchall=True
                )
                
                if categories:
                    df_cat = pd.DataFrame(categories, columns=["ID", "Κατηγορία", "Βαρύτητα (%)"])
                    st.dataframe(df_cat, use_container_width=True)
                    
                    total_weight = df_cat["Βαρύτητα (%)"].sum()
                    if total_weight == 100.0:
                        st.success(f"✅ Συνολική Βαρύτητα: {total_weight:.1f}% (Έτοιμο για υπολογισμούς)")
                    else:
                        st.error(f"⚠️ Συνολική Βαρύτητα: {total_weight:.1f}%. Πρέπει το άθροισμα να ισούται ακριβώς με 100%!")

            # ------------------------------------------------------------------
            # TAB 2: ΕΙΣΑΓΩΓΗ ΜΑΘΗΤΩΝ ΑΠΟ EXCEL
            # ------------------------------------------------------------------
            with tab_students:
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
                            if st.button("Εισαγωγή Μαθητών στη Βάση"):
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
                                st.success(f"Εισήχθησαν επιτυχώς {count} μαθητές!")
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
                    df_std = pd.DataFrame(students, columns=["ID", "A.M.", "Ονοματεπώνυμο"])
                    st.dataframe(df_std, use_container_width=True)

            # ------------------------------------------------------------------
            # TAB 3: ΚΑΤΑΧΩΡΗΣΗ ΒΑΘΜΩΝ & ΑΥΤΟΜΑΤΟΣ ΥΠΟΛΟΓΙΣΜΟΣ
            # ------------------------------------------------------------------
            with tab_grades:
                st.subheader("Πίνακας Βαθμολογίας")
                
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
                        row = {"StudentID": std_id, "Α.Μ.": am or "", "Ονοματεπώνυμο": name}
                        
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
                    
                    st.caption("Επεξεργαστείτε τους βαθμούς απευθείας στον πίνακα και πατήστε **'Αποθήκευση Βαθμών'**.")
                    
                    edited_df = st.data_editor(
                        df_editor,
                        disabled=["StudentID", "Α.Μ.", "Ονοματεπώνυμο", "Γενικός Βαθμός"],
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    if st.button("💾 Αποθήκευση Βαθμών", type="primary"):
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        for _, row in edited_df.iterrows():
                            std_id = row["StudentID"]
                            for cat_id, col_title in cat_map.items():
                                val = row[col_title]
                                score_val = float(val) if pd.notna(val) and str(val).strip() != "" else None
                                
                                # UPSERT με MERGE στον SQL Server (%s placeholders για pymssql)
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
                        st.success("Οι βαθμοί αποθηκεύτηκαν επιτυχώς!")
                        st.rerun()
