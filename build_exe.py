import os
import sys
import PyInstaller.__main__
import shutil
import importlib.util

def get_ctk_tcl_path():
    """获取CustomTkinter的tcl路径"""
    try:
        ctk_spec = importlib.util.find_spec("customtkinter")
        if ctk_spec is None or ctk_spec.submodule_search_locations is None:
            print("错误: 未安装CustomTkinter! 请运行: pip install customtkinter")
            sys.exit(1)
        
        ctk_path = ctk_spec.submodule_search_locations[0]
        tcl_path = os.path.join(ctk_path, "tcl")
        
        if not os.path.exists(tcl_path):
            # 创建tcl目录
            os.makedirs(tcl_path, exist_ok=True)
            print(f"警告: 在CustomTkinter包中未找到tcl目录，已创建: {tcl_path}")
            print("请从以下位置下载tcl文件并放置在此目录:")
            print("https://github.com/TomSchimansky/CustomTkinter/tree/master/src/customtkinter/tcl")
            print("然后重新运行此脚本。")
            sys.exit(1)
        
        return tcl_path
    except Exception as e:
        print(f"获取CustomTkinter路径时出错: {e}")
        sys.exit(1)

def main():
    # 获取当前目录路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 主脚本路径
    main_script_file = "MIDI.py"
    script_path = os.path.join(current_dir, main_script_file)
    
    # 检查主脚本是否存在
    if not os.path.isfile(script_path):
        print(f"错误: 找不到脚本文件 '{script_path}'")
        py_files = [f for f in os.listdir(current_dir) if f.endswith(".py")]
        print("当前目录下的Python文件:")
        for f in py_files:
            print(f" - {f}")
        sys.exit(1)
    
    # 获取CustomTkinter的tcl路径
    ctk_tcl_path = get_ctk_tcl_path()
    
    # 打包参数
    args = [
        script_path,           # 主脚本文件
        '--windowed',           # 不显示控制台窗口
        '--onefile',            # 打包为单个可执行文件
        '--noconsole',          # 无控制台窗口
        '--name=MIDI-Converter', # 可执行文件名称
        f'--add-data={ctk_tcl_path}{os.pathsep}customtkinter/tcl',  # 添加tcl资源
        '--collect-all=pygame', # 收集pygame及其所有依赖
        '--collect-all=zlib',   # 包含zlib压缩库
        '--collect-all=mido',   # 包含mido
        '--collect-all=numpy',   # 包含numpy
        '--hidden-import=pygame._sdl2',  # 隐藏导入
        '--hidden-import=pygame.midi',
        '--hidden-import=numpy'
    ]
    
    # 图标处理
    icon_path = os.path.join(current_dir, "app.png")
    if os.path.exists(icon_path):
        args.append(f'--icon={icon_path}')
    else:
        print("警告: 未找到app.ico图标文件，跳过使用图标")
    
    # 添加NumPy相关解决方法
    if sys.platform == 'win32':
        args.extend([
            '--paths', os.path.join(sys.exec_prefix, 'Lib', 'site-packages', 'numpy', '.libs')
        ])
    
    # 打印打包参数
    print("\n开始PyInstaller打包，参数如下:")
    print(" ".join(args))
    
    # 清理之前的构建文件
    build_dir = os.path.join(current_dir, "build")
    dist_dir = os.path.join(current_dir, "dist")
    spec_file = os.path.join(current_dir, f"{os.path.splitext(main_script_file)[0]}.spec")
    
    for path in [build_dir, dist_dir, spec_file]:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    
    # 执行打包
    try:
        PyInstaller.__main__.run(args)
        print("\n打包成功完成!")
    except Exception as e:
        print(f"\n打包过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 确定可执行文件路径
    exe_name = "MIDI-Converter.exe" if sys.platform == 'win32' else "MIDI-Converter"
    exe_path = os.path.join(dist_dir, exe_name)
    
    if os.path.exists(exe_path):
        print(f"\n成功生成可执行文件: {exe_path}")
        print(f"文件大小: {os.path.getsize(exe_path) / (1024 * 1024):.2f} MB")
        
        # 尝试运行可执行文件（仅Windows）
        if sys.platform == 'win32':
            print("\n尝试运行可执行文件进行测试...")
            os.chdir(dist_dir)
            os.startfile(exe_name)
    else:
        print("\n错误: 未能生成可执行文件")
        sys.exit(1)

if __name__ == "__main__":
    main()