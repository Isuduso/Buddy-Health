import sys
print("Python version:", sys.version)

try:
    from flask import Flask
    print("✓ Flask imported")
except Exception as e:
    print("✗ Flask error:", e)

try:
    from flask_sqlalchemy import SQLAlchemy
    print("✓ SQLAlchemy imported")
except Exception as e:
    print("✗ SQLAlchemy error:", e)

try:
    import spacy
    print("✓ spaCy imported")
except Exception as e:
    print("✗ spaCy error:", e)

try:
    import jwt
    print("✓ JWT imported")
except Exception as e:
    print("✗ JWT error:", e)

print("\nTrying to import app...")
try:
    from app import app
    print("✓ app imported successfully!")
    print("Starting Flask app on port 5000...")
    app.run(debug=True, port=5000)
except Exception as e:
    print("✗ Error importing app:")
    print(type(e).__name__, ":", e)
    import traceback
    traceback.print_exc()
