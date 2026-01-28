import cv2
import numpy as np
import os
from django.conf import settings
from attendance.models import Student

class SimpleFaceRecognizer:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.known_face_encodings = []
        self.known_face_names = []
        
    def load_and_train(self):
        """Load student photos and train the recognizer"""
        try:
            faces = []
            labels = []
            label_ids = {}
            current_id = 0
            
            students = Student.objects.filter(is_active=True)
            
            for student in students:
                if student.photo:
                    image_path = student.photo.path
                    if os.path.exists(image_path):
                        # Read and process image
                        image = cv2.imread(image_path)
                        if image is not None:
                            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                            
                            # Detect faces
                            face_rects = self.face_cascade.detectMultiScale(
                                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                            )
                            
                            for (x, y, w, h) in face_rects:
                                face_roi = gray[y:y+h, x:x+w]
                                face_roi = cv2.resize(face_roi, (100, 100))
                                
                                faces.append(face_roi)
                                labels.append(current_id)
                                
                                label_ids[current_id] = student.student_id
                                current_id += 1
            
            if faces and labels:
                self.recognizer.train(faces, np.array(labels))
                self.label_ids = label_ids
                print(f"Model trained with {len(faces)} faces")
                return True
            else:
                print("No faces found for training")
                return False
                
        except Exception as e:
            print(f"Training error: {e}")
            return False
    
    def recognize_face(self, image_path):
        """Recognize face from image and return student ID"""
        try:
            if not hasattr(self, 'label_ids'):
                if not self.load_and_train():
                    return None
            
            image = cv2.imread(image_path)
            if image is None:
                return None
                
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            
            if len(faces) == 0:
                return None
            
            for (x, y, w, h) in faces:
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (100, 100))
                
                # Predict using LBPH
                label, confidence = self.recognizer.predict(face_roi)
                
                # Lower confidence is better in LBPH
                if confidence < 70:  # Adjust this threshold as needed
                    student_id = self.label_ids.get(label)
                    return student_id
            
            return None
            
        except Exception as e:
            print(f"Recognition error: {e}")
            return None
    
    def verify_face(self, student_id, image_path):
        """Verify if the face matches a specific student"""
        try:
            recognized_id = self.recognize_face(image_path)
            return recognized_id == student_id
        except Exception as e:
            print(f"Verification error: {e}")
            return False
    
    def detect_face(self, image_path):
        """Simply check if a face is present in the image"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return False
                
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            
            return len(faces) > 0
            
        except Exception as e:
            print(f"Face detection error: {e}")
            return False