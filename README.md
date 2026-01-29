# Aadhaar backend
A simple FastAPI backend that verifies age using the QR code on an Aadhaar card.
Built to help teenonly platforms filter out adults without storing personal data.
Upload a QR image, get age + under-18 status.
Nothing is saved, everything runs in memory.

# What it does
	Scans Aadhaar QR from images
	Works with old and new QR formats
	Handles blurry or rotated photos
	Extracts DOB and calculates exact age
	Returns under-18 or adult
	No database, no storage


# Why

Because age verification should not mean data collection.


# Tech

FastAPI, OpenCV, Pyzbar, NumPy, Zlib, Python


# Example

{ "success": true, "age": 14, "is_under_18": true }
