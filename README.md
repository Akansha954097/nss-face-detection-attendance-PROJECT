# nss-face-detection-attendance-PROJECT


##  Project Overview

This project is developed for **NSS (National Service Scheme)** activities. It is a **Face Detection based Attendance System** where attendance is marked using face recognition technology. The system is **admin-controlled**, ensuring security and proper access management.

Only the **Admin** has full control over the system. No user can access the system unless the **Admin approves the request**.


##  Key Features

###  Admin Authentication & Control

* Only **Admin** can access the system initially
* Users must send an **access request**
* Until the **Admin accepts the request**, users cannot use the system

### Event Management (Admin Only)

* Create new events
* Edit existing events
* Delete events

### Face Detection Attendance

* Attendance is marked using **face detection/recognition**
* Ensures accurate and duplicate-free attendance

###  Manual Attendance (Admin Only)

* Only **Admin** can mark attendance manually
* Coordinators or users are **not allowed** to mark manual attendance
* Used only in special cases like camera or system issues

### Secure System

* Unauthorized users cannot access any feature
* All critical actions are restricted to Admin



## User Roles

### Admin

* Accept or reject user access requests
* Create, edit, and delete events
* Mark attendance using face detection
* Mark attendance manually
* View complete attendance records

### Coordinator

* Cannot give access to any user
* Cannot mark attendance manually
* Can only view assigned event details (if allowed by admin)

### User

* Can only access the system **after admin approval**
* Cannot create, edit, or delete events
* Cannot manually mark attendance



##  Technologies Used

* Python
* Face Recognition
* Django
* HTML, CSS, JavaScript
* Database (SQLite)



##  How It Works

1. Admin logs into the system
2. Users send access requests
3. Admin approves the request
4. Admin creates an event
5. Attendance is marked using face detection
6. Admin can also mark attendance manually
7. Attendance data is stored securely


## Project Use Case

This system is specially designed for **NSS events**, workshops, and activities where:

* Manual attendance is time-consuming
* Accuracy is important
* Admin-level control is required



##  Advantages

* Saves time
* Reduces proxy attendance
* Secure and admin-controlled
* Easy event management



##  Conclusion

The NSS Face Detection Attendance System provides a smart, secure, and efficient way to manage attendance for NSS activities with complete admin control and reliable face recognition technology.



✨ *Developed as an NSS Project*

