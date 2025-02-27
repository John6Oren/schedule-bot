import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from flask import Flask, render_template_string
import json
import os
import logging

# הגדרת לוגר לתיעוד מפורט
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# רשימת הקבוצות הרלוונטיות
RELEVANT_TEAMS = {
    "נערות א על": "JdEgwNeI0MR0VjZutkS2hV",  # Group ID של נערות א על
    "נשים לאומית": "BM2gyfNW2DvCdlscAoPyUH"  # Group ID של נשים לאומית
}

# כתובות היומנים
TRAININGS_URL = "https://www.gilboamaayanot.co.il/public/diary/weeklydiary"
GAMES_URL = "https://www.gilboamaayanot.co.il/public/diary/diarygames"

# ScrapingBee API key
SCRAPINGBEE_API_KEY = "IULKB9QFUJ4G8HNJCD1O93RPTCC2ZE52FC9ZCI2W7ZK22GZWCHU2BELR053RBCTVLDV4MI5SOI14BJ8D"

# פונקציה לשליפת נתונים מהאתר באמצעות ScrapingBee
def fetch_page_with_scrapingbee(url):
    logger.info(f"שולף דף מ-URL: {url}")
    
    # הגדרת פרמטרים עבור ScrapingBee
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true',  # להריץ JavaScript בדף
        'wait': '2000',       # לחכות 2 שניות לטעינת הדף
        'premium_proxy': 'true'  # להשתמש בפרוקסי פרמיום למניעת חסימות
    }
    
    try:
        response = requests.get('https://app.scrapingbee.com/api/v1/', params=params)
        logger.info(f"סטטוס תשובה מ-ScrapingBee: {response.status_code}")
        
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"שגיאה בשליפת הדף: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"תקלה בשליפת הדף: {str(e)}")
        return None

# פונקציה לשליפת אירועים מהיומן
def fetch_schedule(url):
    logger.info(f"מתחיל שליפת אירועים מ: {url}")
    
    # שליפת תוכן הדף באמצעות ScrapingBee
    html_content = fetch_page_with_scrapingbee(url)
    if not html_content:
        logger.error("לא התקבל תוכן מהדף")
        return []
    
    # פירוק ה-HTML באמצעות BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # איתור אירועים בדף
    event_items = soup.find_all("div", class_="event-item")
    logger.info(f"נמצאו {len(event_items)} אירועים בדף")
    
    # ניסיון מבנה אלטרנטיבי אם לא נמצאו אירועים
    if len(event_items) == 0:
        logger.info("מנסה למצוא אירועים במבנה אלטרנטיבי")
        event_items = soup.find_all(lambda tag: tag.name == 'div' and 'event' in tag.get('class', []))
        logger.info(f"נמצאו {len(event_items)} אירועים במבנה אלטרנטיבי")
    
    for event in event_items:
        try:
            # ניסיון למצוא את הכותרת במבנים שונים
            title_element = event.find("h3") or event.find("h4") or event.find(class_="event-title")
            if not title_element:
                logger.warning("לא נמצאה כותרת לאירוע, מדלג")
                continue
            
            title = title_element.text.strip()
            logger.info(f"מעבד אירוע: {title}")
            
            # ניסיון למצוא את הפרטים במבנים שונים
            details_element = event.find("p") or event.find(class_="event-details")
            if not details_element:
                logger.warning("לא נמצאו פרטים לאירוע, מדלג")
                continue
                
            details = details_element.text.strip()
            
            # פירוק פרטי האירוע
            details_parts = details.split("·")
            if len(details_parts) < 3:
                logger.warning(f"פורמט פרטים לא תקין: {details}")
                continue
                
            date_str = details_parts[0].strip()
            time_str = details_parts[1].strip()
            location = details_parts[2].strip()
            
            # עיבוד התאריך
            try:
                logger.debug(f"מעבד תאריך: {date_str}")
                event_date = parse_date(date_str)
                if not event_date:
                    logger.warning(f"לא ניתן לפרסר תאריך: {date_str}")
                    continue
            except Exception as e:
                logger.error(f"שגיאה בפרסור תאריך {date_str}: {str(e)}")
                continue
            
            # זיהוי האם זה אימון או משחק
            is_game = False
            team_name = None
            opponent = None
            home_away = None
            
            for team in RELEVANT_TEAMS.keys():
                if team in title:
                    team_name = team
                    if "-" in title:  # זה משחק
                        is_game = True
                        teams = title.split("-")
                        if team in teams[0]:  # משחק בית
                            opponent = teams[1].strip()
                            home_away = "בית"
                        else:  # משחק חוץ
                            opponent = teams[0].strip()
                            home_away = "חוץ"
                    break
            
            if team_name:  # אם נמצאה קבוצה רלוונטית
                event_data = {
                    "team": team_name,
                    "date": event_date,
                    "time": time_str,
                    "location": location,
                    "is_game": is_game,
                    "opponent": opponent,
                    "home_away": home_away if is_game else None
                }
                logger.info(f"הוספת אירוע: {event_data}")
                events.append(event_data)
        except Exception as e:
            logger.error(f"שגיאה בעיבוד אירוע: {str(e)}")
            continue
    
    logger.info(f"סה\"כ {len(events)} אירועים רלוונטיים נמצאו")
    return events

# פונקציה לפרסור תאריך עם טיפול בפורמטים שונים
def parse_date(date_str):
    formats = [
        "%A, %d %B",      # Friday, 12 March
        "%d/%m/%Y",       # 12/03/2023
        "%d/%m/%y",       # 12/03/23
        "%d.%m.%Y",       # 12.03.2023
        "%d.%m.%y",       # 12.03.23
        "%d %B %Y",       # 12 March 2023
        "%d %B",          # 12 March
    ]
    
    current_year = datetime.now().year
    
    for fmt in formats:
        try:
            # נסה לפרסר עם הפורמט הנוכחי
            if '%Y' in fmt or '%y' in fmt:
                # אם הפורמט כולל שנה, פרסר ישירות
                return datetime.strptime(date_str, fmt)
            else:
                # אם הפורמט לא כולל שנה, הוסף את השנה הנוכחית
                date = datetime.strptime(date_str, fmt)
                date = date.replace(year=current_year)
                
                # טיפול במקרים של מעבר שנה (דצמבר -> ינואר)
                if date.month < datetime.now().month and date.month < 3:
                    date = date.replace(year=current_year + 1)
                
                return date
        except ValueError:
            # אם הפורמט לא מתאים, המשך לנסות את הבא
            continue
    
    logger.warning(f"לא ניתן לפרסר תאריך בפורמט: {date_str}")
    return None

# פונקציה ליצירת הודעה מותאמת בפורמט המבוקש
def create_message(events, team_name):
    logger.info(f"יוצר הודעה עבור קבוצת {team_name}")
    
    today = datetime.now()
    end_date = today + timedelta(days=7)
    
    # סינון אירועים רק לשבוע הקרוב והקבוצה המבוקשת
    filtered_events = [
        e for e in events 
        if e["team"] == team_name and today <= e["date"] <= end_date
    ]
    
    # מיון לפי תאריך ושעה
    filtered_events.sort(key=lambda e: (e["date"], e["time"]))
    
    logger.info(f"נמצאו {len(filtered_events)} אירועים בשבוע הקרוב עבור {team_name}")
    
    # יצירת הודעה בפורמט שנקבע
    message = f"היי\n\nמצרף לכן את לוח האימונים והמשחקים לשבוע הקרוב:\n"
    
    days_in_hebrew = {
        0: "שני",
        1: "שלישי",
        2: "רביעי",
        3: "חמישי",
        4: "שישי",
        5: "שבת",
        6: "ראשון"
    }
    
    for event in filtered_events:
        # המרת היום בשבוע ופורמט התאריך
        day_name = days_in_hebrew[event["date"].weekday()]
        date_str = event["date"].strftime("%d.%m.%y")
        
        if event["is_game"]:
            message += f"יום {day_name} {date_str}, {event['time']}, משחק {event['home_away']} נגד {event['opponent']}, {event['location']}\n"
        else:
            message += f"יום {day_name} {date_str}, {event['time']}, אימון, {event['location']}\n"
    
    message += "\nניפגש 🏀"
    
    return message, filtered_events

# ריצת הבוט לקבלת לוח האירועים
def get_schedule_for_team(team_name):
    logger.info(f"משיג לוח זמנים לקבוצת {team_name}")
    
    try:
        # שליפת נתונים מהיומנים
        training_events = fetch_schedule(TRAININGS_URL)
        game_events = fetch_schedule(GAMES_URL)
        
        # שילוב האימונים והמשחקים
        all_events = training_events + game_events
        
        logger.info(f"נמצאו {len(all_events)} אירועים רלוונטיים בסך הכל")
        
        # יצירת ההודעה והאירועים המסוננים
        message, filtered_events = create_message(all_events, team_name)
        
        return {
            "message": message,
            "events": filtered_events,
            "total_events": len(filtered_events),
            "success": True
        }
    except Exception as e:
        logger.error(f"שגיאה בהשגת לוח זמנים: {str(e)}")
        return {
            "message": f"אירעה שגיאה: {str(e)}",
            "events": [],
            "total_events": 0,
            "success": False
        }

# ממשק ווב
@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html dir="rtl" lang="he">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>בוט לוח אימונים</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
                text-align: center;
            }
            .container {
                max-width: 800px;
                margin: 30px auto;
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            .date-range {
                margin-bottom: 20px;
                color: #666;
                font-size: 16px;
            }
            .button-container {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
            }
            .btn {
                padding: 12px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                transition: all 0.3s;
            }
            .btn-blue {
                background-color: #3498db;
                color: white;
            }
            .btn-blue:hover {
                background-color: #2980b9;
            }
            .btn-yellow {
                background-color: #f1c40f;
                color: white;
            }
            .btn-yellow:hover {
                background-color: #f39c12;
            }
            .refresh-btn {
                background-color: #2ecc71;
                color: white;
                margin-top: 20px;
            }
            .refresh-btn:hover {
                background-color: #27ae60;
            }
            .schedule-container {
                margin-top: 30px;
                text-align: right;
                display: none;
                background-color: #f9f9f9;
                padding: 20px;
                border-radius: 5px;
                border: 1px solid #ddd;
            }
            .schedule-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .schedule-title {
                font-size: 18px;
                font-weight: bold;
                color: #333;
            }
            .copy-btn {
                background-color: #3498db;
                color: white;
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            .copy-btn:hover {
                background-color: #2980b9;
            }
            .schedule-content {
                white-space: pre-line;
                line-height: 1.6;
                font-size: 16px;
            }
            .alert {
                padding: 15px;
                margin-bottom: 20px;
                border-radius: 5px;
            }
            .alert-info {
                background-color: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }
            .alert-warning {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeeba;
            }
            .alert-danger {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .loading {
                display: none;
                margin: 20px auto;
                text-align: center;
            }
            .spinner {
                border: 4px solid rgba(0, 0, 0, 0.1);
                border-radius: 50%;
                border-top: 4px solid #3498db;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
                margin: 10px auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .debug-btn {
                background-color: #95a5a6;
                color: white;
                padding: 5px 10px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                margin-top: 30px;
            }
            .debug-container {
                display: none;
                margin-top: 20px;
                text-align: left;
                background-color: #f9f9f9;
                padding: 20px;
                border-radius: 5px;
                border: 1px solid #ddd;
                font-family: monospace;
                overflow-x: auto;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>בוט לוח אימונים</h1>
            
            <div class="date-range">
                לוח זמנים לשבוע הקרוב: 
                <span id="dateRange"></span>
            </div>
            
            <div class="button-container">
                <button id="btnTeam1" class="btn btn-blue">הצג לוז נערות א על</button>
                <button id="btnTeam2" class="btn btn-yellow">הצג לוז נשים לאומית</button>
            </div>
            
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <p>טוען את לוח האימונים... זה עשוי לקחת כמה שניות</p>
            </div>
            
            <div id="alertContainer"></div>
            
            <div id="scheduleContainer" class="schedule-container">
                <div class="schedule-header">
                    <div class="schedule-title" id="scheduleTitle"></div>
                    <button id="copyButton" class="copy-btn">העתק הודעה</button>
                </div>
                <div id="scheduleContent" class="schedule-content"></div>
            </div>
            
            <button id="refreshButton" class="btn refresh-btn" style="display: none;">הפעלת הדף</button>
            
            <button id="debugButton" class="debug-btn">הצג מידע טכני</button>
            <div id="debugContainer" class="debug-container"></div>
        </div>
        
        <script>
            // עדכון טווח תאריכים
            function updateDateRange() {
                const today = new Date();
                const nextWeek = new Date();
                nextWeek.setDate(today.getDate() + 7);
                
                const formatDate = (date) => {
                    return `${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear().toString().substr(2)}`;
                };
                
                document.getElementById('dateRange').textContent = 
                    `${formatDate(today)} - ${formatDate(nextWeek)}`;
            }
            
            // פונקציה להצגת התראה
            function showAlert(message, type = 'info') {
                const alertContainer = document.getElementById('alertContainer');
                alertContainer.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
            }
            
            // פונקציה לקבלת לוח זמנים לקבוצה
            function getSchedule(team) {
                document.getElementById('loading').style.display = 'block';
                document.getElementById('scheduleContainer').style.display = 'none';
                document.getElementById('alertContainer').innerHTML = '';
                document.getElementById('debugContainer').style.display = 'none';
                
                fetch('/get_schedule/' + team)
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('loading').style.display = 'none';
                        
                        if (data.success) {
                            if (data.total_events > 0) {
                                document.getElementById('scheduleTitle').textContent = `לוח אימונים ומשחקים - ${team} (${data.total_events} אירועים)`;
                                document.getElementById('scheduleContent').textContent = data.message;
                                document.getElementById('scheduleContainer').style.display = 'block';
                                document.getElementById('refreshButton').style.display = 'none';
                            } else {
                                showAlert(`לא נמצאו אירועים מתוכננים לקבוצת ${team} בשבוע הקרוב.`, 'warning');
                                document.getElementById('refreshButton').style.display = 'inline-block';
                            }
                            
                            // הוספת מידע דיבאג
                            document.getElementById('debugContainer').innerHTML = 
                                `<h3>מידע טכני:</h3>
                                 <p>מספר אירועים שנמצאו: ${data.total_events}</p>
                                 <p>סטטוס: ${data.success ? 'הצלחה' : 'שגיאה'}</p>
                                 <pre>${JSON.stringify(data.events || [], null, 2)}</pre>`;
                        } else {
                            showAlert(`שגיאה בטעינת הלוח: ${data.message}`, 'danger');
                            document.getElementById('refreshButton').style.display = 'inline-block';
                        }
                    })
                    .catch(error => {
                        document.getElementById('loading').style.display = 'none';
                        showAlert(`שגיאת תקשורת: ${error.message}`, 'danger');
                        document.getElementById('refreshButton').style.display = 'inline-block';
                    });
            }
            
            // מאזיני אירועים
            document.addEventListener('DOMContentLoaded', function() {
                updateDateRange();
                
                document.getElementById('btnTeam1').addEventListener('click', function() {
                    getSchedule('נערות א על');
                });
                
                document.getElementById('btnTeam2').addEventListener('click', function() {
                    getSchedule('נשים לאומית');
                });
                
                document.getElementById('copyButton').addEventListener('click', function() {
                    const content = document.getElementById('scheduleContent').textContent;
                    navigator.clipboard.writeText(content)
                        .then(() => alert('ההודעה הועתקה בהצלחה!'))
                        .catch(err => alert('שגיאה בהעתקה: ' + err));
                });
                
                document.getElementById('refreshButton').addEventListener('click', function() {
                    location.reload();
                });
                
                document.getElementById('debugButton').addEventListener('click', function() {
                    const debugContainer = document.getElementById('debugContainer');
                    debugContainer.style.display = debugContainer.style.display === 'none' || 
                                                   debugContainer.style.display === '' ? 'block' : 'none';
                });
            });
        </script>
    </body>
    </html>
    ''')

# נתיב להשגת לוח זמנים לקבוצה
@app.route('/get_schedule/<team_name>')
def get_schedule_route(team_name):
    if team_name not in RELEVANT_TEAMS:
        return json.dumps({
            "message": f"קבוצה לא נמצאה: {team_name}",
            "success": False
        })
    
    result = get_schedule_for_team(team_name)
    return json.dumps(result, default=lambda obj: obj.isoformat() if isinstance(obj, datetime) else str(obj))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
