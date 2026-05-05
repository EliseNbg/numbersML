#!/usr/bin/env python3
"""
Rename Algorithm/Algorithms to Algorithm/Algorithms in the entire codebase.
Handles case-sensitive renaming of:
- Algorithm -> Algorithm
- algorithms -> algorithms  
- algorithm -> algorithm
- ALGORITHM -> ALGORITHM (where applicable)
"""

import os
import re
from pathlib import Path

# Define the rename mappings (order matters - do longer matches first)
RENAME_MAP = [
    # Plural forms first to avoid partial replacements
    ('Algorithms', 'Algorithms'),
    ('algorithms', 'algorithms'),
    ('ALGORITHMS', 'ALGORITHMS'),
    # Singular forms
    ('Algorithm', 'Algorithm'),
    ('algorithm', 'algorithm'),
    ('ALGORITHM', 'ALGORITHM'),
]

# File extensions to process
EXTENSIONS = {'.py', '.js', '.html', '.sql', '.md', '.json', '.yml', '.yaml', '.cfg', '.ini', '.txt'}

# Directories to skip
SKIP_DIRS = {'__pycache__', '.git', '.venv', 'node_modules', 'dist', 'build', '.pytest_cache'}

def should_process_file(filepath):
    """Check if file should be processed."""
    path = Path(filepath)
    # Check extension
    if path.suffix not in EXTENSIONS:
        return False
    # Check if in skip directory
    for part in path.parts:
        if part in SKIP_DIRS:
            return False
    return True

def rename_in_file(filepath):
    """Rename all occurrences in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError):
        return False
    
    original_content = content
    for old, new in RENAME_MAP:
        content = content.replace(old, new)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    base_dir = Path('/home/andy/projects/numbers/numbersML')
    renamed_files = []
    processed_count = 0
    
    for root, dirs, files in os.walk(base_dir):
        # Skip directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for file in files:
            filepath = os.path.join(root, file)
            if should_process_file(filepath):
                processed_count += 1
                if rename_in_file(filepath):
                    renamed_files.append(filepath)
    
    print(f"Processed {processed_count} files")
    print(f"Renamed in {len(renamed_files)} files")
    return renamed_files

if __name__ == '__main__':
    renamed = main()
    for f in renamed[:20]:  # Show first 20
        print(f"  {f}")
    if len(renamed) > 20:
        print(f"  ... and {len(renamed) - 20} more")
