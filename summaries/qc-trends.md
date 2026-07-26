# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 6 ריצות (2026-07-08 – 2026-07-26), 55 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.33 / 5 |
| כיסוי | 4.95 / 5 |
| שטף | 4.84 / 5 |

סיכומים: ✅ 36 · 🟡 18 · 🔴 1

---

## דפוסים חוזרים

### 1. הזיות ותוספות לא מבוססות  (26 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה להשלים מידע חסר או לפרש באופן חופשי מדי את התקצירים, במיוחד כאשר המידע המבוקש אינו מופיע במפורש במקורות שסופקו לו, או כשהוא מנסה להרחיב על מנגנונים שלא פורטו.

*דוגמאות:*
- נאמר: כאשר האם סובלת ממצוקה נפשית, זה לא נשאר רק ברובד הפסיכולוגי. זה משפיע על היכולת שלה לשקף לתינוק את הרגשות שלו, ואפילו... על הורמוני סטרס שעוברים דרך חלב אם. | מקור: לא מופיע במקור
- נאמר: ומה שראו שם, ברמת הממצאים, מצביע על פער מטריד מאוד בין רמת המצוקה לבין הניצול בפועל של מערכות התמיכה. (02:27) | מקור: לא מופיע במקור.
- נאמר: המאמר מזהה עלייה ברורה ברישום של תרופות פסיכוטרופיות. (04:42) | מקור: המאמר בוחן את 'Risk of Psychotropic Medication Use' (סיכון לשימוש בתרופות פסיכוטרופיות) ולא 'עלייה ברורה ברישום'.

*הצעת ניסוח להוספה לפרומפט:*

```text
Strictly adhere to the provided source abstracts. Do not infer, elaborate, or add information that is not explicitly stated in the text. If a detail or mechanism is not present in the abstract, state that it is not mentioned or avoid discussing it.
```

### 2. אי דיוקים בפרטי מחקר  (12 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה לעיתים לפרש נתונים סטטיסטיים באופן שגוי (כמו AUC), או להוסיף פרטים ספציפיים (כמו מספר קבוצות או מיקום גאוגרפי) שאינם מופיעים במפורש בתקציר, אלא נגזרים או משוערים.

*דוגמאות:*
- נאמר: המודל הציג AUC... של 0.70 עבור הפרעות מצב רוח ו-0.61 עבור פסיכוזה. כלומר, יש למודל סיכוי של כ-70% לסווג נכונה מטופל ככזה שיפתח הפרעת מצב רוח. (08:41) | מקור: AUC אינו שווה ישירות ל'סיכוי של כ-70% לסווג נכונה'.
- נאמר: המאמר של היינדמן וביסין חילק את הסטודנטים לשלוש קבוצות: קבוצה אחת קיבלה דדליינים חיצוניים... | מקור: התקציר מזכיר 'מועדי הגשה מפוזרים באופן שווה, שהוכתבו חיצונית על ידי הנסיינים' אך אינו מפרט את כל שלוש הקבוצות כפי שתוארו באודיו.
- נאמר: המאמר של Huang S et al. בדק 2,016 ילדים באנגליה (המחקר בדק ילדים מה-UK Millennium Cohort Study, אך לא צוין שהם מאנגליה בלבד).

*הצעת ניסוח להוספה לפרומפט:*

```text
When presenting numerical findings or study details, quote or paraphrase directly from the abstract. Do not interpret statistical measures (e.g., AUC) into probabilities unless the abstract explicitly does so. Do not add specific details (e.g., number of groups, exact geographical location) if they are not explicitly stated in the source.
```

### 3. בעיות שטף וקטיעות בדיאלוג  (7 מופעים)

**⛔ מגבלה — לא ניתן לתקן בפרומפט**

*אבחנה:* המודל מתקשה לשמור על שטף דיבור טבעי לחלוטין ולמנוע קטיעות או חפיפות בין הדוברים, מה שפוגע בחווית ההאזנה.

*דוגמאות:*
- הערה: ישנם קטיעות קלות וקפיצות בין הדוברים לעיתים, אך לא ברמה שמפריעה להבנה.
- הערה: The hosts frequently interrupt each other, which is typical for a conversational podcast but can sometimes make it harder to follow.
- הערה: The hosts sometimes speak over each other, making it hard to follow.

*מה כן יעזור:* זוהי מגבלה של מודל השפה ויכולות ה-TTS הנוכחיות, ודורשת שיפור בטכנולוגיות הבסיסיות של יצירת דיאלוג וסינתזת דיבור.

### 4. שימוש באנלוגיות ומטאפורות לא מבוססות  (6 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה לייצר אנלוגיות ומטאפורות כדי להסביר מושגים מורכבים, אך אלו אינן מבוססות על המקור ועלולות להטעות או להוסיף פרשנות לא רצויה.

*דוגמאות:*
- הערה: הדוברים מסכמים את הצורך בתכנון קפדני של 'מסילות' לטכנולוגיה, אך ניסוח זה הוא מטאפורי ואינו מופיע במפורש בתקציר המאמר.
- הערה: The analogy of the wrench and the house (0:34-0:55, 5:29-5:39) is a creative framing device by the hosts, not directly from the source abstracts, but used to explain the papers' concepts.
- הערה: The male host uses a metaphor of a 'sophisticated radar' and 'hidden frequencies' to describe children's perception, which is not directly from the scientific abstracts.

*הצעת ניסוח להוספה לפרומפט:*

```text
Avoid using analogies or metaphors that are not explicitly present in the source material. Focus on clear, direct explanations of the research findings.
```

### 5. הגייה לא עקבית של שמות ומונחים  (3 מופעים)

**⛔ מגבלה — לא ניתן לתקן בפרומפט**

*אבחנה:* המודל מתקשה לשמור על עקביות בהגיית שמות לועזיים (חוקרים, כתבי עת) ומונחים מקצועיים, מה שפוגע באמינות ובבהירות.

*דוגמאות:*
- הערה: הגייה לא עקבית של שמות חוקרים (לדוגמה, 'חוארז' במקום 'ג'וארז').
- הערה: הגייה לא עקבית של שמות כתבי עת (לדוגמה, 'Journal of Child Psychology and Psychiatry' לעומת 'Journal of Child Psychology and Psychiatry').
- הערה: הגייה לא עקבית של מונחים מקצועיים (לדוגמה, 'אפנירס' במקום 'fNIRS').

*מה כן יעזור:* זוהי מגבלה של מודל ה-TTS (Text-to-Speech) ודורשת שיפור ביכולות ההגייה והעקביות שלו עבור מילים לועזיות ומונחים מקצועיים.

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.