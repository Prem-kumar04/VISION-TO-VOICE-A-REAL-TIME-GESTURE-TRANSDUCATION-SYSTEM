import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import pickle
import numpy as np

print("1. Loading data from 'data.csv'...")
try:
    data = pd.read_csv('data.csv')
except FileNotFoundError:
    print("Error: 'data.csv' not found. Did you run collect_data.py?")
    exit()

# --- FIX: CLEAN THE DATA ---
print(f"   Original size: {len(data)} rows")
if data.isnull().values.any():
    print("   Found empty/corrupted rows. Removing them...")
    data.dropna(inplace=True)
    print(f"   Cleaned size: {len(data)} rows")

# Separate the Labels (A, B, C...) from the Coordinates
X = data.drop('label', axis=1) # The numbers
y = data['label']              # The answers

# Split data (20% for testing)
x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=True, stratify=y)

print("2. Training the Random Forest Classifier...")
model = RandomForestClassifier()
model.fit(x_train, y_train)

# Test accuracy
y_predict = model.predict(x_test)
score = accuracy_score(y_test, y_predict)

print(f"3. Success! Model Accuracy: {score * 100:.2f}%")

# Save the trained model
with open('model.p', 'wb') as f:
    pickle.dump(model, f)
    
print("4. Saved trained brain to 'model.p'. You can now run app.py!")