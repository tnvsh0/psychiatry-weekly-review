# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-07-19 – 2026-08-12), 72 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.51 / 5 |
| כיסוי | 4.96 / 5 |
| שטף | 5.00 / 5 |

סיכומים: ✅ 59 · 🟡 12 · 🔴 1

---

## דפוסים חוזרים

### 1. המצאת פרטים וממצאים  (15 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל ממציא פרטים, נתונים, ממצאים ואף מאמרים שלמים שאינם קיימים במקורות שסופקו, או מייחס למקורות מידע שאינו מופיע בהם.

*דוגמאות:*
- נאמר: החוקרים עצמם מודעים לזה לחלוטין. אי אפשר לדעת בוודאות אם מספר המריבות בבית אובייקטיבית עלה או שהסף של הילד למה נחשב ריב פשוט ירד. | מקור: לא מופיע במקור
- נאמר: אני מסתכלת על מאמר מחקרי, ספציפית זה מחקר חתך רוחב שפורסם בכתב העת Archives of Clinical Neuropsychology. | מקור: לא מופיע במקור. כתב העת Archives of Clinical Neuropsychology אינו כלול ברשימת המאמרים שסופקה.
- נאמר: כאשר האם סובלת ממצוקה נפשית, זה לא נשאר רק ברובד הפסיכולוגי. זה משפיע על היכולת שלה לשקף לתינוק את הרגשות שלו, ואפילו... על הורמוני סטרס שעוברים דרך חלב אם. | מקור: לא מופיע במקור

*הצעת ניסוח להוספה לפרומפט:*

```text
Ensure all factual statements, statistics, and findings are directly supported by the provided source material for each article. Do not infer or invent information not explicitly present in the abstracts or full texts provided. If a specific detail or number is not in the source, do not include it. Clearly distinguish between information from the article and your own clinical interpretation or general knowledge.
```

### 2. פרשנות יתר או הגזמה של נתונים  (10 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה להגזים, לפשט יתר על המידה או לפרש באופן שגוי נתונים סטטיסטיים וממצאים קליניים, מה שמוביל למסקנות שאינן נתמכות במדויק על ידי המקור.

*דוגמאות:*
- נאמר: הפרעות ששכיחות פי 2 אצל נשים (על דיכאון עמיד וטראומה) | מקור: המאמר מציין שנשים חוות 'נטל לא פרופורציונלי של הפרעות אפקטיביות וקשורות לסטרס', אך אינו מציין שהן שכיחות 'פי 2' אצל נשים.
- נאמר: הנתונים בסקירה מראים שחלק עצום מהשונות, לפעמים מעל 80% מהנתונים שמקבלים מדגימת דם של מטופל פסיכיאטרי, זה בכלל לא קשור למחלה. | מקור: המאמר מדבר על הצורך ב'מיזעור רעש ביולוגי וטכני'... אך אינו מציין אחוז ספציפי כמו 'מעל 80%'.
- נאמר: המודל הציג AUC... של 0.70 עבור הפרעות מצב רוח ו-0.61 עבור פסיכוזה. כלומר, יש למודל סיכוי של כ-70% לסווג נכונה מטופל ככזה שיפתח הפרעת מצב רוח. | מקור: AUC אינו שווה ישירות ל'סיכוי של כ-70% לסווג נכונה'. AUC הוא מדד לביצועי המודל על פני כל ספי ההחלטה האפשריים, ולא אחוז סיווג נכון בנקודה ספציפית.

*הצעת ניסוח להוספה לפרומפט:*

```text
When presenting numerical data, statistical measures (e.g., odds ratios, effect sizes, AUC), or clinical outcomes, state them precisely as they appear in the source. Avoid overstating, simplifying, or misinterpreting their meaning. If a direct interpretation is not provided in the source, present the raw data and then offer a cautious, qualified interpretation, clearly labeling it as such.
```

### 3. שיבוש שמות כתבי עת ומחברים  (8 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל משבש באופן עקבי שמות של כתבי עת, שמות משפחה של מחברים או ראשי תיבות של כתבי עת, לעיתים קרובות על ידי תרגום מילולי או שיבוש פונטי.

*דוגמאות:*
- נאמר: המאמר שפורסם על ידי קבוצת מחקר ברשות יאפ (YAPP) | מקור: מחברים: Yap CX et al.
- נאמר: המאמר השלישי, בכתב העת The American Journal of Psychiatry, זה מאמר סקירה של החוקרים פורגולה ו-ויינברגר. | מקור: כתב העת הוא The American Journal of Psychiatry (Am J Psychiatry), לא 'The American Journal of Psychiatry'.
- נאמר: המאמר הרביעי מציג משהו שהוא הכי פיזי ואגרסיבי שיש. זה התפרסם בסנטה מנטל הלת'. | מקור: כתב העת הוא 'Sante Ment Que', לא 'סנטה מנטל הלת''.

*הצעת ניסוח להוספה לפרומפט:*

```text
When referring to journal names or author names, use their exact English spelling as provided in the source. Do not translate or phonetically approximate them into Hebrew. For journal abbreviations, use the full name if available, otherwise use the exact abbreviation.
```

### 4. אי דיוק בפרטי מחקר  (5 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מציג פרטים לא מדויקים לגבי מתודולוגיית המחקר, סוג ההשוואה, או היקף הטיפול, גם כאשר המידע המדויק זמין במקור.

*דוגמאות:*
- נאמר: המאמר הרביעי הוא פיילוט לטיפול מואץ בגריה מגנטית מוחית מול פלצבו. | מקור: הוא משווה בין iTBS מונחה fMRI, iTBS לא מונחה, וגירוי דמה (sham stimulation), לא רק 'מול פלצבו'.
- נאמר: 90,000 פולסים בתוך חמישה ימים, עם ניווט של fMRI. | מקור: המאמר מציין '10 daily sessions spanning 5 consecutive days (90,000 pulses total)', כלומר 10 סשנים ב-5 ימים, לא '90,000 פולסים בתוך חמישה ימים'.
- נאמר: למרות שחשוב אולי שנדייק רגע שמדובר למעשה בסקירת תיאורטית שמציעה מודל חדש | מקור: TOP-DOWN TO BOTTOM-UP: RHYTHMIC SYNCHRONY RELAXES SOCIAL PRIORS TO ENABLE CHANGE... this review integrates findings from cognitive motor science, biomusicology, and adjacent fields to synthesize the relaxed priors through synchrony (RePS) model.

*הצעת ניסוח להוספה לפרומפט:*

```text
Describe study methodologies, comparisons, and intervention details with high fidelity to the source material. Avoid simplifying or altering the reported design, participant numbers, or treatment protocols.
```

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.