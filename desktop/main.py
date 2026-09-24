import sys, json, time, traceback
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QThread
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QTextEdit, QFileDialog, QMessageBox, QProgressBar, QComboBox, QGroupBox, QFormLayout, QStackedWidget, QInputDialog

APP_NAME='Hn38videoAItool'
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
FLOWS_FILE=DATA/'flows.json'; PROFILE=DATA/'meta_browser_profile'; DOWNLOADS=DATA/'downloads'; DOWNLOADS.mkdir(exist_ok=True)
DEFAULT_FLOWS=[
 {'name':'Văn bản → Ảnh','type':'text_image','prompt':'','images':[],'enabled':True},
 {'name':'Ảnh → Ảnh','type':'image_image','prompt':'','images':[],'enabled':True},
 {'name':'Ảnh → Ảnh → Ảnh','type':'image_chain','prompt':'','images':[],'enabled':True},
 {'name':'Văn bản → Video','type':'text_video','prompt':'','images':[],'enabled':True},
 {'name':'Ảnh → Video','type':'image_video','prompt':'','images':[],'enabled':True},]

def load_flows():
    try:return json.loads(FLOWS_FILE.read_text(encoding='utf-8'))
    except Exception:
        FLOWS_FILE.write_text(json.dumps(DEFAULT_FLOWS,ensure_ascii=False,indent=2),encoding='utf-8'); return DEFAULT_FLOWS.copy()

def save_flows(v): FLOWS_FILE.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

class BrowserWorker(QObject):
    status=Signal(str); error=Signal(str); finished=Signal(str); progress=Signal(int)
    def __init__(self,prompt,flow_type,image_paths): super().__init__(); self.prompt=prompt; self.flow_type=flow_type; self.image_paths=image_paths; self.stop=False
    @Slot()
    def run(self):
        try:
            from playwright.sync_api import sync_playwright
            PROFILE.mkdir(parents=True,exist_ok=True)
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(str(PROFILE),headless=False,accept_downloads=True,viewport={'width':1440,'height':900})
                page=context.pages[0] if context.pages else context.new_page(); page.goto('https://www.meta.ai/',wait_until='domcontentloaded',timeout=60000)
                self.progress.emit(10); self.status.emit('Mở Meta AI. Nếu chưa đăng nhập, hãy đăng nhập trực tiếp trong trình duyệt.'); page.wait_for_timeout(2500)
                if self.stop: context.close(); self.finished.emit('Đã dừng'); return
                box=self.find_prompt(page)
                if not box: self.error.emit('Không tìm thấy ô nhập prompt trên Meta AI. Giao diện có thể đã thay đổi.'); context.close(); return
                if self.image_paths: self.attach_images(page,self.image_paths)
                box.fill(self.prompt); self.progress.emit(35); box.press('Enter'); self.progress.emit(50); self.status.emit('Đã gửi prompt, đang chờ Meta AI...')
                deadline=time.time()+120
                while time.time()<deadline and not self.stop:
                    if page.locator('img').count()>0 or page.locator('video').count()>0:
                        self.progress.emit(100); self.finished.emit('Meta AI đã trả về kết quả'); context.close(); return
                    page.wait_for_timeout(1500)
                if self.stop:self.finished.emit('Đã dừng')
                else:self.error.emit('Chưa nhận được kết quả trong thời gian chờ. Kiểm tra tính năng/tài khoản hoặc giao diện Meta AI.')
                context.close()
        except Exception as e:self.error.emit(f'{type(e).__name__}: {e}'); traceback.print_exc()
    def find_prompt(self,page):
        for loc in [page.get_by_role('textbox').last,page.locator('textarea').last,page.locator('input[type="text"]').last,page.locator('[contenteditable="true"]').last]:
            try:
                if loc.count() and loc.is_visible(): return loc
            except Exception: pass
    def attach_images(self,page,paths):
        try:
            bs=page.get_by_role('button')
            for i in range(min(bs.count(),100)):
                b=bs.nth(i); s=((b.get_attribute('aria-label') or '')+' '+(b.inner_text() or '')).lower()
                if any(k in s for k in ['attach','upload','image','photo','ảnh','tệp']):
                    try:
                        with page.expect_file_chooser(timeout=2500) as fc:b.click()
                        fc.value.set_files(paths); return
                    except Exception:pass
        except Exception:pass

class Main(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1380,860); self.flows=load_flows(); self.current=0; self.thread=None; self.worker=None; self.ui()
    def ui(self):
        self.setStyleSheet('''QMainWindow,QWidget{background:#111318;color:#ECEFF4} QListWidget{background:#171A21;border:0;padding:8px} QListWidget::item{padding:13px 10px;border-radius:8px} QListWidget::item:selected{background:#2A3040} QPushButton{background:#252B36;border:1px solid #3A4352;border-radius:7px;padding:9px 14px} QPushButton:hover{background:#303846} QTextEdit,QComboBox{background:#191D25;border:1px solid #394150;border-radius:7px;padding:8px} QGroupBox{border:1px solid #303744;border-radius:10px;margin-top:12px;padding:12px} QProgressBar{border:0;background:#202530;border-radius:6px;height:12px} QProgressBar::chunk{background:#5B8CFF;border-radius:6px} QLabel#title{font-size:22px;font-weight:700} QLabel#muted{color:#9AA3B2}''')
        c=QWidget(); self.setCentralWidget(c); lay=QHBoxLayout(c); lay.setContentsMargins(0,0,0,0)
        sw=QWidget(); sw.setFixedWidth(270); sl=QVBoxLayout(sw); brand=QLabel(APP_NAME); brand.setObjectName('title'); sl.addWidget(brand); s=QLabel('Flow automation for Meta AI'); s.setObjectName('muted'); sl.addWidget(s)
        self.nav=QListWidget(); self.nav.addItems(['🎬 Video Flow','👤 Meta AI','📋 Log Chi Tiết','⚙️ Cài đặt']); self.nav.currentRowChanged.connect(self.stack_to); sl.addWidget(self.nav,1)
        b=QPushButton('+ Tạo Flow'); b.clicked.connect(self.create_flow); sl.addWidget(b); lay.addWidget(sw)
        self.stack=QStackedWidget(); self.flow=self.flow_page(); self.account=self.account_page(); self.logpage=self.log_page(); self.settings=self.settings_page(); [self.stack.addWidget(x) for x in [self.flow,self.account,self.logpage,self.settings]]; lay.addWidget(self.stack,1)
    def flow_page(self):
        w=QWidget(); r=QHBoxLayout(w); self.list=QListWidget(); self.list.setFixedWidth(245); [self.list.addItem(x['name']) for x in self.flows]; self.list.currentRowChanged.connect(self.load_flow); r.addWidget(self.list)
        p=QVBoxLayout(); self.title=QLabel(); self.title.setObjectName('title'); p.addWidget(self.title); self.kind=QLabel(); self.kind.setObjectName('muted'); p.addWidget(self.kind)
        g=QGroupBox('Prompt'); q=QVBoxLayout(g); self.prompt=QTextEdit(); self.prompt.setPlaceholderText('Nhập prompt...'); q.addWidget(self.prompt); p.addWidget(g)
        g2=QGroupBox('Ảnh đầu vào / tham chiếu'); q2=QVBoxLayout(g2); self.images=QLabel('Chưa chọn ảnh'); q2.addWidget(self.images); bi=QPushButton('Chọn ảnh'); bi.clicked.connect(self.choose_images); q2.addWidget(bi); p.addWidget(g2)
        row=QHBoxLayout(); br=QPushButton('▶ Chạy Flow'); br.clicked.connect(self.run); bs=QPushButton('■ Dừng'); bs.clicked.connect(self.stop_run); bv=QPushButton('💾 Lưu Flow'); bv.clicked.connect(self.save); row.addWidget(br); row.addWidget(bs); row.addWidget(bv); p.addLayout(row)
        self.bar=QProgressBar(); self.bar.setValue(0); p.addWidget(self.bar); self.status=QLabel('Sẵn sàng'); self.status.setObjectName('muted'); p.addWidget(self.status)
        self.queue=QListWidget(); p.addWidget(QLabel('Hàng đợi / trạng thái')); p.addWidget(self.queue,1); r.addLayout(p,1); return w
    def account_page(self):
        w=QWidget(); l=QVBoxLayout(w); t=QLabel('Meta AI'); t.setObjectName('title'); l.addWidget(t); l.addWidget(QLabel('Đăng nhập trực tiếp trong trình duyệt. Tool không yêu cầu mật khẩu, OTP hoặc cookie.')); b=QPushButton('🌐 Mở Meta AI'); b.clicked.connect(lambda: __import__('webbrowser').open('https://www.meta.ai/')); l.addWidget(b); l.addStretch(); return w
    def log_page(self):
        w=QWidget(); l=QVBoxLayout(w); t=QLabel('Log Chi Tiết'); t.setObjectName('title'); l.addWidget(t); self.logs=QTextEdit(); self.logs.setReadOnly(True); l.addWidget(self.logs); return w
    def settings_page(self):
        w=QWidget(); l=QVBoxLayout(w); t=QLabel('Cài đặt'); t.setObjectName('title'); l.addWidget(t); ui=QGroupBox('Giao diện'); f=QFormLayout(ui); theme=QComboBox(); theme.addItems(['Tối','Sáng']); f.addRow('Chủ đề',theme); l.addWidget(ui)
        a=QGroupBox('Giới thiệu'); al=QVBoxLayout(a); al.addWidget(QLabel('<b>Hn38videoAItool</b><br>Flow automation cho Meta AI<br><br><b>Developer:</b> Hoainguyenstudio<br><b>Zalo:</b> 0965.043.000<br><b>Version:</b> 1.0.0')); l.addWidget(a)
        c=QGroupBox('Bản quyền'); cl=QVBoxLayout(c); cl.addWidget(QLabel('© 2026 Hoainguyenstudio. Hn38videoAItool.')); l.addWidget(c); l.addStretch(); return w
    def stack_to(self,i): self.stack.setCurrentIndex(i)
    def load_flow(self,i):
        if i<0 or i>=len(self.flows):return
        self.current=i; f=self.flows[i]; self.title.setText(f['name']); self.kind.setText('Loại Flow: '+f['type']); self.prompt.setPlainText(f.get('prompt','')); self.images.setText(' | '.join(Path(x).name for x in f.get('images',[])) or 'Chưa chọn ảnh'); self.bar.setValue(0); self.queue.clear(); self.queue.addItem('Sẵn sàng')
    def choose_images(self):
        p,_=QFileDialog.getOpenFileNames(self,'Chọn ảnh','','Images (*.png *.jpg *.jpeg *.webp)');
        if p:self.flows[self.current]['images']=p; self.images.setText(' | '.join(Path(x).name for x in p))
    def save(self): self.flows[self.current]['prompt']=self.prompt.toPlainText(); save_flows(self.flows); self.log('Đã lưu Flow: '+self.flows[self.current]['name'])
    def create_flow(self):
        n,ok=QInputDialog.getText(self,'Tạo Flow','Tên Flow:');
        if ok and n.strip(): self.flows.append({'name':n.strip(),'type':'text_image','prompt':'','images':[],'enabled':True}); save_flows(self.flows); self.list.addItem(n.strip()); self.list.setCurrentRow(len(self.flows)-1)
    def run(self):
        self.save(); f=self.flows[self.current]; prompt=self.prompt.toPlainText().strip();
        if not prompt: QMessageBox.warning(self,'Thiếu prompt','Hãy nhập prompt.'); return
        self.bar.setValue(5); self.queue.clear(); self.queue.addItem('Đang chạy: '+f['name']); self.thread=QThread(); self.worker=BrowserWorker(prompt,f['type'],f.get('images',[])); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.status.connect(self.on_status); self.worker.progress.connect(self.bar.setValue); self.worker.error.connect(self.on_error); self.worker.finished.connect(self.on_finished); self.thread.start()
    def stop_run(self):
        if self.worker:self.worker.stop=True; self.log('Yêu cầu dừng Flow.')
    def on_status(self,s):self.status.setText(s); self.log(s); self.queue.addItem(s)
    def on_error(self,s):self.status.setText('Lỗi: '+s); self.log('ERROR: '+s); self.queue.addItem('❌ '+s)
    def on_finished(self,s):self.status.setText(s); self.log(s); self.queue.addItem('✅ '+s); self.thread.quit() if self.thread else None
    def log(self,s):self.logs.append(time.strftime('[%Y-%m-%d %H:%M:%S] ')+s)

if __name__=='__main__':
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); win=Main(); win.show(); sys.exit(app.exec())
