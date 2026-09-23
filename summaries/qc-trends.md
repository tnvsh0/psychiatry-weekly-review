# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-08-23 – 2026-09-16), 52 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.73 / 5 |
| כיסוי | 5.06 / 5 |
| שטף | 4.98 / 5 |

סיכומים: ✅ 47 · 🟡 4 · 🔴 1

---

## דפוסים חוזרים

### 1. היפוך עובדות מדעיות ושגיאות נתונים  (5 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל הוזה ומשבש פרטים מדעיים קריטיים, הופך קשרים בין משתנים, משנה מינונים מספריים, ומייחס ממצאים שגויים למאמרים אחרים.

*דוגמאות:*
- אקסון 1d זוהה בלב ובאבי העורקים אבל לא במוח
- ההשפעה נוגדת הפחד הייתה תלויה באיתות של בטא-ארסטין 2
- דקסאמפטמין במינון של 5 מ"ג לק"ג

*הצעת ניסוח להוספה לפרומפט:*

```text
CRITICAL: You must strictly adhere to the scientific facts, numbers, and directionality in the text. Do not reverse findings (e.g., dependent vs independent, included vs excluded). Accurately cite dosages without altering numbers. Ensure findings are attributed to the correct study.
```

### 2. המצאת תירוצים ושבירת הקיר הרביעי  (4 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* כאשר חסר מידע בטקסט, המודל ממציא תירוצים טכניים ('המאמר לא סופק') או בודה החלטות הפקה עתידיות כדי להסביר את החוסר, במקום לדון בטבעיות במידע הקיים.

*דוגמאות:*
- המאמר לא מפרט את השמות של התרופות ברשימה
- המאמר לא סופק במלואו ולכן נתמקד בכותרת
- החלטנו להקדיש לו פרק זרקור מלא משלו

*הצעת ניסוח להוספה לפרומפט:*

```text
Never break the fourth wall to state that the full article was not provided, that details are missing from the abstract, or that a list was omitted. Never invent excuses for missing information or fabricate future podcast episodes. Discuss only the provided text naturally.
```

### 3. המצאת שמות פרטיים לחוקרים  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מנסה לייצר שיחה אישית וטבעית יותר ולכן הוא ממציא לחוקרים שמות פרטיים כאשר המקור מספק רק שם משפחה או ראשי תיבות.

*דוגמאות:*
- קבוצת מחקר בראשות יוסי קרוז
- אריק פומפון
- אריק פומבון

*הצעת ניסוח להוספה לפרומפט:*

```text
Do not invent or guess first names for researchers. If the source only provides initials or a last name, use only the provided last name. Do not assign random first names to authors.
```

### 4. סיווג שגוי של מערך המחקר  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל טועה בסיווג סוג המאמר (למשל מזהה סקירה כמחקר מקורי) ומשבש את תיאור מבנה זרועות הניסוי וקבוצות הביקורת.

*דוגמאות:*
- הקבוצה השלישית הייתה קבוצת ביקורת של אנשים בריאים ללא שום אבחנה פסיכיאטרית
- והוא מחקר איכותני (Qualitative study)
- המאמר של סורמני הוא מאמר מחקרי

*הצעת ניסוח להוספה לפרומפט:*

```text
Accurately state the study design (e.g., Clinical Trial, Review, Original Research) exactly as provided in the metadata. Do not misrepresent the study arms or confuse healthy control groups with intervention arms.
```

### 5. שיבושי הגייה ותעתיק של שמות  (3 מופעים)

**⛔ מגבלה — לא ניתן לתקן בפרומפט**

*אבחנה:* מנוע ה-TTS בעברית יחד עם המודל מתקשים להגות ולתעתק נכון שמות משפחה לועזיים מורכבים, מה שמוביל לעיוותים פונטיים משמעותיים בהקלטה שאינם תלויים בפרומפט המרכזי.

*דוגמאות:*
- זמולביץ' (הוגה כ-Zmoolevich במקום Shmoolevich)
- קבוצת מחקר בראשות יוסי קרוז
- אריק פומפון

*מה כן יעזור:* זוהי מגבלה טכנית של המודל ושל מנוע ההקראה; כדי לפתור זאת יש לנקד את השמות במפורש בשלב עיבוד מקדים או להשתמש בכתיב פונטי מדויק.

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.