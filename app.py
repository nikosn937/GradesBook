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
            
            # ΔΙΑΤΗΡΗΣΗ ΕΝΕΡΓΟΥ TAB ΣΤΟ SESSION STATE
            if "active_tab" not in st.session_state:
                st.session_state.active_tab = "⚙️ 1. Κατηγορίες & Βαρύτητες (%)"
                
            selected_tab = st.radio(
                "Επιλέξτε Ενότητα:",
                ["⚙️ 1. Κατηγορίες & Βαρύτητες (%)", "👥 2. Εισαγωγή Μαθητών (Excel)", "📝 3. Καταχώρηση & Υπολογισμός Βαθμών"],
                index=["⚙️ 1. Κατηγορίες & Βαρύτητες (%)", "👥 2. Εισαγωγή Μαθητών (Excel)", "📝 3. Καταχώρηση & Υπολογισμός Βαθμών"].index(st.session_state.active_tab),
                horizontal=True,
                key="tab_selector"
            )
            st.session_state.active_tab = selected_tab
            st.divider()

            # ------------------------------------------------------------------
            # TAB 1: ΚΑΤΗΓΟΡΙΕΣ ΒΑΘΜΟΛΟΓΗΣΗΣ & ΒΑΡΥΤΗΤΕΣ
            # ------------------------------------------------------------------
            if selected_tab == "⚙️ 1. Κατηγορίες & Βαρύτητες (%)":
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
                        st.session_state.flash_msg = "Η κατηγορία προστέθηκε επιτυχώς!"
                        st.rerun()

                st.divider()
                st.write("### Υπάρχουσες Κατηγορίες")
                
                categories = run_query(
                    "SELECT CategoryID, CategoryName, WeightPercentage FROM dbo.GradingCategories WHERE ClassSubjectID = %s",
                    (class_subject_id,), fetchall=True
                )
                
                if categories:
                    total_weight = sum([float(c[2]) for c in categories])
                    
                    for cat in categories:
                        cat_id, name_val, weight_val = cat[0], cat[1], float(cat[2])
                        
                        col_name, col_w, col_btn_edit, col_btn_del = st.columns([3, 2, 1, 1])
                        
                        new_name = col_name.text_input("Όνομα", value=name_val, key=f"cat_name_{cat_id}")
                        new_weight = col_w.number_input("Βαρύτητα (%)", min_value=1.0, max_value=100.0, value=weight_val, step=1.0, key=f"cat_w_{cat_id}")
                        
                        if col_btn_edit.button("💾 Αποθήκευση", key=f"save_cat_{cat_id}"):
                            run_query(
                                "UPDATE dbo.GradingCategories SET CategoryName = %s, WeightPercentage = %s WHERE CategoryID = %s",
                                (new_name.strip(), new_weight, cat_id), commit=True
                            )
                            st.session_state.flash_msg = "Η κατηγορία ενημερώθηκε!"
                            st.rerun()
                            
                        if col_btn_del.button("🗑️ Διαγραφή", key=f"del_cat_{cat_id}"):
                            run_query("DELETE FROM dbo.GradingCategories WHERE CategoryID = %s", (cat_id,), commit=True)
                            st.session_state.flash_msg = "Η κατηγορία διαγράφηκε!"
                            st.rerun()

                    st.markdown("---")
                    if total_weight == 100.0:
                        st.success(f"✅ Συνολική Βαρύτητα: **{total_weight:.1f}%** (Έτοιμο για υπολογισμούς)")
                    else:
                        st.error(f"⚠️ Συνολική Βαρύτητα: **{total_weight:.1f}%**. Πρέπει το άθροισμα να ισούται ακριβώς με **100%**!")

            # ------------------------------------------------------------------
            # TAB 2: ΕΙΣΑΓΩΓΗ ΜΑΘΗΤΩΝ ΑΠΟ EXCEL
            # ------------------------------------------------------------------
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
                    df_std = pd.DataFrame(students, columns=["ID", "A.M.", "Ονοματεπώνυμο"])
                    st.dataframe(df_std, use_container_width=True)

            # ------------------------------------------------------------------
            # TAB 3: ΚΑΤΑΧΩΡΗΣΗ ΒΑΘΜΩΝ (0-20 & VALIDATION)
            # ------------------------------------------------------------------
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
                        use_container_width=True,
                        key=f"grades_editor_{class_subject_id}"  # Σταθερό key για αποφυγή flicker
                    )
                    
                    if st.button("💾 Αποθήκευση Βαθμών", type="primary"):
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
                            conn = get_connection()
                            cursor = conn.cursor()
                            
                            for _, row in edited_df.iterrows():
                                std_id = row["StudentID"]
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
                            st.session_state.flash_msg = "💾 Οι βαθμοί αποθηκεύτηκαν επιτυχώς στη βάση δεδομένων!"
                            st.rerun()
