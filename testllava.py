import requests
import base64
from PIL import Image
import io

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def ask_llava(prompt, image_path):
    base64_image = encode_image(image_path)
    
    response = requests.post('http://localhost:11434/api/generate',
        json={
            'model': 'llava',
            'prompt': prompt,
            'images': [base64_image],
            'stream': False,
            'options': {
                'temperature': 0
            }
        })
    
    if response.status_code == 200:
        return response.json()['response']
    else:
        return f"Error: {response.status_code}, {response.text}"

# Example usage
image_path = '/Users/patrickliu/Desktop/Startups/AIMonitoring/debug_images/capture_latest.png'
question = "Is this person coding in this image, reply with 'Yes' or 'No'"

answer = ask_llava(question, image_path)
print(answer)