import os

gameplay_folder = "gameplay_videos"

print(f"Checking folder: {gameplay_folder}")
print(f"Folder exists: {os.path.exists(gameplay_folder)}")
print()

if os.path.exists(gameplay_folder):
    all_files = os.listdir(gameplay_folder)
    print(f"Total files found: {len(all_files)}")
    print()
    
    for file in all_files:
        print(f"  File: {file}")
        print(f"    Extension: {os.path.splitext(file)[1]}")
        print(f"    Is video: {file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))}")
        print()
    
    video_files = [f for f in all_files if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
    print(f"Video files found: {len(video_files)}")
    for video in video_files:
        print(f"  - {video}")
else:
    print("Folder does not exist!")
