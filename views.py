from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
import os
import json
from datetime import datetime
import cv2
import numpy as np

from .models import Student, Event, Attendance, Notification
from .forms import UserRegisterForm, StudentForm, EventForm
from .face_recognition.face_utils import SimpleFaceRecognizer

# Helper functions
def is_admin(user):
    return hasattr(user, 'student') and user.student.role == 'admin'

def notify(user, title, body, url='', approve_url='', reject_url=''):
    try:
        Notification.objects.create(
            user=user, title=title, body=body, url=url,
            approve_url=approve_url, reject_url=reject_url
        )
    except Exception:
        pass

def is_coordinator(user):
    return hasattr(user, 'student') and user.student.role in ['admin', 'coordinator']

def is_student(user):
    return hasattr(user, 'student')

# Authentication Views
def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Block login until admin approval
            user.save()

            # Student was created by signal; update its fields
            student = Student.objects.get(user=user)
            student.student_id = form.cleaned_data['student_id']
            student.name = form.cleaned_data['name']
            student.phone = form.cleaned_data['phone']
            student.role = form.cleaned_data['role']
            student.photo = form.cleaned_data['photo']
            student.approval_status = 'pending'
            student.email = form.cleaned_data['email']
            student.save()

            # Notify admins about new registration (optional)
            try:
                admin_students = Student.objects.filter(role='admin')
                admin_emails = [a.email for a in admin_students]
                for a in admin_students:
                    notify(
                        a.user,
                        'User approval required',
                        f"{student.name} ({student.student_id}) registered.",
                        url='students/',
                        approve_url=f'students/approve/{student.student_id}/',
                        reject_url=f'students/reject/{student.student_id}/'
                    )
                if admin_emails:
                    send_mail(
                        'New user awaiting approval',
                        f"New user registered: {student.name} ({student.student_id}). Please review and approve.",
                        settings.DEFAULT_FROM_EMAIL,
                        admin_emails,
                        fail_silently=False,
                    )
            except Exception as e:
                print(f"Admin notify email failed: {e}")

            messages.success(request, 'Account created! Wait until admin approves your account.')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'registration/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # If account exists but not approved yet, show proper message
        try:
            pending_user = User.objects.get(username=username)
            if not pending_user.is_active:
                messages.warning(request, 'Your account is pending admin approval. Please wait.')
                return render(request, 'registration/login.html')
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Send login notification email
            try:
                student = Student.objects.get(user=user)
                send_mail(
                    'Login Notification - NSS System',
                    f"""Hello {student.name},

You have successfully logged into NSS Face Attendance System at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}.

If this was not you, please contact admin immediately.

Best regards,
NSS Team""",
                    settings.DEFAULT_FROM_EMAIL,
                    [student.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Login email failed: {e}")
            
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'registration/login.html')

def logout_view(request):
    user = request.user
    logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('login')

# Dashboard Views
@login_required
def dashboard(request):
    student = get_object_or_404(Student, user=request.user)
    
    context = {
        'student': student,
        'total_students': Student.objects.filter(is_active=True).count(),
        'total_events': Event.objects.count(),
        'pending_events': Event.objects.filter(status='pending').count(),
    }
    
    if student.role == 'admin':
        context.update({
            'recent_events': Event.objects.all().order_by('-created_at')[:5],
            'pending_events_list': Event.objects.filter(status='pending').order_by('-created_at'),
            'approved_events': Event.objects.filter(status='approved').count(),
            'total_attendance': Attendance.objects.count(),
            'coordinators_count': Student.objects.filter(role='coordinator', is_active=True).count(),
            'recent_attendance': Attendance.objects.select_related('student','event').order_by('-attendance_time')[:10],
            'pending_students': Student.objects.filter(approval_status='pending').order_by('-created_at'),
        })
        return render(request, 'admin_dashboard.html', context)
    elif student.role == 'coordinator':
        # Show all approved events (including those created by admin), newest first
        context['my_events'] = Event.objects.filter(status='approved').order_by('-date', '-time', '-created_at')
        return render(request, 'coordinator_dashboard.html', context)
    else:
        # Student dashboard - only view attendance
        context['my_attendance'] = Attendance.objects.filter(student=student).order_by('-attendance_time')[:10]
        context['upcoming_events'] = Event.objects.filter(status='approved', date__gte=datetime.today().date())
        return render(request, 'student_dashboard.html', context)

# Student Management (Admin Only)
@login_required
@user_passes_test(is_admin)
def student_list(request):
    students = Student.objects.all().order_by('-created_at')
    return render(request, 'student_list.html', {'students': students})

@login_required
@user_passes_test(is_admin)
def approve_student(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    student.approval_status = 'approved'
    student.user.is_active = True
    student.user.save(update_fields=['is_active'])
    student.save(update_fields=['approval_status'])
    notify(student.user, 'Account approved', 'Your account has been approved. You can now log in.', url='login')
    # AJAX request: return JSON
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'student_id': student_id})
    messages.success(request, f"Approved {student.name}")
    return redirect('student_list')

@login_required
@user_passes_test(is_admin)
def reject_student(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    student.approval_status = 'rejected'
    student.user.is_active = False
    student.user.save(update_fields=['is_active'])
    student.save(update_fields=['approval_status'])
    notify(student.user, 'Account rejected', 'Your account request has been rejected. Contact admin for details.')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'student_id': student_id})
    messages.info(request, f"Rejected {student.name}")
    return redirect('student_list')

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from .forms import StudentForm
from .models import Student


# Helper function to check if the current user is an admin
def is_admin(user):
    return user.is_superuser or (hasattr(user, 'student') and user.student.role == 'admin')


@login_required
@user_passes_test(is_admin)
def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('student_list')  # URL name ke hisaab se change karo
    else:
        form = StudentForm()
    return render(request, 'add_student.html', {'form': form})
@login_required
@user_passes_test(is_admin)
def edit_student(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            if student.user.email != form.cleaned_data['email']:
                student.user.email = form.cleaned_data['email']
                student.user.save()
            
            messages.success(request, f'Student {student.name} updated successfully!')
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'edit_student.html', {'form': form, 'student': student})

@login_required
@user_passes_test(is_admin)
def delete_student(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    if request.method == 'POST':
        student_name = student.name
        user = student.user
        
        # Send deletion notification email
        try:
            send_mail(
                'Account Deleted - NSS System',
                f"""Hello {student.name},

Your NSS account has been deleted from the system.

If this was a mistake, please contact admin.

Best regards,
NSS Team""",
                settings.DEFAULT_FROM_EMAIL,
                [student.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Deletion email failed: {e}")
        
        student.delete()
        user.delete()
        
        messages.success(request, f'Student {student_name} deleted successfully!')
        return redirect('student_list')
    return render(request, 'delete_student.html', {'student': student})

# Event Management
@login_required
@user_passes_test(is_coordinator)
def event_list(request):
    student = get_object_or_404(Student, user=request.user)
    
    if student.role == 'admin':
        events = Event.objects.all().order_by('-created_at')
    else:
        events = Event.objects.filter(coordinator=student).order_by('-created_at')
    
    # Statistics calculate kare
    total_events = events.count()
    approved_events = events.filter(status='approved').count()
    pending_events = events.filter(status='pending').count()
    rejected_events = events.filter(status='rejected').count()
    
    context = {
        'events': events,
        'total_events': total_events,
        'approved_events': approved_events,
        'pending_events': pending_events,
        'rejected_events': rejected_events,
    }
    
    return render(request, 'event_list.html', context)

@login_required
@user_passes_test(is_coordinator)
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.coordinator = get_object_or_404(Student, user=request.user)
            event.save()
            
            # Notify admin about new event
            try:
                admins = Student.objects.filter(role='admin')
                admin_emails = [admin.email for admin in admins]
                for a in admins:
                    notify(
                        a.user,
                        'Event approval required',
                        f"{event.title} by {event.coordinator.name}",
                        url='events/',
                        approve_url=f'events/approve/{event.id}/',
                        reject_url=f'events/reject/{event.id}/'
                    )
                send_mail(
                    'New Event Created - Approval Required',
                    f"""Hello Admin,

A new event has been created and requires your approval.

Event: {event.title}
Date: {event.date}
Time: {event.time}
Venue: {event.venue}
Coordinator: {event.coordinator.name}

Please review and approve/reject the event.

Thank you!""",
                    settings.DEFAULT_FROM_EMAIL,
                    admin_emails,
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Event notification email failed: {e}")
            
            messages.success(request, 'Event created successfully! Waiting for admin approval.')
            return redirect('event_list')
    else:
        form = EventForm()
    return render(request, 'add_event.html', {'form': form})

@login_required
@user_passes_test(is_coordinator)
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    student = get_object_or_404(Student, user=request.user)
    if student.role != 'admin' and event.coordinator != student:
        messages.error(request, 'You can only edit your own events!')
        return redirect('event_list')
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully!')
            return redirect('event_list')
    else:
        form = EventForm(instance=event)
    return render(request, 'edit_event.html', {'form': form, 'event': event})

@login_required
@user_passes_test(is_coordinator)
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    student = get_object_or_404(Student, user=request.user)
    if student.role != 'admin' and event.coordinator != student:
        messages.error(request, 'You can only delete your own events!')
        return redirect('event_list')
    if request.method == 'POST':
        event_title = event.title
        coordinator_email = event.coordinator.email
        
        # Send deletion notification
        try:
            send_mail(
                'Event Deleted',
                f"""Hello,

The event "{event_title}" has been deleted from the system.

If this was a mistake, please contact admin.

Best regards,
NSS Team""",
                settings.DEFAULT_FROM_EMAIL,
                [coordinator_email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Event deletion email failed: {e}")
        
        event.delete()
        messages.success(request, 'Event deleted successfully!')
        return redirect('event_list')
    return render(request, 'delete_event.html', {'event': event})

@login_required
@user_passes_test(is_admin)
def approve_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    event.status = 'approved'
    event.save(update_fields=['status'])
    notify(event.coordinator.user, 'Event approved', f'Your event "{event.title}" has been approved.', url='events/')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'event_id': event_id})
    
    # Send approval email to coordinator (disabled backend can ignore)
    try:
        send_mail(
            'Event Approved - NSS System',
            f"""Hello {event.coordinator.name},

Your event "{event.title}" has been approved by admin.

Event Details:
- Date: {event.date}
- Time: {event.time}
- Venue: {event.venue}

You can now use this event for attendance marking.

Thank you!""",
            settings.DEFAULT_FROM_EMAIL,
            [event.coordinator.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Approval email failed: {e}")
    
    messages.success(request, 'Event approved successfully!')
    return redirect('event_list')

@login_required
@user_passes_test(is_admin)
def reject_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    event.status = 'rejected'
    event.save(update_fields=['status'])
    notify(event.coordinator.user, 'Event rejected', f'Your event "{event.title}" has been rejected.', url='events/')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'event_id': event_id})
    
    # Send rejection email to coordinator
    try:
        send_mail(
            'Event Rejected - NSS System',
            f"""Hello {event.coordinator.name},

Your event "{event.title}" has been rejected by admin.

Please contact admin for more details.

Best regards,
NSS Team""",
            settings.DEFAULT_FROM_EMAIL,
            [event.coordinator.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Rejection email failed: {e}")
    
    messages.success(request, 'Event rejected!')
    return redirect('event_list')

# ATTENDANCE SYSTEM
@login_required
@user_passes_test(is_coordinator)
def group_attendance(request, event_id=None):
    """Coordinator group photo se attendance mark karega"""
    event = None
    if event_id:
        event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'POST' and 'group_photo' in request.FILES:
        group_photo = request.FILES['group_photo']
        event_id = request.POST.get('event_id')
        
        if not event_id:
            messages.error(request, 'Please select an event!')
            return redirect('group_attendance')
        
        event = get_object_or_404(Event, id=event_id)
        coordinator = get_object_or_404(Student, user=request.user)
        
        # Save group photo temporarily
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"group_{group_photo.name}")
        
        with open(temp_path, 'wb+') as destination:
            for chunk in group_photo.chunks():
                destination.write(chunk)
        
        # Initialize face recognizer
        recognizer = SimpleFaceRecognizer()
        
        # Recognize multiple faces from group photo
        recognized_students = []
        try:
            image = cv2.imread(temp_path)
            if image is None:
                messages.error(request, 'Invalid image file!')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return redirect('group_attendance')
                
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            
            if len(faces) == 0:
                messages.error(request, 'No faces detected in the group photo!')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return redirect('group_attendance')
            
            # Train model if not trained
            if not hasattr(recognizer, 'label_ids'):
                recognizer.load_and_train()
            
            # Recognize each face
            for (x, y, w, h) in faces:
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (100, 100))
                
                if hasattr(recognizer, 'recognizer'):
                    label, confidence = recognizer.recognizer.predict(face_roi)
                    
                    if confidence < 70 and hasattr(recognizer, 'label_ids'):
                        student_id = recognizer.label_ids.get(label)
                        if student_id:
                            try:
                                student = Student.objects.get(student_id=student_id, is_active=True)
                                recognized_students.append(student)
                            except Student.DoesNotExist:
                                continue
            
            # Mark attendance for recognized students
            attendance_count = 0
            for student in recognized_students:
                attendance, created = Attendance.objects.get_or_create(
                    student=student,
                    event=event,
                    defaults={
                        'marked_by': coordinator,
                        'is_manual': False
                    }
                )
                if created:
                    attendance_count += 1
                    
                    # Send attendance email to student
                    try:
                        send_mail(
                            'Attendance Marked - NSS Event',
                            f"""Hello {student.name},

Your attendance has been marked for:
Event: {event.title}
Date: {event.date}
Time: {datetime.now().strftime("%H:%M:%S")}
Marked by: {coordinator.name} (Coordinator)

Thank you for your participation!""",
                            settings.DEFAULT_FROM_EMAIL,
                            [student.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        print(f"Attendance email failed: {e}")
            
            # Send summary to coordinator
            try:
                send_mail(
                    'Group Attendance Summary',
                    f"""Hello {coordinator.name},

Group attendance completed for event: {event.title}

Total faces detected: {len(faces)}
Students recognized: {len(recognized_students)}
Attendance marked: {attendance_count}

Thank you!""",
                    settings.DEFAULT_FROM_EMAIL,
                    [coordinator.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Summary email failed: {e}")
            
            messages.success(request, f'Group attendance completed! {attendance_count} students marked present.')
            
        except Exception as e:
            messages.error(request, f'Error in group attendance: {str(e)}')
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return redirect('attendance_records')
    
    # GET request - show form
    if request.user.student.role == 'admin':
        events = Event.objects.filter(status='approved')
    else:
        events = Event.objects.filter(coordinator=request.user.student, status='approved')
    
    return render(request, 'group_attendance.html', {
        'events': events, 
        'selected_event': event
    })

@login_required
@user_passes_test(is_admin)
def manual_attendance(request, event_id=None):
    """Admin manually attendance mark karega (for unrecognized faces)"""
    event = None
    if event_id:
        event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'POST':
        event_id = request.POST.get('event_id')
        student_ids = request.POST.getlist('students')
        
        if not event_id or not student_ids:
            messages.error(request, 'Please select event and at least one student!')
            return redirect('manual_attendance')
        
        event = get_object_or_404(Event, id=event_id)
        admin = get_object_or_404(Student, user=request.user)
        
        attendance_count = 0
        for student_id in student_ids:
            try:
                student = Student.objects.get(id=student_id, is_active=True)
                attendance, created = Attendance.objects.get_or_create(
                    student=student,
                    event=event,
                    defaults={
                        'marked_by': admin,
                        'is_manual': True,
                        'notes': 'Manually marked by admin'
                    }
                )
                if created:
                    attendance_count += 1
                    
                    # Send manual attendance email
                    try:
                        send_mail(
                            'Attendance Manually Marked - NSS Event',
                            f"""Hello {student.name},

Your attendance has been manually marked by admin for:
Event: {event.title}
Date: {event.date}
Time: {datetime.now().strftime("%H:%M:%S")}
Marked by: {admin.name}

Reason: Face not recognized in group photo

Thank you for your participation!""",
                            settings.DEFAULT_FROM_EMAIL,
                            [student.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        print(f"Manual attendance email failed: {e}")
                        
            except Student.DoesNotExist:
                continue
        
        messages.success(request, f'Manual attendance completed! {attendance_count} students marked present.')
        return redirect('attendance_records')
    
    # GET request - show form
    events = Event.objects.filter(status='approved')
    students = Student.objects.filter(is_active=True, role='student')
    
    return render(request, 'manual_attendance.html', {
        'events': events, 
        'selected_event': event,
        'students': students
    })

@login_required
def attendance_records(request):
    """Attendance records dekhega"""
    student = get_object_or_404(Student, user=request.user)
    
    if student.role == 'admin':
        records = Attendance.objects.all().order_by('-attendance_time')
    elif student.role == 'coordinator':
        my_events = Event.objects.filter(coordinator=student)
        records = Attendance.objects.filter(event__in=my_events).order_by('-attendance_time')
    else:
        records = Attendance.objects.filter(student=student).order_by('-attendance_time')
    
    # Calculate statistics
    face_recognition_count = records.filter(is_manual=False).count()
    manual_count = records.filter(is_manual=True).count()
    unique_students_count = records.values('student').distinct().count()
    
    context = {
        'records': records,
        'face_recognition_count': face_recognition_count,
        'manual_count': manual_count,
        'unique_students': unique_students_count,
    }
    
    return render(request, 'attendance_records.html', context)

# Notifications API
@login_required
def notifications_feed(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
    data = [{
        'id': n.id,
        'title': n.title,
        'body': n.body,
        'url': n.url,
        'is_read': n.is_read,
'time': n.created_at.strftime('%Y-%m-%d %H:%M'),
        'approve_url': n.approve_url,
        'reject_url': n.reject_url,
    } for n in notifs]
    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'items': data, 'unread': unread})

@login_required
def notifications_mark_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})

# AJAX view for face verification
@login_required
def verify_face_photo(request):
    if request.method == 'POST' and request.FILES.get('photo'):
        photo = request.FILES['photo']
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"verify_{photo.name}")
        
        with open(temp_path, 'wb+') as destination:
            for chunk in photo.chunks():
                destination.write(chunk)
        
        recognizer = SimpleFaceRecognizer()
        face_detected = recognizer.detect_face(temp_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return JsonResponse({'face_detected': face_detected})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def take_attendance(request):
    """Take attendance page - redirect to group attendance"""
    return redirect('group_attendance')
@login_required
@user_passes_test(is_admin)
def manual_attendance(request, event_id=None):
    """Admin manually attendance mark karega (for unrecognized faces)"""
    event = None
    if event_id:
        event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'POST':
        event_id = request.POST.get('event_id')
        student_ids = request.POST.getlist('students')
        admin_notes = request.POST.get('admin_notes', '')
        
        if not event_id or not student_ids:
            messages.error(request, 'Please select event and at least one student!')
            return redirect('manual_attendance')
        
        event = get_object_or_404(Event, id=event_id)
        admin = get_object_or_404(Student, user=request.user)
        
        attendance_count = 0
        for student_id in student_ids:
            try:
                student = Student.objects.get(id=student_id, is_active=True)
                attendance, created = Attendance.objects.get_or_create(
                    student=student,
                    event=event,
                    defaults={
                        'marked_by': admin,
                        'is_manual': True,
                        'notes': f'Manually marked by admin. {admin_notes}'
                    }
                )
                if created:
                    attendance_count += 1
                    
                    # Send manual attendance email
                    try:
                        send_mail(
                            'Attendance Manually Marked - NSS Event',
                            f"""Hello {student.name},

Your attendance has been manually marked by admin for:
Event: {event.title}
Date: {event.date}
Time: {datetime.now().strftime("%H:%M:%S")}
Marked by: {admin.name}

Reason: {admin_notes or 'Face not recognized in group photo'}

Thank you for your participation!""",
                            settings.DEFAULT_FROM_EMAIL,
                            [student.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        print(f"Manual attendance email failed: {e}")
                        
            except Student.DoesNotExist:
                continue
        
        messages.success(request, f'Manual attendance completed! {attendance_count} students marked present.')
        return redirect('attendance_records')
    
    # GET request - show form
    events = Event.objects.filter(status='approved')
    students = Student.objects.filter(is_active=True, role='student')
    
    # Statistics for template
    total_students = Student.objects.filter(is_active=True).count()
    active_students = Student.objects.filter(is_active=True, role='student').count()
    approved_events = Event.objects.filter(status='approved').count()
    today_events = Event.objects.filter(date=datetime.today().date(), status='approved').count()
    total_attendance = Attendance.objects.count()
    
    context = {
        'events': events, 
        'selected_event': event,
        'students': students,
        'total_students': total_students,
        'active_students': active_students,
        'approved_events': approved_events,
        'today_events': today_events,
        'total_attendance': total_attendance,
    }
    return render(request, 'manual_attendance.html', context)
