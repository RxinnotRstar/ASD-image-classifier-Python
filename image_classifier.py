import os
import json
import shutil
from tkinter import *
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from datetime import datetime
import win32api
import win32con

class ImageClassifier:
    def __init__(self, root):
        self.root = root
        self.root.title("图片分类工具")
        self.root.geometry("1000x700")
        
        # 配置文件路径
        self.config_file = "classifier_config.json"
        
        # 初始化变量
        self.input_folder = StringVar()
        self.include_subfolders = BooleanVar(value=False)
        self.sort_method = StringVar(value="name")
        self.reverse_sort = BooleanVar(value=False)
        
        # 输出文件夹
        self.output_folders = [
            {"name": "文件夹１", "path": StringVar()},
            {"name": "文件夹２", "path": StringVar()},
            {"name": "文件夹３", "path": StringVar()}
        ]
        
        # 图片相关
        self.image_files = []
        self.current_index = 0
        self.history = []  # 用于撤销操作
        
        # 支持的文件格式
        self.supported_formats = (
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico',
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
            '.swf'
        )
        
        self.load_config()
        self.setup_ui()
        
    def setup_ui(self):
        # 输入路径区域
        input_frame = Frame(self.root)
        input_frame.pack(fill=X, padx=10, pady=5)
        
        Label(input_frame, text="输入路径:").pack(side=LEFT)
        Entry(input_frame, textvariable=self.input_folder, width=50).pack(side=LEFT, padx=5)
        Button(input_frame, text="浏览...", command=self.browse_input).pack(side=LEFT, padx=5)
        Checkbutton(input_frame, text="包含子文件夹", variable=self.include_subfolders,
                   command=self.load_images).pack(side=LEFT, padx=5)
        
        # 排序选项区域
        sort_frame = Frame(self.root)
        sort_frame.pack(fill=X, padx=10, pady=5)
        
        Label(sort_frame, text="排序方式:").pack(side=LEFT)
        
        sort_options = [
            ("按时间排序（新的在前）", "time"),
            ("按大小排序（大的在前）", "size"),
            ("按名称排序（正序）", "name")
        ]
        
        for text, value in sort_options:
            Radiobutton(sort_frame, text=text, variable=self.sort_method, 
                       value=value, command=self.load_images).pack(side=LEFT, padx=5)
        
        Checkbutton(sort_frame, text="倒序", variable=self.reverse_sort,
                   command=self.load_images).pack(side=LEFT, padx=5)
        
        # 输出文件夹区域
        output_frame = Frame(self.root)
        output_frame.pack(fill=X, padx=10, pady=5)
        
        for i, folder in enumerate(self.output_folders):
            frame = Frame(output_frame)
            frame.pack(fill=X, pady=2)
            Button(frame, text=folder["name"], width=10,
                  command=lambda f=folder: self.browse_output(f)).pack(side=LEFT)
            Entry(frame, textvariable=folder["path"], width=60).pack(side=LEFT, padx=5)
        
        # 图片显示区域
        self.image_frame = Frame(self.root, bg='white', relief=SUNKEN, bd=2)
        self.image_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.image_label = Label(self.image_frame, bg='white')
        self.image_label.pack(fill=BOTH, expand=True)
        self.image_label.bind("<Double-Button-1>", self.open_current_file)
        
        # 状态信息
        self.status_label = Label(self.root, text="", bd=1, relief=SUNKEN, anchor=W)
        self.status_label.pack(side=BOTTOM, fill=X)
        
        # 键盘绑定
        self.root.bind('<a>', lambda e: self.move_to_folder(0))
        self.root.bind('<s>', lambda e: self.move_to_folder(1))
        self.root.bind('<d>', lambda e: self.move_to_folder(2))
        self.root.bind('<w>', lambda e: self.skip_image())
        self.root.bind('<Control-z>', lambda e: self.undo())
        
        # 初始显示
        self.update_display()
        
    def browse_input(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder.set(folder)
            self.load_images()
            self.save_config()
    
    def browse_output(self, folder_config):
        folder = filedialog.askdirectory()
        if folder:
            folder_config["path"].set(folder)
            self.save_config()
            self.update_display()
    
    def load_images(self):
        if not self.input_folder.get():
            return
            
        self.image_files = []
        input_path = self.input_folder.get()
        
        if not os.path.exists(input_path):
            self.update_display()
            return
            
        # 获取所有支持的文件
        if self.include_subfolders.get():
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith(self.supported_formats):
                        self.image_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(input_path):
                if file.lower().endswith(self.supported_formats):
                    full_path = os.path.join(input_path, file)
                    if os.path.isfile(full_path):
                        self.image_files.append(full_path)
        
        # 排序
        if self.sort_method.get() == "time":
            self.image_files.sort(key=lambda x: os.path.getmtime(x), reverse=not self.reverse_sort.get())
        elif self.sort_method.get() == "size":
            self.image_files.sort(key=lambda x: os.path.getsize(x), reverse=not self.reverse_sort.get())
        else:  # name
            self.image_files.sort(reverse=self.reverse_sort.get())
        
        self.current_index = 0
        self.update_display()
    
    def update_display(self):
        # 检查输出文件夹
        valid_outputs = sum(1 for folder in self.output_folders if folder["path"].get())
        
        if not self.input_folder.get():
            self.show_welcome_screen()
            return
        elif not os.path.exists(self.input_folder.get()):
            self.show_error_screen(f"目录：{self.input_folder.get()} 不存在")
            return
        elif not self.image_files:
            self.show_error_screen(f"目录：{self.input_folder.get()} 没有图片")
            return
        elif valid_outputs < 2:
            self.show_error_screen("请选择至少２个输出文件夹")
            return
        
        # 显示当前图片
        self.show_current_image()
        self.update_status()
    
    def show_welcome_screen(self):
        welcome_text = """图片分类工具

双击此处可打开图片

按下A、S、D可进行分类，按W跳过这张图片

按Ctrl + Z 可撤销上一次的移动（支持连续撤销）

在上方选择分类的图片文件夹"""
        
        self.image_label.config(text=welcome_text, fg='gray', font=('Arial', 12))
        self.status_label.config(text="")
    
    def show_error_screen(self, message):
        self.image_label.config(text=message, fg='red', font=('Arial', 12))
        self.status_label.config(text="")
    
    def show_current_image(self):
        if not self.image_files:
            return
            
        image_path = self.image_files[self.current_index]
        
        try:
            # 检查是否为视频或flash
            if image_path.lower().endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.swf')):
                self.image_label.config(
                    text=f"视频文件：{os.path.basename(image_path)}\n\n双击此处用Windows打开预览",
                    fg='blue', font=('Arial', 12)
                )
            else:
                # 显示图片
                image = Image.open(image_path)
                
                # 计算缩放比例
                frame_width = self.image_frame.winfo_width() - 10
                frame_height = self.image_frame.winfo_height() - 10
                
                if frame_width > 1 and frame_height > 1:
                    image.thumbnail((frame_width, frame_height), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(image)
                self.image_label.config(image=photo, text="")
                self.image_label.image = photo
                
        except Exception as e:
            self.image_label.config(text=f"无法加载图片：{str(e)}", fg='red')
    
    def update_status(self):
        if self.image_files:
            total = len(self.image_files)
            current = self.current_index + 1
            current_file = os.path.basename(self.image_files[self.current_index])
            self.status_label.config(text=f"{current}/{total}: {current_file}")
        else:
            self.status_label.config(text="")
    
    def move_to_folder(self, folder_index):
        if not self.image_files or folder_index >= len(self.output_folders):
            return
            
        output_folder = self.output_folders[folder_index]["path"].get()
        if not output_folder:
            messagebox.showwarning("警告", f"请先选择{self.output_folders[folder_index]['name']}")
            return
        
        # 创建输出文件夹（如果不存在）
        if not os.path.exists(output_folder):
            try:
                os.makedirs(output_folder)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建文件夹：{str(e)}")
                return
        
        # 移动文件
        source_path = self.image_files[self.current_index]
        filename = os.path.basename(source_path)
        target_path = os.path.join(output_folder, filename)
        
        # 如果目标文件已存在，添加数字后缀
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(target_path):
            target_path = os.path.join(output_folder, f"{base}_{counter}{ext}")
            counter += 1
        
        try:
            shutil.move(source_path, target_path)
            
            # 添加到历史记录
            self.history.append({
                'source': target_path,
                'target': source_path,
                'index': self.current_index
            })
            
            # 从列表中移除
            self.image_files.pop(self.current_index)
            
            # 调整索引
            if self.current_index >= len(self.image_files) and len(self.image_files) > 0:
                self.current_index = len(self.image_files) - 1
            
            self.update_display()
            
        except Exception as e:
            messagebox.showerror("错误", f"移动文件失败：{str(e)}")
    
    def skip_image(self):
        if not self.image_files:
            return
            
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.update_display()
    
    def undo(self):
        if not self.history:
            return
            
        last_action = self.history.pop()
        
        try:
            shutil.move(last_action['source'], last_action['target'])
            
            # 将文件重新添加到列表
            self.image_files.insert(last_action['index'], last_action['target'])
            self.current_index = last_action['index']
            
            self.update_display()
            
        except Exception as e:
            messagebox.showerror("错误", f"撤销操作失败：{str(e)}")
    
    def open_current_file(self, event=None):
        if not self.image_files:
            return
            
        file_path = self.image_files[self.current_index]
        
        try:
            # 使用Windows默认程序打开
            win32api.ShellExecute(
                0,
                'open',
                file_path,
                None,
                None,
                win32con.SW_SHOWNORMAL
            )
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件：{str(e)}")
    
    def save_config(self):
        config = {
            'input_folder': self.input_folder.get(),
            'include_subfolders': self.include_subfolders.get(),
            'sort_method': self.sort_method.get(),
            'reverse_sort': self.reverse_sort.get(),
            'output_folders': [folder["path"].get() for folder in self.output_folders]
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.input_folder.set(config.get('input_folder', ''))
                self.include_subfolders.set(config.get('include_subfolders', False))
                self.sort_method.set(config.get('sort_method', 'name'))
                self.reverse_sort.set(config.get('reverse_sort', False))
                
                output_paths = config.get('output_folders', [])
                for i, path in enumerate(output_paths):
                    if i < len(self.output_folders):
                        self.output_folders[i]["path"].set(path)
        except Exception:
            pass

if __name__ == "__main__":
    root = Tk()
    app = ImageClassifier(root)
    root.mainloop()