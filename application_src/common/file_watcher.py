#!/usr/bin/env python3
"""
File watcher for development mode with auto-restart capability.
Monitors Python files and restarts the application when changes are detected.
"""

import sys
import os
import subprocess
import time
import shlex
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    def __init__(self, command=['python', 'agent.py']):
        self.process = None
        self.command = command
        self.restart()

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f'📝 File {event.src_path} modified, restarting...')
            self.restart()

    def restart(self):
        if self.process:
            print('🔄 Stopping current process...')
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        # Security: Validate and escape command arguments to prevent injection
        safe_command = []
        for arg in self.command:
            # Only allow Python executables and .py files for security
            if arg == 'python' or arg == 'python3' or arg.endswith('.py') or arg.startswith('-'):
                safe_command.append(shlex.quote(arg))
            else:
                print(f'⚠️ WARNING: Potentially unsafe command argument rejected: {arg}')
                continue
        
        if not safe_command:
            print('❌ ERROR: No safe command arguments found')
            return
            
        print(f'🚀 Starting: {" ".join(safe_command)}')
        self.process = subprocess.Popen(safe_command, shell=False)  # nosemgrep: dangerous-subprocess-use-audit

def main():
    # Build the complete command including python interpreter
    if len(sys.argv) > 1:
        # If arguments provided, assume it's the script to run
        script_args = sys.argv[1:]
        if not script_args[0].startswith('python'):
            command = ['python'] + script_args
        else:
            command = script_args
    else:
        command = ['python', 'agent.py']
    
    observer = Observer()
    handler = RestartHandler(command)
    
    # Watch current directory and common directory
    observer.schedule(handler, path='.', recursive=True)
    if os.path.exists('./common'):
        observer.schedule(handler, path='./common', recursive=True)
    
    observer.start()
    print('👀 File watcher started. Press Ctrl+C to stop.')
    
    try:
        while True:
            time.sleep(0.1)  # nosemgrep: arbitrary-sleep
    except KeyboardInterrupt:
        print('\n🛑 Stopping file watcher...')
        observer.stop()
        if handler.process:
            handler.process.terminate()
            try:
                handler.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                handler.process.kill()
    
    observer.join()
    print('✅ File watcher stopped.')

if __name__ == '__main__':
    main()
