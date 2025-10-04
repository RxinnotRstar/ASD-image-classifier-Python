# image_classifier_ptr_readonly_hint.py
import os, json, shutil, ctypes
from tkinter import *
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import win32api, win32con

class HintEntry(Entry):
    """只读+灰色提示文字"""
    def __init__(self, master, hint='', **kw):
        super().__init__(master, **kw)
        self.hint = hint
        self.hint_color = 'grey'
        self.normal_color = self['fg']
        self.bind('<FocusIn>',  self._clear_hint)
        self.bind('<FocusOut>', self._show_hint)
        self._show_hint()

    def _clear_hint(self, *_):
        if self['fg'] == self.hint_color:
            self.delete(0, END)
            self.config(fg=self.normal_color)

    def _show_hint(self, *_):
        if not self.get():
            self.insert(0, self.hint)
            self.config(fg=self.hint_color)

    def set(self, text):
        """外部回填路径时调用"""
        self._clear_hint()
        self.insert(0, text)
        self.config(fg=self.normal_color)

class ImageClassifier:
    def __init__(self, root):
        self.root = root
        self.root.title("图片分类工具")
        self.root.state('zoomed')
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        import tkinter.font as tkfont
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font.configure(size=20)
        self.root.option_add("*Font", self.default_font)

        self.config_file = "classifier_config.json"

        self.input_folder   = StringVar()
        self.inc_subfolders = BooleanVar(value=False)
        self.sort_method    = StringVar(value="name")
        self.reverse_sort   = BooleanVar(value=False)
        self.copy_mode      = BooleanVar(value=True)

        self.output_folders = [
            {"name": "文件夹１(A)", "path": StringVar()},
            {"name": "文件夹２(S)", "path": StringVar()},
            {"name": "文件夹３(D)", "path": StringVar()}
        ]

        self.all_images = []
        self.ptr = 0
        self.history = []
        self.skip_stack = []

        self.img_ext = ('.jpg','.jpeg','.png','.gif','.bmp','.tiff','.ico')
        self.vid_ext = ('.mp4','.avi','.mov','.wmv','.flv','.mkv')
        self.swf_ext = ('.swf',)
        self.supported_formats = self.img_ext + self.vid_ext + self.swf_ext

        self.load_config()
        self.build_ui()
        self.root.after(100, lambda: self.root.focus_force())
        if self.input_folder.get() and os.path.exists(self.input_folder.get()):
            self.root.after(200, self.load_images)

    # ---------------- UI ----------------
    def build_ui(self):
        line1 = Frame(self.root)
        line1.pack(fill=X, padx=10, pady=5)
        Label(line1, text="输入路径：").pack(side=LEFT)
        self.input_entry = HintEntry(line1, textvariable=self.input_folder,
                                     hint='这里是需要处理的文件夹路径', state='readonly')
        self.input_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        Button(line1, text="浏览…", command=self.browse_input).pack(side=LEFT, padx=5)
        Checkbutton(line1, text="包含子文件夹", variable=self.inc_subfolders,
                   command=self.load_images).pack(side=LEFT, padx=5)

        line2 = Frame(self.root)
        line2.pack(fill=X, padx=10, pady=5)
        sort_frm = Frame(line2)
        sort_frm.pack(side=LEFT, fill=X, expand=True)
        for txt, val in [("按时间排序（新的在前）","time"),
                         ("按大小排序（大的在前）","size"),
                         ("按名称排序（方向为正）","name")]:
            Radiobutton(sort_frm, text=txt, variable=self.sort_method,
                       value=val, command=self.load_images).pack(side=LEFT, padx=5)
        Checkbutton(sort_frm, text="倒序排列", variable=self.reverse_sort,
                   command=self.load_images).pack(side=LEFT, padx=10)
        sep = Frame(line2, width=2, bg="gray")
        sep.pack(side=LEFT, fill=Y, padx=10)
        mode_frm = Frame(line2)
        mode_frm.pack(side=LEFT)
        Radiobutton(mode_frm, text="复制模式", variable=self.copy_mode, value=True).pack(side=LEFT)
        Radiobutton(mode_frm, text="移动模式", variable=self.copy_mode, value=False).pack(side=LEFT)

        self.img_frame = Frame(self.root, bg='white', relief=SUNKEN, bd=2)
        self.img_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        self.img_label = Label(self.img_frame, bg='white', anchor=CENTER)
        self.img_label.pack(fill=BOTH, expand=True)
        self.img_label.bind("<Double-Button-1>", self.open_current_file)

        line4 = Frame(self.root)
        line4.pack(fill=X, padx=10, pady=5)
        self.out_entries = []
        hints = ['这里是输出文件夹A的路径',
                 '这里是输出文件夹B的路径',
                 '这里是输出文件夹C的路径']
        for i, fo in enumerate(self.output_folders):
            frm = Frame(line4)
            frm.pack(side=LEFT, fill=X, expand=True, padx=(0,5) if i<2 else 0)
            Button(frm, text=fo["name"], width=10,
                  command=lambda f=fo: self.browse_output(f)).pack(side=LEFT)
            e = HintEntry(frm, textvariable=fo["path"], hint=hints[i], state='readonly')
            e.pack(side=LEFT, fill=X, expand=True, padx=5)
            self.out_entries.append(e)

        self.status = Label(self.root, text="", bd=1, relief=SUNKEN, anchor=W)
        self.status.pack(side=BOTTOM, fill=X)

        for key, func in (('a', lambda e: self.move_to(0)),
                         ('s', lambda e: self.move_to(1)),
                         ('d', lambda e: self.move_to(2)),
                         ('w', lambda e: self.skip()),
                         ('x', lambda e: self.go_back()),
                         ('<Control-z>', lambda e: self.undo())):
            self.root.bind(key, func)

        self.update_display()

    # ---------------- 加载图片 ----------------
    def load_images(self):
        self.all_images = []
        if not self.input_folder.get(): return
        root_path = self.input_folder.get()
        if not os.path.exists(root_path): return

        if self.inc_subfolders.get():
            for r, _, fs in os.walk(root_path):
                for f in fs:
                    if f.lower().endswith(self.supported_formats):
                        self.all_images.append(os.path.join(r, f))
        else:
            for f in os.listdir(root_path):
                if f.lower().endswith(self.supported_formats):
                    full = os.path.join(root_path, f)
                    if os.path.isfile(full):
                        self.all_images.append(full)

        rev = self.reverse_sort.get()
        if self.sort_method.get() == "time":
            self.all_images.sort(key=lambda x: os.path.getmtime(x), reverse=not rev)
        elif self.sort_method.get() == "size":
            self.all_images.sort(key=lambda x: os.path.getsize(x), reverse=not rev)
        else:
            self.all_images.sort(reverse=rev)

        self.ptr = 0
        self.update_display()

    # ---------------- 显示逻辑 ----------------
    def update_display(self):
        self.update_status_bar()
        if not self.input_folder.get():
            self.show_welcome(); return
        if not os.path.exists(self.input_folder.get()):
            self.show_error(f"目录：{self.input_folder.get()} 不存在"); return
        if not self.all_images:
            self.show_error(f"目录：{self.input_folder.get()} 没有图片"); return
        valid = sum(1 for fo in self.output_folders if fo["path"].get())
        if valid < 2:
            self.show_error("请选择至少２个输出文件夹！")
            return
        self.show_current()

    def show_welcome(self):
        txt = ("图片分类工具 by Kimi-AI & Rxinns\n\n"
              "——————————————————————\n\n"
              "操作方法：\n\n"
              "1. 在上方选择输入文件夹\n\n"
              "2. 在下方选择 2 到 3 个输出文件夹\n\n"
              "3. 在键盘上按下 A、S、D ，即可分类到对应的文件夹，支持复制或移动\n\n"
              "4. 不知道该怎么分类？按下“W”，可以跳过这张图片\n\n"
              "5. 突然想分类刚才跳过的图？按“X”即可逐张回退，直到栈空\n\n"
              "6. 不小心按错了？按 Ctrl+Z 可以撤销上一次的分类，支持连续撤销\n\n"
              "7. 感觉字体太小？右键编辑代码，搜索：default_font.configure，可以更改字体大小")
        self.img_label.config(text=txt, fg='gray',
                            font=(self.default_font.actual()['family'],
                                  self.default_font.actual()['size']))

    def show_error(self, msg):
        self.img_label.config(text=msg, fg='red', font=('微软雅黑', 12))

    def show_current(self):
        if not self.all_images: return
        f = self.all_images[self.ptr]
        ext = os.path.splitext(f)[1].lower()

        if ext in self.vid_ext + self.swf_ext:
            self.img_label.config(
                text=f"视频／Flash 文件：{os.path.basename(f)}\n\n双击此处用默认程序打开",
                fg='blue', font=('微软雅黑', 12))
        else:
            try:
                img = Image.open(f)
                fw = self.img_frame.winfo_width() - 10
                fh = self.img_frame.winfo_height() - 10
                if fw > 1 and fh > 1:
                    img.thumbnail((fw, fh), Image.Resampling.LANCZOS)
                ph = ImageTk.PhotoImage(img)
                self.img_label.config(image=ph, text="")
                self.img_label.image = ph
            except Exception as e:
                self.img_label.config(text=f"无法加载图片：{e}", fg='red')

    def update_status_bar(self):
        if self.all_images:
            cur = os.path.basename(self.all_images[self.ptr])
            self.status.config(text=f"{self.ptr + 1}/{len(self.all_images)}：{cur}")
        else:
            self.status.config(text="")

    # ---------------- 核心操作 ----------------
    def skip(self):
        if not self.all_images: return
        self.skip_stack.append(self.all_images[self.ptr])
        self.ptr = (self.ptr + 1) % len(self.all_images)
        self.update_display()

    def go_back(self):
        if not self.all_images: return
        self.ptr = (self.ptr - 1) % len(self.all_images)
        self.update_display()

    def move_to(self, idx):
        if not self.all_images or idx >= 3: return
        fo = self.output_folders[idx]["path"].get()
        if not fo:
            messagebox.showwarning("提示", f"请先选择 {self.output_folders[idx]['name']}")
            return
        os.makedirs(fo, exist_ok=True)

        src = self.all_images[self.ptr]
        name = os.path.basename(src)
        dst = os.path.join(fo, name)
        base, ext = os.path.splitext(name)
        c = 1
        while os.path.exists(dst):
            dst = os.path.join(fo, f"{base}_{c}{ext}")
            c += 1

        try:
            if self.copy_mode.get():
                shutil.copy2(src, dst)
            else:
                shutil.move(src, dst)
            self.history.append({
                'src': dst,
                'dst': src,
                'idx': self.ptr,
                'copy': self.copy_mode.get()
            })
            self.all_images.pop(self.ptr)
            if self.all_images:
                self.ptr = self.ptr % len(self.all_images)
            self.update_display()
        except Exception as e:
            messagebox.showerror("错误", f"操作失败：{e}")

    def undo(self):
        if not self.history: return
        act = self.history.pop()
        try:
            if act['copy']:
                os.remove(act['src'])
            else:
                shutil.move(act['src'], act['dst'])
            self.all_images.insert(act['idx'], act['dst'])
            self.ptr = act['idx']
            self.update_display()
        except Exception as e:
            messagebox.showerror("错误", f"撤销失败：{e}")

    # ---------------- 配置 ----------------
    def save_config(self):
        cfg = {
            'input_folder': self.input_folder.get(),
            'inc_subfolders': self.inc_subfolders.get(),
            'sort_method': self.sort_method.get(),
            'reverse_sort': self.reverse_sort.get(),
            'copy_mode': self.copy_mode.get(),
            'output_folders': [fo["path"].get() for fo in self.output_folders]
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.input_folder.set(cfg.get('input_folder', ''))
                self.inc_subfolders.set(cfg.get('inc_subfolders', False))
                self.sort_method.set(cfg.get('sort_method', 'name'))
                self.reverse_sort.set(cfg.get('reverse_sort', False))
                self.copy_mode.set(cfg.get('copy_mode', True))
                for i, p in enumerate(cfg.get('output_folders', [])):
                    if i < 3:
                        self.output_folders[i]["path"].set(p)
        except:
            print("配置文件丢失或损坏，已恢复默认设置。")
            pass

    # ---------------- 浏览/打开 ----------------
    def browse_input(self):
        d = filedialog.askdirectory()
        if d:
            self.input_folder.set(d)
            self.input_entry.set(d)        # 同步回填并清除提示
            self.load_images()
            self.save_config()

    def browse_output(self, fo):
        d = filedialog.askdirectory()
        if d:
            fo["path"].set(d)
            idx = next(i for i,x in enumerate(self.output_folders) if x is fo)
            self.out_entries[idx].set(d)   # 同步回填并清除提示
            self.save_config()
            self.update_display()

    def open_current_file(self, _):
        if not self.all_images: return
        f = self.all_images[self.ptr]
        try:
            win32api.ShellExecute(0, 'open', f, None, None, win32con.SW_SHOWNORMAL)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件：{e}")


# ----------------------------------------------------------------------
if __name__ == "__main__":
    root = Tk()
    ImageClassifier(root)
    root.mainloop()