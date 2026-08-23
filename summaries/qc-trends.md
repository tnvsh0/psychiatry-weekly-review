# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-07-22 – 2026-08-16), 72 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.51 / 5 |
| כיסוי | 4.99 / 5 |
| שטף | 5.00 / 5 |

סיכומים: ✅ 59 · 🟡 11 · 🔴 2

---

## דפוסים חוזרים

### 1. המצאת מידע ואי-דיוקים עובדתיים  (19 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה לייצר מידע שאינו נתמך במקורות שסופקו, בין אם על ידי המצאת מאמרים שלמים, פרטים ספציפיים, או סילוף ממצאים קיימים, ככל הנראה בניסיון למלא פערים או להרחיב את הדיון.

*דוגמאות:*
- נאמר: המאמר הראשון שנסקר עסק בתוכנית התערבות אוניברסלית של מיינדפולנס בבתי ספר יסודיים... המחקר מצא שמיינדפולנס לא רק שלא עזר, אלא החמיר את תסמיני הדיכאון בילדי יסודי. | מקור: לא מופיע במקור.
- נאמר: במדד של דיווחי הילדים עצמם לחרדה, הם הראו הפחתה משמעותית יותר של 4.5 נקודות... | מקור: SCARED-C mean score in the intervention group was 4.5... points higher
- נאמר: אני מסתכלת על מאמר מחקרי... שפורסם בכתב העת Archives of Clinical Neuropsychology. | מקור: לא מופיע במקור. כתב העת Archives of Clinical Neuropsychology אינו כלול ברשימת המאמרים שסופקה.

*הצעת ניסוח להוספה לפרומפט:*

```text
Strictly adhere to the provided source material. Do not invent information, studies, or findings. If a detail is not explicitly present in the source, do not include it. Do not misrepresent the direction or significance of findings. If a statistical measure is mentioned, explain it accurately based on its definition, not as a simplified percentage of correctness unless explicitly stated as such in the source.
```

### 2. הצגת מידע חלקי או חוסר הדגשת ניואנסים  (12 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה להשמיט פרטים חשובים, להציג ממצאים באופן פשטני מדי, או לא להדגיש מגבלות וניואנסים קריטיים של המחקרים, מה שעלול להוביל להבנה שגויה או לא מלאה של המידע המדעי.

*דוגמאות:*
- נאמר: המאמר של צוות המחקר של גאסטון... מדובר פה על מטה-אנליזה ענקית שהיגדה 12 סקירות שיטתיות... | מקור: המאמר הוא 'An overview of systematic reviews and a global evidence map' ולא מטה-אנליזה ענקית. הוא אכן אגד 12 סקירות שיטתיות, אך רק אחת מהן הייתה מטה-אנליזה.
- נאמר: המאמר של צוות המחקר של גאסטון... הנתונים מצביעים על קשר חזק וקבוע. | מקור: המאמר מציין כי 'Confidence in findings was generally critically low, and risk of bias was high, resulting in low certainty, overall', מה שלא מודגש באודיו.
- נאמר: המאמר הרביעי הוא פיילוט לטיפול מואץ בגריה מגנטית מוחית מול פלצבו. וזה מיועד לסימפטומים השליליים של סכיזופרניה, אלו שלא מגיבים לתרופות. | מקור: המאמר אינו מציין שהטיפול מיועד ספציפית לאלו 'שלא מגיבים לתרופות', אלא ל'מבוגרים עם סימפטומים שליליים משמעותיים קלינית'.

*הצעת ניסוח להוספה לפרומפט:*

```text
When discussing study findings, ensure to include relevant caveats, limitations, and nuances as presented in the source material. Clearly state the type of study (e.g., systematic review, meta-analysis, pilot, RCT) and its implications for the strength of the evidence. Avoid overstating the certainty or generalizability of findings if the source indicates otherwise.
```

### 3. שיבוש שמות חוקרים וכתבי עת  (7 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל משבש באופן עקבי שמות של חוקרים וכתבי עת, ככל הנראה עקב קשיי תעתיק או זיהוי מדויק של ישויות אלו מהטקסט המקורי.

*דוגמאות:*
- נאמר: יש לנו סקירה מעניינת של החוקר סטווארט שפורסמה בכתב העת Journal of School Health. | מקור: המאמר הוא של Stoddard SA et al., לא Stuart. כתב העת הוא The Journal of School Health, לא Journal of School Health.
- נאמר: המאמר שפורסם על ידי קבוצת מחקר ברשות יאפ (YAPP) | מקור: מחברים: Yap CX et al.
- נאמר: המאמר הרביעי מציג משהו שהוא הכי פיזי ואגרסיבי שיש. זה התפרסם בסנטה מנטל הלת'. | מקור: כתב העת הוא 'Sante Ment Que', לא 'סנטה מנטל הלת''.

*הצעת ניסוח להוספה לפרומפט:*

```text
Ensure accurate pronunciation and spelling of researchers' names and journal titles. Double-check against the provided source text for exact wording. If a journal title is abbreviated in the source, use the full name if available or clearly state it as an abbreviation.
```

### 4. הגיית שמות כתבי עת לא מדויקת  (4 מופעים)

**⛔ מגבלה — לא ניתן לתקן בפרומפט**

*אבחנה:* המודל מתקשה להגות שמות כתבי עת באופן מדויק, ככל הנראה בשל מגבלות מובנות של מנוע ה-TTS או חוסר ידע פונטי ספציפי לשמות אלו.

*דוגמאות:*
- הערה: הגיית שמות כתבי העת BMJ Paediatr Open, Med Sci (Basel), Int J Lang Commun Disord, Rev Lat Am Enfermagem, Ann Fam Med אינה מדויקת, אך הוכרה כחלק מהמפרט המותר.
- נאמר: המאמר הזה מתמקד בהתערבויות לקידום תקשורת בילדים אוטיסטים עם יכולת ורבלית מינימלית. זה נושא חשוב מאוד. | מקור: כתב העת הוא Med Sci (Basel), לא Medical Sciences.
- נאמר: המאמר הזה בוחן כיצד מידע על הילד והמשפחה נלקח בחשבון בתהליכי קבלת החלטות קליניות. | מקור: כתב העת הוא International Journal of Language and Communication Disorders, לא International Journal of Language and Communication Disorders.

*מה כן יעזור:* זוהי מגבלה של מנוע ה-Text-to-Speech ואינה ניתנת לתיקון באמצעות שינוי הפרומפט. יש לשקול שיפור במנוע ה-TTS או מתן רשימת הגייה מפורשת לשמות אלו.

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.