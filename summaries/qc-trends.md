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

### 1. סילוף עובדות, שיבוש מספרי והיפוך משמעויות  (6 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה להזות ולעוות נתונים קריטיים, לרבות התעלמות מנקודות עשרוניות, היפוך קשרים לוגיים (כגון 'תלוי' במקום 'בלתי תלוי'), וערבוב ממצאים בין מאמרים שונים.

*דוגמאות:*
- אקסון 1d זוהה בלב ובאבי העורקים אבל לא במוח
- ההשפעה נוגדת הפחד הייתה תלויה באיתות של בטא-ארסטין 2
- דקסאמפטמין במינון של 5 מ"ג לק"ג

*הצעת ניסוח להוספה לפרומפט:*

```text
Strictly adhere to the factual data and numbers provided in the source text. Pay special attention to decimal points and negative words (e.g., 'not', 'independent'). Do not reverse logical relationships, and never mix findings or methodologies between different articles.
```

### 2. עיוות, תרגום והמצאת שמות חוקרים  (4 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מנסה 'לגייר' שמות לועזיים ומתרגם אותם למילים עבריות קיימות (כמו 'יוסי קרוז' במקום Kosik-Rose), או שהוא מנחש שמות פרטיים מתוך ראשי התיבות של החוקרים.

*דוגמאות:*
- קבוצת מחקר בראשות יוסי קרוז
- מטא-אנליזה של קבוצת המחקר של קליין וין
- אריק פומפון

*הצעת ניסוח להוספה לפרומפט:*

```text
Do not translate, localize, or alter researchers' names. Never guess a first name from an initial. Use the exact last name provided in the text and transliterate it highly accurately and phonetically into Hebrew.
```

### 3. שבירת 'הקיר הרביעי' ותירוצים על מידע חסר  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* כאשר המודל מקבל מידע חלקי (כמו תקציר או כותרת בלבד), הוא שובר את הדמות שלו כפודקאסט ומציין שהמידע לא סופק לו, או שהוא ממציא שהמאמר המקורי בחר להסתיר את המידע כדי לחפות על חוסר הידיעה שלו.

*דוגמאות:*
- המאמר לא מפרט את השמות של התרופות ברשימה, אלא מדבר על עצם הקיום שלה
- המאמר לא סופק במלואו ולכן נתמקד בכותרת ובפרמטרים הבסיסיים
- גם כאן, הכותרת עצמה מספרת את הסיפור המרכזי

*הצעת ניסוח להוספה לפרומפט:*

```text
Never break the fourth wall to mention that you were only provided with an abstract, title, or partial text. If specific details are missing, seamlessly discuss what is available without inventing excuses or claiming the full article omitted them.
```

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.