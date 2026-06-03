#!/usr/bin/env python3
"""
Simple Tkinter GUI for 2D to 3D Building Blueprint Converter
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import sys
import os
from pathlib import Path

# Import main functionality
import main as main_module
import logging
import subprocess
import webbrowser

logger = logging.getLogger(__name__)


class BlueprintConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("2D to 3D Building Blueprint Converter")
        self.root.geometry("500x600")
        
        # Variables
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar(value="output")
        self.height = tk.DoubleVar(value=3.5)
        self.scale = tk.DoubleVar(value=100.0)
        self.wall_thickness = tk.DoubleVar(value=0.2)
        self.stair_width = tk.DoubleVar(value=1.2)
        self.show_furniture = tk.BooleanVar(value=True)
        self.show_map = tk.BooleanVar(value=False)
        self.map_file = tk.StringVar()
        self.lat = tk.StringVar()
        self.lon = tk.StringVar()
        self.zoom = tk.IntVar(value=18)
        
        # Viewer server state
        self.viewer_process = None
        self.viewer_running = tk.BooleanVar(value=False)
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        row = 0
        
        # Title
        title_label = ttk.Label(main_frame, text="2D to 3D Converter", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # Input file
        ttk.Label(main_frame, text="Blueprint File:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_file, width=35).grid(row=row, column=1, sticky=tk.W, padx=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_input).grid(row=row, column=2)
        row += 1
        
        # Output directory
        ttk.Label(main_frame, text="Output Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir, width=35).grid(row=row, column=1, sticky=tk.W, padx=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(row=row, column=2)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Height
        ttk.Label(main_frame, text="Building Height (m):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(main_frame, from_=1.0, to=50.0, textvariable=self.height, width=15).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1
        
        # Scale
        ttk.Label(main_frame, text="Pixels per Meter:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(main_frame, from_=10.0, to=500.0, textvariable=self.scale, width=15).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1
        
        # Wall thickness
        ttk.Label(main_frame, text="Wall Thickness (m):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(main_frame, from_=0.1, to=2.0, increment=0.05, textvariable=self.wall_thickness, width=15).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1
        
        # Stair width
        ttk.Label(main_frame, text="Stair Width (m):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(main_frame, from_=0.5, to=3.0, increment=0.1, textvariable=self.stair_width, width=15).grid(row=row, column=1, sticky=tk.W, padx=5)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Options
        ttk.Label(main_frame, text="Options:", font=("Arial", 10, "bold")).grid(row=row, column=0, sticky=tk.W)
        row += 1
        
        ttk.Checkbutton(main_frame, text="Generate Furniture", variable=self.show_furniture).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5)
        row += 1
        
        ttk.Checkbutton(main_frame, text="Show Map Overlay", variable=self.show_map, 
                       command=self.toggle_map_input).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5)
        row += 1
        
        # Map file (hidden by default)
        self.map_frame = ttk.Frame(main_frame)
        self.map_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), padx=20)
        ttk.Label(self.map_frame, text="Map File:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(self.map_frame, textvariable=self.map_file, width=25).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(self.map_frame, text="Browse", command=self.browse_map).grid(row=0, column=2)
        # Lat/Lon/Zoom inputs
        ttk.Label(self.map_frame, text="Latitude:").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Entry(self.map_frame, textvariable=self.lat, width=15).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(self.map_frame, text="Longitude:").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Entry(self.map_frame, textvariable=self.lon, width=15).grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(self.map_frame, text="Zoom:").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(self.map_frame, from_=0, to=22, textvariable=self.zoom, width=6).grid(row=3, column=1, sticky=tk.W, padx=5)
        row += 1
        self.map_frame.grid_remove()
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=row, column=0, columnspan=3, pady=5)
        row += 1
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=10)
        
        self.convert_button = ttk.Button(button_frame, text="Convert", command=self.start_conversion)
        self.convert_button.pack(side=tk.LEFT, padx=5)
        
        self.viewer_button = ttk.Button(button_frame, text="Launch Viewer", command=self.launch_viewer_server)
        self.viewer_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Exit", command=self.on_exit).pack(side=tk.LEFT, padx=5)
        
    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="Select Blueprint File",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp"),
                ("DXF files", "*.dxf"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.input_file.set(filename)
            
    def browse_output(self):
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.output_dir.set(dirname)
            
    def browse_map(self):
        filename = filedialog.askopenfilename(
            title="Select Map File",
            filetypes=[("MBTiles", "*.mbtiles"), ("All files", "*.*")]
        )
        if filename:
            self.map_file.set(filename)
            
    def toggle_map_input(self):
        if self.show_map.get():
            self.map_frame.grid()
        else:
            self.map_frame.grid_remove()
            
    def start_conversion(self):
        if not self.input_file.get():
            messagebox.showerror("Error", "Please select a blueprint file")
            return
            
        # Disable button and start progress
        self.convert_button.config(state='disabled')
        self.progress.start()
        self.status_label.config(text="Processing...", foreground="blue")
        
        # Run conversion in separate thread
        thread = threading.Thread(target=self.run_conversion)
        thread.daemon = True
        thread.start()
        
    def run_conversion(self):
        try:
            # Build arguments
            sys.argv = [
                'main.py',
                '--input', self.input_file.get(),
                '--output', self.output_dir.get(),
                '--height', str(self.height.get()),
                '--scale', str(self.scale.get()),
                '--wall-thickness', str(self.wall_thickness.get()),
                '--stair-width', str(self.stair_width.get())
            ]
            
            if not self.show_furniture.get():
                sys.argv.append('--no-furniture')
                
            if self.show_map.get() and self.map_file.get():
                sys.argv.extend(['--map', self.map_file.get()])
            # Include geolocation if provided
            if self.lat.get() and self.lon.get():
                sys.argv.extend(['--lat', self.lat.get(), '--lon', self.lon.get()])
                try:
                    z = int(self.zoom.get())
                    sys.argv.extend(['--zoom', str(z)])
                except Exception:
                    pass
                
            # Run main conversion
            result = main_module.main()
            
            # Update UI in main thread
            self.root.after(0, self.conversion_complete, result == 0)
            
        except Exception as e:
            self.root.after(0, self.conversion_error, str(e))
            
    def conversion_complete(self, success):
        self.progress.stop()
        self.convert_button.config(state='normal')
        
        if success:
            self.status_label.config(text="Conversion complete!", foreground="green")
            messagebox.showinfo("Success", f"3D model generated in:\n{self.output_dir.get()}")
        else:
            self.status_label.config(text="Conversion failed", foreground="red")
            messagebox.showerror("Error", "Conversion failed. Check console for details.")
            
    def conversion_error(self, error_msg):
        self.progress.stop()
        self.convert_button.config(state='normal')
        self.status_label.config(text="Error occurred", foreground="red")
        messagebox.showerror("Error", f"An error occurred:\n{error_msg}")
        
    def launch_viewer_server(self):
        """Launch the map server and open the viewer in a browser."""
        if self.viewer_running.get():
            messagebox.showinfo("Info", "Viewer server is already running at http://localhost:8000")
            try:
                webbrowser.open("http://localhost:8000/viewer/index.html")
            except Exception:
                pass
            return
        
        output_dir = self.output_dir.get()
        if not Path(output_dir).exists():
            messagebox.showerror("Error", f"Output directory does not exist: {output_dir}")
            return
        
        # Build map_server command
        cmd = [sys.executable, 'map_server.py', '--output', output_dir, '--port', '8000']
        if self.show_map.get() and self.map_file.get():
            cmd.extend(['--map', self.map_file.get()])
        
        try:
            # Start map_server in background
            self.viewer_process = subprocess.Popen(
                cmd,
                cwd=str(Path(__file__).parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.viewer_running.set(True)
            self.viewer_button.config(state='disabled', text='Viewer Running')
            self.status_label.config(text="Viewer server started at :8000", foreground="blue")
            
            # Wait a moment then open browser
            import time
            time.sleep(1)
            try:
                webbrowser.open("http://localhost:8000/viewer/index.html")
            except Exception:
                pass
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start viewer server:\n{e}")
            
    def on_exit(self):
        """Stop viewer server and exit."""
        if self.viewer_process and self.viewer_running.get():
            try:
                self.viewer_process.terminate()
                self.viewer_process.wait(timeout=3)
            except Exception:
                try:
                    self.viewer_process.kill()
                except Exception:
                    pass
        self.root.quit()


def launch_ui():
    """Launch the GUI application."""
    root = tk.Tk()
    app = BlueprintConverterGUI(root)
    root.mainloop()


if __name__ == '__main__':
    launch_ui()
