import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import pdfplumber
import re
from datetime import datetime
import dateparser
import os

# --- AYARLAR ---
DB_FILE = "insurance_lite.db"
COMPANY_LIST = ["Ankara", "Mapfre", "AXA", "Anaaadolu", "Ray", "Allianz", "Sompo", "Türkiye Sigorta", "Diğer"]

# --- VERİTABANI İŞLEMLERİ ---
def get_db_connection():
    return sqlite3.connect(DB_FILE)

def setup_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            tc_no TEXT,
            phone TEXT,
            license_no TEXT,
            plate TEXT,
            policy_no TEXT,
            company TEXT,
            insurance_type TEXT,
            policy_start DATE,
            policy_end DATE
        )
        ''')
        conn.commit()

def insert_customer(data):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO customers (full_name, tc_no, phone, license_no, plate, policy_no, 
            company, insurance_type, policy_start, policy_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()

def fetch_customers(filter_name=""):
    with get_db_connection() as conn:
        c = conn.cursor()
        if filter_name:
            c.execute("SELECT * FROM customers WHERE LOWER(full_name) LIKE ?", 
                      ('%'+filter_name.lower()+'%',))
        else:
            c.execute("SELECT * FROM customers")
        rows = c.fetchall()
    return rows

def delete_customer(customer_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        conn.commit()

def update_customer(customer_id, new_data):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE customers SET full_name=?, tc_no=?, phone=?, license_no=?, plate=?, policy_no=?,
            company=?, insurance_type=?, policy_start=?, policy_end=? WHERE id=?
        ''', (*new_data, customer_id))
        conn.commit()

# --- FORMATLAMA ---
def format_date_for_display(date_str):
    if not date_str: return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return date_str

def format_date_for_db(date_str):
    if not date_str: return ""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    parsed = dateparser.parse(date_str, languages=['tr'])
    return parsed.strftime("%Y-%m-%d") if parsed else ""

def validate_tc_no(tc_no):
    """TC Kimlik numarası - 11 haneli olmalı ve sadece rakamlardan oluşmalı"""
    if not tc_no:
        return True  # Boş TC'ye izin ver (opsiyonel alan)
    
    # Boşlukları ve yıldızları kaldır
    tc_clean = tc_no.replace(" ", "").replace("*", "")
    
    # 11 haneli olmalı ve sadece rakamlardan oluşmalı
    if len(tc_clean) != 11:
        return False
    
    if not tc_clean.isdigit():
        return False
    
    return True

# --- PDF PARSE ---
def parse_pdf_regex(file_path):
    full_text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if text:
                    full_text += text + "\n"
    except Exception as e:
        messagebox.showerror("Hata", f"PDF okunurken hata: {e}")
        return None

    tc_match = re.search(r"\b[1-9]\d{6}\s*(?:\*{4}|\d{4})\b", full_text)
    tc_no = tc_match.group(0) if tc_match else ""

    full_name = ""
    name_pattern = r"(?:ADI SOYADI\s*/\s*ÜNVANI|SİGORTA ETTİREN|ADI SOYADI|MÜŞTERİ)\s*[:]\s*([A-ZİĞÜŞÖÇ][A-ZİĞÜŞÖÇa-zçğıöşü\s]+)"
    name_match = re.search(name_pattern, full_text, re.IGNORECASE)
    if name_match:
        raw_name = name_match.group(1).strip()
        full_name = " ".join(raw_name.split())

    plate_match = re.search(r"\b\d{2}\s?[A-Z]{1,3}\s?\d{2,4}\b", full_text)
    plate = plate_match.group(0).replace(" ", "") if plate_match else ""

    policy_match = re.search(r"Poliçe\s*No\s*[:\s\-\.]+(\d+)", full_text, re.IGNORECASE)
    policy_no = policy_match.group(1) if policy_match else ""

    dates = re.findall(r"\d{2}[./]\d{2}[./]\d{4}", full_text)
    policy_start = format_date_for_db(dates[0]) if len(dates) >= 1 else ""
    policy_end = format_date_for_db(dates[1]) if len(dates) >= 2 else ""

    insurance_type = "Diğer"
    upper_text = full_text.upper()
    if "KASKO" in upper_text: insurance_type = "Kasko"
    elif "TRAFİK" in upper_text: insurance_type = "Trafik Sigortası"
    elif "DASK" in upper_text: insurance_type = "DASK"

    phone = ""
    license_no = ""
    company = "" 

    return [full_name, tc_no, phone, license_no, plate, policy_no, company, insurance_type, policy_start, policy_end]

# --- ARAYÜZ ---
class InsuranceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FRH Özkardesler Sigorta Müşteri Takip Sistemi")
        self.root.geometry("1500x900") 
        self.root.configure(bg="#FFFFFF")
        
        setup_db()
        self.columns = ("Ad Soyad", "TC", "Tel", "Ruhsat", "Plaka", 
                        "Poliçe No", "Şirket", "Sigorta Türü", "Başlangıç", "Bitiş")
        
        self.setup_styles()
        self.setup_ui()
        self.load_data()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # FONTLAR
        # Tablo içi için biraz daha kalın font (Semibold)
        font_table = ("Segoe UI Semibold", 18) 
        font_head = ("Segoe UI", 14, "bold")
        font_tab = ("Segoe UI", 40, "bold")
        
        style.configure("TFrame", background="#FF0E0E")
        style.configure("TLabel", background="#FFFFFF", foreground="#333333", font=("Segoe UI", 13))
        
        # --- TABLAR ---
        style.configure("TNotebook", background="#FFFFFF", borderwidth=0)
        style.configure("TNotebook.Tab", 
                        font=font_tab, 
                        padding=[30, 15], 
                        background="#F2F2F2", 
                        foreground="#7F8C8D")
        
        style.map("TNotebook.Tab", 
                  background=[("selected", "#3498DB")], 
                  foreground=[("selected", "white")])

        # --- TREEVIEW (Tablo Kalınlaştı) ---
        style.configure("Treeview", 
                        background="white",
                        foreground="#222222", 
                        rowheight=55, 
                        fieldbackground="white",
                        font=font_table, # Semibold kullanıldı
                        borderwidth=0)
        
        style.configure("Treeview.Heading", 
                        font=font_head, 
                        background="#ECF0F1", 
                        foreground="#2C3E50",
                        relief="flat")
        
        style.map("Treeview", background=[('selected', '#3498DB')])

        # --- BUTONLAR ---
        style.configure("TButton", 
                        font=("Segoe UI", 13, "bold"), 
                        padding=15, 
                        borderwidth=0,
                        background="#E0E0E0")
        
        style.map("TButton", 
                  background=[('active', '#3498DB'), ('!disabled', '#F0F0F0')],
                  foreground=[('active', 'white')])
        
        style.configure("Accent.TButton", background="#3498DB", foreground="white")
        style.map("Accent.TButton", background=[('active', '#2980B9')])

        # --- KIRMIZI SİL BUTONU İÇİN ÖZEL STİL ---
        style.configure("Danger.TButton", background="#E0E0E0", foreground="#C0392B") # Yazısı kırmızı başlar
        style.map("Danger.TButton", 
                  background=[('active', '#C0392B')], # Üzerine gelince ARKA PLAN Kırmızı
                  foreground=[('active', 'white')])   # Yazı Beyaz

    def setup_ui(self):
        # ÜST HEADER (Sadece Başlık)
        header_frame = tk.Frame(self.root, bg="white", pady=25, padx=40)
        header_frame.pack(fill='x')

        tk.Label(header_frame, text="MÜŞTERI TAKİP SİSTEMİ", font=("Segoe UI", 32, "bold"), bg="white", fg="#2C3E50").pack(side='left')

        # --- BUTON VE ARAMA PANELİ (BİRLEŞTİRİLDİ) ---
        # Gri bir şerit içinde hepsi
        btn_frame = tk.Frame(self.root, bg="#FAFAFA", pady=20, padx=40, height=100)
        btn_frame.pack(fill='x')
        
        # Butonlar (SOLDA) command=self.add_from_pdf).pack(side='left', padx=(0, 15))
        ttk.Button(btn_frame, text="+ PDF EKLE", style="Accent.TButton", command=self.edit_selected).pack(side='left', padx=15)
        # SİL butonu kırmızı stilini kullanıyor
        ttk.Button(btn_frame, text="DÜZENLE", command=self.add_from_pdf).pack(side='left', padx=(0, 15))
        # SİL butonu kırmızı stilini kullanıyor
        ttk.Button(btn_frame, text="SİL", style="Danger.TButton", command=self.delete_selected).pack(side='left', padx=15)

        # Arama Çubuğu (EN SAĞDA)
        # Sağ tarafa yaslamak için frame kullanıyoruz
        search_frame = tk.Frame(btn_frame, bg="#CE1818")
        search_frame.pack(side='right', anchor='center')

        tk.Label(search_frame, text="🔍", bg="#FAFAFA", font=("Segoe UI", 18)).pack(side='left', padx=(0,10))
        
        # Arama çubuğu genişletildi (width=40)
        self.entry_search = tk.Entry(search_frame, width=40, font=("Segoe UI", 15), 
                                     bd=2, relief="solid", fg="#333") 
        self.entry_search.config(highlightbackground="#BDC3C7", highlightcolor="#3498DB", highlightthickness=1)
        self.entry_search.pack(side='left', ipady=8)
        self.entry_search.bind("<KeyRelease>", lambda event: self.load_data(self.entry_search.get()))

        # TABLO ALANI
        main_content = tk.Frame(self.root, bg="white", padx=40, pady=20)
        main_content.pack(fill='both', expand=True)

        self.tab_control = ttk.Notebook(main_content)
        self.tab_control.pack(expand=1, fill='both')
        
        self.tab_guncel = ttk.Frame(self.tab_control)
        self.tab_yenileme = ttk.Frame(self.tab_control)
        self.tab_eski = ttk.Frame(self.tab_control)
        
        self.tab_control.add(self.tab_guncel, text='   Güncel Poliçeler   ')
        self.tab_control.add(self.tab_yenileme, text='   Yaklaşanlar (<30 Gün)   ')
        self.tab_control.add(self.tab_eski, text='   Süresi Bitenler   ')

        self.tree_guncel = self.create_tree(self.tab_guncel)
        self.tree_yenileme = self.create_tree(self.tab_yenileme)
        self.tree_eski = self.create_tree(self.tab_eski)

    def create_tree(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)

        tree = ttk.Treeview(frame, columns=self.columns, show='headings', selectmode="browse")
        
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        tree.pack(side='left', expand=True, fill='both')

        for col in self.columns:
            tree.heading(col, text=col, anchor="center")
            tree.column(col, anchor="center") 
            
            if col == "Ad Soyad": tree.column(col, width=280, anchor="center")
            elif col == "TC": tree.column(col, width=160, anchor="center")
            elif col == "Plaka": tree.column(col, width=130, anchor="center")
            elif col == "Şirket": tree.column(col, width=160, anchor="center")
            else: tree.column(col, width=140, anchor="center")
        
        tree.tag_configure('odd', background='white')
        tree.tag_configure('even', background='#F8F9F9')

        return tree

    def load_data(self, filter_name=""):
        for tree in [self.tree_guncel, self.tree_eski, self.tree_yenileme]:
            tree.delete(*tree.get_children())
            
        rows = fetch_customers(filter_name)
        today = datetime.today().date()
        
        for i, row in enumerate(rows):
            tag = 'even' if i % 2 == 0 else 'odd'

            p_start_display = format_date_for_display(row[9])
            p_end_display = format_date_for_display(row[10])
            
            display_values = (row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], p_start_display, p_end_display)
            
            try:
                end_date = datetime.strptime(row[10], "%Y-%m-%d").date() if row[10] else None
            except ValueError:
                end_date = None

            if not end_date:
                self.tree_guncel.insert("", "end", iid=row[0], values=display_values, tags=(tag,))
                continue

            days_left = (end_date - today).days

            if days_left < 0:
                self.tree_eski.insert("", "end", iid=row[0], values=display_values, tags=(tag,))
            elif 0 <= days_left <= 30:
                self.tree_yenileme.insert("", "end", iid=row[0], values=display_values, tags=(tag,))
            else:
                self.tree_guncel.insert("", "end", iid=row[0], values=display_values, tags=(tag,))

    def add_from_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF Dosyaları", "*.pdf")])
        if not file_path: return
        
        data = parse_pdf_regex(file_path)
        if data:
            data[8] = format_date_for_display(data[8])
            data[9] = format_date_for_display(data[9])
            self.open_edit_window("Yeni Kayıt Ekle", data, is_new=True)

    def edit_selected(self):
        current_tab = self.tab_control.nametowidget(self.tab_control.select())
        frame = current_tab.winfo_children()[0]
        tree = None
        for widget in frame.winfo_children():
            if isinstance(widget, ttk.Treeview):
                tree = widget
                break
        
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen düzenlemek için bir kayıt seçin!")
            return
            
        item_id = selected[0]
        display_values = tree.item(item_id, "values")
        self.open_edit_window("Kaydı Düzenle", list(display_values), is_new=False, item_id=item_id)

    def delete_selected(self):
        current_tab = self.tab_control.nametowidget(self.tab_control.select())
        frame = current_tab.winfo_children()[0]
        tree = None
        for widget in frame.winfo_children():
            if isinstance(widget, ttk.Treeview):
                tree = widget
                break
        
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Uyarı", "Silinecek kayıt seçilmedi.")
            return
            
        if messagebox.askyesno("Onay", "Seçili kayıt(lar) silinsin mi?"):
            for item_id in selected:
                delete_customer(item_id)
            self.load_data(self.entry_search.get())

    def open_edit_window(self, title, data, is_new, item_id=None):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("800x850") 
        win.configure(bg="white")
        win.transient(self.root)
        
        # Grid ayarları: Dikey ve Yatay genişleme için
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        
        content = tk.Frame(win, bg="white", padx=50, pady=40)
        content.grid(row=0, column=0, sticky="nsew")
        
        content.columnconfigure(1, weight=1) # Entry sütunu yatayda genişler

        tk.Label(content, text=title, font=("Segoe UI", 22, "bold"), bg="white", fg="#3498DB").grid(row=0, column=0, columnspan=2, pady=(0, 30), sticky="w")
        
        entries = []
        for i, col in enumerate(self.columns):
            # SATIR AĞIRLIĞI EKLENDİ (DİKEY BÜYÜME İÇİN)
            # i+1 çünkü başlık 0. satırda. Her satıra ağırlık veriyoruz.
            content.rowconfigure(i+1, weight=1)

            lbl = tk.Label(content, text=col, font=("Segoe UI", 14, "bold"), bg="white", fg="#555")
            # sticky="ns" etiketi de dikeyde ortalar
            lbl.grid(row=i+1, column=0, padx=10, pady=5, sticky='w')
            
            if col == "Şirket":
                e = ttk.Combobox(content, values=COMPANY_LIST, font=("Segoe UI", 14))
            else:
                # bd=2 (Kalın kenarlık)
                e = tk.Entry(content, font=("Segoe UI", 14), bd=2, relief="solid")
            
            # sticky="nsew" -> Hem yatay (ew) hem dikey (ns) büyüme
            # ipady=5 -> İç dolguyu artırarak kutuyu doğal olarak kalınlaştırır
            e.grid(row=i+1, column=1, padx=10, pady=5, sticky="nsew", ipady=5) 
            
            if data and i < len(data):
                val = data[i] if data[i] else ""
                if col == "Şirket": e.set(val)
                else: e.insert(0, val)
            
            entries.append(e)

        def save():
            new_data = [e.get().strip() for e in entries]
            
            # TC Kimlik No validasyonu (index 1)
            tc_no = new_data[1]
            if not validate_tc_no(tc_no):
                messagebox.showerror("Hata", "TC Kimlik Numarası 11 haneli olmalıdır!")
                return
            
            new_data[8] = format_date_for_db(new_data[8])
            new_data[9] = format_date_for_db(new_data[9])

            if is_new: insert_customer(new_data)
            else: update_customer(item_id, new_data)
            
            self.load_data(self.entry_search.get())
            win.destroy()

        btn_text = "💾 KAYDET" if is_new else "💾 GÜNCELLE"
        save_btn = tk.Button(content, text=btn_text, command=save, 
                             bg="#3498DB", fg="white", font=("Segoe UI", 16, "bold"), 
                             bd=0, pady=15, padx=40, cursor="hand2")
        
        # Buton satırı için de dikey genişleme
        content.rowconfigure(len(self.columns)+2, weight=1)
        save_btn.grid(row=len(self.columns)+2, column=0, columnspan=2, pady=20)

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = InsuranceApp(root)
    root.mainloop()