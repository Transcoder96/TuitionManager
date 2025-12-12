import sqlite3
import calendar
import os
from datetime import datetime, date, timedelta
from shutil import copyfile

# Kivy / KivyMD Imports
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconRightWidget, ThreeLineListItem, ImageLeftWidget
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.button import MDRaisedButton, MDFloatingActionButton, MDIconButton, MDRoundFlatButton, MDFlatButton, MDTextButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.toast import toast
from kivy.metrics import dp, sp
from kivy.utils import platform
from kivy.core.window import Window
from kivy.clock import Clock

# --- NOTIFICATIONS SETUP ---
try:
    from plyer import notification
except ImportError:
    notification = None # Handle if user hasn't installed plyer yet

# --- DATABASE SETUP ---
DB_NAME = 'tuition_v19_final.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY, 
                    name TEXT,
                    photo_path TEXT,
                    fee_amount TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY, 
                    student_id INTEGER, 
                    subject TEXT, 
                    day_name TEXT, 
                    class_time TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance (
                    student_id INTEGER, 
                    date_str TEXT, 
                    status TEXT,
                    UNIQUE(student_id, date_str)
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS fee_history (
                    student_id INTEGER, 
                    month_str TEXT, 
                    is_paid INTEGER,
                    UNIQUE(student_id, month_str)
                )""")
    conn.commit()
    conn.close()

# --- REMINDER LOGIC ---
def schedule_class_reminders():
    """Checks every minute if a class is 30 mins away"""
    if not notification:
        return

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        now = datetime.now()
        current_day = now.strftime("%a")  # Mon, Tue...
        
        # Get today's classes
        c.execute("""
            SELECT s.name, sch.subject, sch.class_time 
            FROM schedules sch 
            JOIN students s ON sch.student_id = s.id 
            WHERE sch.day_name = ?
        """, (current_day,))
        
        classes = c.fetchall()
        conn.close()
        
        for student_name, subject, class_time in classes:
            try:
                # Parse time (supports "4:00 PM" and "16:00")
                t_str = class_time.strip().upper()
                try:
                    class_dt = datetime.strptime(t_str, "%I:%M %p")
                except ValueError:
                    try:
                        class_dt = datetime.strptime(t_str, "%H:%M")
                    except ValueError:
                        continue # Skip invalid time formats
                
                # Combine with today's date
                class_full_dt = datetime.combine(now.date(), class_dt.time())
                
                # Reminder time = Class Time - 30 minutes
                reminder_time = class_full_dt - timedelta(minutes=30)
                
                # Check if we are in the exact minute of the reminder
                # (now >= reminder AND now < reminder + 1 min)
                if reminder_time <= now < (reminder_time + timedelta(minutes=1)):
                    notification.notify(
                        title=f"Class in 30 Mins!",
                        message=f"{student_name}: {subject} at {t_str}",
                        app_name="Tuition Manager",
                        timeout=10
                    )
                    toast(f"Reminder: {student_name} in 30 mins")
                    
            except Exception as e:
                print(f"Reminder Error: {e}")
                
    except Exception as e:
        print(f"DB Error in Reminders: {e}")

# --- CUSTOM WIDGETS ---
class DayTimeRow(MDBoxLayout):
    def __init__(self, day_text, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.adaptive_height = True
        self.spacing = dp(5)
        self.padding = [0, dp(2), 0, dp(2)]
        
        self.chk = MDCheckbox(size_hint=(None, None), size=(dp(30), dp(30)))
        self.chk.bind(active=self.on_checkbox_active)
        self.add_widget(self.chk)
        
        self.lbl = MDLabel(text=day_text, size_hint_x=None, width=dp(40), bold=True, font_style="Caption", theme_text_color="Primary")
        self.add_widget(self.lbl)
        
        self.time_field = MDTextField(hint_text="Time (e.g. 4:00 PM)", disabled=True, mode="line", font_size=dp(14))
        self.add_widget(self.time_field)
        self.day_name = day_text

    def on_checkbox_active(self, checkbox, value):
        self.time_field.disabled = not value

class SubjectSection(MDCard):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.adaptive_height = True 
        self.padding = dp(15)
        self.spacing = dp(10)
        self.elevation = 1
        self.radius = [12]
        
        self.subject_field = MDTextField(hint_text="Subject Name", mode="rectangle")
        self.add_widget(self.subject_field)
        
        self.add_widget(MDLabel(text="Select Days & Times:", font_style="Caption", size_hint_y=None, height=dp(20), theme_text_color="Secondary"))
        
        self.days_layout = MDBoxLayout(orientation='vertical', spacing=dp(5), adaptive_height=True)
        self.day_rows = []
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in days:
            row = DayTimeRow(day)
            self.days_layout.add_widget(row)
            self.day_rows.append(row)
        self.add_widget(self.days_layout)

# --- SCREEN 1: LIST SCREEN ---
class StudentListScreen(MDScreen):
    def on_enter(self):
        self.load_students()

    def load_students(self):
        self.ids.container.clear_widgets()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, name, photo_path FROM students")
        rows = c.fetchall()
        conn.close()

        for r in rows:
            sid, name, photo = r[0], r[1], r[2]
            
            item = TwoLineAvatarIconListItem(
                text=name,
                secondary_text="Tap for details",
                on_release=lambda x, s=sid, n=name: self.open_detail(s, n),
                bg_color=(1, 1, 1, 1)
            )
            
            # Load Photo safely
            if photo and os.path.exists(photo):
                avatar = ImageLeftWidget(source=photo)
            else:
                avatar = ImageLeftWidget(source="data/logo/kivy-icon-256.png")
            
            item.add_widget(avatar)
            
            icon = IconRightWidget(icon="trash-can-outline", theme_text_color="Error", on_release=lambda x, s=sid: self.delete_student(s))
            item.add_widget(icon)
            self.ids.container.add_widget(item)

    def open_detail(self, sid, name):
        app = MDApp.get_running_app()
        app.current_student_id = sid
        app.current_student_name = name
        self.manager.current = 'detail'

    def delete_student(self, sid):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM students WHERE id=?", (sid,))
        c.execute("DELETE FROM schedules WHERE student_id=?", (sid,))
        c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
        c.execute("DELETE FROM fee_history WHERE student_id=?", (sid,))
        conn.commit()
        conn.close()
        self.load_students()
        toast("Deleted")

# --- SCREEN 2: ADD / EDIT SCREEN ---
class AddEditScreen(MDScreen):
    mode = "add"
    student_id = None
    selected_photo_path = ""
    file_manager = None
    
    def on_enter(self):
        self.ids.subjects_container.clear_widgets()
        self.ids.name_field.text = ""
        self.ids.fee_field.text = ""
        self.ids.lbl_photo.text = "No photo selected"
        self.selected_photo_path = ""
        
        # Init File Manager
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path,
            preview=False, # Preview disabled to prevent Pydroid crashes
            ext=[".png", ".jpg", ".jpeg"] 
        )

        if self.mode == "add":
            self.add_subject_block()
        elif self.mode == "edit":
            self.load_existing_data()

    def open_file_manager(self):
        # Open Pydroid storage root
        path = "/storage/emulated/0/"
        if not os.path.exists(path):
            path = "." 
        self.file_manager.show(path)

    def select_path(self, path):
        # Copy file to app folder so we don't lose access
        try:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            dest_dir = os.path.join(app_dir, "student_photos")
            if not os.path.exists(dest_dir): os.makedirs(dest_dir)
            
            filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            dest_path = os.path.join(dest_dir, filename)
            
            copyfile(path, dest_path)
            self.selected_photo_path = dest_path
            self.ids.lbl_photo.text = "Photo Selected"
            toast("Photo Saved")
        except Exception as e:
            self.selected_photo_path = path # Fallback
            self.ids.lbl_photo.text = "Photo Selected (Linked)"
            
        self.exit_manager()

    def exit_manager(self, *args):
        self.file_manager.close()

    def add_subject_block(self):
        if len(self.ids.subjects_container.children) >= 4:
            toast("Max 4 subjects allowed")
            return
        block = SubjectSection()
        self.ids.subjects_container.add_widget(block)

    def load_existing_data(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, fee_amount, photo_path FROM students WHERE id=?", (self.student_id,))
        res = c.fetchone()
        if res: 
            self.ids.name_field.text = res[0]
            self.ids.fee_field.text = res[1] if res[1] else ""
            if res[2]:
                self.selected_photo_path = res[2]
                self.ids.lbl_photo.text = "Photo Selected"
        
        c.execute("SELECT subject, day_name, class_time FROM schedules WHERE student_id=?", (self.student_id,))
        rows = c.fetchall()
        conn.close()
        
        subject_data = {}
        order_list = [] 
        for r in rows:
            sub, day, time = r[0], r[1], r[2]
            if sub not in subject_data:
                subject_data[sub] = {}
                order_list.append(sub)
            subject_data[sub][day] = time
            
        for sub_name in order_list:
            block = SubjectSection()
            block.subject_field.text = sub_name
            schedule_map = subject_data[sub_name]
            for row_widget in block.day_rows:
                if row_widget.day_name in schedule_map:
                    row_widget.chk.active = True
                    row_widget.time_field.text = schedule_map[row_widget.day_name]
            self.ids.subjects_container.add_widget(block)
        if not order_list: self.add_subject_block()

    def save_data(self):
        name = self.ids.name_field.text
        fee = self.ids.fee_field.text
        if not name:
            toast("Name Required")
            return
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        if self.mode == "add":
            c.execute("INSERT INTO students (name, fee_amount, photo_path) VALUES (?, ?, ?)", 
                      (name, fee, self.selected_photo_path))
            sid = c.lastrowid
        else:
            sid = self.student_id
            c.execute("UPDATE students SET name=?, fee_amount=?, photo_path=? WHERE id=?", 
                      (name, fee, self.selected_photo_path, sid))
            c.execute("DELETE FROM schedules WHERE student_id=?", (sid,))

        blocks = reversed(self.ids.subjects_container.children) 
        for block in blocks:
            subject = block.subject_field.text
            if subject:
                for row in block.day_rows:
                    if row.chk.active:
                        day = row.day_name
                        time = row.time_field.text
                        if not time: time = "TBD"
                        c.execute("INSERT INTO schedules (student_id, subject, day_name, class_time) VALUES (?,?,?,?)",
                                  (sid, subject, day, time))
        conn.commit()
        conn.close()
        self.manager.current = 'list'

    def cancel(self):
        self.manager.current = 'list'

# --- SCREEN 3: DETAIL, ATTENDANCE & HISTORY ---
class DetailScreen(MDScreen):
    dialog = None
    student_fee_amount = "0"
    
    def on_enter(self):
        app = MDApp.get_running_app()
        self.sid = app.current_student_id
        self.refresh_screen()

    def refresh_screen(self):
        self.load_basics()
        self.load_schedule_list()
        self.build_smart_calendar()

    def load_basics(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, fee_amount FROM students WHERE id=?", (self.sid,))
        res = c.fetchone()
        
        name = res[0]
        self.student_fee_amount = res[1] if res and res[1] else "0"
        
        curr_month = datetime.now().strftime("%Y-%m")
        c.execute("SELECT is_paid FROM fee_history WHERE student_id=? AND month_str=?", (self.sid, curr_month))
        paid_res = c.fetchone()
        is_paid = True if (paid_res and paid_res[0] == 1) else False
        
        self.ids.chk_fee.active = is_paid
        self.update_due_display(is_paid)
        self.ids.lbl_student_name.text = name
        conn.close()

    def update_due_display(self, is_paid):
        if is_paid:
            self.ids.lbl_main_fee.text = "DUE: 0"
            self.ids.lbl_main_fee.text_color = (0, 0.7, 0, 1)
        else:
            self.ids.lbl_main_fee.text = f"DUE: {self.student_fee_amount}"
            self.ids.lbl_main_fee.text_color = (0.8, 0.2, 0.2, 1)

    def toggle_fee_status(self, is_active):
        curr_month = datetime.now().strftime("%Y-%m")
        val = 1 if is_active else 0
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO fee_history (student_id, month_str, is_paid) VALUES (?, ?, ?)",
                  (self.sid, curr_month, val))
        conn.commit()
        conn.close()
        self.update_due_display(is_active)

    def show_history(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT month_str, is_paid FROM fee_history WHERE student_id=? ORDER BY month_str DESC", (self.sid,))
        fees = c.fetchall()
        
        msg = "PAYMENT HISTORY:\n"
        if not fees: msg += "No records.\n"
        for f in fees:
            status = "✅ PAID" if f[1] else "❌ DUE"
            msg += f"{f[0]}: {status}\n"
            
        conn.close()
        self.dialog = MDDialog(title="History", text=msg, buttons=[MDFlatButton(text="OK", on_release=lambda x: self.dialog.dismiss())])
        self.dialog.open()

    def load_schedule_list(self):
        self.ids.schedule_list.clear_widgets()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT subject, day_name, class_time FROM schedules WHERE student_id=?", (self.sid,))
        rows = c.fetchall()
        conn.close()
        
        day_map = { "Mon": [], "Tue": [], "Wed": [], "Thu": [], "Fri": [], "Sat": [], "Sun": [] }
        for r in rows:
            if r[1] in day_map: day_map[r[1]].append((r[0], r[2]))

        self.active_days = set()
        days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in days_order:
            classes = day_map[day]
            if classes:
                self.active_days.add(day)
                if len(classes) == 1:
                    sub, time = classes[0]
                    self.ids.schedule_list.add_widget(ThreeLineListItem(text=f"{sub} | {day} @ {time}"))
                else:
                    combined = " | ".join([f"{c[0]} @ {c[1]}" for c in classes])
                    self.ids.schedule_list.add_widget(ThreeLineListItem(text=f"{day} : {combined}"))

    # --- SMART CALENDAR ---
    def build_smart_calendar(self):
        grid = self.ids.cal_grid
        grid.clear_widgets()
        now = datetime.now()
        month_days = calendar.monthrange(now.year, now.month)[1]
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT date_str, status FROM attendance WHERE student_id=?", (self.sid,))
        logs = {row[0]: row[1] for row in c.fetchall()} 
        conn.close()

        total, completed, due_list = 0, 0, []

        for d in range(1, month_days + 1):
            curr_date = date(now.year, now.month, d)
            date_str = curr_date.strftime("%Y-%m-%d")
            day_name = curr_date.strftime("%a")
            
            show_button = False
            bg_col = (0,0,0,0)
            txt_col = (0,0,0,1)
            
            if day_name in self.active_days:
                show_button = True
                total += 1
                status = logs.get(date_str)
                
                if status == 'done':
                    bg_col = (0, 0.7, 0, 1) # Green
                    txt_col = (1,1,1,1)
                    completed += 1
                elif status == 'missed':
                    bg_col = (0.9, 0, 0, 1) # Red
                    txt_col = (1,1,1,1)
                    due_list.append(date_str)
                else:
                    if curr_date < date.today():
                        bg_col = (0.9, 0, 0, 1)
                        txt_col = (1,1,1,1)
                        due_list.append(date_str)
                    else:
                        bg_col = (0.2, 0.5, 0.8, 1)
                        txt_col = (1,1,1,1)

            elif date_str in logs and logs[date_str] == 'missed':
                show_button = True
                bg_col = (0.9, 0, 0, 1)
                txt_col = (1,1,1,1)
                due_list.append(date_str)

            if show_button:
                btn_text = f"{d}\n{day_name}" 
                btn = MDFlatButton(
                    text=btn_text, 
                    theme_text_color="Custom", 
                    text_color=txt_col, 
                    md_bg_color=bg_col,
                    size_hint=(None, None), 
                    size=(dp(50), dp(50)), 
                    padding=(0,0),
                    font_size=sp(11),
                    pos_hint={'center_x': 0.5, 'center_y': 0.5},
                    on_release=lambda x, ds=date_str: self.show_attendance_dialog(ds)
                )
                grid.add_widget(btn)

        remaining = total - completed
        self.ids.lbl_stats.text = f"Total: {total}  |  Done: {completed}  |  Left: {remaining}"
        
        if due_list:
            formatted_due = ", ".join([d.split("-")[2] for d in due_list])
            self.ids.lbl_due.text = f"MISSED: {formatted_due}"
        else:
            self.ids.lbl_due.text = ""

    def show_attendance_dialog(self, date_str):
        self.dialog = MDDialog(
            title=f"Class: {date_str}",
            buttons=[
                MDFlatButton(text="MISSED", theme_text_color="Error", on_release=lambda x: self.update_attendance(date_str, 'missed')),
                MDFlatButton(text="TAKEN", theme_text_color="Custom", text_color=(0,0.7,0,1), on_release=lambda x: self.update_attendance(date_str, 'done')),
            ],
        )
        self.dialog.open()

    def update_attendance(self, date_str, status):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO attendance (student_id, date_str, status) VALUES (?, ?, ?)",
                  (self.sid, date_str, status))
        conn.commit()
        conn.close()
        self.dialog.dismiss()
        self.refresh_screen()

    def go_edit(self):
        app = MDApp.get_running_app()
        screen = self.manager.get_screen('add_edit')
        screen.mode = "edit"
        screen.student_id = self.sid
        self.manager.current = 'add_edit'

    def go_back(self):
        self.manager.current = 'list'

# --- MAIN APP CLASS ---
class TuitionManagerApp(MDApp):
    current_student_id = None
    current_student_name = ""

    def build(self):
        self.theme_cls.primary_palette = "BlueGray" 
        self.theme_cls.accent_palette = "Teal"
        self.theme_cls.theme_style = "Light"
        init_db()
        
        # Start Reminder Check Loop (Every 60 Seconds)
        Clock.schedule_interval(lambda dt: schedule_class_reminders(), 60)
        
        sm = MDScreenManager()

        # 1. LIST SCREEN
        list_scr = StudentListScreen(name='list')
        layout = MDBoxLayout(orientation='vertical')
        
        header_card = MDCard(size_hint_y=None, height=dp(60), elevation=2, md_bg_color=self.theme_cls.primary_color)
        header_lbl = MDLabel(text="Tuition Manager", halign="center", font_style="H5", theme_text_color="Custom", text_color=(1,1,1,1), bold=True)
        header_card.add_widget(header_lbl)
        layout.add_widget(header_card)
        
        scroll = MDScrollView()
        ls = MDList(id="container", spacing=dp(5), padding=dp(10))
        list_scr.ids["container"] = ls
        scroll.add_widget(ls)
        layout.add_widget(scroll)
        
        fab = MDFloatingActionButton(icon="plus", pos_hint={'right': 0.95, 'y': 0.05}, on_release=lambda x: self.switch_to_add(sm))
        list_scr.add_widget(layout)
        list_scr.add_widget(fab)
        sm.add_widget(list_scr)

        # 2. ADD/EDIT SCREEN
        ae_scr = AddEditScreen(name='add_edit')
        ae_layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        
        ae_layout.add_widget(MDLabel(text="Student Profile", font_style="H5", size_hint_y=None, height=dp(30), bold=True, theme_text_color="Primary"))
        
        ae_layout.add_widget(MDTextField(id="name_field", hint_text="Full Name", mode="rectangle"))
        ae_layout.add_widget(MDTextField(id="fee_field", hint_text="Monthly Fees (e.g. 500)", mode="rectangle", input_filter="int"))
        
        photo_box = MDBoxLayout(adaptive_height=True, spacing=dp(10))
        photo_box.add_widget(MDIconButton(icon="image-search", on_release=lambda x: ae_scr.open_file_manager()))
        photo_lbl = MDLabel(id="lbl_photo", text="Select Profile Photo", theme_text_color="Hint", valign="center")
        ae_scr.ids["lbl_photo"] = photo_lbl
        photo_box.add_widget(photo_lbl)
        ae_layout.add_widget(photo_box)

        ae_layout.add_widget(MDLabel(text="Schedule (e.g. 4:00 PM)", font_style="H6", size_hint_y=None, height=dp(25)))
        sub_scroll = MDScrollView()
        sub_cont = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(10), padding=[0,0,0,20])
        ae_scr.ids["subjects_container"] = sub_cont
        sub_scroll.add_widget(sub_cont)
        ae_layout.add_widget(sub_scroll)
        
        plus_box = MDBoxLayout(adaptive_height=True)
        # SAFE BUTTON COLOR
        plus_box.add_widget(MDFlatButton(text="+ Add Subject", theme_text_color="Custom", text_color=(0, 0.5, 0.5, 1), on_release=lambda x: ae_scr.add_subject_block()))
        ae_layout.add_widget(plus_box)
        
        btns = MDBoxLayout(adaptive_height=True, spacing=dp(10))
        btns.add_widget(MDRaisedButton(text="SAVE PROFILE", size_hint_x=1, on_release=lambda x: ae_scr.save_data()))
        btns.add_widget(MDRectangleFlatButton(text="CANCEL", on_release=lambda x: ae_scr.cancel()))
        ae_layout.add_widget(btns)
        
        ae_scr.ids["name_field"] = ae_layout.children[6]
        ae_scr.ids["fee_field"] = ae_layout.children[5]
        
        ae_scr.add_widget(ae_layout)
        sm.add_widget(ae_scr)

        # 3. DETAIL SCREEN
        det_scr = DetailScreen(name='detail')
        d_layout = MDBoxLayout(orientation='vertical', padding=dp(0), spacing=dp(10))
        
        # --- Top Card ---
        top_card = MDCard(orientation="vertical", size_hint_y=None, height=dp(150), elevation=2, md_bg_color=self.theme_cls.primary_color, padding=dp(20))
        
        det_scr.ids["lbl_main_fee"] = MDLabel(text="DUE: 0", halign="center", font_style="H4", theme_text_color="Custom", text_color=(1,1,1,1), bold=True)
        top_card.add_widget(det_scr.ids["lbl_main_fee"])
        
        det_scr.ids["lbl_student_name"] = MDLabel(text="Student Name", halign="center", theme_text_color="Custom", text_color=(0.9,0.9,0.9,1), font_style="Subtitle1")
        top_card.add_widget(det_scr.ids["lbl_student_name"])

        pay_box = MDBoxLayout(adaptive_height=True, spacing=dp(10), padding=[0, dp(10), 0, 0], pos_hint={'center_x': 0.5})
        pay_box.add_widget(MDLabel(text="Mark Paid:", halign="right", theme_text_color="Custom", text_color=(1,1,1,1), size_hint_x=None, width=dp(80)))
        det_scr.ids["chk_fee"] = MDCheckbox(size_hint=(None, None), size=(dp(35), dp(35)), color_active=(1,1,1,1), color_inactive=(1,1,1,0.5))
        det_scr.ids["chk_fee"].bind(active=lambda x, val: det_scr.toggle_fee_status(val))
        pay_box.add_widget(det_scr.ids["chk_fee"])
        top_card.add_widget(pay_box)
        d_layout.add_widget(top_card)

        # Actions
        act_box = MDBoxLayout(adaptive_height=True, spacing=dp(20), padding=[dp(20), 0, dp(20), 0], pos_hint={'center_x': 0.5})
        act_box.add_widget(MDRoundFlatButton(text="HISTORY", icon="history", on_release=lambda x: det_scr.show_history()))
        act_box.add_widget(MDRoundFlatButton(text="EDIT", icon="pencil", on_release=lambda x: det_scr.go_edit()))
        d_layout.add_widget(act_box)

        # --- SMART CALENDAR CARD (ADAPTIVE) ---
        cal_card = MDCard(
            orientation="vertical", 
            size_hint_y=None, 
            adaptive_height=True, # Fixed: Grows to fit buttons
            padding=dp(8), 
            size_hint_x=0.92,
            pos_hint={'center_x': 0.5},
            elevation=1
        )
        cal_card.add_widget(MDLabel(text="Attendance (This Month)", bold=True, size_hint_y=None, height=dp(20), halign="center"))
        
        # 5 cols for clear, readable buttons
        det_scr.ids["cal_grid"] = MDGridLayout(cols=5, adaptive_height=True, spacing=dp(5), pos_hint={'center_x': 0.5})
        cal_card.add_widget(det_scr.ids["cal_grid"])
        
        det_scr.ids["lbl_stats"] = MDLabel(text="Loading...", halign="center", font_style="Caption", size_hint_y=None, height=dp(20))
        cal_card.add_widget(det_scr.ids["lbl_stats"])
        
        det_scr.ids["lbl_due"] = MDLabel(text="", halign="center", font_style="Caption", theme_text_color="Error", size_hint_y=None, height=dp(20))
        cal_card.add_widget(det_scr.ids["lbl_due"])
        
        d_layout.add_widget(cal_card)
        
        # Schedule Bottom
        sch_list = MDList(id="schedule_list")
        det_scr.ids["schedule_list"] = sch_list
        d_layout.add_widget(MDScrollView(size_hint_y=1, bar_width=0))
        d_layout.children[0].add_widget(sch_list)

        d_layout.add_widget(MDIconButton(icon="arrow-left", pos_hint={'center_x': 0.1}, on_release=lambda x: det_scr.go_back()))

        det_scr.add_widget(d_layout)
        sm.add_widget(det_scr)

        return sm

    def switch_to_add(self, sm):
        # THIS IS THE FUNCTION THAT WAS MISSING
        screen = sm.get_screen('add_edit')
        screen.mode = "add"
        screen.ids.name_field.text = "" 
        sm.current = 'add_edit'

if __name__ == "__main__":
    TuitionManagerApp().run()