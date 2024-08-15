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
image_path = '/Users/patrickliu/Desktop/Startups/AIMonitoring/readthistext.png'
question = "In this image, is the user doing anything related to this: coding or writing or planning tasks? Reply with 'yes' or 'no' if they are definetely distracted. and reasoning"
question = "Describe what this user in this image is doing briefly (5 words max) from these options: reading book, learning, coding, watching youtube video, watching tiktok, browsing social media, reading manga, gaming, watching live stream, chatting online."
question = "Read the text in this image"
answer = ask_llava(question, image_path)
print(answer)