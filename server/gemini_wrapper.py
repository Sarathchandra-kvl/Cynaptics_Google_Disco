import subprocess
import re

def call_gemini_cli(prompt):
    """
    Calls the Google Gemini CLI via npx.
    Requires user to have run `npx @google/gemini-cli login` first.
    """
    try:
        # Escape double quotes in prompt for shell safety (basic)
        safe_prompt = prompt.replace('"', '\\"')
        
        # Command structure: npx @google/gemini-cli "PROMPT"
        # We add --no-install to avoid interactive prompts if possible, though npx usually handles it
        command = f'npx @google/gemini-cli "{safe_prompt}"'
        
        print("🚀 Invoking Gemini CLI...")
        # Use shell=True for windows npx resolution
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode != 0:
            print(f"Gemini CLI Error: {result.stderr}")
            raise Exception(result.stderr)
            
        output = result.stdout
        
        # Cleanup Markdown
        output = re.sub(r'^```html', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```jsx', '', output, flags=re.MULTILINE) 
        output = re.sub(r'^```', '', output, flags=re.MULTILINE)
        
        return output.strip()

    except Exception as e:
        print(f"Gemini CLI Failed: {e}")
        return None
