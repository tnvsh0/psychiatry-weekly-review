# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-08-05 – 2026-09-02), 70 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.71 / 5 |
| כיסוי | 5.06 / 5 |
| שטף | 5.00 / 5 |

סיכומים: ✅ 61 · 🟡 8 · 🔴 1

---

## דפוסים חוזרים

### 1. אי דיוקים עובדתיים והמצאות  (11 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל ממציא או מגזים בפרטים, מפרש לא נכון ממצאים, או מערבב מידע ממקורות שונים או מוסיף מידע שאינו קיים במקורות שסופקו.

*דוגמאות:*
- החוקרים במאמר של קונג השתמשו ב-EEG בצפיפות גבוהה מאוד, מה שאפשר להם להקליט פעילות חשמלית מאלפי נוירונים בודדים בו-זמנית.
- המאמר הראשון שנסקר עסק בתוכנית התערבות אוניברסלית של מיינדפולנס בבתי ספר יסודיים... המחקר מצא שמיינדפולנס לא רק שלא עזר, אלא החמיר את תסמיני הדיכאון בילדי יסודי.
- הנתונים בסקירה מראים שחלק עצום מהשונות, לפעמים מעל 80% מהנתונים שמקבלים מדגימת דם של מטופל פסיכיאטרי, זה בכלל לא קשור למחלה.

*הצעת ניסוח להוספה לפרומפט:*

```text
Strictly adhere to the provided source material for all factual claims, including specific numbers, study designs, and outcomes. Do not invent or exaggerate details, or infer information not explicitly present in the abstracts or provided text. If a detail is not in the source, do not mention it as a finding from that specific paper.
```

### 2. שמות שגויים או לא מדויקים (מחברים, כתבי עת)  (11 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתבלבל בשמות מחברים, מאיית אותם לא נכון, או משתמש בשמות לא רשמיים/מקוצרים של כתבי עת במקום השם המלא כפי שמופיע במקור.

*דוגמאות:*
- המאמר הראשון מבין השניים פורסם ב-European Journal of Psychotraumatology. זו בעצם מטא-אנליזה של קבוצת המחקר של קליין וין.
- יש לנו סקירה מעניינת של החוקר סטווארט שפורסמה בכתב העת Journal of School Health.
- המאמר הרביעי מציג משהו שהוא הכי פיזי ואגרסיבי שיש. זה התפרסם בסנטה מנטל הלת'.

*הצעת ניסוח להוספה לפרומפט:*

```text
When referring to authors, use the exact last name(s) as provided in the source. When referring to journal names, use the full, official name as provided in the source, not an abbreviated or colloquial version.
```

### 3. הכללות ופישוט יתר  (10 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה לפשט יתר על המידה את סוג המחקר, את מטרותיו או את ממצאיו, לעיתים קרובות על ידי התעלמות מניואנסים חשובים או תנאים ספציפיים המוזכרים במקור.

*דוגמאות:*
- המחקר הזה בעצם אומר שזה פחות רלוונטי [סוג ההתעללות]. המצטברות היא שהכי משנה.
- המאמר של סורמני הוא מאמר מחקרי
- המאמר עוסק במושג שנקרא אינטרון ריטנשן (Intron retention), בעברית שימור אינטרונים, גם באנשים בריאים וגם ב-ALS.

*הצעת ניסוח להוספה לפרומפט:*

```text
Ensure that the description of the study type, objectives, and findings accurately reflects the nuances and specific conditions mentioned in the source material. Avoid oversimplification or broad generalizations that omit important context.
```

### 4. חוסר דיוק בנתונים מספריים  (8 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מציג נתונים מספריים (כמו ציונים, אחוזים, מספרים מוחלטים) בצורה לא מדויקת, לעיתים קרובות על ידי עיגול, שינוי כיוון או אי התאמה למקור.

*דוגמאות:*
- הקבוצה המונחית המטפל ירדה ב-17 נקודות, וקבוצת הטיפול הרגיל ירדה רק ב-11.6 נקודות.
- החוקרים סרקו את כל הספרות ויתרו בהתחלה 66 מחקרים תצפיתיים. אבל מתוכם 24 מחקרים היתרו מבחינת הדיווח הסטטיסטי שלהם והם אלו שנכנסו למטא-אנליזה עצמה.
- 90,000 פולסים בתוך חמישה ימים, עם ניווט של fMRI.

*הצעת ניסוח להוספה לפרומפט:*

```text
When quoting or referring to numerical data (e.g., scores, percentages, counts, effect sizes, p-values), ensure absolute precision and fidelity to the numbers provided in the source material. Do not round, approximate, or alter these values.
```

### 5. התעלמות ממידע חשוב או הסתייגויות  (6 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתעלם מהסתייגויות חשובות, מגבלות מחקר, או רמות ביטחון נמוכות בממצאים, ובכך מציג את התוצאות כחד משמעיות יותר ממה שהן באמת.

*דוגמאות:*
- התוצאות של המטא-אנליזה השבוע מאשרות את הנחת היסוד הזו שחוסן מגן עלינו, אבל מנוסחות את זה בצורה מאוד זהירה.
- המחברים מודים שרמת הביטחון שלהם בנתונים על פי מדדים סטטיסטיים מחמירים היא נמוכה מאוד. הם ממש משתמשים בביטוי אנגלי critically low. ויש שם גם בעיה של ייצוג גיאוגרפי.
- המאמר של צוות המחקר של גאסטון מכתב העת Sleep Medicine Reviews... הנתונים מצביעים על קשר חזק וקבוע. חוויות ילדות שליליות מתורגמות לשינה פגועה בבגרות, החל מאינסומניה דרך יקיצות מרובות ועד ציוטים.

*הצעת ניסוח להוספה לפרומפט:*

```text
Always include any significant caveats, limitations, or statements about the certainty of findings (e.g., 'critically low confidence', 'high risk of bias') that are present in the source material, especially when discussing the strength or generalizability of results.
```

### 6. התייחסות למידע מחוץ למקורות שסופקו  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתייחס למאמרים או למידע שאינם חלק מהמקורות שסופקו, או שאינם נתמכים על ידי תקציר זמין, מבלי לסמן זאת בבירור כמידע חיצוני או כהשערה.

*דוגמאות:*
- הערה: ההתייחסות למאמרים שאינם מהסקירה השבועית (כמו מחקר המיינדפולנס) אינה מסומנת בבירור כמידע חיצוני למאמרים שסופקו, מה שעלול להטעות את המאזין לחשוב שמדובר באחד ממאמרי השבוע.
- הערה: הדיון על מאמר Sormani MP et al. (Brain) היה קצר מאוד מכיוון שהתקציר לא היה זמין, אך ההתייחסות לנושא הייתה קיימת.
- הערה: הדיון על מאמר 'Coupling neuroprosthetics with neuromodulation' התבסס על הכותרת וההיגיון הקליני, מכיוון שלא סופק תקציר למאמר זה במקור. זה תואם את הציפייה במפרט במקרה של חוסר תקציר.

*הצעת ניסוח להוספה לפרומפט:*

```text
If discussing a paper or information not explicitly provided in the current week's source material, clearly state that this information comes from an external source or general knowledge, and is not part of the reviewed papers.
```

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.