from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import zlib
import re
from datetime import datetime

app = FastAPI()

# Allow your Vercel/HTML frontend to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def smart_scan(img_array):
    """
    Scans the image using multiple high-definition strategies.
    1. Standard Scan
    2. Sharpened (for blurry dots)
    3. High Contrast (for glare)
    4. Rotated (for vertical photos)
    """
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    # Helper to run the zbar decoder
    def try_decode(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return decode(gray)

    # Strategy 1: Raw Image (Best if cropped by frontend)
    decoded = try_decode(img)
    if decoded: return decoded

    # Strategy 2: Sharpen (Unsharp Mask)
    # Good for high-res photos where dots blur together
    gaussian = cv2.GaussianBlur(img, (0, 0), 3)
    sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
    decoded = try_decode(sharpened)
    if decoded: return decoded

    # Strategy 3: High Contrast (Binary Threshold)
    # Good for removing shadows/glare
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    decoded = decode(binary)
    if decoded: return decoded

    # Strategy 4: Rotate 90 Degrees
    rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    decoded = try_decode(rotated)
    if decoded: return decoded

    return None

def calculate_exact_age(dob_string):
    """Calculates age accurately down to the specific day."""
    # Handle YYYY-MM-DD or DD-MM-YYYY
    if "-" in dob_string:
        parts = dob_string.split("-")
        if len(parts[0]) == 4: # YYYY-MM-DD
            year, month, day = map(int, parts)
        else: # DD-MM-YYYY
            day, month, year = map(int, parts)
    elif "/" in dob_string:
        day, month, year = map(int, dob_string.split("/"))
    
    birth_date = datetime(year, month, day)
    today = datetime.now()
    
    age = today.year - birth_date.year
    # Subtract 1 if birthday hasn't happened yet this year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
        
    return age

def decode_secure_qr(data_bytes):
    """
    Handles both OLD Aadhaar (XML Text) and NEW Aadhaar (Secure Number).
    """
    try:
        # 1. Try treating it as a Secure BigInt (New Cards)
        big_int = int(data_bytes.decode("utf-8"))
        byte_len = (big_int.bit_length() + 7) // 8
        binary_data = big_int.to_bytes(byte_len, byteorder='big')
        decompressed = zlib.decompress(binary_data, 16+zlib.MAX_WBITS)
        return decompressed.decode("latin-1")
    except:
        # 2. If that fails, it might be an Old Card (XML Text)
        # Just return the raw text
        return data_bytes.decode("utf-8")

@app.post("/verify")
async def verify_aadhaar(file: UploadFile = File(...)):
    print(f" Processing: {file.filename}")
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)

    # 1. SCAN
    decoded_objects = smart_scan(nparr)

    if not decoded_objects:
        return {"success": False, "message": "No QR code detected. Try cropping exactly to the QR."}

    for obj in decoded_objects:
        try:
            # 2. DECODE
            text_data = decode_secure_qr(obj.data)
            
            # 3. EXTRACT DOB
            # Regex looks for DD-MM-YYYY or YYYY-MM-DD
            match = re.search(r"([0-9]{2}-[0-9]{2}-[0-9]{4})", text_data)
            if not match:
                match = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", text_data)

            if match:
                dob = match.group(1)
                age = calculate_exact_age(dob)
                
                print(f"Verified: Age {age}")
                return {
                    "success": True, 
                    "age": age, 
                    "is_under_18": age < 18,
                    "dob": dob
                }
                
        except Exception as e:
            print(f"Error processing QR: {e}")

    return {"success": False, "message": "QR found, but could not read DOB."}
