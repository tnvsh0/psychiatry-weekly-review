# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-07-29 – 2026-08-26), 72 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.65 / 5 |
| כיסוי | 4.99 / 5 |
| שטף | 5.00 / 5 |

סיכומים: ✅ 60 · 🟡 10 · 🔴 2

---

## דפוסים חוזרים

### 1. הזיות עובדתיות ואי-דיוקים מהותיים  (18 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מייצר מידע שגוי לחלוטין, כולל פרטי מחקרים שלמים או נתונים מספריים ספציפיים, שאינם קיימים במקורות שסופקו או סותרים אותם ישירות.

*דוגמאות:*
- המאמר הראשון שנסקר עסק בתוכנית התערבות אוניברסלית של מיינדפולנס בבתי ספר יסודיים... המחקר מצא שמיינדפולנס לא רק שלא עזר, אלא החמיר את תסמיני הדיכאון בילדי יסודי. | מקור: לא מופיע במקור.
- אני מסתכלת על מאמר מחקרי... פורסם בכתב העת Archives of Clinical Neuropsychology. | מקור: לא מופיע במקור.
- החוקרים מצאו ש-58% מאלו שאובחנו עם הפרעת קשב סבלו גם מהפרעה פסיכיאטרית נלווית. | מקור: לא מופיע במקור.

*הצעת ניסוח להוספה לפרומפט:*

```text
Ensure all factual statements, especially numerical data, study designs, and specific findings, are directly and explicitly supported by the provided source text. Do not infer, extrapolate, or invent details. If a detail is not in the source, do not mention it as a finding from that source. If the source text is missing, state that the discussion is based on the title and clinical reasoning only.
```

### 2. שיבוש שמות כתבי עת ומחברים  (10 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתקשה לדייק בשמות כתבי עת ובשמות מחברים, לעיתים משבש אותם או מתרגם אותם באופן שגוי לעברית.

*דוגמאות:*
- המאמר השלישי, שנכתב על ידי פומבון וליאו | מקור: המחברים הם Fombonne E, Liao L
- המאמר של צוות המחקר של גאסטון מכתב העת Sleep Medicine Reviews | מקור: המאמר הוא 'An overview of systematic reviews and a global evidence map' ולא מטה-אנליזה ענקית.
- המאמר הרביעי מציג משהו שהוא הכי פיזי ואגרסיבי שיש. זה התפרסם בסנטה מנטל הלת'. | מקור: כתב העת הוא 'Sante Ment Que', לא 'סנטה מנטל הלת''.

*הצעת ניסוח להוספה לפרומפט:*

```text
When referring to journal names or author names, always use the exact spelling and capitalization as provided in the source material. Do not translate or transliterate journal names unless explicitly instructed. For author teams, use 'צוות המחקר של [שם המחבר הראשון]' only if the source explicitly refers to a team, otherwise list the first author's last name.
```

### 3. פרשנות כעובדה/הצגת מידע חיצוני כמידע מהמאמר  (6 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מציג פרשנויות אישיות או מידע כללי שאינו מופיע במקורות כעובדות מתוך המאמר, או שאינו מסמן בבירור מתי הוא חורג מתוכן המאמר.

*דוגמאות:*
- המאמר הזה בוחן שימוש בבינה מלאכותית לזיהוי מוקדם של אוטיזם... הנימוק 'בינה מלאכותית פשוט לא מוגבלת למה שהעין האנושית מסוגלת לעבד' הוא פרשנות של המגיש ולא ציטוט ישיר מהמאמר.
- המאמר מציין שנשים חוות 'נטל לא פרופורציונלי של הפרעות אפקטיביות וקשורות לסטרס', אך אינו מציין שהן שכיחות 'פי 2' אצל נשים. זהו מידע כללי שלא מיוחס למאמר במפורש, אך גם לא מסומן כמידע חיצוני.
- ההבחנה בין מידע מהמאמר לבין פרשנות או הרחבה סומנה בבירור, כנדרש במפרט. | הערה: ההתייחסות למאמרים שאינם מהסקירה השבועית (כמו מחקר המיינדפולנס) אינה מסומנת בבירור כמידע חיצוני למאמרים שסופקו, מה שעלול להטעות את המאזין לחשוב שמדובר באחד ממאמרי השבוע.

*הצעת ניסוח להוספה לפרומפט:*

```text
Clearly distinguish between information directly stated in the article and your own clinical interpretation, analogies, or general knowledge. When introducing information not directly from the provided abstract/article, explicitly state that it is an external comment, analogy, or broader context, for example, by saying 'בהקשר רחב יותר', 'כדאי לזכור ש', or 'זוהי פרשנות שלנו'.
```

### 4. אי-דיוקים בסוג המחקר/הסקירה  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתבלבל בין סוגי מאמרים (לדוגמה, סקירת ספרות מול מאמר מחקרי מקורי, או סקירת סקירות מול מטה-אנליזה), ומציג את סוג המחקר באופן שגוי.

*דוגמאות:*
- המאמר של סורמני הוא מאמר מחקרי | מקור: המאמר של סורמני הוא 'סקירת ספרות' (Review Article) ולא מאמר מחקרי (Research Article).
- המאמר של צוות המחקר של גאסטון מכתב העת Sleep Medicine Reviews... מדובר פה על מטה-אנליזה ענקית שהיגדה 12 סקירות שיטתיות | מקור: המאמר הוא 'An overview of systematic reviews and a global evidence map' ולא מטה-אנליזה ענקית.
- המאמר עוסק במושג שנקרא אינטרון ריטנשן (Intron retention)... | מקור: The abstract itself is a 'Review Article', not a research article as stated in the audio.

*הצעת ניסוח להוספה לפרומפט:*

```text
Always accurately state the study type (e.g., 'מאמר מחקרי', 'סקירת ספרות', 'מטה-אנליזה', 'מחקר פיילוט') as indicated in the source. If the source specifies 'Review Article', do not refer to it as a 'Research Article'.
```

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.