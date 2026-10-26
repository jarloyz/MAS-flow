#!/usr/bin/env python3
import sys
import json
import os

def print_usage():
    print("Usage:")
    print("  python3 files_to_inject.py <file_path1> <file_path2> ...")
    print("  python3 files_to_inject.py --json '<json_string_with_files_to_inject_array>'")
    sys.exit(1)

def inject_files(file_paths):
    output = []
    output.append("=== INJECTED SOURCE CODE CONTEXT ===")
    
    if not file_paths:
        output.append("No files to inject.")
        return "\n".join(output)

    for path in file_paths:
        output.append(f"\n--- FILE: {path} ---")
        try:
            # We assume paths are absolute or relative to the workspace root
            if not os.path.exists(path):
                output.append(f"[ERROR: File not found at {path}]")
                continue
                
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                output.append("```")
                output.append(content)
                output.append("```")
        except Exception as e:
            output.append(f"[ERROR: Could not read file {path} - {str(e)}]")
            
    output.append("\n=== END OF INJECTED CONTEXT ===")
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()

    paths = []
    
    if sys.argv[1] == "--json":
        if len(sys.argv) < 3:
            print_usage()
        try:
            data = json.loads(sys.argv[2])
            # Intenta extraer la llave files_to_inject o archivos_relevantes
            if isinstance(data, dict):
                if "files_to_inject" in data:
                    paths = data["files_to_inject"]
                elif "data" in data and "files_to_inject" in data["data"]:
                    paths = data["data"]["files_to_inject"]
                else:
                    print("[ERROR] No 'files_to_inject' key found in the provided JSON.")
                    sys.exit(1)
            elif isinstance(data, list):
                paths = data
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON string provided.")
            sys.exit(1)
    else:
        paths = sys.argv[1:]

    # Imprimir el resultado para que el script maestro lo capture (pipe o subshell)
    print(inject_files(paths))
