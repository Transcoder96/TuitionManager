import sqlite3
import calendar
import os
from datetime import datetime, date, timedelta
from shutil import copyfile

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconRightWidget, ThreeLineListItem, ImageLeftWidget
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.button import MDRaisedButton, MDFloatingActionButton, MDIconButton, MDRoundFlatButton, MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.toast import toast
from kivy.metrics import dp, sp
from kivy.utils import platform
from kivy.clock import Clock

# --- PERMISSIONS & NOTIFICATIONS ---
if platform == "android":
    try:
        from android.permissions import request_permissions, Permission
        from plyer import notification
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE, 
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.POST_NOTIFICATIONS, 
            Permission.SCHEDULE_EXACT_ALARM 
        ])
    except Exception:
        notification = None
else:
    try:
        from plyer import notification
    except:
        notification = None

DB_NAME = 'tuition_final_v21.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, photo_path TEXT, fee_amount TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY, student_id INTEGER, subject TEXT, day_name TEXT, class_time TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS attendance (student_id INTEGER, date_str TEXT, status TEXT, UNIQUE(student_id, date_str))")
    c.execute("CREATE TABLE IF NOT EXISTS fee_history (student_id INTEGER, month_str TEXT, is_paid INTEGER, UNIQUE(student_id, month_str))")
    conn.commit()
    conn.close()

def schedule_class_reminders(*args):
    if not notification: return
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        now = datetime.now()
        current_day = now.strftime("%a")
        c.execute("""SELECT s.name, sch.subject, sch.class_time FROM schedules sch JOIN students s ON sch.student_id = s.id WHERE sch.day_name = ?""", (current_day,))
        classes = c.fetchall()
        conn.close()
        
        for name, subject, time_str in classes:
            try:
                t_str = time_str.strip().upper()
                try: class_dt = datetime.strptime(t_str, "%I:%M %p")
                except: class_dt = datetime.strptime(t_str, "%H:%M")
                
                class_full = datetime.combine(now.date(), class_dt.time())
                reminder = class_full - timedelta(minutes=30)
                
                if reminder <= now < (reminder + timedelta(minutes=1)):
                    notification.notify(title="Class in 30 Mins!", message=f"{name}: {subject} at {t_str}", app_name="Tuition Manager", timeout=10)
            except: pass
    except: pass

class DayTimeRow(MDBoxLayout):
    def __init__(self, day_text, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.adaptive_height = True
        self.spacing = dp(5)
        self.chk = MDCheckbox(size_hint=(None, None), size=(dp(30), dp(30)))
        self.chk.bind(active=self.on_checkbox_active)
        self.add_widget(self.chk)
        self.add_widget(MDLabel(text=day_text, size_hint_x=None, width=dp(40), bold=True))
        self.time_field = MDTextField(hint_text="Time (4:00 PM)", disabled=True)
        self.add_widget(self.time_field)
        self.day_name = day_text
    def on_checkbox_active(self, checkbox, value): self.time_field.disabled = not value

class SubjectSection(MDCard):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.adaptive_height = True 
        self.padding = dp(15)
        self.spacing = dp(10)
        self.elevation = 1
        self.radius = [12]
        self.subject_field = MDTextField(hint_text="Subject Name")
        self.add_widget(self.subject_field)
        self.add_widget(MDLabel(text="Select Days:", font_style="Caption"))
        self.days_layout = MDBoxLayout(orientation='vertical', adaptive_height=True)
        self.day_rows = []
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            row = DayTimeRow(day)
            self.days_layout.add_widget(row)
            self.day_rows.append(row)
        self.add_widget(self.days_layout)

class StudentListScreen(MDScreen):
    def on_enter(self): self.load_students()
    def load_students(self):
        self.ids.container.clear_widgets()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, name, photo_path FROM students")
        for r in c.fetchall():
            item = TwoLineAvatarIconListItem(text=r[1], secondary_text="Tap for details", on_release=lambda x, s=r[0]: self.open_detail(s))
            if r[2] and os.path.exists(r[2]): item.add_widget(ImageLeftWidget(source=r[2]))
            else: item.add_widget(ImageLeftWidget(source="data/logo/kivy-icon-256.png"))
            item.add_widget(IconRightWidget(icon="trash-can", on_release=lambda x, s=r[0]: self.delete_student(s)))
            self.ids.container.add_widget(item)
        conn.close()
    def open_detail(self, sid):
        app = MDApp.get_running_app()
        app.current_student_id = sid
        self.manager.current = 'detail'
    def delete_student(self, sid):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM students WHERE id=?", (sid,))
        conn.commit()
        conn.close()
        self.load_students()

class AddEditScreen(MDScreen):
    mode = "add"
    student_id = None
    selected_photo_path = ""
    def on_enter(self):
        self.ids.subjects_container.clear_widgets()
        self.ids.name_field.text = ""
        self.ids.fee_field.text = ""
        self.file_manager = MDFileManager(exit_manager=self.exit_manager, select_path=self.select_path)
        if self.mode == "add": self.add_subject_block()
    def open_file_manager(self):
        path = "/storage/emulated/0/" if platform == "android" else "."
        self.file_manager.show(path)
    def select_path(self, path):
        self.exit_manager()
        try:
            dest = os.path.join(os.path.dirname(__file__), f"photo_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
            copyfile(path, dest)
            self.selected_photo_path = dest
            toast("Photo Selected")
        except: pass
    def exit_manager(self, *args): self.file_manager.close()
    def add_subject_block(self):
        if len(self.ids.subjects_container.children) < 4:
            self.ids.subjects_container.add_widget(SubjectSection())
    def save_data(self):
        name = self.ids.name_field.text
        if not name: return
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        if self.mode == "add":
            c.execute("INSERT INTO students (name, fee_amount, photo_path) VALUES (?,?,?)", (name, self.ids.fee_field.text, self.selected_photo_path))
            sid = c.lastrowid
        else:
            sid = self.student_id
            c.execute("UPDATE students SET name=?, fee_amount=?, photo_path=? WHERE id=?", (name, self.ids.fee_field.text, self.selected_photo_path, sid))
            c.execute("DELETE FROM schedules WHERE student_id=?", (sid,))
        
        # Save schedules
        # Note: We reverse children because Kivy adds to index 0 by default
        for block in reversed(self.ids.subjects_container.children):
            if block.subject_field.text:
                for row in block.day_rows:
                    if row.chk.active:
                        c.execute("INSERT INTO schedules (student_id, subject, day_name, class_time) VALUES (?,?,?,?)", 
                                  (sid, block.subject_field.text, row.day_name, row.time_field.text))
        conn.commit()
        conn.close()
        self.manager.current = 'list'
    def cancel(self): self.manager.current = 'list'

class DetailScreen(MDScreen):
    def on_enter(self):
        app = MDApp.get_running_app()
        self.sid = app.current_student_id
        self.load_data()
    def load_data(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name, fee_amount FROM students WHERE id=?", (self.sid,))
        res = c.fetchone()
        self.ids.lbl_name.text = res[0]
        self.ids.lbl_fee.text = f"DUE: {res[1]}"
        
        # Schedule
        self.ids.schedule_list.clear_widgets()
        c.execute("SELECT subject, day_name, class_time FROM schedules WHERE student_id=?", (self.sid,))
        rows = c.fetchall()
        self.active_days = [r[1] for r in rows]
        for r in rows:
            self.ids.schedule_list.add_widget(ThreeLineListItem(text=f"{r[0]} | {r[1]} @ {r[2]}"))
            
        # Smart Calendar
        self.ids.cal_grid.clear_widgets()
        c.execute("SELECT date_str, status FROM attendance WHERE student_id=?", (self.sid,))
        logs = {r[0]:r[1] for r in c.fetchall()}
        
        now = datetime.now()
        month_days = calendar.monthrange(now.year, now.month)[1]
        
        # Only create buttons for relevant days (Classes + Missed)
        for d in range(1, month_days + 1):
            d_date = date(now.year, now.month, d)
            d_str = d_date.strftime("%Y-%m-%d")
            d_name = d_date.strftime("%a")
            
            show = False
            bg = (0,0,0,0)
            txt = (0,0,0,1)
            
            if d_name in self.active_days:
                show = True
                if logs.get(d_str) == 'done': bg = (0, 0.8, 0, 1); txt=(1,1,1,1)
                elif logs.get(d_str) == 'missed': bg = (1, 0, 0, 1); txt=(1,1,1,1)
                elif d_date < date.today(): bg = (1, 0, 0, 1); txt=(1,1,1,1) # Auto Missed
                else: bg = (0.2, 0.6, 1, 1); txt=(1,1,1,1) # Future
            elif logs.get(d_str) == 'missed':
                show = True
                bg = (1, 0, 0, 1); txt=(1,1,1,1)

            if show:
                btn = MDFlatButton(text=f"{d}\n{d_name}", theme_text_color="Custom", text_color=txt, md_bg_color=bg, 
                                   size_hint=(None, None), size=(dp(45), dp(45)), on_release=lambda x, ds=d_str: self.mark_att(ds))
                self.ids.cal_grid.add_widget(btn)
        conn.close()

    def mark_att(self, date_str):
        self.dialog = MDDialog(title=f"Class: {date_str}", buttons=[
            MDFlatButton(text="MISSED", on_release=lambda x: self.save_att(date_str, 'missed')),
            MDFlatButton(text="TAKEN", on_release=lambda x: self.save_att(date_str, 'done'))
        ])
        self.dialog.open()
    def save_att(self, date_str, status):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT OR REPLACE INTO attendance VALUES (?,?,?)", (self.sid, date_str, status))
        conn.commit()
        conn.close()
        self.dialog.dismiss()
        self.load_data()
    def go_back(self): self.manager.current = 'list'

class TuitionManagerApp(MDApp):
    current_student_id = None
    def build(self):
        self.theme_cls.primary_palette = "BlueGray"
        init_db()
        Clock.schedule_interval(lambda dt: schedule_class_reminders(), 60)
        
        sm = MDScreenManager()
        
        # List Screen
        ls_scr = StudentListScreen(name='list')
        layout = MDBoxLayout(orientation='vertical')
        layout.add_widget(MDCard(MDLabel(text="Tuition Manager", halign="center", font_style="H5", theme_text_color="Custom", text_color=(1,1,1,1)), size_hint_y=None, height=dp(60), md_bg_color=self.theme_cls.primary_color))
        scroll = MDScrollView()
        ls = MDList(id="container")
        ls_scr.ids["container"] = ls
        scroll.add_widget(ls)
        layout.add_widget(scroll)
        ls_scr.add_widget(layout)
        ls_scr.add_widget(MDFloatingActionButton(icon="plus", pos_hint={'right': 0.95, 'y': 0.05}, on_release=lambda x: self.switch_add(sm)))
        sm.add_widget(ls_scr)
        
        # Add Screen
        add_scr = AddEditScreen(name='add_edit')
        add_layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        add_layout.add_widget(MDLabel(text="Student Profile", font_style="H5", size_hint_y=None, height=dp(30)))
        add_layout.add_widget(MDTextField(id="name_field", hint_text="Name"))
        add_layout.add_widget(MDTextField(id="fee_field", hint_text="Fees"))
        add_layout.add_widget(MDRoundFlatButton(text="Select Photo", on_release=lambda x: add_scr.open_file_manager()))
        add_scr.ids["lbl_photo"] = MDLabel(text="No photo", size_hint_y=None, height=dp(20))
        add_layout.add_widget(add_scr.ids["lbl_photo"])
        
        sub_scroll = MDScrollView()
        sub_cont = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(10))
        add_scr.ids["subjects_container"] = sub_cont
        sub_scroll.add_widget(sub_cont)
        add_layout.add_widget(sub_scroll)
        
        add_layout.add_widget(MDFlatButton(text="+ Add Subject", on_release=lambda x: add_scr.add_subject_block()))
        add_layout.add_widget(MDRaisedButton(text="SAVE", on_release=lambda x: add_scr.save_data()))
        add_layout.add_widget(MDRectangleFlatButton(text="CANCEL", on_release=lambda x: add_scr.cancel()))
        
        # Register IDs manually for safety
        add_scr.ids["name_field"] = add_layout.children[6]
        add_scr.ids["fee_field"] = add_layout.children[5]
        
        add_scr.add_widget(add_layout)
        sm.add_widget(add_scr)
        
        # Detail Screen
        det_scr = DetailScreen(name='detail')
        det_layout = MDBoxLayout(orientation='vertical')
        det_layout.add_widget(MDCard(MDLabel(id="lbl_name", text="Name", halign="center", font_style="H5", theme_text_color="Custom", text_color=(1,1,1,1)), size_hint_y=None, height=dp(80), md_bg_color=self.theme_cls.primary_color))
        det_scr.ids["lbl_name"] = det_layout.children[0].children[0]
        
        det_layout.add_widget(MDLabel(id="lbl_fee", text="DUE: 0", halign="center", font_style="H6", size_hint_y=None, height=dp(40)))
        det_scr.ids["lbl_fee"] = det_layout.children[0]
        
        # Scrollable Calendar Container
        cal_scroll = MDScrollView(size_hint_y=0.4)
        det_scr.ids["cal_grid"] = MDGridLayout(cols=5, adaptive_height=True, spacing=dp(5), padding=dp(10), pos_hint={'center_x': 0.5})
        cal_scroll.add_widget(det_scr.ids["cal_grid"])
        det_layout.add_widget(cal_scroll)
        
        sch_scroll = MDScrollView()
        sch_list = MDList(id="schedule_list")
        det_scr.ids["schedule_list"] = sch_list
        sch_scroll.add_widget(sch_list)
        det_layout.add_widget(sch_scroll)
        
        det_layout.add_widget(MDRaisedButton(text="BACK", on_release=lambda x: det_scr.go_back(), pos_hint={'center_x': 0.5}))
        det_scr.add_widget(det_layout)
        sm.add_widget(det_scr)
        
        return sm

    def switch_add(self, sm):
        sm.current = 'add_edit'
        sm.get_screen('add_edit').mode = 'add'

if __name__ == "__main__":
    TuitionManagerApp().run()
