"""
AUTO-REFRESH HEADER TEST
Automatically regenerates preview when you save header.py
Perfect for iterative design work!
"""

import os
import time
from quick_header_test import quick_header_test

def watch_and_test(test_title=None, check_interval=2):
    """
    Watch header.py for changes and auto-regenerate preview
    
    Args:
        test_title: Title to test (None = use default)
        check_interval: How often to check for changes (seconds)
    """
    
    print("=" * 60)
    print("👀 WATCHING HEADER.PY FOR CHANGES")
    print("=" * 60)
    print("\n📝 How to use:")
    print("   1. Edit header.py")
    print("   2. Save the file")
    print("   3. This script will auto-regenerate the preview!")
    print("   4. Open QUICK_HEADER_TEST.png to see changes")
    print("\n⏸️  Press Ctrl+C to stop\n")
    print("=" * 60)
    
    header_file = "header.py"
    
    if not os.path.exists(header_file):
        print(f"❌ Error: {header_file} not found!")
        print("   Make sure this script is in the same folder as header.py")
        return
    
    # Generate initial preview
    print("\n🎨 Generating initial preview...")
    quick_header_test(test_title)
    
    # Track last modification time
    last_modified = os.path.getmtime(header_file)
    
    try:
        while True:
            time.sleep(check_interval)
            
            # Check if file was modified
            current_modified = os.path.getmtime(header_file)
            
            if current_modified != last_modified:
                print(f"\n🔄 Changes detected! Regenerating preview...")
                print(f"   Time: {time.strftime('%H:%M:%S')}")
                
                try:
                    # Reload the header module
                    import importlib
                    import header
                    importlib.reload(header)
                    
                    # Regenerate preview
                    quick_header_test(test_title)
                    print("✅ Preview updated!\n")
                    
                except Exception as e:
                    print(f"❌ Error generating preview: {e}\n")
                
                last_modified = current_modified
                
    except KeyboardInterrupt:
        print("\n\n👋 Stopped watching. Goodbye!")


if __name__ == "__main__":
    # ========================================
    # 🎯 EDIT THIS TO TEST DIFFERENT TITLES
    # ========================================
    
    # Default title (change this to test different text)
    test_title = "AITA she doesn't want to pay rent"
    
    # Start watching for changes
    watch_and_test(test_title, check_interval=2)
