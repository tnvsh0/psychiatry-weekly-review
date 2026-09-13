# 📈 מגמות בקרת איכות — דפוסים חוזרים והצעות לשיפור

*מבוסס על 8 ריצות (2026-08-12 – 2026-09-09), 64 פרקים.*

## ציונים ממוצעים

| מדד | ממוצע |
|---|:---:|
| דיוק | 4.73 / 5 |
| כיסוי | 5.08 / 5 |
| שטף | 5.00 / 5 |

סיכומים: ✅ 58 · 🟡 5 · 🔴 1

---

## דפוסים חוזרים

### 1. אי-דיוקים בתיאור ממצאי מחקר  (8 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל נוטה לפרשנות יתר, להכללות או להוספת פרטים שאינם מופיעים במפורש בתקציר המאמר, במיוחד כשמדובר בנתונים מספריים או בתיאור מנגנונים מורכבים.

*דוגמאות:*
- נאמר: המחקר חילק את המשתתפים לשלוש זרועות שונות... והקבוצה השלישית הייתה קבוצת ביקורת של אנשים בריאים ללא שום אבחנה פסיכיאטרית. | מקור: In a triple-blind, randomized, placebo-controlled MRI study, 62 antipsychotic-naïve people with first-episode psychosis (FEP) received a second-generation antipsychotic or placebo over 6 months (n = 35 at 12 months) alongside a healthy control group (n = 27 at baseline, n = 21 at 12 months).
- נאמר: החוקרים במאמר של קונג השתמשו ב-EEG בצפיפות גבוהה מאוד, מה שאפשר להם להקליט פעילות חשמלית מאלפי נוירונים בודדים בו-זמנית. | מקור: המאמר מציין 'high-density EEG' ו-'time-resolved multivariate pattern analysis (MVPA)', אך לא מציין הקלטה מאלפי נוירונים בודדים.
- נאמר: במדד של דיווחי הילדים עצמם לחרדה, הם הראו הפחתה משמעותית יותר של 4.5 נקודות, לעומת קבוצת הביקורת אחרי 12 חודשים. | מקור: the primary outcomes (SCARED-C and SCARED-P total scores) showed statistically significant differences between the groups at both the 12-month (SCARED-C mean score in the intervention group was 4.5 [95% CI, 2.2-6.8] points higher; P < .001; Cohen d = 0.35; and SCARED-P mean score was 3.4 [95% CI, 1.8-5.1] points higher; P < .001; Cohen d…

*הצעת ניסוח להוספה לפרומפט:*

```text
When describing study findings, especially numerical results, specific methodologies, or mechanisms, adhere strictly to the information provided in the source text. Do not infer, elaborate, or add details that are not explicitly stated in the abstract or provided text.
```

### 2. ייחוס שגוי של מידע למאמרים  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל ממציא לעיתים מידע או מייחס ממצאים למאמרים שאינם קשורים, ככל הנראה בניסיון למלא פערים או ליצור נרטיב קוהרנטי.

*דוגמאות:*
- נאמר: המאמר הזה הוא כל כך חשוב ורחב יריעה שהחלטנו להקדיש לו פרק זרקור מלא משלו בערוץ הזרקור שלנו בעוד כמה ימים. | מקור: לא מופיע במקור
- נאמר: המאמר הראשון שנסקר עסק בתוכנית התערבות אוניברסלית של מיינדפולנס בבתי ספר יסודיים, ופורסם בכתב העת European Child and Adolescent Psychiatry. המחקר מצא שמיינדפולנס לא רק שלא עזר, אלא החמיר את תסמיני הדיכאון בילדי יסודי. | מקור: לא מופיע במקור. אף אחד מהמאמרים שסופקו לא עוסק במיינדפולנס או בתוכניות התערבות בבתי ספר יסודיים, ובוודאי שלא בתוצאות שהוזכרו.
- נאמר: המאמר של צוות המחקר של יאנג שפורסם בכתב העת Frontiers in Public Health מראה שכל הסטרס הזה גובה מס גם ברמה הפיזית. הם מצאו שמדובר בתחלואה מרובה. פגיעה שמשלבת בעיות פיזיות, פסיכולוגיות וגם קוגניטיביות שמתרחשות כולן בו זמנית. | מקור: לא מופיע במקור

*הצעת ניסוח להוספה לפרומפט:*

```text
All information presented as factual findings from a specific paper must be directly supported by the provided source text for that paper. Do not invent details, results, or connections to external content.
```

### 3. זיהוי שגוי של מחברים  (3 מופעים)

**🔧 ניתן לתקן בפרומפט**

*אבחנה:* המודל מתקשה לעיתים בתעתיק מדויק של שמות מחברים ללא הקשר מלא, או מניח שמות פרטיים שאינם מופיעים במקור.

*דוגמאות:*
- נאמר: קבוצת מחקר בראשות יוסי קרוז | מקור: מחברים: Kosik-Rose E et al. (החוקר הראשי הוא Kosik-Rose)
- נאמר: השלישי, שנכתב על ידי פומבון וליאו (03:00) | מקור: המחברים הם Fombonne E, Liao L (מתוך המקור)
- נאמר: המאמר שפורסם על ידי קבוצת מחקר ברשות יאפ (YAPP) | מקור: מחברים: Yap CX et al.

*הצעת ניסוח להוספה לפרומפט:*

```text
When referring to authors, use the exact last name as it appears in the source. Do not invent first names or alter spellings unless explicitly provided.
```

---

> הצעות בלבד — אף שינוי לא הוחל אוטומטית. NotebookLM אינו לומד בין פרקים והפלט אינו דטרמיניסטי, ולכן שינוי פרומפט נעשה רק באישור אנושי.